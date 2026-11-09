//! Uygulamanın tek merkezi durumu (Python core/state.py). Arayüz buradan okur; her değişiklikte
//! `surum` artar, arayüz sadece değiştiyse yeniden çizer.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

#[derive(Clone, Debug, PartialEq)]
pub struct Durum {
    pub cikis_acik: bool,
    pub sanal_kamera: String, // kapalı | açık | yok | hata | koptu
    pub ekran_kaynagi: String,
    pub yakalama_yontemi: String,
    pub fps: f32,
    pub kare_suresi_ms: f32,
    pub son_hata: String,
    pub aktif_sahne: usize,
    pub sahne_adi: String,
    pub webcam: String,
    pub sanal_mikrofon: String,
    pub mikrofon: String,
    pub mikrofon_adi: String,
    pub mikrofon_sessiz: bool,
    pub sistem_sesi: String,
    pub sistem_kaynagi: String,
    pub sistem_sessiz: bool,
    pub ses_hatasi: String,
    pub bolge: String,
    pub kalem_acik: bool,
    pub panik: bool,
    pub kayit: String,
    pub kayit_suresi: u64,
    pub kayit_duraklatildi: bool,
    pub tekrar_acik: bool,
    pub kaynak_turu: String,
    pub kaynak_adi: String,
}

impl Default for Durum {
    fn default() -> Self {
        let k = || "kapalı".to_string();
        Durum {
            cikis_acik: false,
            sanal_kamera: k(),
            ekran_kaynagi: k(),
            yakalama_yontemi: String::new(),
            fps: 0.0,
            kare_suresi_ms: 0.0,
            son_hata: String::new(),
            aktif_sahne: 0,
            sahne_adi: String::new(),
            webcam: k(),
            sanal_mikrofon: k(),
            mikrofon: k(),
            mikrofon_adi: String::new(),
            mikrofon_sessiz: false,
            sistem_sesi: k(),
            sistem_kaynagi: String::new(),
            sistem_sessiz: false,
            ses_hatasi: String::new(),
            bolge: String::new(),
            kalem_acik: false,
            panik: false,
            kayit: k(),
            kayit_suresi: 0,
            kayit_duraklatildi: false,
            tekrar_acik: false,
            kaynak_turu: "ekran".into(),
            kaynak_adi: String::new(),
        }
    }
}

#[derive(Clone, Default)]
pub struct DurumDeposu {
    ic: Arc<(Mutex<Durum>, AtomicU64)>,
}

impl DurumDeposu {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn al(&self) -> Durum {
        self.ic.0.lock().unwrap().clone()
    }

    pub fn surum(&self) -> u64 {
        self.ic.1.load(Ordering::Relaxed)
    }

    /// Değişiklik yapar; gerçekten bir şey değiştiyse sürümü artırır.
    pub fn guncelle(&self, f: impl FnOnce(&mut Durum)) {
        let mut d = self.ic.0.lock().unwrap();
        let eski = d.clone();
        f(&mut d);
        if *d != eski {
            self.ic.1.fetch_add(1, Ordering::Relaxed);
        }
    }
}

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn degismeyince_surum_artmaz() {
        let d = DurumDeposu::new();
        d.guncelle(|x| x.fps = 30.0);
        let s = d.surum();
        d.guncelle(|x| x.fps = 30.0);
        assert_eq!(d.surum(), s);
        d.guncelle(|x| x.panik = true);
        assert_eq!(d.surum(), s + 1);
    }
}
