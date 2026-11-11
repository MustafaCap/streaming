//! Video hattı (Python core/video_pipeline.py): kaynak -> sahne -> çıkışlar, sabit FPS'te ayrı iş parçacığında.
//!
//!   1) aktif sahne ekran istiyorsa ekranı yakala, çıkış boyutuna sığdır (+ imleç)
//!   2) kamera istiyorsa webcam'in son karesini al
//!   3) sahneyi kur, sahne değiştiyse yumuşak geçiş
//!   4) sanal kameraya, kayda ve anlık tekrara gönder; son kareyi önizleme için sakla
//!
//! Arayüz bu iş parçacığını asla beklemez; `son_kare()` ile en son kareyi alır.
//! Sanal kamera arka planda hep açık (2.0.0); sürücü yoksa birkaç saniyede bir yeniden denenir.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use crate::durum::DurumDeposu;
use crate::kare::{self, Kare, KareRef};
use crate::kayit::Kayitci;
use crate::obs_kamera::ObsSanalKamera;
use crate::sahne::{self, KameraYerlesimi, SahneGirdisi, SahneYoneticisi};
use crate::tekrar::AnlikTekrar;
use crate::yakalama::ekran::EkranKaynagi;
use crate::yazi;

const CIKIS_YENIDEN_DENEME: Duration = Duration::from_secs(5);

#[derive(Clone, Debug)]
pub struct HatAyari {
    pub imlec_goster: bool,
    /// Eski genel ayar (video.cursor_highlight); sahnedeki "İmleç vurgusu" kaynağı da açar
    pub imlec_vurgusu: bool,
    pub bekleme_metni: String,
    pub bekleme_gorseli: String,
    pub yer: KameraYerlesimi,
    pub monitor: usize,
    pub yakalama: String,
    pub kamera_cihazi: usize,
    pub kamera_ayna: bool,
    pub kamera_bulanik: bool,
}

/// Arayüzün ve kısayolların hatla konuştuğu ortak kısım (iş parçacığı güvenli).
pub struct HatKontrol {
    pub depo: DurumDeposu,
    pub sahneler: Arc<SahneYoneticisi>,
    pub kayitci: Arc<Kayitci>,
    pub tekrar: Arc<AnlikTekrar>,
    pub genislik: u32,
    pub yukseklik: u32,
    pub fps: u32,
    pub cikis_istegi: AtomicBool,
    cikis_hemen: AtomicBool,
    pub kamera_istegi: AtomicBool,
    pub panik: AtomicBool,
    /// Ana pencere ya da mini bar açık mı; ikisi de kapalıysa (tepside) ve kayıt yoksa webcam'e dokunulmaz.
    pub onizleme_gorunur: AtomicBool,
    pub mini_gorunur: AtomicBool,
    /// Toplantı penceresi açık mı (açıkken kamera da kullanılıyor sayılır)
    pub toplanti_gorunur: AtomicBool,
    pub ayar: Mutex<HatAyari>,
    /// Sadece bir pencere gösteriliyorsa (hwnd, başlık); None: tüm ekran
    pub pencere: Mutex<Option<(isize, String)>>,
    /// Bölge seçme: yumuşak yakınlaştırma / vurgulama (monitöre oranla)
    pub bolge: crate::bolge::BolgeSecimi,
    /// Son ham kaynak karesinin boyutu (bölge seçerken ekran koordinatına çevirmek için)
    pub kaynak_boyutu: Mutex<(u32, u32)>,
    /// Kalem çizimleri (monitöre oranlı); ekran kaynağının üstüne çizilir
    pub cizim: Arc<crate::cizim::CizimDeposu>,
    son_kare: Mutex<KareRef>,
    calis: AtomicBool,
}

impl HatKontrol {
    pub fn son_kare(&self) -> KareRef {
        self.son_kare.lock().unwrap().clone()
    }

    pub fn cikisi_ayarla(&self, acik: bool) {
        self.cikis_istegi.store(acik, Ordering::SeqCst);
        self.cikis_hemen.store(true, Ordering::SeqCst);
    }

    pub fn kamerayi_ayarla(&self, acik: bool) {
        self.kamera_istegi.store(acik, Ordering::SeqCst);
    }

    pub fn kamera_sahnede(&self) -> bool {
        self.sahneler.aktif().kamera_var()
    }

    pub fn kamera_kullaniliyor(&self) -> bool {
        self.onizleme_gorunur.load(Ordering::Relaxed) || self.mini_gorunur.load(Ordering::Relaxed)
            || self.toplanti_gorunur.load(Ordering::Relaxed)
            || self.kayitci.kayitta()
    }
}

/// Görüntü kaynağı: tüm ekran ya da tek pencere.
enum Kaynak {
    Ekran(EkranKaynagi),
    #[cfg(windows)]
    Pencere(crate::yakalama::pencere::PencereKaynagi),
}

impl Kaynak {
    fn grab(&mut self) -> Option<KareRef> {
        match self {
            Kaynak::Ekran(e) => e.grab(),
            #[cfg(windows)]
            Kaynak::Pencere(p) => p.grab(),
        }
    }
    fn yontem(&self) -> &'static str {
        match self {
            Kaynak::Ekran(e) => e.yontem(),
            #[cfg(windows)]
            Kaynak::Pencere(p) => p.yontem(),
        }
    }
    fn imlec(&self) -> Option<(f32, f32)> {
        match self {
            Kaynak::Ekran(e) => e.imlec(),
            #[cfg(windows)]
            Kaynak::Pencere(p) => p.imlec(),
        }
    }
}

type KaynakAnahtari = (usize, String, Option<isize>);

struct EkranOnbellek {
    ham: KareRef,
    imza: (Option<(i32, i32)>, (bool, bool), u32, u32, [i64; 9], u64),
    cikis: KareRef,
}

/// Hattın kendi iş parçacığına ait olanlar.
struct Ic {
    k: Arc<HatKontrol>,
    kaynak: Kaynak,
    kaynak_ayari: KaynakAnahtari,
    #[cfg(windows)]
    kamera: Option<crate::yakalama::kamera::WebcamKaynagi>,
    cikis: Option<ObsSanalKamera>,
    cikis_sonraki: Option<Instant>,
    onbellek: Option<EkranOnbellek>,
    ek_kaynaklar: crate::ek_kaynaklar::EkKaynaklar,
    bekleme_videosu: Arc<crate::video_oynatici::VideoOynatici>,
    kare_sayaci: u64,
    vurgu: crate::imlec_vurgusu::ImlecVurgusu,
}

impl Ic {
    fn cikis_istegini_isle(&mut self) {
        let istek = self.k.cikis_istegi.load(Ordering::Relaxed);
        if istek == self.cikis.is_some() {
            return;
        }
        if !istek {
            self.cikis = None;
            self.k.depo.guncelle(|d| {
                d.cikis_acik = false;
                d.sanal_kamera = "kapalı".into();
            });
            return;
        }
        if self.k.cikis_hemen.swap(false, Ordering::SeqCst) {
            self.cikis_sonraki = None;
        }
        if self.cikis_sonraki.is_some_and(|t| Instant::now() < t) {
            return; // açılamadı; birkaç saniye sonra yeniden denenir (OBS sonradan kurulabilir)
        }
        match ObsSanalKamera::ac(self.k.genislik, self.k.yukseklik, self.k.fps as f64) {
            Ok(c) => {
                self.cikis = Some(c);
                self.k.depo.guncelle(|d| {
                    d.cikis_acik = true;
                    d.sanal_kamera = "açık".into();
                    d.son_hata.clear();
                });
            }
            Err(e) => {
                let yok = e.contains("bulunamadı");
                if self.k.depo.al().sanal_kamera != if yok { "yok" } else { "hata" } {
                    log::warn!("Sanal kamera açılamadı: {e}");
                }
                self.cikis_sonraki = Some(Instant::now() + CIKIS_YENIDEN_DENEME);
                self.k.depo.guncelle(|d| {
                    d.cikis_acik = false;
                    d.sanal_kamera = if yok { "yok" } else { "hata" }.into();
                    d.son_hata = e;
                });
            }
        }
    }

    fn sayac_kare(&mut self) -> u64 {
        self.kare_sayaci = self.kare_sayaci.wrapping_add(1);
        self.kare_sayaci
    }

    fn kaynak_ac(anahtar: &KaynakAnahtari) -> Kaynak {
        #[cfg(windows)]
        if let Some(h) = anahtar.2 {
            return Kaynak::Pencere(crate::yakalama::pencere::PencereKaynagi::yeni(h, ""));
        }
        Kaynak::Ekran(EkranKaynagi::yeni(anahtar.0, &anahtar.1))
    }

    fn ekran_karesi(&mut self, ayar: &HatAyari, sahne: &sahne::Sahne) -> Option<KareRef> {
        let pencere = self.k.pencere.lock().unwrap().clone();
        let anahtar: KaynakAnahtari = (ayar.monitor, ayar.yakalama.clone(), pencere.as_ref().map(|p| p.0));
        if self.kaynak_ayari != anahtar {
            self.kaynak = Self::kaynak_ac(&anahtar);
            #[cfg(windows)]
            if let (Kaynak::Pencere(p), Some((_, baslik))) = (&mut self.kaynak, &pencere) {
                p.baslik = baslik.clone();
            }
            self.kaynak_ayari = anahtar;
            self.onbellek = None;
        }
        let Some(ham) = self.kaynak.grab() else {
            self.k.depo.guncelle(|d| {
                d.ekran_kaynagi = "koptu".into();
                d.yakalama_yontemi.clear();
            });
            self.onbellek = None;
            return None;
        };
        *self.k.kaynak_boyutu.lock().unwrap() = (ham.w, ham.h);
        let yontem = self.kaynak.yontem();
        self.k.depo.guncelle(|d| {
            if d.ekran_kaynagi != "çalışıyor" || d.yakalama_yontemi != yontem {
                d.ekran_kaynagi = "çalışıyor".into();
                d.yakalama_yontemi = yontem.into();
            }
        });
        let (w, h) = (self.k.genislik, self.k.yukseklik);
        let gorunum = self.k.bolge.gorunum();
        let vurgu = ayar.imlec_vurgusu || sahne.imlec_vurgusu();
        let imlec_iste = ayar.imlec_goster || vurgu;
        let konum = if imlec_iste { self.kaynak.imlec() } else { None };
        if vurgu {
            self.vurgu.guncelle(konum);
        }
        let dalga = vurgu && self.vurgu.dalga_var();
        let bolge_imza = gorunum.imza();
        // Kalem: çizim yoksa hiçbir iş yapılmaz; varsa sürümü önbellek imzasına girer
        let ekran_modu = pencere.is_none();
        let cizimler = (ekran_modu && sahne.kalem() && !self.k.cizim.bos()).then(|| self.k.cizim.anlik());
        let cizim_surumu = match &cizimler {
            // lazer izi her karede solar: önbellek kullanılmasın
            Some((_, lazer, _)) if !lazer.is_empty() => u64::MAX - self.sayac_kare(),
            Some(_) => self.k.cizim.surum(),
            None => 0,
        };
        let imza = (konum.map(|(x, y)| (x as i32, y as i32)), (ayar.imlec_goster, vurgu), w, h, bolge_imza, cizim_surumu);
        if let Some(o) = &self.onbellek {
            if Arc::ptr_eq(&o.ham, &ham) && o.imza == imza && !dalga {
                return Some(o.cikis.clone()); // ekran ve fare yerinde: hiçbir iş yapılmaz
            }
        }
        let (mut cikis, (bx, by, olcek, dx, dy)) = if gorunum.tam_mi() {
            let (o, dx, dy) = kare::sigdir_donusumu(ham.w, ham.h, w, h);
            (kare::sigdir(&ham, w, h), (0.0, 0.0, o, dx as f64, dy as f64))
        } else {
            crate::bolge::uygula(&ham, &gorunum, w, h, self.k.bolge.karartma_gucu)
        };
        let donusum = |x: f64, y: f64| ((x - bx) * olcek + dx, (y - by) * olcek + dy);
        if let Some((sekiller, lazer, lazer_rengi)) = &cizimler {
            let (hw, hh) = (ham.w as f64, ham.h as f64);
            crate::cizim::ciz(
                &mut cikis,
                sekiller,
                lazer,
                *lazer_rengi,
                |x, y| {
                    let (a, b) = donusum(x as f64 * hw, y as f64 * hh);
                    (a as f32, b as f32)
                },
                (hh * olcek) as f32,
            );
        }
        if imlec_iste {
            let cikis_konumu = konum.map(|(x, y)| donusum(x as f64, y as f64)).filter(|&(cx, cy)| cx > -30.0 && cx < w as f64 && cy > -30.0 && cy < h as f64);
            if vurgu {
                let o = (olcek * ham.h as f64 / 1080.0).max(0.3) as f32;
                self.vurgu.ciz(&mut cikis, cikis_konumu.map(|(x, y)| (x as f32, y as f32)), donusum, o);
            }
            if let (true, Some((cx, cy))) = (ayar.imlec_goster, cikis_konumu) {
                kare::imlec_ciz(&mut cikis, cx as f32, cy as f32, 22.0);
            }
        }
        let cikis = cikis.arc();
        self.onbellek = Some(EkranOnbellek { ham, imza, cikis: cikis.clone() });
        Some(cikis)
    }

    #[cfg(windows)]
    fn kamera_karesi(&mut self, sahne: &sahne::Sahne, ayar: &HatAyari) -> Option<KareRef> {
        use crate::yakalama::kamera::WebcamKaynagi;
        let istek = self.k.kamera_istegi.load(Ordering::Relaxed);
        let gerekli = istek && sahne.kamera().is_some() && self.k.kamera_kullaniliyor();
        if self.kamera.as_ref().is_some_and(|c| c.cihaz != ayar.kamera_cihazi) {
            if let Some(mut c) = self.kamera.take() {
                c.durdur(false);
            }
        }
        let kam = self.kamera.get_or_insert_with(|| WebcamKaynagi::yeni(ayar.kamera_cihazi, 1280, 720, 30, ayar.kamera_ayna));
        kam.ayna.store(ayar.kamera_ayna, Ordering::Relaxed);
        kam.bulanik.store(ayar.kamera_bulanik, Ordering::Relaxed);
        if gerekli && !kam.acik() {
            kam.baslat();
        } else if !gerekli && kam.acik() {
            kam.durdur(false);
        }
        let durum = |s: &str| self.k.depo.guncelle(|d| d.webcam = s.into());
        if !istek {
            durum("kapalı");
            return None;
        }
        if !gerekli {
            durum("beklemede"); // açık istendi ama şu an kullanılmıyor: cihaz kapalı
            return None;
        }
        let kare = kam.son_kare();
        if kare.is_some() {
            durum("açık");
        } else if !kam.son_hata().is_empty() {
            durum("yok");
        }
        kare
    }

    #[cfg(not(windows))]
    fn kamera_karesi(&mut self, _s: &sahne::Sahne, _a: &HatAyari) -> Option<KareRef> {
        None
    }

    fn ek_kareler(&mut self, sahne: &sahne::Sahne) -> HashMap<String, KareRef> {
        let kamera = self.k.kamera_istegi.load(Ordering::Relaxed) && self.k.kamera_kullaniliyor();
        self.ek_kaynaklar.kareler(sahne, kamera)
    }

    fn kare_uret(&mut self) -> KareRef {
        let (w, h) = (self.k.genislik, self.k.yukseklik);
        let ayar = self.k.ayar.lock().unwrap().clone();
        // bekleme ekranı: video seçildiyse döngüde oynar, yoksa görsel ya da yazı
        let video = crate::yollar::video_mu(&ayar.bekleme_gorseli);
        if !video && self.bekleme_videosu.acik_mi() {
            self.bekleme_videosu.kapat();
        }
        let bekleme_videosu = self.bekleme_videosu.clone();
        let bekleme = || {
            if video {
                bekleme_videosu
                    .kare(&ayar.bekleme_gorseli, w, h)
                    .unwrap_or_else(|| yazi::bilgi_karesi(w, h, &ayar.bekleme_metni, None))
            } else {
                yazi::bekleme_karesi(w, h, &ayar.bekleme_metni, &ayar.bekleme_gorseli)
            }
        };
        if self.k.panik.load(Ordering::Relaxed) {
            // Panik: geçiş beklemeden bekleme ekranı; kamera(lar) da kapanır, ışığı sönsün
            #[cfg(windows)]
            if let Some(k) = self.kamera.as_mut() {
                if k.acik() {
                    k.durdur(false);
                    self.k.depo.guncelle(|d| d.webcam = "beklemede".into());
                }
            }
            self.ek_kaynaklar.kapat();
            return bekleme();
        }
        let sahne = self.k.sahneler.aktif();
        let indeks = self.k.sahneler.indeks();
        self.k.depo.guncelle(|d| {
            d.aktif_sahne = indeks;
            if d.sahne_adi != sahne.ad {
                d.sahne_adi = sahne.ad.clone();
            }
        });
        let ekran = if sahne.ekran() { self.ekran_karesi(&ayar, &sahne) } else { None };
        let kamera = self.kamera_karesi(&sahne, &ayar);
        let ek = self.ek_kareler(&sahne);
        let girdi = SahneGirdisi {
            ekran,
            kamera,
            kamera_acik: self.k.kamera_istegi.load(Ordering::Relaxed),
            yer: &ayar.yer,
            bekleme: &bekleme,
            ek: &ek,
        };
        let kare = sahne::sahne_karesi(&sahne, w, h, &girdi);
        let onceki = self.k.son_kare();
        self.k.sahneler.gecis_uygula(kare, Some(&onceki))
    }

    fn gonder(&mut self, kare: &Kare) {
        if let Some(c) = self.cikis.as_mut() {
            if let Err(e) = c.gonder(kare) {
                log::warn!("Sanal kamera koptu: {e}");
                self.cikis = None;
                self.cikis_sonraki = Some(Instant::now() + CIKIS_YENIDEN_DENEME);
                self.k.depo.guncelle(|d| {
                    d.cikis_acik = false;
                    d.sanal_kamera = "koptu".into();
                    d.son_hata = format!("Sanal kamera koptu: {e}");
                });
            }
        }
    }

    fn dongu(mut self) {
        let aralik = Duration::from_secs_f64(1.0 / self.k.fps.max(1) as f64);
        let mut sonraki = Instant::now();
        let (mut sayac, mut is_suresi, mut rapor) = (0u32, Duration::ZERO, Instant::now());
        let mut son_hata_log: Option<Instant> = None;
        while self.k.calis.load(Ordering::Relaxed) {
            let t0 = Instant::now();
            let sonuc = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                self.cikis_istegini_isle();
                let kare = self.kare_uret();
                self.gonder(&kare);
                self.k.kayitci.kare_yaz(&kare);
                self.k.tekrar.kare_yaz(&kare);
                *self.k.son_kare.lock().unwrap() = kare;
            }));
            if sonuc.is_err() && son_hata_log.is_none_or(|t| t.elapsed() > Duration::from_secs(10)) {
                // hiçbir hata hattı durdurmamalı; logla (seyrek) ve devam et
                log::error!("Video hattında hata");
                son_hata_log = Some(Instant::now());
            }
            is_suresi += t0.elapsed();
            sayac += 1;
            if rapor.elapsed() >= Duration::from_secs(1) {
                let fps = sayac as f32 / rapor.elapsed().as_secs_f32();
                let ms = is_suresi.as_secs_f32() * 1000.0 / sayac as f32;
                let sure = self.k.kayitci.sure();
                self.k.depo.guncelle(|d| {
                    d.fps = (fps * 10.0).round() / 10.0;
                    d.kare_suresi_ms = (ms * 10.0).round() / 10.0;
                    d.kayit_suresi = sure;
                });
                sayac = 0;
                is_suresi = Duration::ZERO;
                rapor = Instant::now();
            }
            sonraki += aralik;
            let simdi = Instant::now();
            if sonraki > simdi {
                std::thread::sleep(sonraki - simdi);
            } else {
                sonraki = simdi; // geride kaldıysak yetişmeye çalışma, saati sıfırla
            }
        }
        self.cikis = None;
        self.ek_kaynaklar.kapat();
        self.bekleme_videosu.kapat();
        #[cfg(windows)]
        if let Some(mut c) = self.kamera.take() {
            c.durdur(true);
        }
        self.k.depo.guncelle(|d| {
            d.cikis_acik = false;
            d.sanal_kamera = "kapalı".into();
            d.ekran_kaynagi = "kapalı".into();
            d.webcam = "kapalı".into();
        });
    }
}

pub struct VideoHatti {
    pub k: Arc<HatKontrol>,
    is: Option<JoinHandle<()>>,
}

impl VideoHatti {
    #[allow(clippy::too_many_arguments)]
    pub fn yeni(
        depo: DurumDeposu,
        sahneler: Arc<SahneYoneticisi>,
        kayitci: Arc<Kayitci>,
        tekrar: Arc<AnlikTekrar>,
        genislik: u32,
        yukseklik: u32,
        fps: u32,
        ayar: HatAyari,
        kamera_acik: bool,
    ) -> Self {
        let k = Arc::new(HatKontrol {
            depo,
            sahneler,
            kayitci,
            tekrar,
            genislik,
            yukseklik,
            fps: fps.clamp(1, 60),
            cikis_istegi: AtomicBool::new(false),
            cikis_hemen: AtomicBool::new(false),
            kamera_istegi: AtomicBool::new(kamera_acik),
            panik: AtomicBool::new(false),
            onizleme_gorunur: AtomicBool::new(true),
            mini_gorunur: AtomicBool::new(false),
            toplanti_gorunur: AtomicBool::new(false),
            ayar: Mutex::new(ayar),
            pencere: Mutex::new(None),
            bolge: Default::default(),
            kaynak_boyutu: Mutex::new((0, 0)),
            cizim: Arc::new(crate::cizim::CizimDeposu::new()),
            son_kare: Mutex::new(Kare::siyah(genislik, yukseklik).arc()),
            calis: AtomicBool::new(false),
        });
        VideoHatti { k, is: None }
    }

    pub fn baslat(&mut self) {
        if self.is.is_some() {
            return;
        }
        self.k.calis.store(true, Ordering::SeqCst);
        let ayar = self.k.ayar.lock().unwrap().clone();
        let ic = Ic {
            k: self.k.clone(),
            kaynak: Kaynak::Ekran(EkranKaynagi::yeni(ayar.monitor, &ayar.yakalama)),
            kaynak_ayari: (ayar.monitor, ayar.yakalama.clone(), None),
            #[cfg(windows)]
            kamera: None,
            cikis: None,
            cikis_sonraki: None,
            onbellek: None,
            ek_kaynaklar: crate::ek_kaynaklar::EkKaynaklar::yeni(self.k.genislik, self.k.yukseklik, self.k.fps),
            bekleme_videosu: Arc::new(crate::video_oynatici::VideoOynatici::yeni(self.k.fps)),
            kare_sayaci: 0,
            vurgu: Default::default(),
        };
        self.is = std::thread::Builder::new().name("video-hatti".into()).spawn(move || ic.dongu()).ok();
    }

    pub fn durdur(&mut self) {
        self.k.calis.store(false, Ordering::SeqCst);
        if let Some(is) = self.is.take() {
            let bitis = Instant::now() + Duration::from_secs(3);
            while !is.is_finished() && Instant::now() < bitis {
                std::thread::sleep(Duration::from_millis(10));
            }
        }
    }
}

impl Drop for VideoHatti {
    fn drop(&mut self) {
        self.durdur();
    }
}
