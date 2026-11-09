//! Küçük diyaloglar (Qt QInputDialog / QMessageBox karşılığı): ayrı, küçük bir pencere.
//! Bir anda tek diyalog açık olur; sonucu `goster` döndürür.

use eframe::egui::{self, RichText};

use super::bilesen;
use super::tema;

#[derive(Clone, Debug, PartialEq)]
pub enum Amac {
    SahneAdi(usize),
    KaynakAdi(String),
    KaynakMetni(String),
    YeniMetin,
    BeklemeYazisi,
    Bilgi,
    Cikis,
}

pub struct Diyalog {
    pub baslik: String,
    pub etiket: String,
    pub metin: String,
    pub amac: Amac,
    /// false: sadece bilgi (Tamam)
    pub girdi: bool,
    /// Evet / Hayır sorusu (Evet'e basılınca amaç döner)
    pub soru: bool,
    ilk: bool,
}

impl Diyalog {
    pub fn girdi(baslik: &str, etiket: &str, metin: &str, amac: Amac) -> Self {
        Diyalog { baslik: baslik.into(), etiket: etiket.into(), metin: metin.into(), amac, girdi: true, soru: false, ilk: true }
    }

    pub fn bilgi(baslik: &str, metin: &str) -> Self {
        Diyalog { baslik: baslik.into(), etiket: metin.into(), metin: String::new(), amac: Amac::Bilgi, girdi: false, soru: false, ilk: true }
    }

    pub fn soru(baslik: &str, metin: &str, amac: Amac) -> Self {
        Diyalog { baslik: baslik.into(), etiket: metin.into(), metin: String::new(), amac, girdi: false, soru: true, ilk: true }
    }
}

/// Açık diyaloğu gösterir. Tamam'a basılınca (amaç, metin) döner; kapanınca `acik` None olur.
pub fn goster(ctx: &egui::Context, acik: &mut Option<Diyalog>) -> Option<(Amac, String)> {
    let d = acik.as_mut()?;
    let mut sonuc = None;
    let mut kapat = false;
    let boyut = if d.girdi { [360.0, 150.0] } else if d.soru { [400.0, 150.0] } else { [380.0, 130.0] };
    let vp = egui::ViewportBuilder::default()
        .with_title(d.baslik.clone())
        .with_inner_size(boyut)
        .with_resizable(false)
        .with_minimize_button(false)
        .with_maximize_button(false)
        .with_always_on_top();
    ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("diyalog"), vp, |ui, _| {
        if ui.input(|i| i.viewport().close_requested()) {
            kapat = true;
        }
        egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(16)).show(ui, |ui| {
            ui.label(RichText::new(&d.etiket).font(tema::yazi(tema::GOVDE_PX)).color(tema::YAZI));
            ui.add_space(8.0);
            if d.girdi {
                let r = ui.add(egui::TextEdit::singleline(&mut d.metin).desired_width(f32::INFINITY).char_limit(120).margin(egui::vec2(8.0, 6.0)));
                if d.ilk {
                    r.request_focus();
                    d.ilk = false;
                }
                if r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                    sonuc = Some((d.amac.clone(), d.metin.clone()));
                }
            }
            ui.with_layout(egui::Layout::bottom_up(egui::Align::Max), |ui| {
                ui.horizontal(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if d.soru {
                            // Qt'deki gibi varsayılan "Hayır"
                            if bilesen::diyalog_dugmesi(ui, "Hayır", true).clicked() {
                                kapat = true;
                            }
                            if bilesen::diyalog_dugmesi(ui, "Evet", false).clicked() {
                                sonuc = Some((d.amac.clone(), String::new()));
                            }
                            return;
                        }
                        if d.girdi && bilesen::diyalog_dugmesi(ui, "Vazgeç", false).clicked() {
                            kapat = true;
                        }
                        if bilesen::diyalog_dugmesi(ui, "Tamam", true).clicked() {
                            if d.girdi {
                                sonuc = Some((d.amac.clone(), d.metin.clone()));
                            } else {
                                kapat = true;
                            }
                        }
                    });
                });
            });
            if ui.input(|i| i.key_pressed(egui::Key::Escape)) {
                kapat = true;
            }
        });
    });
    if sonuc.is_some() || kapat {
        *acik = None;
    }
    sonuc
}
