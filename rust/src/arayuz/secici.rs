//! "Ne gösterilsin?" penceresi (Python ui/pencere_secici.py): tüm ekran ya da tek bir pencere.

use std::sync::Arc;

use eframe::egui::{self, RichText};

use rizeon::uygulama::Uygulama;

use super::tema;

#[derive(Default)]
pub struct PencereSecici {
    acik: bool,
    #[cfg(windows)]
    liste: Vec<rizeon::yakalama::pencere::PencereBilgisi>,
    ara: String,
}

impl PencereSecici {
    pub fn ac(&mut self) {
        self.acik = true;
        self.ara.clear();
        self.yenile();
    }

    fn yenile(&mut self) {
        #[cfg(windows)]
        {
            self.liste = rizeon::yakalama::pencere::pencereler();
        }
    }

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) {
        if !self.acik {
            return;
        }
        let mut acik = true;
        #[allow(unused_mut)]
        let mut sec: Option<(isize, String)> = None;
        let mut ekran = false;
        egui::Window::new("Ne gösterilsin?").open(&mut acik).collapsible(false).default_size([460.0, 420.0]).show(ctx, |ui| {
            ui.horizontal(|ui| {
                if ui.button("Tüm ekran").clicked() {
                    ekran = true;
                }
                ui.add(egui::TextEdit::singleline(&mut self.ara).hint_text("Ara").desired_width(200.0));
                if ui.button("Yenile").clicked() {
                    self.yenile();
                }
            });
            ui.label(RichText::new("Sadece seçtiğin pencere gösterilir; üstüne başka pencere gelse de görünmez.").small().color(tema::YAZI2));
            ui.separator();
            egui::ScrollArea::vertical().max_height(320.0).show(ui, |ui| {
                #[cfg(windows)]
                {
                    let ara = self.ara.to_lowercase();
                    for p in &self.liste {
                        if !ara.is_empty() && !p.baslik.to_lowercase().contains(&ara) && !p.program.to_lowercase().contains(&ara) {
                            continue;
                        }
                        let metin = if p.program.is_empty() { p.baslik.clone() } else { format!("{}  ·  {}", p.baslik, p.program) };
                        if ui.selectable_label(false, metin).clicked() {
                            sec = Some((p.hwnd, p.baslik.clone()));
                        }
                    }
                    if self.liste.is_empty() {
                        ui.label("Açık pencere bulunamadı");
                    }
                }
                #[cfg(not(windows))]
                ui.label("Pencere yakalama sadece Windows'ta var");
            });
        });
        if let Some((h, b)) = sec {
            let m = uyg.pencere_sec(h, &b);
            uyg.bildir(&m, None, false);
            self.acik = false;
        } else if ekran {
            let m = uyg.tam_ekran();
            uyg.bildir(&m, None, false);
            self.acik = false;
        } else if !acik {
            self.acik = false;
        }
    }
}
