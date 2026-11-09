//! Dosyadan döngüde video (Python core/standby.py BeklemeVideosu karşılığı): video kaynağı ve
//! bekleme ekranı videosu.
//!
//! Uygulamayla gelen FFmpeg videoyu çıkış boyutuna sığdırıp (siyah kenarlı) BGRA olarak boruya
//! yazar; okuyucu iş parçacığı kareleri hat hızında alır. Kimse kare istemezse (sahne değişti,
//! bekleme ekranı kapandı) okuma durur, FFmpeg boruda bekler ve işlemci harcamaz; tekrar
//! istenince kaldığı yerden devam eder. Video bitince başa sarar (-stream_loop -1).

use std::io::Read;
use std::process::{Child, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::kare::{Kare, KareRef};

/// Bu kadar süre kare istenmezse okuma durur.
const BOSTA: Duration = Duration::from_millis(1000);

struct Acik {
    yol: String,
    boyut: (u32, u32),
    cocuk: Child,
    calis: Arc<AtomicBool>,
}

#[derive(Default)]
struct Ortak {
    son: Mutex<Option<KareRef>>,
    hata: Mutex<String>,
    /// Son kare isteğinin zamanı (başlangıçtan beri ms)
    son_istek: AtomicU64,
}

pub struct VideoOynatici {
    fps: u32,
    acik: Mutex<Option<Acik>>,
    ortak: Arc<Ortak>,
    t0: Instant,
}

impl VideoOynatici {
    pub fn yeni(fps: u32) -> Self {
        VideoOynatici { fps: fps.clamp(1, 60), acik: Mutex::new(None), ortak: Arc::default(), t0: Instant::now() }
    }

    pub fn hata(&self) -> String {
        self.ortak.hata.lock().unwrap().clone()
    }

    fn simdi_ms(&self) -> u64 {
        self.t0.elapsed().as_millis() as u64
    }

    /// Videonun şu anki karesi (w×h). Açılamazsa None.
    pub fn kare(&self, yol: &str, w: u32, h: u32) -> Option<KareRef> {
        self.ortak.son_istek.store(self.simdi_ms(), Ordering::Relaxed);
        let mut acik = self.acik.lock().unwrap();
        let ayni = acik.as_ref().is_some_and(|a| a.yol == yol && a.boyut == (w, h));
        if !ayni {
            if let Some(a) = acik.take() {
                Self::durdur(a);
            }
            *self.ortak.son.lock().unwrap() = None;
            match self.ac(yol, w, h) {
                Ok(a) => {
                    self.ortak.hata.lock().unwrap().clear();
                    *acik = Some(a);
                }
                Err(e) => {
                    let mut hata = self.ortak.hata.lock().unwrap();
                    if *hata != e {
                        log::warn!("{e}");
                        *hata = e;
                    }
                    return None;
                }
            }
        }
        drop(acik);
        // ilk kare gelene kadar en fazla biraz bekle (bekleme ekranına geçerken siyah kare görünmesin)
        let bitis = Instant::now() + Duration::from_millis(if ayni { 0 } else { 400 });
        loop {
            if let Some(k) = self.ortak.son.lock().unwrap().clone() {
                return Some(k);
            }
            if Instant::now() >= bitis {
                return None;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    fn ac(&self, yol: &str, w: u32, h: u32) -> Result<Acik, String> {
        if yol.is_empty() || !std::path::Path::new(yol).is_file() {
            return Err(format!("Video bulunamadı: {yol}"));
        }
        let ff = crate::ffmpeg::ffmpeg_bul().ok_or("Video oynatılamıyor: FFmpeg bulunamadı")?;
        let vf = format!(
            "fps={fps},scale={w}:{h}:force_original_aspect_ratio=decrease:flags=bilinear,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
            fps = self.fps
        );
        let mut k = crate::ffmpeg::komut(&ff);
        k.args(["-hide_banner", "-loglevel", "error", "-nostdin", "-stream_loop", "-1", "-i"])
            .arg(yol)
            .args(["-an", "-sn", "-threads", "2", "-vf", &vf, "-pix_fmt", "bgra", "-f", "rawvideo", "pipe:1"])
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut cocuk = k.spawn().map_err(|e| format!("Video açılamadı: {yol} ({e})"))?;
        let mut cikis = cocuk.stdout.take().ok_or("Video açılamadı")?;
        let calis = Arc::new(AtomicBool::new(true));
        let (ortak, c2, fps, t0) = (self.ortak.clone(), calis.clone(), self.fps, self.t0);
        let yol2 = yol.to_string();
        std::thread::Builder::new()
            .name("video-oynatici".into())
            .spawn(move || {
                let boyut = (w * h * 4) as usize;
                let aralik = Duration::from_secs_f64(1.0 / fps as f64);
                let mut sonraki = Instant::now();
                let mut ilk = true;
                while c2.load(Ordering::Relaxed) {
                    let simdi_ms = t0.elapsed().as_millis() as u64;
                    if !ilk && simdi_ms.saturating_sub(ortak.son_istek.load(Ordering::Relaxed)) > BOSTA.as_millis() as u64 {
                        // kimse bakmıyor: FFmpeg boruda beklesin
                        std::thread::sleep(Duration::from_millis(50));
                        sonraki = Instant::now();
                        continue;
                    }
                    let mut veri = vec![0u8; boyut];
                    if let Err(e) = cikis.read_exact(&mut veri) {
                        if c2.load(Ordering::Relaxed) {
                            let m = format!("Video okunamadı: {yol2} ({e})");
                            log::warn!("{m}");
                            *ortak.hata.lock().unwrap() = m;
                        }
                        return;
                    }
                    ilk = false;
                    *ortak.son.lock().unwrap() = Some(Kare::yeni(w, h, veri).arc());
                    sonraki += aralik;
                    let simdi = Instant::now();
                    if sonraki > simdi {
                        std::thread::sleep(sonraki - simdi);
                    } else if simdi - sonraki > aralik * 4 {
                        sonraki = simdi; // çok geride kaldı: saati eşitle
                    }
                }
            })
            .map_err(|e| format!("Video açılamadı: {e}"))?;
        log::info!("Video açıldı: {yol} ({w}×{h})");
        Ok(Acik { yol: yol.to_string(), boyut: (w, h), cocuk, calis })
    }

    fn durdur(mut a: Acik) {
        a.calis.store(false, Ordering::Relaxed);
        let _ = a.cocuk.kill();
        let _ = a.cocuk.wait();
    }

    pub fn acik_mi(&self) -> bool {
        self.acik.lock().unwrap().is_some()
    }

    /// Bir süredir kare istenmediyse FFmpeg'i kapatır (bekleme videosu artık seçili değilse).
    pub fn kapat(&self) {
        if let Some(a) = self.acik.lock().unwrap().take() {
            Self::durdur(a);
        }
        *self.ortak.son.lock().unwrap() = None;
    }
}

impl Drop for VideoOynatici {
    fn drop(&mut self) {
        self.kapat();
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn olmayan_dosya_hata_verir() {
        let v = VideoOynatici::yeni(30);
        assert!(v.kare("/yok/boyle/bir/video.mp4", 64, 36).is_none());
        assert!(v.hata().contains("bulunamadı"));
        assert!(!v.acik_mi());
    }

    /// FFmpeg varsa (geliştirme: RIZEON_GELISTIRME=1) küçük bir test videosu oynatılır.
    #[test]
    fn video_oynar_ve_doner() {
        let Some(ff) = crate::ffmpeg::ffmpeg_bul() else { return };
        let klasor = std::env::temp_dir().join(format!("rizeon_video_{}", std::process::id()));
        std::fs::create_dir_all(&klasor).unwrap();
        let yol = klasor.join("deneme.mp4");
        let ok = crate::ffmpeg::komut(&ff)
            .args(["-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=160x120:d=0.5:r=30", "-pix_fmt", "yuv420p"])
            .arg(&yol)
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !ok {
            return;
        }
        let v = VideoOynatici::yeni(30);
        let yol = yol.to_string_lossy().to_string();
        let k = v.kare(&yol, 64, 36).expect("ilk kare");
        assert_eq!(k.boyut(), (64, 36));
        // 4:3 video 16:9 çıkışa sığdırılır: kenarlar siyah, orta kırmızı (BGRA)
        assert_eq!(&k.veri[0..3], &[0, 0, 0]);
        let orta = ((18 * 64 + 32) * 4) as usize;
        assert!(k.veri[orta + 2] > 200 && k.veri[orta] < 50, "orta kırmızı olmalı: {:?}", &k.veri[orta..orta + 4]);
        // video 0,5 sn; 1 sn sonra hâlâ kare gelmeli (döngü)
        std::thread::sleep(Duration::from_millis(1000));
        let k2 = v.kare(&yol, 64, 36).unwrap();
        assert!(!Arc::ptr_eq(&k, &k2));
        assert!(v.hata().is_empty(), "{}", v.hata());
        v.kapat();
        let _ = std::fs::remove_dir_all(&klasor);
    }
}
