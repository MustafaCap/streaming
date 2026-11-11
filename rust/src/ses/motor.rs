//! Ses motoru (Python core/audio_engine.py): cihazları açar, mikserle bağlar, koparsa yeniden bağlanır.
//!
//!   Mikrofon (seçilen cihaz)                       ┐
//!   Bilgisayar sesi (uygulama bazlı ya da hoparlör) ├─> Karistirici ─> "CABLE Input" (VB-Cable)
//!
//! - Windows'un varsayılan mikrofonuna güvenme: CABLE ise kendi sesimizi geri alırız. CABLE asla mikrofon olmaz.
//! - Bilgisayar sesinde Zoom/Discord hariç tutulur, karşı taraf yankı duymaz.
//! Denetçi saniyede bir her şeyi kontrol eder; cihaz çıkarılırsa çökmez, yeniden bağlanır.

use crate::dil::t;
use crate::trf;
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use super::karistirici::Karistirici;
use super::surec_sesi;
use super::wasapi::{self, kablo_mu, Akis};
use super::ORNEKLEME;
use crate::durum::DurumDeposu;

pub const KABLO_ADI: &str = "CABLE Input";
pub const VARSAYILAN_HARIC: &[&str] = &["Zoom.exe", "Discord.exe", "ms-teams.exe", "Teams.exe", "Skype.exe"];

#[derive(Clone, Debug, PartialEq)]
pub struct MotorAyari {
    pub mikrofon_adi: String,
    /// "auto" | "all" | "app"
    pub sistem_modu: String,
    pub haric_uygulamalar: Vec<String>,
    pub dahil_uygulama: String,
}

struct Ic {
    depo: DurumDeposu,
    mikser: Arc<Mutex<Karistirici>>,
    ayar: Mutex<MotorAyari>,
    yayin_istek: AtomicBool,
    kayit_istek: AtomicBool,
    calis: AtomicBool,
    yeniden: AtomicBool,
    cihaz_listesi: Mutex<Vec<String>>,
    /// mikrofon sesine gürültü azaltma uygulansın mı
    gurultu: Arc<AtomicBool>,
}

pub struct SesMotoru {
    ic: Arc<Ic>,
    is: Mutex<Option<JoinHandle<()>>>,
}

impl SesMotoru {
    pub fn yeni(depo: DurumDeposu, mikser: Arc<Mutex<Karistirici>>, ayar: MotorAyari) -> Self {
        let mut ayar = ayar;
        if !matches!(ayar.sistem_modu.as_str(), "auto" | "all" | "app") {
            ayar.sistem_modu = "auto".into();
        }
        SesMotoru {
            ic: Arc::new(Ic {
                depo,
                mikser,
                ayar: Mutex::new(ayar),
                yayin_istek: AtomicBool::new(false),
                kayit_istek: AtomicBool::new(false),
                calis: AtomicBool::new(false),
                yeniden: AtomicBool::new(false),
                cihaz_listesi: Default::default(),
                gurultu: Arc::new(AtomicBool::new(false)),
            }),
            is: Mutex::new(None),
        }
    }

    pub fn baslat(&self) {
        let mut g = self.is.lock().unwrap();
        if g.is_some() {
            return;
        }
        self.ic.calis.store(true, Ordering::SeqCst);
        let ic = self.ic.clone();
        *g = std::thread::Builder::new().name("ses-denetci".into()).spawn(move || Denetci::new(ic).calistir()).ok();
    }

    pub fn durdur(&self) {
        self.ic.yayin_istek.store(false, Ordering::SeqCst);
        self.ic.kayit_istek.store(false, Ordering::SeqCst);
        self.ic.calis.store(false, Ordering::SeqCst);
        if let Some(is) = self.is.lock().unwrap().take() {
            let bitis = Instant::now() + Duration::from_secs(5);
            while !is.is_finished() && Instant::now() < bitis {
                std::thread::sleep(Duration::from_millis(20));
            }
        }
        self.ic.depo.guncelle(|d| d.sanal_mikrofon = "kapalı".into());
    }

    /// Sesi VB-Cable'a göndermeye başla/durdur.
    pub fn ac(&self, acik: bool) {
        self.ic.yayin_istek.store(acik, Ordering::SeqCst);
    }
    /// Yerel kayıt sürerken ses cihazları yayın kapalı olsa da açık kalır.
    pub fn kayit_icin_ac(&self, acik: bool) {
        self.ic.kayit_istek.store(acik, Ordering::SeqCst);
    }
    pub fn istek(&self) -> bool {
        self.ic.yayin_istek.load(Ordering::Relaxed) || self.ic.kayit_istek.load(Ordering::Relaxed)
    }

    pub fn mikrofon_sec(&self, ad: &str) {
        self.ic.ayar.lock().unwrap().mikrofon_adi = ad.into();
        self.ic.yeniden.store(true, Ordering::SeqCst);
    }

    pub fn sistem_ayarla(&self, modu: &str, dahil: Option<&str>) {
        let mut a = self.ic.ayar.lock().unwrap();
        a.sistem_modu = if matches!(modu, "auto" | "all" | "app") { modu.into() } else { "auto".into() };
        if let Some(d) = dahil {
            a.dahil_uygulama = d.into();
        }
        self.ic.yeniden.store(true, Ordering::SeqCst);
    }

    /// Ayarlar penceresinden: değiştiyse cihazlar yeniden açılır.
    pub fn ayar_degistir(&self, yeni: MotorAyari) {
        let mut a = self.ic.ayar.lock().unwrap();
        if *a != yeni {
            *a = yeni;
            self.ic.yeniden.store(true, Ordering::SeqCst);
        }
    }

    /// Gürültü azaltmayı aç/kapat (mikrofon yeniden açılmadan, bir sonraki blokta geçerli).
    pub fn gurultu_ayarla(&self, acik: bool) {
        self.ic.gurultu.store(acik, Ordering::SeqCst);
    }

    pub fn gurultu_acik(&self) -> bool {
        self.ic.gurultu.load(Ordering::Relaxed)
    }

    pub fn yenile(&self) {
        self.ic.yeniden.store(true, Ordering::SeqCst);
    }

    /// Seçilebilir mikrofonlar (CABLE hariç).
    pub fn mikrofonlar(&self) -> Vec<String> {
        self.ic.cihaz_listesi.lock().unwrap().clone()
    }
}

impl Drop for SesMotoru {
    fn drop(&mut self) {
        self.durdur();
    }
}

struct Denetci {
    ic: Arc<Ic>,
    kablo: Option<Akis>,
    mik: Option<Akis>,
    hoparlor: Option<Akis>,
    surec: Option<(Akis, (u32, bool))>,
    surecler: HashMap<u32, Akis>,
    basarisiz: HashSet<u32>,
    mik_son_deneme: Option<Instant>,
    surec_kontrol: Option<Instant>,
    oturum_kontrol: Option<Instant>,
    coklu_kullanilamaz: bool,
    sistem_modu: String,
    acik_gosterildi: bool,
    /// Uygulama bazlı yakalama (process loopback) önceki açılışta uygulamayı çökertmiş: bu sürümde
    /// hoparlör loopback kullanılır. Bkz. `kilit_yolu`.
    surec_sesi_yasak: bool,
    kilit_zamani: Option<Instant>,
}

/// Uygulama bazlı ses yakalama ilk kez kurulurken bir kilit dosyası yazılır; 60 sn sorunsuz
/// çalışınca silinir. Uygulama bu arada çökerse (Rust panik değil, Windows tarafında çökme:
/// log'a hiçbir şey düşmez) bir sonraki açılışta dosya durur ve bu sürüm için hoparlör loopback'e
/// geçilir (aynı derleme için). Böylece kullanıcı açılamayan bir uygulamayla kalmaz.
fn kilit_yolu() -> std::path::PathBuf {
    crate::yollar::log_klasoru().join("uygulama_sesi.kilit")
}

/// Kilit yalnızca aynı derlemede geçerli: yeni bir derleme uygulama bazlı yakalamayı yeniden dener.
fn kilit_icerigi() -> String {
    format!("{}-{}", crate::surum::SURUM, crate::surum::DERLEME)
}

static YASAK: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

/// Düzgün kapanış: bu açılış çökmediyse kilit silinir (60 sn dolmadan kapatılsa da).
pub fn temiz_cikis() {
    if !YASAK.load(Ordering::Relaxed) {
        let _ = std::fs::remove_file(kilit_yolu());
    }
}

fn surec_sesi_onceden_coktu_mu() -> bool {
    match std::fs::read_to_string(kilit_yolu()) {
        Ok(s) if s.trim() == kilit_icerigi() => true,
        Ok(_) => {
            let _ = std::fs::remove_file(kilit_yolu()); // başka bir derlemenin kilidi
            false
        }
        Err(_) => false,
    }
}

fn mikrofon_listesi() -> Vec<wasapi::Cihaz> {
    wasapi::cihazlar(true).into_iter().filter(|c| !kablo_mu(&c.ad)).collect()
}

impl Denetci {
    fn new(ic: Arc<Ic>) -> Self {
        let sistem_modu = ic.ayar.lock().unwrap().sistem_modu.clone();
        Denetci {
            ic,
            kablo: None,
            mik: None,
            hoparlor: None,
            surec: None,
            surecler: HashMap::new(),
            basarisiz: HashSet::new(),
            mik_son_deneme: None,
            surec_kontrol: None,
            oturum_kontrol: None,
            coklu_kullanilamaz: false,
            sistem_modu,
            acik_gosterildi: false,
            surec_sesi_yasak: {
                let y = surec_sesi_onceden_coktu_mu();
                YASAK.store(y, Ordering::Relaxed);
                if y {
                    log::warn!("Uygulama bazlı ses yakalama önceki açılışta uygulamayı kapattı; bu sürümde hoparlör loopback kullanılıyor (yeni derleme yeniden dener)");
                }
                y
            },
            kilit_zamani: None,
        }
    }

    fn istek(&self) -> bool {
        self.ic.yayin_istek.load(Ordering::Relaxed) || self.ic.kayit_istek.load(Ordering::Relaxed)
    }

    fn calistir(mut self) {
        crate::win::com_baslat();
        self.listeyi_yenile();
        while self.ic.calis.load(Ordering::Relaxed) {
            if self.ic.yeniden.swap(false, Ordering::SeqCst) {
                self.hepsini_kapat();
                self.sistem_modu = self.ic.ayar.lock().unwrap().sistem_modu.clone();
                self.listeyi_yenile();
            }
            if self.istek() {
                self.isle();
            } else if self.kablo.is_some() || self.mik.is_some() || self.surec.is_some() || self.hoparlor.is_some() || !self.surecler.is_empty() {
                self.hepsini_kapat();
                self.ic.depo.guncelle(|d| d.sanal_mikrofon = "kapalı".into());
            }
            // 1 sn bekle; ayar değişirse hemen uyan
            for _ in 0..20 {
                if !self.ic.calis.load(Ordering::Relaxed) || self.ic.yeniden.load(Ordering::Relaxed) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
        }
        self.hepsini_kapat();
    }

    fn listeyi_yenile(&self) {
        *self.ic.cihaz_listesi.lock().unwrap() = mikrofon_listesi().into_iter().map(|c| c.ad).collect();
    }

    fn isle(&mut self) {
        let kablo_koptu = self.kablo.as_ref().is_some_and(|a| !a.saglikli(Duration::from_millis(1500)));
        let mik_koptu = self.mik.as_ref().is_some_and(|a| !a.saglikli(Duration::from_millis(1500)));
        if kablo_koptu || mik_koptu {
            log::warn!("Ses cihazı koptu; yeniden bağlanılıyor");
            self.hepsini_kapat();
        }
        // Hoparlör sessizken Windows hiç veri vermeyebilir; sadece akış durduysa kopmuş say.
        if self.hoparlor.as_ref().is_some_and(|a| !a.calisiyor()) {
            self.hoparlor = None;
            self.sistem_durumu("yok", t("Hoparlör sesi koptu"));
        }
        if self.surec.as_ref().is_some_and(|(a, _)| !a.calisiyor()) {
            self.surec = None;
        }
        if self.kablo.is_none() && !self.kabloyu_ac() {
            self.hepsini_kapat();
            std::thread::sleep(Duration::from_secs(4)); // VB-Cable kurulana kadar çok sık deneme
            return;
        }
        if self.mik.is_none() && self.mik_son_deneme.is_none_or(|t| t.elapsed() >= Duration::from_secs(5)) {
            self.mikrofonu_ac();
        }
        self.sistem_sesini_ayarla();
    }

    fn kabloyu_ac(&mut self) -> bool {
        let Some(kablo) = wasapi::cihazlar(false).into_iter().find(|c| c.ad.to_lowercase().contains(&KABLO_ADI.to_lowercase())) else {
            self.ic.depo.guncelle(|d| {
                d.sanal_mikrofon = "yok".into();
                d.ses_hatasi = t("VB-Cable bulunamadı. vb-audio.com/Cable'dan kurup bilgisayarı yeniden başlat.").into();
            });
            return false;
        };
        let mikser = self.ic.mikser.clone();
        match wasapi::cal(&kablo.kimlik, move |n, blok| {
            let mut m = mikser.lock().unwrap();
            blok.extend_from_slice(m.karistir(n));
        }) {
            Ok(a) => {
                log::info!("Ses çıkışı: {}", kablo.ad);
                self.kablo = Some(a);
                self.ic.depo.guncelle(|d| {
                    d.sanal_mikrofon = "açık".into();
                    d.ses_hatasi.clear();
                });
                true
            }
            Err(e) => {
                log::warn!("CABLE Input açılamadı: {e}");
                self.ic.depo.guncelle(|d| {
                    d.sanal_mikrofon = "hata".into();
                    d.ses_hatasi = trf!("VB-Cable açılamadı: {}", e);
                });
                false
            }
        }
    }

    fn mikrofon_cihazi(&self) -> Result<wasapi::Cihaz, String> {
        let liste = mikrofon_listesi();
        let ad = self.ic.ayar.lock().unwrap().mikrofon_adi.clone();
        if !ad.is_empty() {
            if kablo_mu(&ad) {
                return Err(t("CABLE mikrofon olarak seçilemez (kendi sesini geri alır). Gerçek mikrofonu seç.").into());
            }
            // Python sürümü MME adlarını (31 karakter) saklıyordu: başı tutan da kabul
            let kisa: String = ad.chars().take(31).collect();
            return liste.into_iter().find(|c| c.ad == ad || c.ad.starts_with(&kisa)).ok_or_else(|| trf!("'{}' bulunamadı", ad));
        }
        if let Some(v) = wasapi::varsayilan(true).filter(|v| !kablo_mu(&v.ad)) {
            return Ok(v);
        }
        liste.into_iter().next().ok_or_else(|| t("Mikrofon bulunamadı").into())
    }

    fn mikrofonu_ac(&mut self) {
        self.mik_son_deneme = Some(Instant::now());
        let cihaz = match self.mikrofon_cihazi() {
            Ok(c) => c,
            Err(h) => {
                self.kanal_bagli("mikrofon", false);
                self.ic.depo.guncelle(|d| {
                    d.mikrofon = "yok".into();
                    d.mikrofon_adi.clear();
                    d.ses_hatasi = h;
                });
                return;
            }
        };
        {
            let mut m = self.ic.mikser.lock().unwrap();
            if let Some(k) = m.kanal("mikrofon") {
                k.tampon("", ORNEKLEME).temizle();
            }
        }
        let mikser = self.ic.mikser.clone();
        let gurultu_acik = self.ic.gurultu.clone();
        let mut gurultu: Option<super::gurultu::GurultuAzaltici> = None;
        match wasapi::cihaz_yakala(&cihaz.kimlik, false, move |blok| {
            // Gürültü azaltma mikser kilidinin dışında (10 ms ses için ~0,1 ms)
            let temiz;
            let blok = if gurultu_acik.load(Ordering::Relaxed) {
                temiz = gurultu.get_or_insert_with(Default::default).isle(blok, 2);
                &temiz[..]
            } else {
                gurultu = None;
                blok
            };
            if let Some(k) = mikser.lock().unwrap().kanal("mikrofon") {
                k.tampon("", ORNEKLEME).yaz(blok, 2);
            }
        }) {
            Ok(a) => {
                self.mik = Some(a);
                self.kanal_bagli("mikrofon", true);
                log::info!("Mikrofon: {}", cihaz.ad);
                self.ic.depo.guncelle(|d| {
                    d.mikrofon = "açık".into();
                    d.mikrofon_adi = cihaz.ad.clone();
                });
            }
            Err(e) => {
                log::warn!("Mikrofon açılamadı: {e}");
                self.kanal_bagli("mikrofon", false);
                self.ic.depo.guncelle(|d| {
                    d.mikrofon = "yok".into();
                    d.mikrofon_adi.clear();
                    d.ses_hatasi = trf!("Mikrofon açılamadı: {}", e);
                });
            }
        }
    }

    fn kanal_bagli(&self, anahtar: &str, bagli: bool) {
        if let Some(k) = self.ic.mikser.lock().unwrap().kanal(anahtar) {
            k.bagli = bagli;
        }
    }

    fn sistem_durumu(&self, durum: &str, aciklama: &str) {
        self.ic.depo.guncelle(|d| {
            d.sistem_sesi = durum.into();
            d.sistem_kaynagi = aciklama.into();
        });
    }

    fn sistem_yazici(&self, anahtar: String) -> impl FnMut(&[f32]) + Send + 'static {
        let mikser = self.ic.mikser.clone();
        move |blok| {
            if let Some(k) = mikser.lock().unwrap().kanal("sistem") {
                k.tampon(&anahtar, ORNEKLEME).yaz(blok, 2);
            }
        }
    }

    fn coklu_durdur(&mut self) {
        let pidler: Vec<u32> = self.surecler.keys().copied().collect();
        self.surecler.clear();
        let mut m = self.ic.mikser.lock().unwrap();
        if let Some(k) = m.kanal("sistem") {
            for p in pidler {
                k.tamponlar.remove(&p.to_string());
            }
        }
    }

    fn sistem_sesini_ayarla(&mut self) {
        if let Some(t) = self.kilit_zamani {
            if t.elapsed() > Duration::from_secs(60) {
                let _ = std::fs::remove_file(kilit_yolu());
                self.kilit_zamani = None;
                log::info!("Uygulama bazlı ses yakalama sorunsuz çalışıyor");
            }
        }
        if self.sistem_modu == "all" || self.surec_sesi_yasak {
            self.surec = None;
            self.coklu_durdur();
            if self.hoparlor.is_none() {
                self.hoparlor_loopback_ac();
            }
            return;
        }
        self.hoparlor = None;
        if self.sistem_modu == "auto" && self.coklu_ayarla() {
            return;
        }
        self.coklu_durdur();
        if self.surec.is_some() && self.surec_kontrol.is_some_and(|t| t.elapsed() < Duration::from_secs(3)) {
            return;
        }
        self.surec_kontrol = Some(Instant::now());
        let ayar = self.ic.ayar.lock().unwrap().clone();
        let (hedef, aciklama): (Option<(u32, bool)>, String) = if self.sistem_modu == "app" {
            if ayar.dahil_uygulama.is_empty() {
                (None, t("Uygulama seçilmedi").into())
            } else {
                match surec_sesi::surec_bul(&ayar.dahil_uygulama, &surec_sesi::surec_tablosu()) {
                    Some(p) => (Some((p, false)), trf!("Sadece {}", ayar.dahil_uygulama)),
                    None => (None, trf!("{} çalışmıyor", ayar.dahil_uygulama)),
                }
            }
        } else {
            // Kendimizi hariç tutarız: VB-Cable'a giden sesimiz geri gelmesin.
            (Some((std::process::id(), true)), t("Tüm bilgisayar sesi").into())
        };
        if hedef.is_some() && self.surec.as_ref().map(|(_, h)| *h) == hedef {
            return;
        }
        self.surec = None;
        let Some((pid, haric)) = hedef else {
            self.kanal_bagli("sistem", false);
            self.sistem_durumu("yok", &aciklama);
            return;
        };
        self.kilit_yaz();
        match surec_sesi::surec_yakala(pid, haric, self.sistem_yazici(String::new())) {
            Ok(a) => {
                self.surec = Some((a, (pid, haric)));
                self.kanal_bagli("sistem", true);
                self.sistem_durumu("açık", &aciklama);
            }
            Err(e) => {
                log::warn!("{e}; hoparlör loopback kullanılacak");
                self.sistem_modu = "all".into();
                self.hoparlor_loopback_ac();
            }
        }
    }

    /// Bu açılışta ilk uygulama bazlı yakalamadan önce kilit yazılır (bkz. kilit_yolu).
    fn kilit_yaz(&mut self) {
        if self.kilit_zamani.is_none() && std::fs::metadata(kilit_yolu()).is_err() {
            let _ = std::fs::write(kilit_yolu(), kilit_icerigi());
            self.kilit_zamani = Some(Instant::now());
        }
    }

    /// "auto": ses çıkaran her uygulamayı ayrı yakala (Zoom/Discord ve kendimiz hariç).
    fn coklu_ayarla(&mut self) -> bool {
        if self.coklu_kullanilamaz {
            return false;
        }
        if self.oturum_kontrol.is_some_and(|t| t.elapsed() < Duration::from_secs(2)) {
            return true;
        }
        self.oturum_kontrol = Some(Instant::now());
        let tablo = surec_sesi::surec_tablosu();
        let haric = self.ic.ayar.lock().unwrap().haric_uygulamalar.clone();
        let pidler = match surec_sesi::ses_oturumu_pidleri() {
            Ok(p) => p,
            Err(e) => {
                log::warn!("Ses çıkaran uygulamalar listelenemedi ({e}); tek yakalama kullanılacak");
                self.coklu_kullanilamaz = true;
                return false;
            }
        };
        let hedefler = surec_sesi::yakalanacak_surecler(&pidler, &haric, std::process::id(), &tablo);
        self.surec = None;
        let bitenler: Vec<u32> = self.surecler.iter().filter(|(p, a)| !hedefler.contains(p) || !a.calisiyor()).map(|(p, _)| *p).collect();
        for p in bitenler {
            self.surecler.remove(&p);
            if let Some(k) = self.ic.mikser.lock().unwrap().kanal("sistem") {
                k.tamponlar.remove(&p.to_string());
            }
        }
        let mut yeniler: Vec<u32> = hedefler.iter().filter(|p| !self.surecler.contains_key(p) && !self.basarisiz.contains(p)).copied().collect();
        yeniler.sort();
        if !yeniler.is_empty() {
            self.kilit_yaz();
        }
        for p in yeniler {
            match surec_sesi::surec_yakala(p, false, self.sistem_yazici(p.to_string())) {
                Ok(a) => {
                    self.surecler.insert(p, a);
                }
                Err(_) => {
                    self.basarisiz.insert(p);
                    if let Some(k) = self.ic.mikser.lock().unwrap().kanal("sistem") {
                        k.tamponlar.remove(&p.to_string());
                    }
                }
            }
        }
        self.kanal_bagli("sistem", true);
        let ad = |p: &u32| tablo.get(p).map(|(_, a)| a.trim_end_matches(".exe").to_string()).unwrap_or("?".into());
        let mut adlar: Vec<String> = self.surecler.keys().map(ad).collect();
        adlar.sort();
        adlar.dedup();
        let haric_k: HashSet<String> = haric.iter().map(|h| h.to_lowercase()).collect();
        let mut calisan_haric: Vec<String> =
            tablo.values().filter(|(_, a)| haric_k.contains(a)).map(|(_, a)| a.trim_end_matches(".exe").to_string()).collect();
        calisan_haric.sort();
        calisan_haric.dedup();
        let mut aciklama = if adlar.is_empty() { t("Ses çıkaran uygulama yok").to_string() } else { adlar.join(", ") };
        if !calisan_haric.is_empty() {
            aciklama += &trf!(" ({} hariç)", calisan_haric.join(", "));
        }
        self.sistem_durumu("açık", &aciklama);
        if !self.acik_gosterildi {
            self.acik_gosterildi = true;
        }
        true
    }

    fn hoparlor_loopback_ac(&mut self) {
        let Some(h) = wasapi::varsayilan(false) else {
            self.kanal_bagli("sistem", false);
            self.sistem_durumu("yok", t("Hoparlör bulunamadı"));
            return;
        };
        if kablo_mu(&h.ad) {
            self.kanal_bagli("sistem", false);
            self.sistem_durumu("yok", t("Windows'ta varsayılan hoparlör CABLE olmuş; gerçek hoparlörü seç"));
            return;
        }
        match wasapi::cihaz_yakala(&h.kimlik, true, self.sistem_yazici(String::new())) {
            Ok(a) => {
                self.hoparlor = Some(a);
                self.kanal_bagli("sistem", true);
                self.sistem_durumu("açık", t("Hoparlörden çıkan tüm ses"));
            }
            Err(e) => {
                self.kanal_bagli("sistem", false);
                self.sistem_durumu("yok", &trf!("Hoparlör sesi açılamadı: {}", e));
            }
        }
    }

    fn hepsini_kapat(&mut self) {
        self.kablo = None;
        self.mik = None;
        self.hoparlor = None;
        self.surec = None;
        self.coklu_durdur();
        self.basarisiz.clear();
        self.oturum_kontrol = None;
        self.coklu_kullanilamaz = false;
        self.mik_son_deneme = None; // tekrar açılınca mikrofon hemen denensin
        {
            let mut m = self.ic.mikser.lock().unwrap();
            for (_, k) in m.kanallar.iter_mut() {
                k.bagli = false;
            }
            m.sifirla();
        }
        self.ic.depo.guncelle(|d| {
            d.mikrofon = "kapalı".into();
            d.sistem_sesi = "kapalı".into();
            d.mikrofon_adi.clear();
            d.sistem_kaynagi.clear();
        });
    }
}
