//! Sistem tepsisi simgesi (Python ui/tray.py karşılığı). Pencere kapatılınca uygulama burada
//! çalışmaya devam eder: sanal kamera ve VB-Cable arka planda açık kalır.

use std::sync::Arc;

use eframe::egui;
use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tray_icon::{Icon, MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};

use rizeon::uygulama::{Komut, Uygulama};

pub struct Tepsi {
    _simge: TrayIcon,
}

impl Tepsi {
    pub fn kur(ctx: egui::Context, uyg: Arc<Uygulama>) -> Option<Tepsi> {
        let resim = image::load_from_memory(include_bytes!("../../../kurulum/uygulama.ico")).ok()?.into_rgba8();
        let resim = image::imageops::resize(&resim, 32, 32, image::imageops::FilterType::Triangle);
        let (w, h) = resim.dimensions();
        let simge = Icon::from_rgba(resim.into_raw(), w, h).ok()?;

        let goster = MenuItem::new("RizeOn'u göster", true, None);
        let mini = MenuItem::new("Mini bar", true, None);
        let cikis_dur = MenuItem::new("Sanal kamerayı ve mikrofonu duraklat / sürdür", true, None);
        let cikis = MenuItem::new("Çıkış", true, None);
        let menu = Menu::new();
        menu.append_items(&[&goster, &mini, &cikis_dur, &PredefinedMenuItem::separator(), &cikis]).ok()?;
        let kimlikler = (goster.id().clone(), mini.id().clone(), cikis_dur.id().clone(), cikis.id().clone());

        {
            let (uyg, ctx) = (uyg.clone(), ctx.clone());
            MenuEvent::set_event_handler(Some(move |e: MenuEvent| {
                let k = if e.id == kimlikler.0 {
                    Komut::AnaPencere
                } else if e.id == kimlikler.1 {
                    Komut::MiniBar
                } else if e.id == kimlikler.2 {
                    let m = uyg.komut(Komut::CikisAcKapat);
                    if !m.is_empty() {
                        uyg.bildir(&m, None, false);
                    }
                    return;
                } else if e.id == kimlikler.3 {
                    Komut::Cikis
                } else {
                    return;
                };
                uyg.arayuz_istekleri.lock().unwrap().push_back(k);
                ctx.request_repaint();
            }));
        }
        {
            // Sol tık: ana pencere
            TrayIconEvent::set_event_handler(Some(move |e: TrayIconEvent| {
                if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = e {
                    uyg.arayuz_istekleri.lock().unwrap().push_back(Komut::AnaPencere);
                    ctx.request_repaint();
                }
            }));
        }
        let t = TrayIconBuilder::new()
            .with_tooltip(format!("RizeOn {}", rizeon::surum::SURUM))
            .with_icon(simge)
            .with_menu(Box::new(menu))
            .with_menu_on_left_click(false)
            .build()
            .map_err(|e| log::warn!("Tepsi simgesi kurulamadı: {e}"))
            .ok()?;
        Some(Tepsi { _simge: t })
    }
}
