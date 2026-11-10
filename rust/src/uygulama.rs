//! Uygulamanın parçalarını bir araya getirir ve komutları çalıştırır (Python main.py:komutlari_kaydet).
//! Komutlar arayüzden, kısayollardan ve tepsiden aynı yoldan gelir; hepsi iş parçacığı güvenli.

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use std::time::Instant;

use serde_json::Value;

use crate::ayarlar::Ayarlar;
use crate::durum::DurumDeposu;
use crate::hat::{HatAyari, HatKontrol, VideoHatti};
use crate::kayit::Kayitci;
use crate::sahne::{self, KameraYerlesimi, SahneYoneticisi};
use crate::ses::karistirici::Karistirici;
use crate::tekrar::{self, AnlikTekrar};

#[derive(Clone, Debug, PartialEq)]
pub enum Komut {
    Mikrofon,
    Sistem,
    Kamera,
    Kayit,
    KayitDurdur,
    KayitDuraklat,
    TekrarKaydet,
    EkranGoruntusu,
    Panik,
    Sahne(usize),
    CikisAcKapat,
    MiniBar,
    AnaPencere,
    /// Bölge seç (bölge varsa tam ekrana döner)
    Bolge,
    /// Ne gösterilsin: tüm ekran ya da bir pencere
    KaynakSec,
    /// Kalem katmanını aç/kapat
    Kalem,
    KalemTemizle,
    /// Kalem açıkken: araç (0-6), renk (0-3), kalınlık (0-2)
    KalemTur(usize),
    KalemRenk(usize),
    KalemKalinlik(usize),
    KalemGeriAl,
    /// Kalemden ya da bölge seçiminden çık (Esc)
    KalemKapat,
    Cikis,
    /// Hakkında penceresi (tepsi menüsü)
    Hakkinda,
    /// "Nasıl düzeltilir?" (sanal çıkış sorunu)
    Yardim,
    KayitKlasoru,
}

impl Komut {
    /// settings.json'daki komut adından ("sahne.sec:3" gibi).
    pub fn coz(ad: &str) -> Option<Komut> {
        let (ad, param) = ad.split_once(':').map(|(a, p)| (a, Some(p))).unwrap_or((ad, None));
        Some(match ad {
            "ses.mikrofon" => Komut::Mikrofon,
            "ses.sistem" => Komut::Sistem,
            "kamera.ac_kapat" => Komut::Kamera,
            "kayit.ac_kapat" => Komut::Kayit,
            "kayit.duraklat" => Komut::KayitDuraklat,
            "anlik_kayit.kaydet" => Komut::TekrarKaydet,
            "ekran.goruntusu" => Komut::EkranGoruntusu,
            "panik" => Komut::Panik,
            "sahne.sec" => Komut::Sahne(param?.parse::<usize>().ok()?.checked_sub(1)?),
            "cikis.ac_kapat" => Komut::CikisAcKapat,
            "bolge.sec" => Komut::Bolge,
            "kaynak.sec" => Komut::KaynakSec,
            "kalem.ac_kapat" => Komut::Kalem,
            "kalem.temizle" => Komut::KalemTemizle,
            "kalem.tur" => Komut::KalemTur(param?.parse::<usize>().ok()?.checked_sub(1).filter(|n| *n < 7)?),
            "kalem.renk" => Komut::KalemRenk(param?.parse::<usize>().ok()?.checked_sub(1).filter(|n| *n < 4)?),
            "kalem.kalinlik" => Komut::KalemKalinlik(param?.parse::<usize>().ok()?.checked_sub(1).filter(|n| *n < 3)?),
            "kalem.geri_al" => Komut::KalemGeriAl,
            "kalem.kapat" => Komut::KalemKapat,
            "kayit.klasor" => Komut::KayitKlasoru,
            "pencere.mini" => Komut::MiniBar,
            _ => return None,
        })
    }
}

/// Bildirimdeki tıklanabilir bağlantı.
#[derive(Clone, Debug, PartialEq)]
pub enum BildirimEylemi {
    Ac(PathBuf),
    KlasordeGoster(PathBuf),
    /// "Nasıl düzeltilir?" (sanal kamera / mikrofon yardımı)
    Yardim,
    /// "Ayarlar" (alınamayan kısayollar)
    Ayarlar(&'static str),
}

/// Sağ altta kısa süre görünen bildirim: "Mikrofon kapandı · Ctrl+Shift+M" ya da "… · Aç".
#[derive(Clone, Debug)]
pub struct Bildirim {
    pub metin: String,
    pub tus: String,
    pub eylem: Option<BildirimEylemi>,
    /// kısayol bildirimi mi (ui.toasts kapalıyken gösterilmez)
    pub kisayol: bool,
    pub zaman: Instant,
}

pub struct Uygulama {
    pub ayarlar: Mutex<Ayarlar>,
    pub depo: DurumDeposu,
    pub mikser: Arc<Mutex<Karistirici>>,
    pub hat: Mutex<VideoHatti>,
    pub k: Arc<HatKontrol>,
    pub kayitci: Arc<Kayitci>,
    pub tekrar: Arc<AnlikTekrar>,
    #[cfg(windows)]
    pub ses: crate::ses::motor::SesMotoru,
    pub bildirimler: Mutex<VecDeque<Bildirim>>,
    /// Arayüzün yapması gerekenler (mini bar, pencereyi göster, çıkış): kısayol iş parçacığından gelir.
    pub arayuz_istekleri: Mutex<VecDeque<Komut>>,
    pub uyandir: Mutex<Option<Box<dyn Fn() + Send + Sync>>>,
    #[cfg(windows)]
    bas_konus: Mutex<Option<crate::kisayol::BasKonus>>,
}

pub fn hat_ayari(a: &Ayarlar) -> HatAyari {
    HatAyari {
        imlec_goster: a.mantik("video.show_cursor", true),
        imlec_vurgusu: a.mantik("video.cursor_highlight", false),
        bekleme_metni: a.al("standby_text").and_then(Value::as_str).unwrap_or("Birazdan döneceğim").to_string(),
        bekleme_gorseli: a.metin("standby_image"),
        yer: KameraYerlesimi::ayarlardan(a.al("camera").unwrap_or(&Value::Null)),
        monitor: a.sayi("video.monitor", 0).max(0) as usize,
        yakalama: a.metin("video.capture_backend"),
        kamera_cihazi: a.sayi("camera.device", 0).max(0) as usize,
        kamera_ayna: a.mantik("camera.mirror", false),
        kamera_bulanik: a.mantik("camera.blur", false),
    }
}

#[cfg(windows)]
fn motor_ayari(a: &Ayarlar) -> crate::ses::motor::MotorAyari {
    crate::ses::motor::MotorAyari {
        mikrofon_adi: a.metin("audio.mic_device"),
        sistem_modu: a.metin("audio.system_mode"),
        haric_uygulamalar: a
            .al("audio.exclude_apps")
            .and_then(Value::as_array)
            .map(|l| l.iter().filter_map(Value::as_str).map(String::from).collect())
            .unwrap_or_else(|| crate::ses::motor::VARSAYILAN_HARIC.iter().map(|s| s.to_string()).collect()),
        dahil_uygulama: a.metin("audio.include_app"),
    }
}

impl Uygulama {
    pub fn kur(ayarlar: Ayarlar) -> Arc<Uygulama> {
        let a = &ayarlar;
        let w = (a.sayi("video.width", 1280).clamp(320, 3840) as u32) & !1;
        let h = (a.sayi("video.height", 720).clamp(180, 2160) as u32) & !1;
        let fps = a.sayi("video.fps", 30).clamp(5, 60) as u32;
        let depo = DurumDeposu::new();
        let mut mikser = Karistirici::new();
        mikser.kanal_ekle("mikrofon", "Mikrofon", a.ondalik("audio.mic_gain", 1.0) as f32, a.mantik("audio.mic_muted", false));
        mikser.kanal_ekle("sistem", "Bilgisayar sesi", a.ondalik("audio.system_gain", 0.7) as f32, a.mantik("audio.system_muted", false));
        mikser.kisma_acik = a.mantik("audio.ducking", false);
        mikser.kisma_seviyesi = a.ondalik("audio.ducking_level", 0.3) as f32;
        depo.guncelle(|d| {
            d.mikrofon_sessiz = a.mantik("audio.mic_muted", false);
            d.sistem_sessiz = a.mantik("audio.system_muted", false);
        });
        let mikser = Arc::new(Mutex::new(mikser));
        let sahneler = Arc::new(SahneYoneticisi::yeni(
            sahne::sahneleri_oku(a.al("scenes"), a.mantik("video.cursor_highlight", false)),
            a.sayi("transition_ms", 300),
        ));
        let klasor = kayit_klasoru(a);
        let kod = a.al("record.encoder").and_then(Value::as_str).unwrap_or("auto").to_string();
        let kayitci = Arc::new(Kayitci::yeni(w, h, fps, klasor, &kod, None));
        let tekrar = Arc::new(AnlikTekrar::yeni(w, h, fps, a.sayi("record.replay_seconds", 15), &kod, None));
        {
            let mut m = mikser.lock().unwrap();
            let t = tekrar.clone();
            m.dinleyici_ekle(Arc::new(move |b| t.ses_yaz(b)));
            let k = kayitci.clone();
            m.dinleyici_ekle(Arc::new(move |b| k.ses_yaz(b)));
        }
        let hat = VideoHatti::yeni(
            depo.clone(),
            sahneler,
            kayitci.clone(),
            tekrar.clone(),
            w,
            h,
            fps,
            hat_ayari(a),
            a.mantik("camera.enabled", true),
        );
        let k = hat.k.clone();
        #[cfg(windows)]
        let ses = crate::ses::motor::SesMotoru::yeni(
            depo.clone(),
            mikser.clone(),
            motor_ayari(a),
        );
        let u = Arc::new(Uygulama {
            ayarlar: Mutex::new(ayarlar),
            depo,
            mikser,
            hat: Mutex::new(hat),
            k,
            kayitci,
            tekrar,
            #[cfg(windows)]
            ses,
            bildirimler: Default::default(),
            arayuz_istekleri: Default::default(),
            uyandir: Mutex::new(None),
            #[cfg(windows)]
            bas_konus: Mutex::new(None),
        });
        let zayif = Arc::downgrade(&u);
        u.kayitci.hata_olunca(Arc::new(move |mesaj| {
            if let Some(u) = zayif.upgrade() {
                // Disk doldu / FFmpeg kapandı: kaydı durdur, o ana kadarki kısım kaydedilir.
                u.bildir(&format!("Kayıt durduruldu: {mesaj}"), None, false);
                let u2 = u.clone();
                std::thread::spawn(move || {
                    u2.komut(Komut::KayitDurdur);
                });
            }
        }));
        u
    }

    /// Açılışta: hattı ve sesi başlat, sanal çıkışı aç, anlık tekrarı başlat, yarım kayıtları kurtar.
    pub fn baslat(self: &Arc<Self>) {
        // Sanal çıkış (OBS Virtual Camera + VB-Cable) arka planda hep açık (2.0.0)
        self.k.cikisi_ayarla(true);
        self.hat.lock().unwrap().baslat();
        #[cfg(windows)]
        {
            self.ses.gurultu_ayarla(self.ayarlar.lock().unwrap().mantik("audio.noise_suppression", false));
            self.ses.baslat();
            self.ses.ac(true);
        }
        if let Err(e) = self.bas_konusu_uygula() {
            self.bildir(&format!("Bas-konuş açılamadı: {e}"), None, false);
        }
        if self.ayarlar.lock().unwrap().mantik("record.replay", true) {
            let u = self.clone();
            std::thread::Builder::new()
                .name("tekrar-baslat".into())
                .spawn(move || {
                    if let Err(e) = u.tekrar.baslat() {
                        log::warn!("Anlık tekrar başlamadı: {e}");
                    }
                    // Seçilen donanım kodlayıcısı sürekli akışta hemen kapanırsa (test kodlamasını geçse de)
                    // anlık tekrar her yerde çalışan mpeg4 ile bir kez daha denenir.
                    std::thread::sleep(std::time::Duration::from_secs(3));
                    if !u.tekrar.acik() && u.tekrar.son_hata().contains("FFmpeg kapandı") {
                        log::warn!("Anlık tekrar mpeg4 ile yeniden deneniyor");
                        u.tekrar.durdur();
                        u.tekrar.kodlayici_ayarla("mpeg4");
                        if let Err(e) = u.tekrar.baslat() {
                            log::warn!("Anlık tekrar yine başlamadı: {e}");
                        }
                    }
                    u.depo.guncelle(|d| d.tekrar_acik = u.tekrar.acik());
                })
                .ok();
        }
        let u = self.clone();
        std::thread::Builder::new()
            .name("kayit-kurtar".into())
            .spawn(move || {
                let ff = crate::ffmpeg::ffmpeg_bul();
                for d in crate::kayit::yarim_kayitlari_kurtar(&u.kayitci.klasor(), ff.as_deref()) {
                    let ad = d.file_name().unwrap_or_default().to_string_lossy().into_owned();
                    u.bildir(&format!("Yarım kalan kayıt kurtarıldı: {ad}"), Some(d), true);
                }
                tekrar::artik_dosyalari_sil(&u.kayitci.klasor(), 120.0);
            })
            .ok();
        let u = self.clone();
        std::thread::Builder::new()
            .name("islemci-olcer".into())
            .spawn(move || {
                let mut o = crate::islemci::IslemciOlcer::new();
                loop {
                    std::thread::sleep(std::time::Duration::from_secs(30));
                    let s = o.olc();
                    let d = u.depo.al();
                    log::info!(
                        "CPU (30 sn): toplam %{:.1} | uygulama %{:.1}, ffmpeg %{:.1} | {} fps, kare {:.1} ms",
                        s.toplam,
                        s.uygulama,
                        s.ffmpeg,
                        d.fps,
                        d.kare_suresi_ms
                    );
                }
            })
            .ok();
    }

    /// Kapanış: kayıt sürüyorsa bitir (yarım kalmasın), her şeyi durdur.
    pub fn kapat(&self) {
        self.kayitci.kapat(60);
        self.tekrar.durdur();
        self.hat.lock().unwrap().durdur();
        #[cfg(windows)]
        {
            self.ses.durdur();
            crate::ses::motor::temiz_cikis();
        }
        self.ayarlar.lock().unwrap().kaydet();
        log::info!("Uygulama kapandı");
    }

    pub fn bildir(&self, metin: &str, dosya: Option<PathBuf>, klasorde: bool) {
        let eylem = dosya.map(|d| if klasorde { BildirimEylemi::KlasordeGoster(d) } else { BildirimEylemi::Ac(d) });
        self.bildirim_ekle(Bildirim { metin: metin.into(), tus: String::new(), eylem, kisayol: false, zaman: Instant::now() });
    }

    pub fn bildirim_ekle(&self, x: Bildirim) {
        log::info!("{}", x.metin);
        let mut b = self.bildirimler.lock().unwrap();
        b.push_back(x);
        while b.len() > 4 {
            b.pop_front();
        }
        drop(b);
        self.uyan();
    }

    fn uyan(&self) {
        if let Some(f) = self.uyandir.lock().unwrap().as_ref() {
            f();
        }
    }

    pub fn ayarla(&self, yol: &str, deger: Value) {
        self.ayarlar.lock().unwrap().ayarla(yol, deger);
    }

    /// Ayarlar penceresinde kaydedilenleri çalışan parçalara uygular (yeniden başlatmadan).
    /// Çözünürlük ve fps hariç: onlar bir sonraki açılışta geçerli olur.
    pub fn ayarlari_uygula(self: &Arc<Self>) {
        let a = self.ayarlar.lock().unwrap();
        *self.k.ayar.lock().unwrap() = hat_ayari(&a);
        self.k.sahneler.gecis_ayarla(a.sayi("transition_ms", 300));
        {
            let mut m = self.mikser.lock().unwrap();
            m.kisma_acik = a.mantik("audio.ducking", false);
            m.kisma_seviyesi = a.ondalik("audio.ducking_level", 0.3) as f32;
        }
        #[cfg(windows)]
        {
            self.ses.ayar_degistir(motor_ayari(&a));
            self.ses.gurultu_ayarla(a.mantik("audio.noise_suppression", false));
        }
        self.kayitci.klasor_ayarla(kayit_klasoru(&a));
        let kod = a.al("record.encoder").and_then(Value::as_str).unwrap_or("auto").to_string();
        self.kayitci.kodlayici_ayarla(&kod);
        self.tekrar.kodlayici_ayarla(&kod);
        self.tekrar.sure_ayarla(a.sayi("record.replay_seconds", 15));
        let tekrar_istek = a.mantik("record.replay", true);
        drop(a);
        if let Err(e) = self.bas_konusu_uygula() {
            self.bildir(&format!("Bas-konuş açılamadı: {e}"), None, false);
        }
        if tekrar_istek != self.tekrar.acik() {
            let u = self.clone();
            std::thread::spawn(move || {
                if tekrar_istek {
                    if let Err(e) = u.tekrar.baslat() {
                        u.bildir(&format!("Anlık tekrar başlamadı: {e}"), None, false);
                    }
                } else {
                    u.tekrar.durdur();
                }
                u.depo.guncelle(|d| d.tekrar_acik = u.tekrar.acik());
            });
        }
    }

    /// Bas-konuş tuşu (hotkeys.bas_konus) ve anahtarı (audio.ptt) ayarlardan okunur: ikisi de varsa
    /// mikrofon sadece tuş basılıyken açık. Tuş yoksa ya da anahtar kapalıysa mikrofon hep açık.
    pub fn bas_konusu_uygula(self: &Arc<Self>) -> Result<(), String> {
        let (acik, tus) = {
            let a = self.ayarlar.lock().unwrap();
            let tus = a.veri.get("hotkeys").and_then(|h| h.get("bas_konus")).and_then(Value::as_str).unwrap_or("").trim().to_string();
            (a.mantik("audio.ptt", false), tus)
        };
        let kapiyi_ac = |u: &Uygulama| {
            if let Some(k) = u.mikser.lock().unwrap().kanal("mikrofon") {
                k.kapi = true;
            }
            u.depo.guncelle(|d| {
                d.bas_konus = false;
                d.konusuyor = false;
            });
        };
        #[cfg(windows)]
        {
            let mut bk = self.bas_konus.lock().unwrap();
            *bk = None;
            kapiyi_ac(self);
            if !acik {
                return Ok(());
            }
            if tus.is_empty() {
                return Err("Ayarlar > Kısayollar'da bas-konuş tuşu seçilmemiş".into());
            }
            let zayif = Arc::downgrade(self);
            *bk = Some(crate::kisayol::BasKonus::baslat(&tus, move |basili| {
                if let Some(u) = zayif.upgrade() {
                    if let Some(k) = u.mikser.lock().unwrap().kanal("mikrofon") {
                        k.kapi = basili;
                    }
                    u.depo.guncelle(|d| {
                        d.bas_konus = true;
                        d.konusuyor = basili;
                    });
                }
            })?);
            log::info!("Bas-konuş açık ({tus})");
            Ok(())
        }
        #[cfg(not(windows))]
        {
            kapiyi_ac(self);
            let _ = (acik, tus);
            Ok(())
        }
    }

    fn uyandir_arayuz(&self) {
        if let Some(f) = self.uyandir.lock().unwrap().as_ref() {
            f();
        }
    }

    /// Sadece bu pencere gösterilsin (bölge kalkar).
    pub fn pencere_sec(&self, hwnd: isize, baslik: &str) -> String {
        self.k.bolge.temizle();
        *self.k.pencere.lock().unwrap() = Some((hwnd, baslik.to_string()));
        self.depo.guncelle(|d| {
            d.kaynak_turu = "pencere".into();
            d.kaynak_adi = baslik.into();
            d.bolge.clear();
        });
        log::info!("Kaynak: pencere ({baslik})");
        format!("Sadece bu pencere gösteriliyor: {baslik}")
    }

    /// Bölge seçildi ya da modu değişti (oranlar monitöre göre 0..1; mod "yakinlastir" | "vurgula").
    pub fn bolge_sec(&self, oranlar: [f64; 4], mod_: &str) {
        self.k.bolge.sec(oranlar, mod_);
        let m = self.k.bolge.mod_().unwrap_or_default();
        self.depo.guncelle(|d| d.bolge = m.into());
        log::info!("Bölge: {oranlar:?} ({m})");
    }

    /// Tam ekrana dön (bölge kalkar, animasyonlu).
    pub fn bolge_temizle(&self) {
        self.k.bolge.temizle();
        self.depo.guncelle(|d| d.bolge.clear());
    }

    /// Tüm ekrana dön (bölge ve pencere kalkar). `monitor` verilirse o ekran seçilir.
    pub fn tam_ekran(&self) -> String {
        self.k.bolge.temizle();
        *self.k.pencere.lock().unwrap() = None;
        self.depo.guncelle(|d| {
            d.kaynak_turu = "ekran".into();
            d.kaynak_adi.clear();
            d.bolge.clear();
        });
        "Tüm ekran gösteriliyor".into()
    }

    pub fn monitor_sec(&self, monitor: usize) -> String {
        self.ayarla("video.monitor", (monitor as u64).into());
        self.k.ayar.lock().unwrap().monitor = monitor;
        self.tam_ekran();
        format!("Ekran {} gösteriliyor", monitor + 1)
    }

    pub fn sahneleri_kaydet(&self) {
        let l = self.k.sahneler.sozluk_listesi();
        self.ayarla("scenes", l);
    }

    fn susturma(&self, anahtar: &str, ayar: &str, ad: &str) -> String {
        let sessiz = {
            let mut m = self.mikser.lock().unwrap();
            let Some(k) = m.kanal(anahtar) else { return String::new() };
            k.sessiz = !k.sessiz;
            k.sessiz
        };
        self.depo.guncelle(|d| {
            if anahtar == "mikrofon" {
                d.mikrofon_sessiz = sessiz
            } else {
                d.sistem_sessiz = sessiz
            }
        });
        self.ayarla(ayar, sessiz.into());
        format!("{ad} {}", if sessiz { "kapandı" } else { "açıldı" })
    }

    pub fn kamera_gorunur_acik(&self) -> bool {
        self.k.kamera_istegi.load(Ordering::Relaxed) && self.k.kamera_sahnede()
    }

    /// Komutu çalıştırır; kullanıcıya gösterilecek kısa metni döndürür (boşsa bildirim yok).
    pub fn komut(self: &Arc<Self>, k: Komut) -> String {
        let mesaj = self.komut_isle(k.clone());
        if !mesaj.is_empty() {
            log::info!("Komut: {k:?} ({mesaj})");
        }
        self.uyan();
        mesaj
    }

    fn komut_isle(self: &Arc<Self>, k: Komut) -> String {
        match k {
            Komut::Mikrofon => self.susturma("mikrofon", "audio.mic_muted", "Mikrofon"),
            Komut::Sistem => self.susturma("sistem", "audio.system_muted", "Bilgisayar sesi"),
            Komut::Kamera => {
                if !self.k.kamera_sahnede() {
                    return "Bu sahnede kamera yok (Kaynaklar'dan ekleyebilirsin)".into();
                }
                let ac = !self.k.kamera_istegi.load(Ordering::Relaxed);
                self.k.kamerayi_ayarla(ac);
                if ac { "Kamera açıldı" } else { "Kamera kapatıldı" }.into()
            }
            Komut::Sahne(i) => {
                if !self.k.sahneler.sec(i) {
                    return format!("{}. sahne yok", i + 1);
                }
                format!("Sahne: {}", self.k.sahneler.aktif().ad)
            }
            Komut::Panik => {
                let p = !self.k.panik.load(Ordering::Relaxed);
                self.k.panik.store(p, Ordering::SeqCst);
                self.mikser.lock().unwrap().ana_sessiz = p; // panikte ses de gitmez
                self.depo.guncelle(|d| d.panik = p);
                if p { "Panik: bekleme ekranı, ses kapalı" } else { "Panik kapandı" }.into()
            }
            Komut::CikisAcKapat => {
                let ac = !self.k.cikis_istegi.load(Ordering::Relaxed);
                self.k.cikisi_ayarla(ac);
                #[cfg(windows)]
                self.ses.ac(ac);
                if ac { "Sanal çıkış açıldı" } else { "Sanal çıkış duraklatıldı · kamera ve mikrofon gönderilmiyor" }.into()
            }
            Komut::Kayit => {
                if self.kayitci.kayitta() {
                    return self.komut_isle(Komut::KayitDurdur);
                }
                if let Err(e) = self.kayitci.baslat() {
                    self.depo.guncelle(|d| d.kayit = "hata".into());
                    return format!("Kayıt başlamadı: {e}");
                }
                #[cfg(windows)]
                self.ses.kayit_icin_ac(true);
                self.depo.guncelle(|d| {
                    d.kayit = "açık".into();
                    d.kayit_duraklatildi = false;
                });
                "Kayıt başladı".into()
            }
            Komut::KayitDurdur => {
                if !self.kayitci.kayitta() {
                    return String::new();
                }
                let u = self.clone();
                self.kayitci.durdur(Some(Box::new(move |dosya, hata| {
                    u.depo.guncelle(|d| {
                        d.kayit = if !hata.is_empty() && dosya.is_none() { "hata" } else { "kapalı" }.into();
                        d.kayit_duraklatildi = false;
                    });
                    #[cfg(windows)]
                    u.ses.kayit_icin_ac(false);
                    match dosya {
                        Some(d) if hata.is_empty() => u.bildir("Kayıt kaydedildi", Some(d), true),
                        Some(d) => u.bildir(&format!("Kayıt kaydedildi ({hata})"), Some(d), true),
                        None => u.bildir(&format!("Kayıt kaydedilemedi: {hata}"), None, false),
                    }
                })));
                self.depo.guncelle(|d| {
                    d.kayit = "kapalı".into();
                    d.kayit_duraklatildi = false;
                });
                "Kayıt durdu, dosya hazırlanıyor".into()
            }
            Komut::KayitDuraklat => {
                if !self.kayitci.kayitta() {
                    return "Kayıt açık değil".into();
                }
                if self.kayitci.duraklatildi() {
                    if !self.kayitci.devam_et() {
                        return format!("Kayda devam edilemedi: {}", self.kayitci.son_hata());
                    }
                    self.depo.guncelle(|d| d.kayit_duraklatildi = false);
                    return "Kayda devam ediliyor".into();
                }
                self.kayitci.duraklat();
                self.depo.guncelle(|d| d.kayit_duraklatildi = true);
                "Kayıt duraklatıldı · devam etmek için tekrar bas".into()
            }
            Komut::TekrarKaydet => {
                if !self.tekrar.acik() {
                    return "Anlık tekrar kapalı · Ayarlar'dan açabilirsin".into();
                }
                let klasor = kayit_klasoru(&self.ayarlar.lock().unwrap());
                let u = self.clone();
                match self.tekrar.kaydet(
                    klasor,
                    Some(Box::new(move |dosya, hata| match dosya {
                        Some(d) => u.bildir(&format!("{} kaydedildi", tekrar::sure_etiketi(u.tekrar.sure_sn() as i64)), Some(d), false),
                        None => u.bildir(&format!("Tekrar kaydedilemedi: {hata}"), None, false),
                    })),
                ) {
                    Ok(()) => String::new(),
                    Err(e) => e,
                }
            }
            Komut::EkranGoruntusu => {
                let klasor = {
                    let a = self.ayarlar.lock().unwrap();
                    let s = a.metin("screenshot.folder");
                    if s.is_empty() {
                        kayit_klasoru(&a)
                    } else {
                        PathBuf::from(s)
                    }
                };
                match ekran_goruntusu_kaydet(&self.k.son_kare(), &klasor) {
                    Ok(d) => {
                        self.bildir("Ekran görüntüsü kaydedildi", Some(d), false);
                        String::new()
                    }
                    Err(e) => format!("Ekran görüntüsü kaydedilemedi: {e}"),
                }
            }
            Komut::Bolge
            | Komut::KalemTur(_)
            | Komut::KalemRenk(_)
            | Komut::KalemKalinlik(_)
            | Komut::KalemGeriAl
            | Komut::KalemKapat
            | Komut::MiniBar | Komut::AnaPencere | Komut::Cikis | Komut::KaynakSec | Komut::Kalem | Komut::KalemTemizle | Komut::Hakkinda | Komut::Yardim | Komut::KayitKlasoru => {
                self.arayuz_istekleri.lock().unwrap().push_back(k);
                self.uyandir_arayuz();
                String::new()
            }
        }
    }
}

pub fn kayit_klasoru(a: &Ayarlar) -> PathBuf {
    let k = a.metin("record.folder");
    if k.is_empty() {
        crate::yollar::varsayilan_kayit_klasoru()
    } else {
        PathBuf::from(k)
    }
}

/// Çıkış karesini PNG olarak kaydeder; aynı saniyede iki kez basılırsa ~2, ~3 eklenir.
pub fn ekran_goruntusu_kaydet(kare: &crate::kare::Kare, klasor: &std::path::Path) -> Result<PathBuf, String> {
    std::fs::create_dir_all(klasor).map_err(|e| e.to_string())?;
    let govde = chrono::Local::now().format("Goruntu_%Y-%m-%d_%H-%M-%S").to_string();
    let mut hedef = klasor.join(format!("{govde}.png"));
    let mut sira = 2;
    while hedef.exists() {
        hedef = klasor.join(format!("{govde}~{sira}.png"));
        sira += 1;
    }
    kare.png_kaydet(&hedef)?;
    Ok(hedef)
}

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn komut_adlari() {
        assert_eq!(Komut::coz("sahne.sec:3"), Some(Komut::Sahne(2)));
        assert_eq!(Komut::coz("sahne.sec:0"), None);
        assert_eq!(Komut::coz("ses.mikrofon"), Some(Komut::Mikrofon));
        assert_eq!(Komut::coz("bilinmeyen"), None);
    }

    #[test]
    fn ekran_goruntusu_cakismaz() {
        let d = std::env::temp_dir().join(format!("rizeon-goruntu-{}", std::process::id()));
        let k = crate::kare::Kare::dolu(8, 8, [1, 2, 3]);
        let a = ekran_goruntusu_kaydet(&k, &d).unwrap();
        let b = ekran_goruntusu_kaydet(&k, &d).unwrap();
        assert_ne!(a, b);
        assert!(b.exists());
    }
}
