//! Webcam kaynağı — Media Foundation (Python capture/webcam.py, orada OpenCV/DirectShow vardı).
//!
//! Kamera ayrı bir iş parçacığında okunur; video hattı her zaman en son kareyi alır, kamerayı beklemez.
//! Kamera çıkarılırsa çökmez: `son_kare` None döner, birkaç saniyede bir yeniden bağlanılır.
//! Kamera kapatılınca cihaz gerçekten bırakılır, kameranın ışığı söner.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use windows::core::{Interface, GUID, PWSTR};
use windows::Win32::Media::MediaFoundation::*;

use crate::kare::{Kare, KareRef};

const ILK_VIDEO: u32 = 0xFFFF_FFFC; // MF_SOURCE_READER_FIRST_VIDEO_STREAM
const YENIDEN_DENEME: Duration = Duration::from_secs(3);
const ESKI_KARE: Duration = Duration::from_secs(1);

fn mf_baslat() {
    static BASLADI: std::sync::Once = std::sync::Once::new();
    BASLADI.call_once(|| unsafe {
        crate::win::com_baslat();
        let _ = MFStartup(MF_VERSION, MFSTARTUP_FULL);
    });
}

unsafe fn cihazlar_ham() -> Vec<IMFActivate> {
    mf_baslat();
    let mut ozellik = None;
    if MFCreateAttributes(&mut ozellik, 1).is_err() {
        return vec![];
    }
    let Some(ozellik) = ozellik else { return vec![] };
    let _ = ozellik.SetGUID(&MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE, &MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID);
    let mut dizi: *mut Option<IMFActivate> = std::ptr::null_mut();
    let mut sayi = 0u32;
    if MFEnumDeviceSources(&ozellik, &mut dizi, &mut sayi).is_err() || dizi.is_null() {
        return vec![];
    }
    let l = std::slice::from_raw_parts_mut(dizi, sayi as usize).iter_mut().filter_map(Option::take).collect();
    windows::Win32::System::Com::CoTaskMemFree(Some(dizi as _));
    l
}

/// Bağlı kameraların adları (Ayarlar > Kamera listesi için).
pub fn kameralar() -> Vec<String> {
    unsafe {
        cihazlar_ham()
            .iter()
            .map(|a| {
                let mut p = PWSTR::null();
                let mut n = 0u32;
                if a.GetAllocatedString(&MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME, &mut p, &mut n).is_ok() {
                    let s = p.to_string().unwrap_or_default();
                    windows::Win32::System::Com::CoTaskMemFree(Some(p.0 as _));
                    s
                } else {
                    "Kamera".into()
                }
            })
            .collect()
    }
}

struct Okuyucu {
    kaynak: IMFMediaSource,
    okuyucu: IMFSourceReader,
    w: u32,
    h: u32,
}

impl Drop for Okuyucu {
    fn drop(&mut self) {
        unsafe {
            let _ = self.kaynak.Shutdown(); // cihaz bırakılır, ışık söner
        }
    }
}

fn boyut(t: &IMFMediaType) -> Option<(u32, u32)> {
    let v = unsafe { t.GetUINT64(&MF_MT_FRAME_SIZE).ok()? };
    Some(((v >> 32) as u32, v as u32))
}

fn fps(t: &IMFMediaType) -> f64 {
    let v = unsafe { t.GetUINT64(&MF_MT_FRAME_RATE).unwrap_or(0) };
    let (pay, payda) = ((v >> 32) as f64, (v as u32) as f64);
    if payda > 0.0 {
        pay / payda
    } else {
        0.0
    }
}

unsafe fn ac(cihaz: usize, ist_w: u32, ist_h: u32, ist_fps: u32) -> Result<Okuyucu, String> {
    let l = cihazlar_ham();
    let a = l.get(cihaz).ok_or_else(|| format!("{cihaz} numaralı kamera yok"))?;
    let kaynak: IMFMediaSource = a.ActivateObject().map_err(|e| e.to_string())?;
    let mut oz = None;
    MFCreateAttributes(&mut oz, 2).map_err(|e| e.to_string())?;
    let oz = oz.ok_or("öznitelik yok")?;
    let _ = oz.SetUINT32(&MF_SOURCE_READER_ENABLE_VIDEO_PROCESSING, 1);
    let okuyucu = MFCreateSourceReaderFromMediaSource(&kaynak, &oz).map_err(|e| {
        let _ = kaynak.Shutdown();
        e.to_string()
    })?;
    // İstenen boyuta (1280x720@30) en yakın yerel biçim
    let mut en_iyi: Option<(f64, IMFMediaType)> = None;
    let mut i = 0;
    while let Ok(t) = okuyucu.GetNativeMediaType(ILK_VIDEO, i) {
        i += 1;
        let Some((w, h)) = boyut(&t) else { continue };
        let f = fps(&t);
        let puan = (w as f64 - ist_w as f64).abs() + (h as f64 - ist_h as f64).abs() + (f - ist_fps as f64).abs() * 20.0
            + if f < 14.0 { 10_000.0 } else { 0.0 };
        if en_iyi.as_ref().is_none_or(|(p, _)| puan < *p) {
            en_iyi = Some((puan, t));
        }
    }
    if let Some((_, t)) = &en_iyi {
        let _ = okuyucu.SetCurrentMediaType(ILK_VIDEO, None, t);
    }
    let cikis = MFCreateMediaType().map_err(|e| e.to_string())?;
    cikis.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video).map_err(|e| e.to_string())?;
    cikis.SetGUID(&MF_MT_SUBTYPE, &MFVideoFormat_RGB32).map_err(|e| e.to_string())?;
    if let Some((_, t)) = &en_iyi {
        if let Ok(v) = t.GetUINT64(&MF_MT_FRAME_SIZE) {
            let _ = cikis.SetUINT64(&MF_MT_FRAME_SIZE, v);
        }
    }
    okuyucu.SetCurrentMediaType(ILK_VIDEO, None, &cikis).map_err(|e| format!("RGB32 biçimi ayarlanamadı: {e}"))?;
    let gercek = okuyucu.GetCurrentMediaType(ILK_VIDEO).map_err(|e| e.to_string())?;
    let (w, h) = boyut(&gercek).ok_or("kare boyutu bilinmiyor")?;
    Ok(Okuyucu { kaynak, okuyucu, w, h })
}

unsafe fn kare_oku(o: &Okuyucu, ayna: bool) -> Result<Option<Kare>, String> {
    let mut akis = 0u32;
    let mut bayrak = 0u32;
    let mut zaman = 0i64;
    let mut ornek: Option<IMFSample> = None;
    o.okuyucu
        .ReadSample(ILK_VIDEO, 0, Some(&mut akis), Some(&mut bayrak), Some(&mut zaman), Some(&mut ornek))
        .map_err(|e| e.to_string())?;
    if bayrak & (MF_SOURCE_READERF_ERROR.0 as u32 | MF_SOURCE_READERF_ENDOFSTREAM.0 as u32) != 0 {
        return Err("kamera akışı bitti".into());
    }
    let Some(ornek) = ornek else { return Ok(None) };
    let tampon = ornek.ConvertToContiguousBuffer().map_err(|e| e.to_string())?;
    let (w, h) = (o.w as usize, o.h as usize);
    let mut veri = vec![0u8; w * h * 4];
    let mut kopyala = |taban: *const u8, adim: isize| {
        for y in 0..h {
            let s = taban.offset(adim * y as isize);
            let satir = std::slice::from_raw_parts(s, w * 4);
            let hedef = &mut veri[y * w * 4..(y + 1) * w * 4];
            if ayna {
                for x in 0..w {
                    hedef[x * 4..x * 4 + 4].copy_from_slice(&satir[(w - 1 - x) * 4..(w - x) * 4]);
                }
            } else {
                hedef.copy_from_slice(satir);
            }
        }
    };
    if let Ok(b2) = tampon.cast::<IMF2DBuffer>() {
        let mut taban = std::ptr::null_mut();
        let mut adim = 0i32;
        b2.Lock2D(&mut taban, &mut adim).map_err(|e| e.to_string())?;
        kopyala(taban, adim as isize);
        let _ = b2.Unlock2D();
    } else {
        let mut taban = std::ptr::null_mut();
        let mut uzunluk = 0u32;
        tampon.Lock(&mut taban, None, Some(&mut uzunluk)).map_err(|e| e.to_string())?;
        if (uzunluk as usize) >= w * h * 4 {
            // RGB32 düz tampon alttan üste: son satırdan başla
            kopyala(taban.add((h - 1) * w * 4), -((w * 4) as isize));
        }
        let _ = tampon.Unlock();
    }
    for p in veri.chunks_exact_mut(4) {
        p[3] = 255;
    }
    Ok(Some(Kare::yeni(o.w, o.h, veri)))
}

#[derive(Default)]
struct Ortak {
    kare: Mutex<Option<(KareRef, Instant)>>,
    son_hata: Mutex<String>,
}

pub struct WebcamKaynagi {
    pub cihaz: usize,
    pub genislik: u32,
    pub yukseklik: u32,
    pub fps: u32,
    pub ayna: Arc<AtomicBool>,
    ortak: Arc<Ortak>,
    calis: Option<Arc<AtomicBool>>,
    is: Option<JoinHandle<()>>,
}

impl WebcamKaynagi {
    pub fn yeni(cihaz: usize, genislik: u32, yukseklik: u32, fps: u32, ayna: bool) -> Self {
        WebcamKaynagi {
            cihaz,
            genislik,
            yukseklik,
            fps,
            ayna: Arc::new(AtomicBool::new(ayna)),
            ortak: Default::default(),
            calis: None,
            is: None,
        }
    }

    /// Kullanıcı kamerayı açtı mı (cihaz bağlı olmasa bile).
    pub fn acik(&self) -> bool {
        self.calis.as_ref().is_some_and(|c| c.load(Ordering::Relaxed))
    }

    pub fn son_hata(&self) -> String {
        self.ortak.son_hata.lock().unwrap().clone()
    }

    pub fn baslat(&mut self) {
        if self.acik() {
            return;
        }
        if let Some(is) = self.is.take() {
            let bitis = Instant::now() + Duration::from_secs(3);
            while !is.is_finished() && Instant::now() < bitis {
                std::thread::sleep(Duration::from_millis(20));
            }
        }
        // Her iş parçacığının kendi bayrağı: eskisi takıldıysa yeni bayrağı görüp çalışmaya devam edemez.
        let calis = Arc::new(AtomicBool::new(true));
        self.calis = Some(calis.clone());
        let (ortak, ayna) = (self.ortak.clone(), self.ayna.clone());
        let (cihaz, w, h, f) = (self.cihaz, self.genislik, self.yukseklik, self.fps);
        self.is = std::thread::Builder::new()
            .name("webcam".into())
            .spawn(move || {
                crate::win::com_baslat();
                let bekle = |sn: Duration| {
                    let bitis = Instant::now() + sn;
                    while calis.load(Ordering::Relaxed) && Instant::now() < bitis {
                        std::thread::sleep(Duration::from_millis(50));
                    }
                };
                let mut okuyucu: Option<Okuyucu> = None;
                while calis.load(Ordering::Relaxed) {
                    if okuyucu.is_none() {
                        match unsafe { ac(cihaz, w, h, f) } {
                            Ok(o) => {
                                log::info!("Kamera açıldı: {cihaz} ({}x{})", o.w, o.h);
                                ortak.son_hata.lock().unwrap().clear();
                                okuyucu = Some(o);
                            }
                            Err(e) => {
                                let m = format!("{cihaz} numaralı kamera açılamadı");
                                log::warn!("{m}: {e} (Windows Ayarlar > Gizlilik > Kamera izni açık mı?)");
                                *ortak.son_hata.lock().unwrap() = m;
                                bekle(YENIDEN_DENEME);
                                continue;
                            }
                        }
                    }
                    match unsafe { kare_oku(okuyucu.as_ref().unwrap(), ayna.load(Ordering::Relaxed)) } {
                        Ok(Some(k)) => {
                            if calis.load(Ordering::Relaxed) {
                                *ortak.kare.lock().unwrap() = Some((k.arc(), Instant::now()));
                            }
                        }
                        Ok(None) => {}
                        Err(e) => {
                            log::warn!("Kameradan kare alınamadı ({e}), yeniden bağlanılacak");
                            okuyucu = None;
                            bekle(Duration::from_secs(1));
                        }
                    }
                }
                if okuyucu.take().is_some() {
                    log::info!("Kamera bırakıldı");
                }
            })
            .ok();
    }

    /// Kamerayı bırakır; `bekle` false iken video hattını bekletmez.
    pub fn durdur(&mut self, bekle: bool) {
        if let Some(c) = self.calis.take() {
            c.store(false, Ordering::SeqCst);
        }
        if bekle {
            if let Some(is) = self.is.take() {
                let bitis = Instant::now() + Duration::from_secs(3);
                while !is.is_finished() && Instant::now() < bitis {
                    std::thread::sleep(Duration::from_millis(20));
                }
            }
        }
        *self.ortak.kare.lock().unwrap() = None;
    }

    /// Son kare ya da kamera yoksa/kopmuşsa None.
    pub fn son_kare(&self) -> Option<KareRef> {
        if !self.acik() {
            return None;
        }
        let g = self.ortak.kare.lock().unwrap();
        g.as_ref().filter(|(_, t)| t.elapsed() < ESKI_KARE).map(|(k, _)| k.clone())
    }
}

impl Drop for WebcamKaynagi {
    fn drop(&mut self) {
        self.durdur(false);
    }
}

#[allow(dead_code)]
const _: GUID = GUID::zeroed();
