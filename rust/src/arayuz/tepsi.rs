//! Sistem tepsisi (Python ui/tray.py karşılığı): pencere kapatılınca uygulama saatin yanında
//! çalışmaya devam eder.
//!
//! Menü: Ana pencereyi göster · Mini bar · Toplantı modu · mikrofon/sistem sesi/kamera · Sahne ▸ · Kaydı başlat ·
//! Son 15 sn'yi kaydet · Kayıt klasörü · Sanal çıkışı duraklat · (sorun varsa: sorun satırı) ·
//! Hakkında · Çıkış.

use std::sync::Arc;

use eframe::egui;
use tray_icon::menu::{CheckMenuItem, Menu, MenuEvent, MenuId, MenuItem, PredefinedMenuItem, Submenu};
use tray_icon::{Icon, MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};

use rizeon::durum::Durum;
use rizeon::uygulama::{Komut, Uygulama};

pub struct Tepsi {
    simge: TrayIcon,
    mik: CheckMenuItem,
    sistem: CheckMenuItem,
    kamera: CheckMenuItem,
    toplanti: CheckMenuItem,
    sahne: Submenu,
    sahne_ogeleri: Vec<CheckMenuItem>,
    sahne_imzasi: Vec<String>,
    kayit: MenuItem,
    tekrar: MenuItem,
    cikis_dur: MenuItem,
    sorun: MenuItem,
    sorun_metni: String,
    sorun_var: bool,
    menu: Menu,
}

const SAHNE_ON_EKI: &str = "sahne:";

impl Tepsi {
    pub fn kur(ctx: egui::Context, uyg: Arc<Uygulama>) -> Option<Tepsi> {
        let resim = image::load_from_memory(include_bytes!("../../varliklar/logo.png")).ok()?.into_rgba8();
        let resim = image::imageops::resize(&resim, 32, 32, image::imageops::FilterType::Triangle);
        let (w, h) = resim.dimensions();
        let ikon = Icon::from_rgba(resim.into_raw(), w, h).ok()?;

        let oge = |id: &str, ad: &str| MenuItem::with_id(MenuId::new(id), ad, true, None);
        let onay = |id: &str, ad: &str| CheckMenuItem::with_id(MenuId::new(id), ad, true, false, None);
        let goster = oge("ana", "Ana pencereyi göster");
        let mini = oge("mini", "Mini bar");
        let toplanti = onay("toplanti.mod", "Toplantı modu (tüm ekran paylaşımı)");
        let mik = onay("ses.mikrofon", "Mikrofon");
        let sistem = onay("ses.sistem", "Sistem sesi");
        let kamera = onay("kamera.ac_kapat", "Kamera");
        let sahne = Submenu::new("Sahne", true);
        let kayit = oge("kayit.ac_kapat", "Kaydı başlat");
        let tekrar = oge("anlik_kayit.kaydet", "Son 15 sn'yi kaydet");
        let klasor = oge("kayit.klasor", "Kayıt klasörünü aç");
        let cikis_dur = oge("cikis.ac_kapat", "Sanal çıkışı duraklat");
        let sorun = oge("sorun", "");
        let hakkinda = oge("hakkinda", "Hakkında");
        let cikis = oge("cikis", "Çıkış");
        let menu = Menu::new();
        menu.append_items(&[
            &goster,
            &mini,
            &toplanti,
            &PredefinedMenuItem::separator(),
            &mik,
            &sistem,
            &kamera,
            &sahne,
            &PredefinedMenuItem::separator(),
            &kayit,
            &tekrar,
            &klasor,
            &PredefinedMenuItem::separator(),
            &cikis_dur,
            &PredefinedMenuItem::separator(),
            &hakkinda,
            &cikis,
        ])
        .ok()?;

        {
            let (uyg, ctx) = (uyg.clone(), ctx.clone());
            MenuEvent::set_event_handler(Some(move |e: MenuEvent| {
                let id = e.id.0.as_str();
                let arayuz = |k: Komut| {
                    uyg.arayuz_istekleri.lock().unwrap().push_back(k);
                };
                match id {
                    "ana" => arayuz(Komut::AnaPencere),
                    "mini" => arayuz(Komut::MiniBar),
                    "hakkinda" => arayuz(Komut::Hakkinda),
                    "sorun" => arayuz(Komut::Yardim),
                    "cikis" => arayuz(Komut::Cikis),
                    _ => {
                        let komut = match id.strip_prefix(SAHNE_ON_EKI) {
                            Some(n) => n.parse::<usize>().ok().map(Komut::Sahne),
                            None => Komut::coz(id),
                        };
                        if let Some(k) = komut {
                            let m = uyg.komut(k);
                            if !m.is_empty() {
                                uyg.bildir(&m, None, false);
                            }
                        }
                    }
                }
                ctx.request_repaint();
            }));
        }
        {
            // Sol tık ya da çift tık: ana pencere
            TrayIconEvent::set_event_handler(Some(move |e: TrayIconEvent| {
                let ac = matches!(
                    e,
                    TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } | TrayIconEvent::DoubleClick { button: MouseButton::Left, .. }
                );
                if ac {
                    uyg.arayuz_istekleri.lock().unwrap().push_back(Komut::AnaPencere);
                    ctx.request_repaint();
                }
            }));
        }
        let simge = TrayIconBuilder::new()
            .with_tooltip("RizeOn")
            .with_icon(ikon)
            .with_menu(Box::new(menu.clone()))
            .with_menu_on_left_click(false)
            .build()
            .map_err(|e| log::warn!("Tepsi simgesi kurulamadı: {e}"))
            .ok()?;
        Some(Tepsi {
            simge,
            mik,
            sistem,
            kamera,
            toplanti,
            sahne,
            sahne_ogeleri: Vec::new(),
            sahne_imzasi: Vec::new(),
            kayit,
            tekrar,
            cikis_dur,
            sorun,
            sorun_metni: String::new(),
            sorun_var: false,
            menu,
        })
    }

    /// Sanal kamera/mikrofon sorunu sürdükçe menüde görünür ("" = sorun yok).
    pub fn sorun_ayarla(&mut self, metin: &str) {
        self.sorun_metni = metin.to_string();
        self.sorun.set_text(format!("{metin} · Nasıl düzeltilir?"));
        let _ = self.simge.set_tooltip(Some(if metin.is_empty() { "RizeOn".to_string() } else { format!("RizeOn · {metin}") }));
    }

    pub fn durumu_goster(&mut self, d: &Durum, uyg: &Uygulama) {
        self.mik.set_checked(!d.mikrofon_sessiz);
        self.mik.set_text(format!("Mikrofon: {}", if d.mikrofon_sessiz { "kapalı" } else { "açık" }));
        self.sistem.set_checked(!d.sistem_sessiz);
        self.sistem.set_text(format!("Sistem sesi: {}", if d.sistem_sessiz { "kapalı" } else { "açık" }));
        let sahnede = uyg.k.kamera_sahnede();
        let acik = uyg.kamera_gorunur_acik();
        self.kamera.set_checked(acik);
        self.kamera.set_enabled(sahnede);
        self.kamera.set_text(if sahnede { format!("Kamera: {}", if acik { "açık" } else { "kapalı" }) } else { "Kamera: bu sahnede yok".into() });
        self.toplanti.set_checked(d.toplanti_modu);
        self.kayit.set_text(if d.kayit == "açık" { "Kaydı bitir" } else { "Kaydı başlat" });
        let etiket = rizeon::tekrar::sure_etiketi(uyg.tekrar.sure_sn() as i64);
        self.tekrar.set_text(if etiket.ends_with("dk") { format!("{etiket}'yı kaydet") } else { format!("{etiket}'yi kaydet") });
        self.tekrar.set_enabled(uyg.tekrar.acik());
        let cikis = uyg.k.cikis_istegi.load(std::sync::atomic::Ordering::Relaxed);
        self.cikis_dur.set_text(if cikis { "Sanal çıkışı duraklat" } else { "Sanal çıkışı sürdür" });

        // sorun satırı: sorun varken "Sanal çıkışı duraklat"tan sonra görünür
        let sorun = !self.sorun_metni.is_empty();
        if sorun != self.sorun_var {
            self.sorun_var = sorun;
            if sorun {
                let _ = self.menu.insert(&self.sorun, 14);
            } else {
                let _ = self.menu.remove(&self.sorun);
            }
        }

        // sahne alt menüsü: sahneler değişince yeniden kurulur
        let sahneler: Vec<String> = uyg.k.sahneler.liste().iter().map(|s| s.ad.clone()).collect();
        if sahneler != self.sahne_imzasi {
            for o in self.sahne_ogeleri.drain(..) {
                let _ = self.sahne.remove(&o);
            }
            for (i, ad) in sahneler.iter().enumerate() {
                let o = CheckMenuItem::with_id(MenuId::new(format!("{SAHNE_ON_EKI}{i}")), ad, true, false, None);
                let _ = self.sahne.append(&o);
                self.sahne_ogeleri.push(o);
            }
            self.sahne_imzasi = sahneler;
        }
        let aktif = uyg.k.sahneler.indeks();
        for (i, o) in self.sahne_ogeleri.iter().enumerate() {
            o.set_checked(i == aktif);
        }
    }
}
