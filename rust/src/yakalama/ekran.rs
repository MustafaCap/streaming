//! Ekran yakalama (Python capture/screen.py). DXGI Masaüstü Çoğaltma (hızlı, GPU'dan) ile başlar;
//! açılamazsa GDI'ye geçer. Kaynak koparsa (monitör çıkarıldı, UAC ekranı) uygulama çökmez:
//! `grab` None döner ve birkaç saniyede bir yeniden denenir.
//!
//! Ekran değişmediyse bir önceki kare (aynı Arc) döner; video hattı bunu görüp ölçekleme ve
//! NV12 çevirmeyi tekrar yapmaz. Masaüstü dururken işlemcinin çoğu buradan kazanılır.

use std::time::{Duration, Instant};

use crate::kare::KareRef;

use super::Monitor;

pub trait Yakalayici: Send {
    fn ad(&self) -> &'static str;
    /// Son kare; ekran değişmediyse öncekiyle aynı Arc. Err: kaynak koptu.
    fn yakala(&mut self) -> Result<Option<KareRef>, String>;
}

pub struct EkranKaynagi {
    pub monitor: usize,
    pub tercih: String,
    yakalayici: Option<Box<dyn Yakalayici>>,
    son_deneme: Option<Instant>,
    pub son_hata: String,
    pub dikdortgen: Option<Monitor>,
}

const YENIDEN_DENEME: Duration = Duration::from_secs(2);

impl EkranKaynagi {
    pub fn yeni(monitor: usize, tercih: &str) -> Self {
        EkranKaynagi { monitor, tercih: tercih.into(), yakalayici: None, son_deneme: None, son_hata: String::new(), dikdortgen: None }
    }

    pub fn yontem(&self) -> &'static str {
        self.yakalayici.as_ref().map(|y| y.ad()).unwrap_or("")
    }

    fn ac(&mut self) {
        #[cfg(windows)]
        {
            let mons = super::monitorler();
            let m = mons.get(self.monitor).cloned().or_else(|| mons.first().cloned());
            self.dikdortgen = m.clone();
            let mut hatalar = vec![];
            let gdi_once = self.tercih == "mss" || self.tercih == "gdi";
            for gdi in [gdi_once, !gdi_once] {
                let sonuc: Result<Box<dyn Yakalayici>, String> = if gdi {
                    match &m {
                        Some(m) => Ok(Box::new(super::gdi::GdiYakalayici::yeni(m.clone()))),
                        None => Err("monitör yok".into()),
                    }
                } else {
                    super::dxgi::DxgiYakalayici::yeni(self.monitor).map(|d| Box::new(d) as Box<dyn Yakalayici>)
                };
                match sonuc {
                    Ok(y) => {
                        log::info!("Ekran yakalama başladı: {}, monitör {} {:?}", y.ad(), self.monitor, m);
                        self.yakalayici = Some(y);
                        self.son_hata.clear();
                        return;
                    }
                    Err(e) => hatalar.push(format!("{}: {e}", if gdi { "gdi" } else { "dxgi" })),
                }
            }
            self.son_hata = hatalar.join("; ");
            log::warn!("Ekran yakalanamıyor ({})", self.son_hata);
        }
        #[cfg(not(windows))]
        {
            self.son_hata = "Ekran yakalama sadece Windows'ta".into();
        }
    }

    /// BGRA kare ya da kaynak yoksa None. Asla panik yapmaz.
    pub fn grab(&mut self) -> Option<KareRef> {
        if self.yakalayici.is_none() {
            if self.son_deneme.is_some_and(|t| t.elapsed() < YENIDEN_DENEME) {
                return None;
            }
            self.son_deneme = Some(Instant::now());
            self.ac();
        }
        let y = self.yakalayici.as_mut()?;
        match y.yakala() {
            Ok(k) => k,
            Err(e) => {
                log::warn!("Ekran yakalama koptu ({}): {e}", y.ad());
                self.son_hata = e;
                self.kapat();
                None
            }
        }
    }

    /// Fare bu monitördeyse monitöre göre (x, y).
    pub fn imlec(&self) -> Option<(f32, f32)> {
        let m = self.dikdortgen.as_ref()?;
        #[cfg(windows)]
        let (fx, fy) = crate::win::fare_konumu()?;
        #[cfg(not(windows))]
        let (fx, fy): (i32, i32) = None?;
        let (x, y) = (fx - m.sol, fy - m.ust);
        (x >= 0 && y >= 0 && (x as u32) < m.w && (y as u32) < m.h).then_some((x as f32, y as f32))
    }

    pub fn kapat(&mut self) {
        self.yakalayici = None;
    }
}
