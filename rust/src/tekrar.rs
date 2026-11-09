//! Anlık tekrar: son 15 saniye (ayarlardan 5 dakikaya kadar) bellekte durur, Ctrl+Shift+B ile MP4 olur.
//! Python core/anlik_tekrar.py'nin karşılığı.
//!
//!   görüntü: kareler -> FFmpeg (stdin) -> MPEG-TS (stdout). TS anahtar karelerden (1 sn'de bir)
//!            parçalara bölünür, parçalar RAM'de tutulur; süreyi aşan en eski parça atılır.
//!   ses    : mikserin 10 ms'lik blokları RAM'de 16 bit PCM olarak tutulur.
//!   kaydet : parçalar + ses geçici dosyaya yazılır, FFmpeg tek MP4'te birleştirir (yeniden kodlamaz).
//! Kapalıyken FFmpeg çalışmaz ve hiç bellek kullanılmaz. Hiçbir ağ bağlantısı açılmaz.

use std::collections::VecDeque;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{sync_channel, SyncSender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime};

use crate::ffmpeg::{self, SES_HIZI, SES_KANALI};
use crate::kare::KareRef;

pub const VARSAYILAN_SURE: u32 = 15;
pub const EN_KISA: u32 = 15;
pub const EN_UZUN: u32 = 300;
const TS: usize = 188;

pub fn sureyi_sinirla(sn: i64) -> u32 {
    sn.clamp(EN_KISA as i64, EN_UZUN as i64) as u32
}

/// 120 -> "Son 2 dk", 90 -> "Son 90 sn"
pub fn sure_etiketi(sn: i64) -> String {
    let sn = sureyi_sinirla(sn);
    if sn % 60 == 0 {
        format!("Son {} dk", sn / 60)
    } else {
        format!("Son {sn} sn")
    }
}

pub fn bos_hedef(klasor: &Path, ad: &str) -> PathBuf {
    let yol = Path::new(ad);
    let govde = yol.file_stem().unwrap_or_default().to_string_lossy().into_owned();
    let uzanti = yol.extension().map(|e| format!(".{}", e.to_string_lossy())).unwrap_or_default();
    let mut hedef = klasor.join(ad);
    let mut sira = 2;
    while hedef.exists() {
        hedef = klasor.join(format!("{govde}~{sira}{uzanti}"));
        sira += 1;
    }
    hedef
}

/// Kaydederken uygulama kapanırsa kalan gizli geçici dosyaları (.Tekrar_*.ts / .pcm) siler.
pub fn artik_dosyalari_sil(klasor: &Path, en_az_yas_sn: f64) -> usize {
    let Ok(o) = std::fs::read_dir(klasor) else { return 0 };
    let mut silinen = 0;
    for g in o.flatten() {
        let ad = g.file_name().to_string_lossy().into_owned();
        if !ad.starts_with(".Tekrar_") || !(ad.ends_with(".ts") || ad.ends_with(".pcm")) {
            continue;
        }
        let yas = g
            .metadata()
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| SystemTime::now().duration_since(t).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);
        if yas >= en_az_yas_sn && std::fs::remove_file(g.path()).is_ok() {
            silinen += 1;
        }
    }
    silinen
}

/// PES başlığındaki PTS (90 kHz).
fn pts(paket: &[u8], bas: usize) -> Option<u64> {
    let pes = paket.get(bas..)?;
    if pes.len() < 14 || pes[0..3] != [0, 0, 1] || pes[7] & 0x80 == 0 {
        return None;
    }
    let p = &pes[9..14];
    Some(
        ((((p[0] >> 1) & 0x07) as u64) << 30)
            | ((p[1] as u64) << 22)
            | (((p[2] >> 1) as u64) << 15)
            | ((p[3] as u64) << 7)
            | ((p[4] >> 1) as u64),
    )
}

/// MPEG-TS akışını anahtar karede başlayan parçalara böler. PAT/PMT (akışın başlığı) ayrıca saklanır.
pub struct TsParcalayici {
    pub baslik: Vec<u8>,
    pmt_pid: Option<u16>,
    video_pid: Option<u16>,
    artik: Vec<u8>,
    parca: Option<Vec<u8>>,
    parca_pts: Option<u64>,
}

impl Default for TsParcalayici {
    fn default() -> Self {
        Self::new()
    }
}

impl TsParcalayici {
    pub fn new() -> Self {
        TsParcalayici { baslik: vec![], pmt_pid: None, video_pid: None, artik: vec![], parca: None, parca_pts: None }
    }

    /// Veriyi besler; biten her parça için (başlangıç pts'i, bayt) döndürür.
    pub fn besle(&mut self, veri: &[u8]) -> Vec<(Option<u64>, Vec<u8>)> {
        let mut biten = vec![];
        self.artik.extend_from_slice(veri);
        let n = self.artik.len() - self.artik.len() % TS;
        let tum = std::mem::take(&mut self.artik);
        for p in tum[..n].chunks_exact(TS) {
            if let Some(b) = self.paket(p) {
                biten.push(b);
            }
        }
        self.artik = tum[n..].to_vec();
        biten
    }

    fn paket(&mut self, p: &[u8]) -> Option<(Option<u64>, Vec<u8>)> {
        if p[0] != 0x47 {
            return None;
        }
        let pid = (((p[1] & 0x1F) as u16) << 8) | p[2] as u16;
        let pusi = p[1] & 0x40 != 0;
        let af = (p[3] >> 4) & 0x3;
        let mut bas = 4;
        let mut rai = false;
        if af == 2 || af == 3 {
            let uzunluk = p[4] as usize;
            if uzunluk > 0 {
                rai = p[5] & 0x40 != 0;
            }
            bas = 5 + uzunluk;
        }
        if pid == 0 {
            if self.pmt_pid.is_none() && pusi && p.len() > bas + 13 {
                let tablo = &p[bas + 1 + p[bas] as usize..];
                self.pmt_pid = Some((((tablo[10] & 0x1F) as u16) << 8) | tablo[11] as u16);
                self.baslik.extend_from_slice(p);
            }
            return None;
        }
        if Some(pid) == self.pmt_pid {
            if self.baslik.len() == TS {
                self.baslik.extend_from_slice(p);
            }
            return None;
        }
        if self.video_pid.is_none() && pusi && p.get(bas..bas + 4) == Some(&[0, 0, 1, 0xe0]) {
            self.video_pid = Some(pid);
        }
        if Some(pid) != self.video_pid {
            return None;
        }
        let mut biten = None;
        if pusi && rai {
            let yeni_pts = pts(p, bas);
            if let (Some(parca), true) = (self.parca.take(), self.parca_pts.is_some()) {
                biten = Some((self.parca_pts, parca));
            }
            self.parca = Some(vec![]);
            self.parca_pts = yeni_pts;
        }
        if let Some(parca) = self.parca.as_mut() {
            parca.extend_from_slice(p);
        }
        biten
    }
}

#[derive(Default)]
struct Bellek {
    parcalar: VecDeque<(Instant, Arc<Vec<u8>>)>,
    sesler: VecDeque<(Instant, Vec<u8>)>,
    kare_zamanlari: VecDeque<(u64, Instant)>,
    yazilan: u64,
    ilk_pts: Option<u64>,
    baslik: Vec<u8>,
}

struct Ortak {
    acik: AtomicBool,
    kaydediliyor: AtomicBool,
    sure_sn: Mutex<u32>,
    bellek: Mutex<Bellek>,
    son_hata: Mutex<String>,
    fps: u32,
}

impl Ortak {
    fn kirp(&self, simdi: Instant) {
        let sure = Duration::from_secs(*self.sure_sn.lock().unwrap() as u64);
        let mut b = self.bellek.lock().unwrap();
        let Some(esik) = simdi.checked_sub(sure) else { return };
        // ikinci parça da eşikten eskiyse ilk parça gereksiz
        while b.parcalar.len() > 1 && b.parcalar[1].0 <= esik {
            b.parcalar.pop_front();
        }
    }

    /// Parçanın ilk karesinin hatta yazıldığı an (ses bununla hizalanır).
    fn kare_zamani(&self, p: Option<u64>) -> Instant {
        let mut b = self.bellek.lock().unwrap();
        let (Some(p), false) = (p, b.kare_zamanlari.is_empty()) else { return Instant::now() };
        let ilk = *b.ilk_pts.get_or_insert(p);
        let indeks = ((p.saturating_sub(ilk)) as f64 * self.fps as f64 / 90000.0).round() as u64;
        b.kare_zamanlari.iter().find(|(i, _)| *i >= indeks).map(|(_, t)| *t).unwrap_or(b.kare_zamanlari.back().unwrap().1)
    }
}

pub type BittiFn = Box<dyn FnOnce(Option<PathBuf>, String) + Send>;

pub struct AnlikTekrar {
    pub genislik: u32,
    pub yukseklik: u32,
    kodlayici_tercihi: Mutex<String>,
    pub ffmpeg: Option<PathBuf>,
    ortak: Arc<Ortak>,
    surec: Mutex<Option<(Child, SyncSender<Option<KareRef>>)>>,
}

impl AnlikTekrar {
    pub fn yeni(genislik: u32, yukseklik: u32, fps: u32, sure_sn: i64, kodlayici: &str, ffmpeg: Option<PathBuf>) -> Self {
        AnlikTekrar {
            genislik,
            yukseklik,
            kodlayici_tercihi: Mutex::new(kodlayici.into()),
            ffmpeg,
            ortak: Arc::new(Ortak {
                acik: AtomicBool::new(false),
                kaydediliyor: AtomicBool::new(false),
                sure_sn: Mutex::new(sureyi_sinirla(sure_sn)),
                bellek: Mutex::new(Bellek::default()),
                son_hata: Mutex::new(String::new()),
                fps: fps.max(1),
            }),
            surec: Mutex::new(None),
        }
    }

    pub fn acik(&self) -> bool {
        self.ortak.acik.load(Ordering::Relaxed)
    }
    pub fn kaydediliyor(&self) -> bool {
        self.ortak.kaydediliyor.load(Ordering::Relaxed)
    }
    pub fn son_hata(&self) -> String {
        self.ortak.son_hata.lock().unwrap().clone()
    }
    pub fn sure_sn(&self) -> u32 {
        *self.ortak.sure_sn.lock().unwrap()
    }
    /// Kullanılan yaklaşık bellek (bayt).
    pub fn bellek(&self) -> usize {
        let b = self.ortak.bellek.lock().unwrap();
        b.parcalar.iter().map(|(_, v)| v.len()).sum::<usize>() + b.sesler.iter().map(|(_, v)| v.len()).sum::<usize>()
    }
    pub fn tutulan_sure(&self) -> f64 {
        let b = self.ortak.bellek.lock().unwrap();
        b.parcalar.front().map(|(t, _)| t.elapsed().as_secs_f64()).unwrap_or(0.0)
    }

    /// Yeni kodlayıcı bir sonraki baslat()'ta kullanılır.
    pub fn kodlayici_ayarla(&self, k: &str) {
        *self.kodlayici_tercihi.lock().unwrap() = k.to_string();
    }

    pub fn sure_ayarla(&self, sn: i64) {
        *self.ortak.sure_sn.lock().unwrap() = sureyi_sinirla(sn);
        self.ortak.kirp(Instant::now());
    }

    pub fn baslat(&self) -> Result<(), String> {
        let mut g = self.surec.lock().unwrap();
        if self.acik() {
            return Ok(());
        }
        let hata = |m: String| {
            *self.ortak.son_hata.lock().unwrap() = m.clone();
            Err(m)
        };
        let Some(ff) = self.ffmpeg.clone().or_else(ffmpeg::ffmpeg_bul) else {
            return hata("FFmpeg bulunamadı".into());
        };
        let tercih = self.kodlayici_tercihi.lock().unwrap().clone();
        let kod = ffmpeg::kodlayici_sec(&ff, &tercih);
        let bicim = ffmpeg::girdi_bicimi(self.genislik, self.yukseklik);
        let fps = self.ortak.fps.to_string();
        let mut c = ffmpeg::komut(&ff);
        c.args(["-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", bicim])
            .args(["-s", &format!("{}x{}", self.genislik, self.yukseklik), "-framerate", &fps, "-i", "-"])
            .args(["-pix_fmt", if kod != "mpeg4" { "nv12" } else { "yuv420p" }, "-c:v", &kod])
            .args(ffmpeg::kodlayici_ayarlari(&kod))
            .args(["-g", &fps, "-bf", "0", "-bsf:v", "dump_extra=freq=keyframe"])
            .args(["-f", "mpegts", "-flush_packets", "1", "-"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut surec = match c.spawn() {
            Ok(s) => s,
            Err(e) => return hata(format!("FFmpeg başlatılamadı: {e}")),
        };
        *self.ortak.bellek.lock().unwrap() = Bellek::default();
        let mut stdin = surec.stdin.take().unwrap();
        let mut stdout = surec.stdout.take().unwrap();
        let (tx, rx) = sync_channel::<Option<KareRef>>((self.ortak.fps / 2).max(4) as usize);
        let (o1, o2, bicim) = (self.ortak.clone(), self.ortak.clone(), bicim.to_string());
        std::thread::Builder::new()
            .name("tekrar-yaz".into())
            .spawn(move || {
                while let Ok(Some(k)) = rx.recv() {
                    if let Err(e) = stdin.write_all(ffmpeg::kare_baytlari(&k, &bicim)) {
                        if o1.acik.load(Ordering::Relaxed) {
                            let m = format!("Anlık tekrar durdu: {e}");
                            log::warn!("{m}");
                            *o1.son_hata.lock().unwrap() = m;
                        }
                        break;
                    }
                    let mut b = o1.bellek.lock().unwrap();
                    let i = b.yazilan;
                    b.kare_zamanlari.push_back((i, Instant::now()));
                    while b.kare_zamanlari.len() > (o1.fps * 20) as usize {
                        b.kare_zamanlari.pop_front();
                    }
                    b.yazilan += 1;
                }
            })
            .map_err(|e| e.to_string())?;
        std::thread::Builder::new()
            .name("tekrar-oku".into())
            .spawn(move || {
                let mut ts = TsParcalayici::new();
                let mut tampon = vec![0u8; 65536];
                loop {
                    let n = match stdout.read(&mut tampon) {
                        Ok(0) | Err(_) => {
                            // FFmpeg beklenmedik kapandı: tekrar kapalı sayılsın (düğme "hazır" görünmesin)
                            if o2.acik.swap(false, Ordering::SeqCst) {
                                let m = "Anlık tekrar durdu: FFmpeg kapandı".to_string();
                                log::warn!("{m}");
                                *o2.son_hata.lock().unwrap() = m;
                            }
                            break;
                        }
                        Ok(n) => n,
                    };
                    for (p, veri) in ts.besle(&tampon[..n]) {
                        let t = o2.kare_zamani(p);
                        if !o2.acik.load(Ordering::Relaxed) {
                            continue;
                        }
                        {
                            let mut b = o2.bellek.lock().unwrap();
                            if b.baslik.is_empty() {
                                b.baslik = ts.baslik.clone();
                            }
                            b.parcalar.push_back((t, Arc::new(veri)));
                        }
                        o2.kirp(Instant::now());
                    }
                }
            })
            .map_err(|e| e.to_string())?;
        *g = Some((surec, tx));
        self.ortak.son_hata.lock().unwrap().clear();
        self.ortak.acik.store(true, Ordering::SeqCst);
        log::info!("Anlık tekrar açık ({} sn, {kod})", self.sure_sn());
        Ok(())
    }

    /// Kapatır ve belleği boşaltır.
    pub fn durdur(&self) {
        let mut g = self.surec.lock().unwrap();
        // FFmpeg kendiliğinden kapandıysa acik zaten false; süreç yine de toplanır
        if !self.ortak.acik.swap(false, Ordering::SeqCst) && g.is_none() {
            return;
        }
        {
            let mut b = self.ortak.bellek.lock().unwrap();
            b.parcalar.clear();
            b.sesler.clear();
        }
        if let Some((mut surec, tx)) = g.take() {
            let _ = tx.try_send(None);
            drop(tx);
            std::thread::spawn(move || {
                let bitis = Instant::now() + Duration::from_secs(3);
                while Instant::now() < bitis {
                    if let Ok(Some(_)) = surec.try_wait() {
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(30));
                }
                let _ = surec.kill();
                let _ = surec.wait();
            });
        }
        log::info!("Anlık tekrar kapandı");
    }

    pub fn kare_yaz(&self, kare: &KareRef) {
        if !self.acik() {
            return;
        }
        if let Ok(g) = self.surec.try_lock() {
            if let Some((_, tx)) = g.as_ref() {
                let _ = tx.try_send(Some(kare.clone())); // kodlayıcı yetişemedi: kare atlanır
            }
        }
    }

    pub fn ses_yaz(&self, blok: &[f32]) {
        if !self.acik() {
            return;
        }
        let mut veri = Vec::with_capacity(blok.len() * 2);
        ffmpeg::pcm16(blok, &mut veri);
        let simdi = Instant::now();
        let sure = *self.ortak.sure_sn.lock().unwrap() as u64 + 5;
        let mut b = self.ortak.bellek.lock().unwrap();
        b.sesler.push_back((simdi, veri));
        if let Some(esik) = simdi.checked_sub(Duration::from_secs(sure)) {
            while b.sesler.front().is_some_and(|(t, _)| *t < esik) {
                b.sesler.pop_front();
            }
        }
    }

    /// Arka planda MP4 yazar; bitince `bitti(dosya, hata)`. Err: kaydedecek bir şey yok.
    pub fn kaydet(&self, klasor: PathBuf, bitti: Option<BittiFn>) -> Result<(), String> {
        let hata = |m: &str| {
            *self.ortak.son_hata.lock().unwrap() = m.to_string();
            Err(m.to_string())
        };
        if !self.acik() {
            return hata("Anlık tekrar kapalı");
        }
        if self.ortak.kaydediliyor.load(Ordering::SeqCst) {
            return hata("Önceki tekrar hâlâ kaydediliyor");
        }
        let (baslik, parcalar, sesler, baslangic) = {
            let b = self.ortak.bellek.lock().unwrap();
            if b.parcalar.is_empty() {
                drop(b);
                return hata("Henüz kaydedilecek görüntü yok");
            }
            let simdi = Instant::now();
            let sure = Duration::from_secs(self.sure_sn() as u64);
            let mut parcalar: Vec<(Instant, Arc<Vec<u8>>)> = b.parcalar.iter().cloned().collect();
            if let Some(esik) = simdi.checked_sub(sure) {
                while parcalar.len() > 1 && parcalar[1].0 <= esik {
                    parcalar.remove(0);
                }
            }
            let baslangic = parcalar[0].0;
            let sesler: Vec<(Instant, Vec<u8>)> = b.sesler.iter().filter(|(t, _)| *t >= baslangic).cloned().collect();
            (b.baslik.clone(), parcalar, sesler, baslangic)
        };
        let Some(ff) = self.ffmpeg.clone().or_else(ffmpeg::ffmpeg_bul) else { return hata("FFmpeg bulunamadı") };
        self.ortak.kaydediliyor.store(true, Ordering::SeqCst);
        let ortak = self.ortak.clone();
        std::thread::Builder::new()
            .name("tekrar-kaydet".into())
            .spawn(move || {
                let (dosya, hata) = kaydet_isle(&ff, &klasor, &baslik, &parcalar, &sesler, baslangic);
                ortak.kaydediliyor.store(false, Ordering::SeqCst);
                if let Some(f) = bitti {
                    f(dosya, hata);
                }
            })
            .map_err(|e| e.to_string())?;
        Ok(())
    }
}

/// Sesi parçanın başladığı andan itibaren yazar; ses gelmeyen aralıklar sessizlikle dolar.
fn sesi_yaz(yol: &Path, sesler: &[(Instant, Vec<u8>)], baslangic: Instant) -> std::io::Result<bool> {
    if sesler.is_empty() {
        return Ok(false);
    }
    let ornek_bayt = 2 * SES_KANALI as usize;
    let mut yazilan: i64 = 0;
    let mut f = std::io::BufWriter::new(std::fs::File::create(yol)?);
    for (t, b) in sesler {
        let ornek = (b.len() / ornek_bayt) as i64;
        let beklenen = (t.saturating_duration_since(baslangic).as_secs_f64() * SES_HIZI as f64) as i64 - ornek;
        let bosluk = beklenen - yazilan;
        if bosluk > (SES_HIZI / 10) as i64 {
            f.write_all(&vec![0u8; bosluk as usize * ornek_bayt])?;
            yazilan += bosluk;
        }
        f.write_all(b)?;
        yazilan += ornek;
    }
    f.flush()?;
    ffmpeg::gizle(yol);
    Ok(yazilan > 0)
}

fn birlestir(ff: &Path, video: &Path, ses: Option<&Path>, hedef: &Path) -> Result<(), String> {
    let mut c = ffmpeg::komut(ff);
    c.args(["-y", "-hide_banner", "-loglevel", "error", "-f", "mpegts", "-i"]).arg(video);
    if let Some(s) = ses {
        c.args(["-f", "s16le", "-ar", &SES_HIZI.to_string(), "-ac", &SES_KANALI.to_string(), "-i"]).arg(s);
        c.args(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k"]);
    } else {
        c.args(["-map", "0:v"]);
    }
    c.args(["-c:v", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart"]).arg(hedef);
    let (ok, hata) = ffmpeg::calistir(c, Duration::from_secs(600));
    if !ok || std::fs::metadata(hedef).map(|m| m.len()).unwrap_or(0) == 0 {
        let _ = std::fs::remove_file(hedef);
        let h = hata.trim();
        let h = &h[h.len().saturating_sub(300)..];
        return Err(if h.is_empty() { "FFmpeg hata verdi".into() } else { h.to_string() });
    }
    Ok(())
}

fn kaydet_isle(
    ff: &Path,
    klasor: &Path,
    baslik: &[u8],
    parcalar: &[(Instant, Arc<Vec<u8>>)],
    sesler: &[(Instant, Vec<u8>)],
    baslangic: Instant,
) -> (Option<PathBuf>, String) {
    let ad = chrono::Local::now().format("Tekrar_%Y-%m-%d_%H-%M-%S.mp4").to_string();
    let _ = std::fs::create_dir_all(klasor);
    let hedef = bos_hedef(klasor, &ad);
    let govde = hedef.file_stem().unwrap_or_default().to_string_lossy().into_owned();
    let video = klasor.join(format!(".{govde}.ts"));
    let ses = klasor.join(format!(".{govde}.pcm"));
    let sonuc = (|| -> Result<(), String> {
        let mut f = std::fs::File::create(&video).map_err(|e| e.to_string())?;
        f.write_all(baslik).map_err(|e| e.to_string())?;
        for (_, b) in parcalar {
            f.write_all(b).map_err(|e| e.to_string())?;
        }
        drop(f);
        ffmpeg::gizle(&video);
        let ses_var = sesi_yaz(&ses, sesler, baslangic).unwrap_or(false);
        match birlestir(ff, &video, ses_var.then_some(ses.as_path()), &hedef) {
            Err(e) if ses_var => {
                log::warn!("Tekrar sesi eklenemedi: {e}");
                birlestir(ff, &video, None, &hedef)
            }
            s => s,
        }
    })();
    let _ = std::fs::remove_file(&video);
    let _ = std::fs::remove_file(&ses);
    match sonuc {
        Ok(()) if hedef.exists() => {
            log::info!("Anlık tekrar kaydedildi: {}", hedef.display());
            (Some(hedef), String::new())
        }
        Ok(()) => (None, "Dosya oluşmadı".into()),
        Err(e) => {
            log::warn!("Anlık tekrar kaydedilemedi: {e}");
            (None, e)
        }
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn etiketler() {
        assert_eq!(sure_etiketi(120), "Son 2 dk");
        assert_eq!(sure_etiketi(90), "Son 90 sn");
        assert_eq!(sure_etiketi(3), "Son 15 sn");
        assert_eq!(sureyi_sinirla(1000), 300);
    }

    #[test]
    fn ffmpeg_ile_tekrar() {
        let Some(ff) = ffmpeg::ffmpeg_bul() else { return };
        let d = std::env::temp_dir().join(format!("rizeon-tekrar-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let t = AnlikTekrar::yeni(320, 240, 30, 15, "mpeg4", Some(ff));
        t.baslat().unwrap();
        let bas = Instant::now();
        let mut i = 0u8;
        while bas.elapsed() < Duration::from_millis(2500) {
            let k = crate::kare::Kare::dolu(320, 240, [i, 100, 50]).arc();
            i = i.wrapping_add(3);
            t.kare_yaz(&k);
            t.ses_yaz(&[0.05f32; 960 * 3]);
            std::thread::sleep(Duration::from_millis(33));
        }
        assert!(t.bellek() > 0);
        let (tx, rx) = std::sync::mpsc::channel();
        t.kaydet(d.clone(), Some(Box::new(move |d, h| tx.send((d, h)).unwrap()))).unwrap();
        let (dosya, hata) = rx.recv_timeout(Duration::from_secs(60)).unwrap();
        assert!(dosya.is_some(), "{hata}");
        t.durdur();
        assert_eq!(t.bellek(), 0);
    }
}
