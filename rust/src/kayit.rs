//! Yerel kayıt (MP4) — FFmpeg ile. Python core/recorder.py'nin karşılığı, aynı dosya adları ve komutlar.
//!
//!   görüntü: video hattı her kareyi `kare_yaz` ile verir -> kuyruk -> FFmpeg (stdin) -> geçici MKV
//!   ses    : mikser her 10 ms'lik bloğu `ses_yaz` ile verir -> kuyruk -> geçici ham PCM dosyası
//!   durunca: FFmpeg görüntü + sesi tek MP4'te birleştirir (görüntü yeniden kodlanmaz)
//!
//! Duraklat/devam: görüntü parçası kapanır, devamda yeni parça başlar; sonda uç uca eklenir.
//! Çökmeye dayanıklı: MKV ve başlıksız PCM yarım kalsa da açılır; bir sonraki açılışta
//! `yarim_kayitlari_kurtar` onları "..._kurtarildi.mp4" yapar.

use std::collections::VecDeque;
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{sync_channel, Receiver, SyncSender, TrySendError};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant, SystemTime};

use crate::ffmpeg::{self, SES_HIZI, SES_KANALI};
use crate::kare::KareRef;

pub const GECICI_VIDEO: &str = ".video.mkv";
pub const GECICI_SES: &str = ".ses.pcm";
const SES_KAYMA: i64 = (SES_HIZI / 10) as i64; // 100 ms'den fazla kayma düzeltilir

pub type BittiFn = Box<dyn FnOnce(Option<PathBuf>, String) + Send>;
pub type HataFn = Arc<dyn Fn(String) + Send + Sync>;

pub fn parca_yolu(klasor: &Path, ad: &str, sira: usize) -> PathBuf {
    if sira == 1 {
        klasor.join(format!(".{ad}{GECICI_VIDEO}"))
    } else {
        klasor.join(format!(".{ad}.video.{sira}.mkv"))
    }
}

/// ".Kayit_2026-11-09_12-00-00~2.video.3.mkv" -> ("Kayit_2026-11-09_12-00-00~2", 3)
pub fn gecici_ad_coz(dosya: &str) -> Option<(String, usize)> {
    let govde = dosya.strip_prefix('.')?.strip_suffix(".mkv")?;
    let (ad, sira) = if let Some(a) = govde.strip_suffix(".video") {
        (a, 1)
    } else {
        let (a, n) = govde.rsplit_once(".video.")?;
        (a, n.parse::<usize>().ok().filter(|n| *n >= 1)?)
    };
    let tarih = ad.strip_prefix("Kayit_")?;
    let (t, ek) = match tarih.split_once('~') {
        Some((t, e)) => (t, Some(e)),
        None => (tarih, None),
    };
    let b = t.as_bytes();
    let bicim_dogru = b.len() == 19
        && b.iter().enumerate().all(|(i, c)| match i {
            4 | 7 | 13 | 16 => *c == b'-',
            10 => *c == b'_',
            _ => c.is_ascii_digit(),
        });
    if !bicim_dogru || ek.is_some_and(|e| e.is_empty() || !e.bytes().all(|c| c.is_ascii_digit())) {
        return None;
    }
    Some((ad.to_string(), sira))
}

fn yas_sn(yol: &Path) -> f64 {
    std::fs::metadata(yol)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| SystemTime::now().duration_since(t).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn bos_degil(yol: &Path) -> bool {
    std::fs::metadata(yol).map(|m| m.len() > 0).unwrap_or(false)
}

/// Önceki çalışmada çökme/elektrik kesintisi yüzünden yarım kalan kayıtları MP4'e çevirir.
pub fn yarim_kayitlari_kurtar(klasor: &Path, ffmpeg: Option<&Path>) -> Vec<PathBuf> {
    let Some(ffmpeg) = ffmpeg else { return vec![] };
    let Ok(okuyucu) = std::fs::read_dir(klasor) else { return vec![] };
    let mut kayitlar: std::collections::BTreeMap<String, Vec<(usize, PathBuf)>> = Default::default();
    for g in okuyucu.flatten() {
        let ad = g.file_name().to_string_lossy().into_owned();
        if let Some((kayit, sira)) = gecici_ad_coz(&ad) {
            if g.path().is_file() {
                kayitlar.entry(kayit).or_default().push((sira, g.path()));
            }
        }
    }
    let mut kurtarilan = vec![];
    for (ad, mut liste) in kayitlar {
        liste.sort();
        let tum: Vec<PathBuf> = liste.into_iter().map(|(_, p)| p).collect();
        let ses = klasor.join(format!(".{ad}{GECICI_SES}"));
        if tum.iter().any(|f| yas_sn(f) < 3.0) {
            continue; // şu an yazılan bir kayıt olabilir
        }
        let parcalar: Vec<PathBuf> = tum.iter().filter(|p| bos_degil(p)).cloned().collect();
        let hedef = klasor.join(format!("{ad}_kurtarildi.mp4"));
        let sonuc = if parcalar.is_empty() {
            Err("boş dosya".to_string())
        } else {
            let ses_var = bos_degil(&ses);
            let s = if ses_var { Some(ses.as_path()) } else { None };
            ffmpeg::birlestir(ffmpeg, &parcalar, s, &hedef)
                .or_else(|e| if ses_var { ffmpeg::birlestir(ffmpeg, &parcalar, None, &hedef) } else { Err(e) })
                .or_else(|e| if parcalar.len() > 1 { ffmpeg::birlestir(ffmpeg, &parcalar[..1], s, &hedef) } else { Err(e) })
        };
        match sonuc {
            Ok(()) => {
                log::info!("Yarım kalan kayıt kurtarıldı: {}", hedef.display());
                kurtarilan.push(hedef);
                for f in tum.iter().chain(std::iter::once(&ses)) {
                    let _ = std::fs::remove_file(f);
                }
            }
            Err(e) => {
                log::warn!("Yarım kalan kayıt kurtarılamadı ({ad}): {e}");
                if parcalar.is_empty() {
                    for f in tum.iter().chain(std::iter::once(&ses)) {
                        let _ = std::fs::remove_file(f);
                    }
                }
            }
        }
    }
    kurtarilan
}

struct Parca {
    tx: SyncSender<Option<KareRef>>,
    surec: Child,
    yazici: JoinHandle<()>,
    yol: PathBuf,
    kare: Arc<AtomicU64>,
}

impl Parca {
    /// Görüntü parçasını bitirir. Hiç kare yazılmadıysa parça silinir.
    fn kapat(mut self) {
        let _ = self.tx.send(None);
        let _ = self.yazici.join();
        drop(self.surec.stdin.take());
        let bitis = Instant::now() + Duration::from_secs(30);
        loop {
            match self.surec.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) if Instant::now() < bitis => std::thread::sleep(Duration::from_millis(20)),
                _ => {
                    let _ = self.surec.kill();
                    let _ = self.surec.wait();
                    break;
                }
            }
        }
        if self.kare.load(Ordering::Relaxed) == 0 {
            let _ = std::fs::remove_file(&self.yol);
        }
    }
}

struct Aktif {
    ad: String,
    hedef: PathBuf,
    gecici_ses: PathBuf,
    kod: String,
    ffmpeg: PathBuf,
    parcalar: Vec<PathBuf>,
    parca: Option<Parca>,
    kapananlar: Vec<JoinHandle<()>>,
    ses_tx: SyncSender<Option<(Instant, Vec<f32>)>>,
    ses_is: JoinHandle<()>,
    duraklama_baslangic: Instant,
}

struct Ortak {
    kayitta: AtomicBool,
    duraklatildi: AtomicBool,
    bitiyor: AtomicBool,
    baslangic: Mutex<Instant>,
    toplam_duraklama_ns: AtomicU64,
    son_hata: Mutex<String>,
    kayit_hatasi: Mutex<String>,
    hata_bildirildi: AtomicBool,
    hata_olunca: Mutex<Option<HataFn>>,
    atlanan_kare: AtomicU64,
    atlanan_ses: AtomicU64,
    ffmpeg_ciktisi: Mutex<VecDeque<String>>,
    kare_tx: Mutex<Option<SyncSender<Option<KareRef>>>>,
    ses_tx: Mutex<Option<SyncSender<Option<(Instant, Vec<f32>)>>>>,
}

impl Ortak {
    fn yazma_hatasi(&self, mesaj: String) {
        log::warn!("{mesaj}");
        *self.son_hata.lock().unwrap() = mesaj.clone();
        *self.kayit_hatasi.lock().unwrap() = mesaj.clone();
        if self.hata_bildirildi.swap(true, Ordering::SeqCst) {
            return;
        }
        if let Some(f) = self.hata_olunca.lock().unwrap().clone() {
            f(mesaj);
        }
    }

    fn kayit_zamani(&self, t: Instant) -> f64 {
        let bas = *self.baslangic.lock().unwrap();
        let d = t.saturating_duration_since(bas).as_secs_f64() - self.toplam_duraklama_ns.load(Ordering::Relaxed) as f64 / 1e9;
        d.max(0.0)
    }
}

pub struct Kayitci {
    pub genislik: u32,
    pub yukseklik: u32,
    pub fps: u32,
    klasor: Mutex<PathBuf>,
    kodlayici_tercihi: Mutex<String>,
    pub ffmpeg: Option<PathBuf>,
    ortak: Arc<Ortak>,
    aktif: Mutex<Option<Aktif>>,
}

impl Kayitci {
    pub fn yeni(genislik: u32, yukseklik: u32, fps: u32, klasor: PathBuf, kodlayici: &str, ffmpeg: Option<PathBuf>) -> Self {
        Kayitci {
            genislik,
            yukseklik,
            fps: fps.max(1),
            klasor: Mutex::new(klasor),
            kodlayici_tercihi: Mutex::new(kodlayici.to_string()),
            ffmpeg,
            ortak: Arc::new(Ortak {
                kayitta: AtomicBool::new(false),
                duraklatildi: AtomicBool::new(false),
                bitiyor: AtomicBool::new(false),
                baslangic: Mutex::new(Instant::now()),
                toplam_duraklama_ns: AtomicU64::new(0),
                son_hata: Mutex::new(String::new()),
                kayit_hatasi: Mutex::new(String::new()),
                hata_bildirildi: AtomicBool::new(false),
                hata_olunca: Mutex::new(None),
                atlanan_kare: AtomicU64::new(0),
                atlanan_ses: AtomicU64::new(0),
                ffmpeg_ciktisi: Mutex::new(VecDeque::new()),
                kare_tx: Mutex::new(None),
                ses_tx: Mutex::new(None),
            }),
            aktif: Mutex::new(None),
        }
    }

    /// Kayıt klasörü (ayarlardan değişebilir; süren kayıt eski klasörde biter).
    pub fn klasor(&self) -> PathBuf {
        self.klasor.lock().unwrap().clone()
    }

    pub fn klasor_ayarla(&self, k: PathBuf) {
        *self.klasor.lock().unwrap() = k;
    }

    pub fn kodlayici_ayarla(&self, k: &str) {
        *self.kodlayici_tercihi.lock().unwrap() = k.to_string();
    }

    /// Kayıt yazılamazsa (disk doldu vb.) çağrılır.
    pub fn hata_olunca(&self, f: HataFn) {
        *self.ortak.hata_olunca.lock().unwrap() = Some(f);
    }

    pub fn kayitta(&self) -> bool {
        self.ortak.kayitta.load(Ordering::Relaxed)
    }
    pub fn duraklatildi(&self) -> bool {
        self.kayitta() && self.ortak.duraklatildi.load(Ordering::Relaxed)
    }
    pub fn bitiyor(&self) -> bool {
        self.ortak.bitiyor.load(Ordering::Relaxed)
    }
    pub fn son_hata(&self) -> String {
        self.ortak.son_hata.lock().unwrap().clone()
    }

    /// Kaydedilen süre (saniye). Duraklatılan süre sayılmaz.
    pub fn sure(&self) -> u64 {
        if !self.kayitta() {
            return 0;
        }
        let mut duraklama = self.ortak.toplam_duraklama_ns.load(Ordering::Relaxed) as f64 / 1e9;
        if self.duraklatildi() {
            if let Some(a) = self.aktif.lock().unwrap().as_ref() {
                duraklama += a.duraklama_baslangic.elapsed().as_secs_f64();
            }
        }
        let gecen = self.ortak.baslangic.lock().unwrap().elapsed().as_secs_f64();
        (gecen - duraklama).max(0.0) as u64
    }

    fn bos_ad(klasor: &Path, ad: &str) -> String {
        let mut aday = ad.to_string();
        let mut sira = 2;
        while klasor.join(format!("{aday}.mp4")).exists()
            || parca_yolu(klasor, &aday, 1).exists()
            || klasor.join(format!(".{aday}{GECICI_SES}")).exists()
        {
            aday = format!("{ad}~{sira}");
            sira += 1;
        }
        aday
    }

    fn parca_baslat(&self, klasor: &Path, ffmpeg: &Path, ad: &str, sira: usize, kod: &str) -> Result<Parca, String> {
        let yol = parca_yolu(klasor, ad, sira);
        let bicim = ffmpeg::girdi_bicimi(self.genislik, self.yukseklik);
        let fps = self.fps.to_string();
        let mut c = ffmpeg::komut(ffmpeg);
        c.args(["-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", bicim])
            .args(["-s", &format!("{}x{}", self.genislik, self.yukseklik), "-framerate", &fps])
            .args(["-use_wallclock_as_timestamps", "1", "-i", "-", "-fps_mode", "cfr", "-r", &fps])
            .args(["-pix_fmt", if kod != "mpeg4" { "nv12" } else { "yuv420p" }, "-c:v", kod])
            .args(ffmpeg::kodlayici_ayarlari(kod))
            .args(["-g", &(self.fps * 2).to_string(), "-f", "matroska", "-flush_packets", "1"])
            .arg(&yol)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        let mut surec = c.spawn().map_err(|e| format!("FFmpeg başlatılamadı: {e}"))?;
        ffmpeg::gizle(&yol);
        // FFmpeg'in hata çıktısı sürekli okunur (okunmazsa boru dolup FFmpeg tıkanabilir)
        if let Some(stderr) = surec.stderr.take() {
            let ortak = self.ortak.clone();
            std::thread::Builder::new()
                .name("kayit-ffmpeg".into())
                .spawn(move || {
                    for satir in std::io::BufReader::new(stderr).lines().map_while(Result::ok) {
                        let s = satir.trim_end().to_string();
                        if !s.is_empty() {
                            let mut c = ortak.ffmpeg_ciktisi.lock().unwrap();
                            c.push_back(s);
                            while c.len() > 50 {
                                c.pop_front();
                            }
                        }
                    }
                })
                .ok();
        }
        let mut stdin = surec.stdin.take().ok_or("FFmpeg girişi açılamadı")?;
        let (tx, rx): (SyncSender<Option<KareRef>>, Receiver<Option<KareRef>>) = sync_channel(self.fps.max(10) as usize);
        let kare = Arc::new(AtomicU64::new(0));
        let (ortak, sayac, bicim) = (self.ortak.clone(), kare.clone(), bicim.to_string());
        let yazici = std::thread::Builder::new()
            .name("kayit-video".into())
            .spawn(move || {
                while let Ok(Some(k)) = rx.recv() {
                    if let Err(e) = stdin.write_all(ffmpeg::kare_baytlari(&k, &bicim)) {
                        std::thread::sleep(Duration::from_millis(200)); // FFmpeg'in son satırları okunsun
                        let ayrinti: Vec<String> = ortak.ffmpeg_ciktisi.lock().unwrap().iter().rev().take(3).rev().cloned().collect();
                        ortak.yazma_hatasi(format!("Kayıt görüntüsü yazılamadı: {e} {}", ayrinti.join(" ")).trim().to_string());
                        break;
                    }
                    sayac.fetch_add(1, Ordering::Relaxed);
                }
                drop(stdin);
            })
            .map_err(|e| e.to_string())?;
        *self.ortak.kare_tx.lock().unwrap() = Some(tx.clone());
        Ok(Parca { tx, surec, yazici, yol, kare })
    }

    pub fn baslat(&self) -> Result<(), String> {
        let mut aktif = self.aktif.lock().unwrap();
        if self.kayitta() {
            return Ok(());
        }
        let hata = |m: String| {
            *self.ortak.son_hata.lock().unwrap() = m.clone();
            Err(m)
        };
        let Some(ffmpeg) = self.ffmpeg.clone().or_else(ffmpeg::ffmpeg_bul) else {
            return hata("FFmpeg bulunamadı (uygulama klasöründe ffmpeg\\ffmpeg.exe olmalı)".into());
        };
        let klasor = self.klasor();
        if let Err(e) = std::fs::create_dir_all(&klasor) {
            return hata(format!("Kayıt klasörü oluşturulamadı: {e}"));
        }
        if self.bitiyor() {
            return hata("Önceki kayıt hâlâ hazırlanıyor, birkaç saniye sonra tekrar dene".into());
        }
        let ad = Self::bos_ad(&klasor, &chrono::Local::now().format("Kayit_%Y-%m-%d_%H-%M-%S").to_string());
        let hedef = klasor.join(format!("{ad}.mp4"));
        let gecici_ses = klasor.join(format!(".{ad}{GECICI_SES}"));
        let tercih = self.kodlayici_tercihi.lock().unwrap().clone();
        let kod = ffmpeg::kodlayici_sec(&ffmpeg, &tercih);
        let ses_dosyasi = match std::fs::File::create(&gecici_ses) {
            Ok(f) => f,
            Err(e) => return hata(format!("Kayıt dosyası açılamadı: {e}")),
        };
        ffmpeg::gizle(&gecici_ses);
        self.ortak.ffmpeg_ciktisi.lock().unwrap().clear();
        self.ortak.hata_bildirildi.store(false, Ordering::SeqCst);
        self.ortak.kayit_hatasi.lock().unwrap().clear();
        let parca = match self.parca_baslat(&klasor, &ffmpeg, &ad, 1, &kod) {
            Ok(p) => p,
            Err(e) => {
                drop(ses_dosyasi);
                let _ = std::fs::remove_file(&gecici_ses);
                return hata(e);
            }
        };
        self.ortak.atlanan_kare.store(0, Ordering::Relaxed);
        self.ortak.atlanan_ses.store(0, Ordering::Relaxed);
        self.ortak.toplam_duraklama_ns.store(0, Ordering::Relaxed);
        self.ortak.duraklatildi.store(false, Ordering::Relaxed);
        *self.ortak.baslangic.lock().unwrap() = Instant::now();
        let (ses_tx, ses_rx) = sync_channel::<Option<(Instant, Vec<f32>)>>(2000);
        let ortak = self.ortak.clone();
        let ses_is = std::thread::Builder::new()
            .name("kayit-ses".into())
            .spawn(move || ses_dongu(ortak, ses_rx, ses_dosyasi))
            .map_err(|e| e.to_string())?;
        *self.ortak.ses_tx.lock().unwrap() = Some(ses_tx.clone());
        log::info!("Kayıt başladı: {} ({kod})", hedef.display());
        *aktif = Some(Aktif {
            parcalar: vec![parca.yol.clone()],
            parca: Some(parca),
            ad,
            hedef,
            gecici_ses,
            kod,
            ffmpeg,
            kapananlar: vec![],
            ses_tx,
            ses_is,
            duraklama_baslangic: Instant::now(),
        });
        self.ortak.son_hata.lock().unwrap().clear();
        self.ortak.kayitta.store(true, Ordering::SeqCst);
        Ok(())
    }

    /// Kaydı duraklatır: görüntü parçası kapanır, ses yazılmaz. Bekletmez.
    pub fn duraklat(&self) -> bool {
        let mut g = self.aktif.lock().unwrap();
        let Some(a) = g.as_mut() else { return false };
        if self.ortak.duraklatildi.load(Ordering::Relaxed) {
            return false;
        }
        self.ortak.duraklatildi.store(true, Ordering::SeqCst);
        *self.ortak.kare_tx.lock().unwrap() = None;
        a.duraklama_baslangic = Instant::now();
        if let Some(p) = a.parca.take() {
            a.kapananlar.push(std::thread::spawn(move || p.kapat()));
        }
        log::info!("Kayıt duraklatıldı");
        true
    }

    /// Duraklatılan kayda devam eder (yeni görüntü parçası başlar).
    pub fn devam_et(&self) -> bool {
        let mut g = self.aktif.lock().unwrap();
        let Some(a) = g.as_mut() else { return false };
        if !self.ortak.duraklatildi.load(Ordering::Relaxed) {
            return false;
        }
        let sira = a.parcalar.len() + 1;
        let klasor = a.hedef.parent().map(Path::to_path_buf).unwrap_or_default();
        match self.parca_baslat(&klasor, &a.ffmpeg.clone(), &a.ad.clone(), sira, &a.kod.clone()) {
            Ok(p) => {
                a.parcalar.push(p.yol.clone());
                a.parca = Some(p);
            }
            Err(e) => {
                *self.ortak.son_hata.lock().unwrap() = e;
                return false;
            }
        }
        let d = a.duraklama_baslangic.elapsed().as_nanos() as u64;
        self.ortak.toplam_duraklama_ns.fetch_add(d, Ordering::Relaxed);
        self.ortak.duraklatildi.store(false, Ordering::SeqCst);
        log::info!("Kayda devam edildi ({}. parça)", sira);
        true
    }

    /// Video hattından her karede çağrılır; asla beklemez (kuyruk doluysa kare atlanır).
    pub fn kare_yaz(&self, kare: &KareRef) {
        if !self.kayitta() || self.ortak.duraklatildi.load(Ordering::Relaxed) {
            return;
        }
        if let Some(tx) = self.ortak.kare_tx.lock().unwrap().as_ref() {
            if let Err(TrySendError::Full(_)) = tx.try_send(Some(kare.clone())) {
                self.ortak.atlanan_kare.fetch_add(1, Ordering::Relaxed);
            }
        }
    }

    /// Mikserden her 10 ms'de çağrılır; asla beklemez.
    pub fn ses_yaz(&self, blok: &[f32]) {
        if !self.kayitta() || self.ortak.duraklatildi.load(Ordering::Relaxed) {
            return;
        }
        if let Some(tx) = self.ortak.ses_tx.lock().unwrap().as_ref() {
            if tx.try_send(Some((Instant::now(), blok.to_vec()))).is_err() {
                self.ortak.atlanan_ses.fetch_add(1, Ordering::Relaxed);
            }
        }
    }

    /// Kaydı bitirir; birleştirme arka planda yapılır, bitince `bitti(dosya, hata)` çağrılır.
    pub fn durdur(&self, bitti: Option<BittiFn>) {
        let mut g = self.aktif.lock().unwrap();
        let Some(a) = g.take() else { return };
        self.ortak.kayitta.store(false, Ordering::SeqCst);
        self.ortak.duraklatildi.store(false, Ordering::SeqCst);
        *self.ortak.kare_tx.lock().unwrap() = None;
        *self.ortak.ses_tx.lock().unwrap() = None;
        self.ortak.bitiyor.store(true, Ordering::SeqCst);
        let ortak = self.ortak.clone();
        std::thread::Builder::new()
            .name("kayit-bitir".into())
            .spawn(move || {
                let (dosya, hata) = bitir(&ortak, a);
                ortak.bitiyor.store(false, Ordering::SeqCst);
                if let Some(f) = bitti {
                    f(dosya, hata);
                }
            })
            .ok();
    }

    /// Kapanışta: kayıt sürüyorsa bitir ve birleştirmenin bitmesini bekle (en fazla `sn` saniye).
    pub fn kapat(&self, sn: u64) {
        if self.kayitta() {
            self.durdur(None);
        }
        let bitis = Instant::now() + Duration::from_secs(sn);
        while self.bitiyor() && Instant::now() < bitis {
            std::thread::sleep(Duration::from_millis(50));
        }
    }
}

/// Sesi görüntüyle aynı saate göre yazar: her blokta "şu ana kadar kaç örnek yazılmış olmalıydı"
/// hesaplanır; 100 ms'den fazla eksikse sessizlik eklenir, fazlaysa blok atlanır.
fn ses_dongu(ortak: Arc<Ortak>, rx: Receiver<Option<(Instant, Vec<f32>)>>, dosya: std::fs::File) {
    let mut dosya = std::io::BufWriter::with_capacity(1 << 16, dosya);
    let mut yazilabilir = true;
    let mut yazilan: i64 = 0;
    let ornek_bayt = 2 * SES_KANALI as usize;
    let mut tampon = Vec::new();
    while let Ok(Some((zaman, blok))) = rx.recv() {
        if !yazilabilir {
            continue;
        }
        let n = (blok.len() / SES_KANALI as usize) as i64;
        let beklenen = (ortak.kayit_zamani(zaman) * SES_HIZI as f64) as i64 - n;
        let fark = beklenen - yazilan;
        let mut sonuc = Ok(());
        if fark > SES_KAYMA {
            sonuc = dosya.write_all(&vec![0u8; fark as usize * ornek_bayt]);
            yazilan += fark;
        } else if fark < -SES_KAYMA {
            continue;
        }
        tampon.clear();
        ffmpeg::pcm16(&blok, &mut tampon);
        sonuc = sonuc.and_then(|_| dosya.write_all(&tampon));
        yazilan += n;
        if let Err(e) = sonuc {
            yazilabilir = false;
            ortak.yazma_hatasi(format!("Kayıt sesi yazılamadı (disk dolu olabilir): {e}"));
        }
    }
    let _ = dosya.flush();
}

fn bitir(ortak: &Ortak, mut a: Aktif) -> (Option<PathBuf>, String) {
    for is in a.kapananlar.drain(..) {
        let _ = is.join();
    }
    if let Some(p) = a.parca.take() {
        p.kapat();
    }
    let _ = a.ses_tx.send(None);
    let _ = a.ses_is.join();
    let (ak, as_) = (ortak.atlanan_kare.load(Ordering::Relaxed), ortak.atlanan_ses.load(Ordering::Relaxed));
    if ak > 0 || as_ > 0 {
        log::warn!("Kayıtta {ak} kare ve {as_} ses bloğu atlandı (bilgisayar yetişemedi)");
    }
    let parcalar: Vec<PathBuf> = a.parcalar.iter().filter(|p| bos_degil(p)).cloned().collect();
    let ses_var = bos_degil(&a.gecici_ses);
    let kayit_hatasi = ortak.kayit_hatasi.lock().unwrap().clone();
    let mut hata = String::new();
    let mut tamam = false;
    if parcalar.is_empty() {
        hata = if kayit_hatasi.is_empty() { "Görüntü kaydedilemedi".into() } else { kayit_hatasi };
    } else {
        let ses = if ses_var { Some(a.gecici_ses.as_path()) } else { None };
        match ffmpeg::birlestir(&a.ffmpeg, &parcalar, ses, &a.hedef) {
            Ok(()) => tamam = true,
            Err(e) if ses_var => {
                log::warn!("Ses birleştirilemedi: {e}");
                match ffmpeg::birlestir(&a.ffmpeg, &parcalar, None, &a.hedef) {
                    Ok(()) => {
                        tamam = true;
                        hata = "Ses eklenemedi; sadece görüntü kaydedildi".into();
                    }
                    Err(e) => hata = format!("Kayıt dosyası oluşturulamadı: {e}"),
                }
            }
            Err(e) => hata = format!("Kayıt dosyası oluşturulamadı: {e}"),
        }
        if tamam && hata.is_empty() && !kayit_hatasi.is_empty() {
            hata = kayit_hatasi; // yarıda kesildi ama o ana kadarki kısım kaydedildi
        }
    }
    if tamam {
        // başarısızsa geçici dosyalar kalır, bir sonraki açılışta yeniden denenir
        for f in a.parcalar.iter().chain(std::iter::once(&a.gecici_ses)) {
            let _ = std::fs::remove_file(f);
        }
    }
    let dosya = a.hedef.exists().then(|| a.hedef.clone());
    log::info!("Kayıt bitti: {:?} {hata}", dosya);
    (dosya, hata)
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn gecici_adlar() {
        assert_eq!(gecici_ad_coz(".Kayit_2026-11-09_12-00-00.video.mkv"), Some(("Kayit_2026-11-09_12-00-00".into(), 1)));
        assert_eq!(gecici_ad_coz(".Kayit_2026-11-09_12-00-00~2.video.3.mkv"), Some(("Kayit_2026-11-09_12-00-00~2".into(), 3)));
        assert_eq!(gecici_ad_coz(".Kayit_2026-11-09.video.mkv"), None);
        assert_eq!(gecici_ad_coz("Kayit_2026-11-09_12-00-00.video.mkv"), None);
        assert_eq!(gecici_ad_coz(".Kayit_2026-11-09_12-00-00~.video.mkv"), None);
    }

    #[test]
    fn parca_yollari() {
        let k = Path::new("/k");
        assert_eq!(parca_yolu(k, "Kayit_x", 1), Path::new("/k/.Kayit_x.video.mkv"));
        assert_eq!(parca_yolu(k, "Kayit_x", 2), Path::new("/k/.Kayit_x.video.2.mkv"));
    }

    /// Gerçek FFmpeg ile uçtan uca (FFmpeg yoksa atlanır).
    #[test]
    fn ffmpeg_ile_kayit() {
        let Some(ff) = ffmpeg::ffmpeg_bul() else { return };
        let d = std::env::temp_dir().join(format!("rizeon-kayit-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let k = Kayitci::yeni(320, 240, 30, d.clone(), "mpeg4", Some(ff));
        k.baslat().unwrap();
        let kare = crate::kare::Kare::dolu(320, 240, [200, 30, 30]).arc();
        let bas = Instant::now();
        while bas.elapsed() < Duration::from_millis(1200) {
            k.kare_yaz(&kare);
            k.ses_yaz(&[0.1f32; 960]);
            std::thread::sleep(Duration::from_millis(10));
        }
        k.duraklat();
        std::thread::sleep(Duration::from_millis(300));
        assert!(k.devam_et());
        for _ in 0..30 {
            k.kare_yaz(&kare);
            std::thread::sleep(Duration::from_millis(33));
        }
        let (tx, rx) = std::sync::mpsc::channel();
        k.durdur(Some(Box::new(move |d, h| tx.send((d, h)).unwrap())));
        let (dosya, hata) = rx.recv_timeout(Duration::from_secs(60)).unwrap();
        assert!(dosya.is_some(), "{hata}");
        assert!(hata.is_empty(), "{hata}");
        let kalan: Vec<_> = std::fs::read_dir(&d).unwrap().flatten().map(|g| g.file_name()).collect();
        assert_eq!(kalan.len(), 1, "{kalan:?}");
    }
}
