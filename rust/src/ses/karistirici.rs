//! Ses mikseri (Python core/audio_mixer.py): kaynakları karıştırıp VB-Cable'a gidecek bloğu üretir.
//!
//!   giriş cihazı -> Tampon::yaz()  (cihazın iş parçacığında)
//!   CABLE Input  <- Karistirici::karistir(n)  (çıkış iş parçacığında)

use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};

use super::{KANAL, ORNEKLEME};

/// Giriş geri çağrılarının yazdığı, çıkışın okuduğu tampon (stereo, iç içe f32).
///
/// Ön tampon: içeride 40 ms birikmeden okunmaz; boşalınca yeniden dolması beklenir (cızırtı olmasın).
/// 120 ms'den fazla dolarsa en eski ses atılır, gecikme büyümez (2.0.3 ses senkronu).
pub struct Tampon {
    pub giris_hizi: u32,
    veri: VecDeque<f32>,
    hazir: bool,
    pub alt_tasma: u64,
    son_ornek: [f32; 2],
    kesir: f64,
}

pub const ON_TAMPON_SN: f32 = 0.04;
pub const EN_FAZLA_SN: f32 = 0.12;

impl Tampon {
    pub fn new(giris_hizi: u32) -> Self {
        Tampon { giris_hizi, veri: VecDeque::new(), hazir: false, alt_tasma: 0, son_ornek: [0.0; 2], kesir: 0.0 }
    }

    pub fn temizle(&mut self) {
        self.veri.clear();
        self.hazir = false;
    }

    fn en_fazla() -> usize {
        (ORNEKLEME as f32 * EN_FAZLA_SN) as usize * KANAL
    }

    /// blok: iç içe örnekler, `kanal` kanallı, -1..1.
    pub fn yaz(&mut self, blok: &[f32], kanal: usize) {
        let kanal = kanal.max(1);
        let n = blok.len() / kanal;
        let stereo = |i: usize| -> [f32; 2] {
            let a = blok[i * kanal];
            let b = if kanal > 1 { blok[i * kanal + 1] } else { a };
            [a, b]
        };
        if self.giris_hizi == ORNEKLEME {
            for i in 0..n {
                self.veri.extend(stereo(i));
            }
        } else {
            // basit doğrusal örnekleme hızı dönüştürme (ör. 44100 -> 48000)
            let adim = self.giris_hizi as f64 / ORNEKLEME as f64;
            let mut t = self.kesir;
            while t < n as f64 {
                let i = t.floor() as usize;
                let f = (t - i as f64) as f32;
                let a = if i == 0 { self.son_ornek } else { stereo(i - 1) };
                let b = stereo(i);
                self.veri.push_back(a[0] + (b[0] - a[0]) * f);
                self.veri.push_back(a[1] + (b[1] - a[1]) * f);
                t += adim;
            }
            self.kesir = t - n as f64;
            if n > 0 {
                self.son_ornek = stereo(n - 1);
            }
        }
        let fazla = self.veri.len().saturating_sub(Self::en_fazla());
        self.veri.drain(..fazla);
    }

    /// n örneklik (stereo) blok okur, `cikis`a ekler (toplar). Ses yoksa hiçbir şey eklemez.
    pub fn oku_ekle(&mut self, cikis: &mut [f32], carpan: f32) -> bool {
        let gerek = cikis.len();
        if !self.hazir {
            if self.veri.len() < (ORNEKLEME as f32 * ON_TAMPON_SN) as usize * KANAL {
                return false;
            }
            self.hazir = true;
        }
        if self.veri.len() < gerek {
            self.alt_tasma += 1;
            self.hazir = false;
            return false;
        }
        for (c, v) in cikis.iter_mut().zip(self.veri.drain(..gerek)) {
            *c += v * carpan;
        }
        true
    }

    pub fn uzunluk(&self) -> usize {
        self.veri.len() / KANAL
    }
}

/// Mikserdeki bir satır: kaynak tampon(lar)ı, kazanç, susturma, seviye göstergesi.
pub struct Kanal {
    pub ad: String,
    /// Aynı kanala birden çok kaynak (ör. her uygulamanın sesi ayrı yakalanır).
    pub tamponlar: HashMap<String, Tampon>,
    kazanc: f32,
    pub sessiz: bool,
    pub bagli: bool,
    pub seviye: f32,
    pub carpan: f32,
    /// bas-konuş: tuş basılı değilken false
    pub kapi: bool,
}

impl Kanal {
    pub fn new(ad: &str, kazanc: f32, sessiz: bool) -> Self {
        let mut k = Kanal { ad: ad.into(), tamponlar: HashMap::new(), kazanc: 1.0, sessiz, bagli: false, seviye: 0.0, carpan: 1.0, kapi: true };
        k.kazanc_ayarla(kazanc);
        k.tamponlar.insert(String::new(), Tampon::new(ORNEKLEME));
        k
    }
    pub fn kazanc(&self) -> f32 {
        self.kazanc
    }
    pub fn kazanc_ayarla(&mut self, d: f32) {
        self.kazanc = d.clamp(0.0, 2.0);
    }
    pub fn tampon(&mut self, anahtar: &str, giris_hizi: u32) -> &mut Tampon {
        let t = self.tamponlar.entry(anahtar.to_string()).or_insert_with(|| Tampon::new(giris_hizi));
        if t.giris_hizi != giris_hizi {
            *t = Tampon::new(giris_hizi);
        }
        t
    }
}

pub type Dinleyici = Arc<dyn Fn(&[f32]) + Send + Sync>;

pub struct Karistirici {
    pub kanallar: Vec<(String, Kanal)>,
    pub cikis_seviyesi: f32,
    pub ana_sessiz: bool,
    pub kisma_acik: bool,
    pub kisma_seviyesi: f32,
    kisma: f32,
    sessizlik_sn: f32,
    pub konusuyor: bool,
    dinleyiciler: Vec<Dinleyici>,
    toplam: Vec<f32>,
    blok: Vec<f32>,
}

pub const KISMA_ESIK: f32 = 0.06;
pub const KISMA_BIRAKMA_SN: f32 = 0.6;

impl Default for Karistirici {
    fn default() -> Self {
        Self::new()
    }
}

impl Karistirici {
    pub fn new() -> Self {
        Karistirici {
            kanallar: vec![],
            cikis_seviyesi: 0.0,
            ana_sessiz: false,
            kisma_acik: false,
            kisma_seviyesi: 0.3,
            kisma: 1.0,
            sessizlik_sn: 99.0,
            konusuyor: false,
            dinleyiciler: vec![],
            toplam: vec![],
            blok: vec![],
        }
    }

    pub fn paylasilan() -> Arc<Mutex<Karistirici>> {
        Arc::new(Mutex::new(Self::new()))
    }

    pub fn kanal_ekle(&mut self, anahtar: &str, ad: &str, kazanc: f32, sessiz: bool) {
        self.kanallar.retain(|(a, _)| a != anahtar);
        self.kanallar.push((anahtar.into(), Kanal::new(ad, kazanc, sessiz)));
        // mikrofon önce: ses kısma kararı ona göre verilir
        self.kanallar.sort_by_key(|(a, _)| a != "mikrofon");
    }

    pub fn kanal(&mut self, anahtar: &str) -> Option<&mut Kanal> {
        self.kanallar.iter_mut().find(|(a, _)| a == anahtar).map(|(_, k)| k)
    }

    pub fn kanal_oku(&self, anahtar: &str) -> Option<&Kanal> {
        self.kanallar.iter().find(|(a, _)| a == anahtar).map(|(_, k)| k)
    }

    pub fn dinleyici_ekle(&mut self, f: Dinleyici) {
        self.dinleyiciler.push(f);
    }

    fn kisma_guncelle(&mut self, n: usize) {
        let mik = self.kanal_oku("mikrofon").map(|k| k.seviye).unwrap_or(0.0);
        self.konusuyor = mik > KISMA_ESIK;
        self.sessizlik_sn = if self.konusuyor { 0.0 } else { self.sessizlik_sn + n as f32 / ORNEKLEME as f32 };
        let hedef = if self.kisma_acik && self.sessizlik_sn < KISMA_BIRAKMA_SN { self.kisma_seviyesi } else { 1.0 };
        let adim = n as f32 / ORNEKLEME as f32;
        if hedef < self.kisma {
            self.kisma = hedef.max(self.kisma - adim / 0.08);
        } else {
            self.kisma = hedef.min(self.kisma + adim / 0.5);
        }
        let k = self.kisma;
        if let Some(s) = self.kanal("sistem") {
            s.carpan = k;
        }
    }

    /// n örneklik stereo blok üretir (iç içe, 2n değer). Dinleyicilere de aynısı gider.
    pub fn karistir(&mut self, n: usize) -> &[f32] {
        self.toplam.clear();
        self.toplam.resize(n * KANAL, 0.0);
        for i in 0..self.kanallar.len() {
            self.blok.clear();
            self.blok.resize(n * KANAL, 0.0);
            let (anahtar, k) = &mut self.kanallar[i];
            let susuk = k.sessiz || !k.bagli || !k.kapi;
            let carpan = k.kazanc * k.carpan;
            for t in k.tamponlar.values_mut() {
                t.oku_ekle(&mut self.blok, carpan); // sessizken de oku ki eski ses birikmesin
            }
            if susuk {
                k.seviye = 0.0;
            } else {
                k.seviye = self.blok.iter().fold(0.0f32, |m, v| m.max(v.abs()));
                for (t, b) in self.toplam.iter_mut().zip(self.blok.iter()) {
                    *t += b;
                }
            }
            if anahtar == "mikrofon" {
                self.kisma_guncelle(n);
            }
        }
        if self.ana_sessiz {
            self.cikis_seviyesi = 0.0;
            self.toplam.iter_mut().for_each(|v| *v = 0.0);
        } else {
            let tepe = self.toplam.iter().fold(0.0f32, |m, v| m.max(v.abs()));
            if tepe > 1.0 {
                self.toplam.iter_mut().for_each(|v| *v = v.clamp(-1.0, 1.0)); // basit sınırlayıcı
            }
            self.cikis_seviyesi = tepe.min(1.0);
        }
        for d in &self.dinleyiciler {
            d(&self.toplam);
        }
        &self.toplam
    }

    /// {"mikrofon": 0.3, "sistem": 0.1, "cikis": 0.35}
    pub fn seviyeler(&self) -> Vec<(String, f32)> {
        let mut v: Vec<(String, f32)> = self.kanallar.iter().map(|(a, k)| (a.clone(), k.seviye)).collect();
        v.push(("cikis".into(), self.cikis_seviyesi));
        v
    }

    pub fn sifirla(&mut self) {
        for (_, k) in self.kanallar.iter_mut() {
            k.tamponlar.values_mut().for_each(Tampon::temizle);
            k.seviye = 0.0;
        }
        self.cikis_seviyesi = 0.0;
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    fn mikser() -> Karistirici {
        let mut m = Karistirici::new();
        m.kanal_ekle("sistem", "Bilgisayar sesi", 1.0, false);
        m.kanal_ekle("mikrofon", "Mikrofon", 1.0, false);
        for (_, k) in m.kanallar.iter_mut() {
            k.bagli = true;
        }
        m
    }

    #[test]
    fn on_tampon_dolmadan_sessiz() {
        let mut m = mikser();
        m.kanal("mikrofon").unwrap().tampon("", ORNEKLEME).yaz(&[0.5; 480 * 2], 2);
        assert!(m.karistir(480).iter().all(|v| *v == 0.0));
        m.kanal("mikrofon").unwrap().tampon("", ORNEKLEME).yaz(&[0.5; 1440 * 2], 2);
        assert!((m.karistir(480)[0] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn gecikme_120ms_ile_sinirli() {
        let mut t = Tampon::new(ORNEKLEME);
        t.yaz(&vec![0.1; 48000 * 2], 2);
        assert_eq!(t.uzunluk(), 5760);
    }

    #[test]
    fn mono_ve_hiz_donusumu() {
        let mut t = Tampon::new(44100);
        t.yaz(&vec![0.2; 4410], 1);
        let n = t.uzunluk();
        assert!((4795..=4805).contains(&n), "{n}");
    }

    #[test]
    fn sinirlayici_ve_panik() {
        let mut m = mikser();
        for a in ["mikrofon", "sistem"] {
            m.kanal(a).unwrap().tampon("", ORNEKLEME).yaz(&[0.8; 4800], 2);
        }
        let b = m.karistir(480).to_vec();
        assert!(b.iter().all(|v| *v <= 1.0));
        assert_eq!(m.cikis_seviyesi, 1.0);
        m.ana_sessiz = true;
        assert!(m.karistir(480).iter().all(|v| *v == 0.0));
    }

    #[test]
    fn konusunca_sistem_kisilir() {
        let mut m = mikser();
        m.kisma_acik = true;
        for _ in 0..30 {
            m.kanal("mikrofon").unwrap().tampon("", ORNEKLEME).yaz(&[0.5; 960], 2);
            m.kanal("sistem").unwrap().tampon("", ORNEKLEME).yaz(&[0.5; 960], 2);
            m.karistir(480);
        }
        assert!((m.kanal_oku("sistem").unwrap().carpan - 0.3).abs() < 1e-3);
    }

    #[test]
    fn dinleyici_ayni_blogu_alir() {
        let mut m = mikser();
        let alinan = Arc::new(Mutex::new(0usize));
        let a = alinan.clone();
        m.dinleyici_ekle(Arc::new(move |b| *a.lock().unwrap() += b.len()));
        m.karistir(480);
        assert_eq!(*alinan.lock().unwrap(), 960);
    }
}
