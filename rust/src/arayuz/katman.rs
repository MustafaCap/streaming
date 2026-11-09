//! Birleşik bölge + kalem katmanı (Python ui/drawing_overlay.py, ui/region_overlay.py).
//!
//! Yakalanan monitörün üstüne saydam, her zaman üstte bir pencere açılır. Ekran yakalamaya girmez;
//! karşı taraf çizimleri video hattının çıkış karesinde görür (tam ekran oyunda da).
//!
//!   bölge : ekran kararır, fareyle kutu çizilir; bırakınca yayına uygulanır. Esc / sağ tık: vazgeç.
//!   kalem : üst ortada kalem barı (Kalem, Fosforlu, Ok, Kare, Yazı, Lazer, Silgi · renk · kalınlık ·
//!           Temizle · Bitti). 1-7 araç, Ctrl+Z geri al, Del hepsini sil, Esc çık.

use std::sync::Arc;

use eframe::egui::{self, Color32, Pos2, Rect, RichText, Stroke};

use rizeon::cizim::{self, CizimDeposu};
use rizeon::uygulama::Uygulama;
use rizeon::yakalama::Monitor;

use super::tema;

const BASLIK: &str = "RizeOn katman";

#[derive(Clone, Copy, PartialEq)]
enum Mod {
    Bolge,
    Kalem,
}

pub struct Katman {
    mod_: Option<Mod>,
    monitor: Option<Monitor>,
    bas: Option<Pos2>,
    son: Option<Pos2>,
    tur: usize,
    renk: usize,
    kalinlik: usize,
    yazi: Option<(Pos2, String)>,
    gizlendi: bool,
}

impl Default for Katman {
    fn default() -> Self {
        Katman { mod_: None, monitor: None, bas: None, son: None, tur: 0, renk: cizim::VARSAYILAN_RENK, kalinlik: 1, yazi: None, gizlendi: false }
    }
}

fn renk32([r, g, b]: [u8; 3], a: u8) -> Color32 {
    Color32::from_rgba_unmultiplied(r, g, b, a)
}

impl Katman {
    pub fn kalem_acik(&self) -> bool {
        self.mod_ == Some(Mod::Kalem)
    }

    fn monitoru_al(uyg: &Uygulama) -> Option<Monitor> {
        let n = uyg.k.ayar.lock().unwrap().monitor;
        let l = rizeon::yakalama::monitorler();
        l.get(n).or(l.first()).cloned()
    }

    pub fn bolge_sec(&mut self, uyg: &Uygulama) {
        self.monitor = Self::monitoru_al(uyg);
        self.mod_ = Some(Mod::Bolge);
        self.bas = None;
        self.son = None;
    }

    pub fn kalem_ac_kapat(&mut self, uyg: &Uygulama) {
        if self.kalem_acik() {
            self.kapat(uyg);
        } else {
            self.monitor = Self::monitoru_al(uyg);
            self.mod_ = Some(Mod::Kalem);
            uyg.depo.guncelle(|d| d.kalem_acik = true);
        }
    }

    fn kapat(&mut self, uyg: &Uygulama) {
        if self.mod_ == Some(Mod::Kalem) {
            uyg.depo.guncelle(|d| d.kalem_acik = false);
            if uyg.ayarlar.lock().unwrap().mantik("pen.clear_on_close", true) {
                uyg.k.cizim.temizle();
            }
        }
        self.mod_ = None;
        self.yazi = None;
        self.gizlendi = false;
    }

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) {
        let Some(mod_) = self.mod_ else { return };
        let Some(m) = self.monitor.clone() else {
            uyg.bildir("Monitör bulunamadı", None, false);
            self.mod_ = None;
            return;
        };
        let ppp = ctx.native_pixels_per_point().unwrap_or(ctx.pixels_per_point()).max(0.5);
        let vb = egui::ViewportBuilder::default()
            .with_title(BASLIK)
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_position([m.sol as f32 / ppp, m.ust as f32 / ppp])
            .with_inner_size([m.w as f32 / ppp, m.h as f32 / ppp]);
        let mut kapat = false;
        ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("katman"), vb, |ui, _| {
            let vctx = ui.ctx().clone();
            self.yakalamadan_gizle();
            let ppp = vctx.pixels_per_point();
            let dis = vctx.input(|i| i.viewport().outer_rect).map(|r| r.min).unwrap_or(Pos2::ZERO);
            // nokta (pencere içi, point) -> monitöre göre fiziksel piksel
            let fiz = |p: Pos2| egui::pos2((dis.x + p.x) * ppp - m.sol as f32, (dis.y + p.y) * ppp - m.ust as f32);
            let geri = |q: Pos2| egui::pos2((q.x + m.sol as f32) / ppp - dis.x, (q.y + m.ust as f32) / ppp - dis.y);
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ui, |ui| {
                let alan = ui.max_rect();
                let cevap = ui.allocate_rect(alan, egui::Sense::click_and_drag());
                match mod_ {
                    Mod::Bolge => kapat |= self.bolge_ciz(ui, &cevap, alan, &fiz, &m, uyg),
                    Mod::Kalem => kapat |= self.kalem_ciz(ui, &vctx, &cevap, alan, &fiz, &geri, &m, uyg),
                }
            });
            if vctx.input(|i| i.viewport().close_requested()) {
                kapat = true;
            }
            vctx.request_repaint_after(std::time::Duration::from_millis(16));
        });
        if kapat {
            self.kapat(uyg);
        }
    }

    #[cfg(windows)]
    fn yakalamadan_gizle(&mut self) {
        if !self.gizlendi {
            if let Some(h) = rizeon::win::pencere_bul(BASLIK) {
                rizeon::win::yakalamadan_gizle(h, true);
                self.gizlendi = true;
            }
        }
    }

    #[cfg(not(windows))]
    fn yakalamadan_gizle(&mut self) {}

    fn ipucu(ui: &egui::Ui, alan: Rect, metin: &str) {
        let p = ui.painter();
        let konum = alan.center_top() + egui::vec2(0.0, 28.0);
        let gal = p.layout_no_wrap(metin.to_string(), egui::FontId::proportional(14.0), tema::YAZI);
        let r = Rect::from_center_size(konum + egui::vec2(0.0, gal.size().y / 2.0), gal.size() + egui::vec2(24.0, 12.0));
        p.rect_filled(r, 8.0, tema::YUZEN);
        p.galley(r.center() - gal.size() / 2.0, gal, tema::YAZI);
    }

    fn bolge_ciz(&mut self, ui: &egui::Ui, cevap: &egui::Response, alan: Rect, fiz: &dyn Fn(Pos2) -> Pos2, m: &Monitor, uyg: &Uygulama) -> bool {
        let karartma = Color32::from_black_alpha(110);
        let p = ui.painter();
        if cevap.drag_started() {
            self.bas = cevap.interact_pointer_pos();
        }
        if cevap.dragged() {
            self.son = cevap.interact_pointer_pos();
        }
        let secim = match (self.bas, self.son) {
            (Some(a), Some(b)) => Some(Rect::from_two_pos(a, b)),
            _ => None,
        };
        match secim {
            Some(s) => {
                // seçimin dışı kararır
                for r in [
                    Rect::from_min_max(alan.min, egui::pos2(alan.max.x, s.min.y)),
                    Rect::from_min_max(egui::pos2(alan.min.x, s.max.y), alan.max),
                    Rect::from_min_max(egui::pos2(alan.min.x, s.min.y), egui::pos2(s.min.x, s.max.y)),
                    Rect::from_min_max(egui::pos2(s.max.x, s.min.y), egui::pos2(alan.max.x, s.max.y)),
                ] {
                    p.rect_filled(r, 0.0, karartma);
                }
                p.rect_stroke(s, 0.0, Stroke::new(1.0, Color32::WHITE), egui::StrokeKind::Outside);
                let (a, b) = (fiz(s.min), fiz(s.max));
                let boyut = format!("{:.0} × {:.0}", b.x - a.x, b.y - a.y);
                p.text(s.left_bottom() + egui::vec2(0.0, 6.0), egui::Align2::LEFT_TOP, boyut, egui::FontId::proportional(13.0), Color32::WHITE);
            }
            None => {
                p.rect_filled(alan, 0.0, karartma);
            }
        }
        Self::ipucu(ui, alan, "Göstermek istediğin alanı sürükle · Esc: vazgeç");
        if cevap.drag_stopped() {
            if let Some(s) = secim {
                let (a, b) = (fiz(s.min), fiz(s.max));
                let (x0, y0) = (a.x.clamp(0.0, m.w as f32), a.y.clamp(0.0, m.h as f32));
                let (x1, y1) = (b.x.clamp(0.0, m.w as f32), b.y.clamp(0.0, m.h as f32));
                if x1 - x0 >= 16.0 && y1 - y0 >= 16.0 {
                    let mesaj = uyg.bolge_ayarla((x0 as f64, y0 as f64, (x1 - x0) as f64, (y1 - y0) as f64));
                    uyg.bildir(&mesaj, None, false);
                    return true;
                }
            }
            self.bas = None;
            self.son = None;
        }
        cevap.secondary_clicked() || ui.input(|i| i.key_pressed(egui::Key::Escape))
    }

    #[allow(clippy::too_many_arguments)]
    fn kalem_ciz(
        &mut self,
        ui: &mut egui::Ui,
        vctx: &egui::Context,
        cevap: &egui::Response,
        alan: Rect,
        fiz: &dyn Fn(Pos2) -> Pos2,
        geri: &dyn Fn(Pos2) -> Pos2,
        m: &Monitor,
        uyg: &Arc<Uygulama>,
    ) -> bool {
        let depo: &CizimDeposu = &uyg.k.cizim;
        depo.oran_ayarla(m.w as f32 / m.h.max(1) as f32);
        let oran = |p: Pos2| {
            let q = fiz(p);
            ((q.x / m.w as f32).clamp(0.0, 1.0), (q.y / m.h as f32).clamp(0.0, 1.0))
        };
        let tur = cizim::TURLER[self.tur];
        let renk = cizim::RENKLER[self.renk];
        let carpan = cizim::KALINLIK_CARPANI[self.kalinlik];
        let mut kapat = false;
        // Fare ile çizim (yazı aracı hariç)
        if self.yazi.is_none() {
            if tur == "yazi" {
                if cevap.clicked() {
                    if let Some(p) = cevap.interact_pointer_pos() {
                        self.yazi = Some((p, String::new()));
                    }
                }
            } else {
                if cevap.drag_started() || (cevap.clicked() && tur != "lazer") {
                    if let Some(p) = cevap.interact_pointer_pos() {
                        let (x, y) = oran(p);
                        depo.basla(tur, renk, x, y, carpan);
                    }
                }
                if cevap.dragged() {
                    if let Some(p) = cevap.interact_pointer_pos() {
                        let (x, y) = oran(p);
                        depo.surukle(x, y);
                    }
                }
                if cevap.drag_stopped() || cevap.clicked() {
                    depo.bitir();
                }
            }
        }
        // Çizimleri bu katmanda da göster (sen görürsün; karşı taraf video karesinde görür)
        let (sekiller, lazer, lazer_rengi) = depo.anlik();
        let p = ui.painter();
        let monitore = |x: f32, y: f32| geri(egui::pos2(x * m.w as f32, y * m.h as f32));
        let olcek = m.h as f32 / vctx.pixels_per_point();
        for s in &sekiller {
            let alfa = if s.tur == "fosforlu" { (cizim::FOSFOR_SAYDAMLIK * 255.0) as u8 } else { 255 };
            let c = renk32(s.renk, alfa);
            let kalin = (s.kalinlik() * olcek).max(1.0);
            let pts: Vec<Pos2> = s.noktalar.iter().map(|(x, y)| monitore(*x, *y)).collect();
            match s.tur {
                "kalem" | "fosforlu" => {
                    if pts.len() == 1 {
                        p.circle_filled(pts[0], kalin / 2.0, c);
                    } else {
                        p.add(egui::Shape::line(pts, Stroke::new(kalin, c)));
                    }
                }
                "ok" => {
                    p.arrow(pts[0], pts[1] - pts[0], Stroke::new(kalin, c));
                }
                "kare" => {
                    p.rect_stroke(Rect::from_two_pos(pts[0], pts[1]), 0.0, Stroke::new(kalin, c), egui::StrokeKind::Middle);
                }
                "yazi" => {
                    p.text(pts[0], egui::Align2::LEFT_TOP, &s.metin, egui::FontId::proportional((s.kalinlik() * olcek).max(8.0)), c);
                }
                _ => {}
            }
        }
        for w in lazer.windows(2) {
            let omur = 1.0 - (w[1].2 / cizim::LAZER_OMRU).clamp(0.0, 1.0);
            let kalin = (cizim::kalinlik("lazer") * olcek).max(2.0) * (0.4 + 0.6 * omur);
            p.line_segment([monitore(w[0].0, w[0].1), monitore(w[1].0, w[1].1)], Stroke::new(kalin, renk32(lazer_rengi, (omur * 255.0) as u8)));
        }
        // Yazı girişi
        if let Some((konum, metin)) = &mut self.yazi {
            let boy = (cizim::kalinlik("yazi") * carpan * olcek).max(10.0);
            let mut bitti = None;
            egui::Area::new(egui::Id::unique("kalem-yazi")).fixed_pos(*konum).show(vctx, |ui| {
                let r = ui.add(
                    egui::TextEdit::singleline(metin)
                        .font(egui::FontId::proportional(boy))
                        .text_color(renk32(renk, 255))
                        .background_color(Color32::from_black_alpha(60))
                        .desired_width(m.w as f32 / 3.0)
                        .hint_text("Yaz, Enter"),
                );
                r.request_focus();
                if ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                    bitti = Some(true);
                } else if ui.input(|i| i.key_pressed(egui::Key::Escape)) {
                    bitti = Some(false);
                }
            });
            if let Some(kaydet) = bitti {
                if kaydet {
                    let (x, y) = oran(*konum);
                    depo.yazi_ekle(renk, x, y, metin, carpan);
                }
                self.yazi = None;
            }
        } else {
            // Kısayollar (sadece katman odaktayken)
            let (num, geri_al, sil, cik) = ui.input(|i| {
                let num = [egui::Key::Num1, egui::Key::Num2, egui::Key::Num3, egui::Key::Num4, egui::Key::Num5, egui::Key::Num6, egui::Key::Num7]
                    .iter()
                    .position(|k| i.key_pressed(*k));
                (num, i.modifiers.command && i.key_pressed(egui::Key::Z), i.key_pressed(egui::Key::Delete), i.key_pressed(egui::Key::Escape))
            });
            if let Some(n) = num {
                self.tur = n;
            }
            if geri_al {
                depo.geri_al();
            }
            if sil {
                depo.temizle();
            }
            kapat |= cik;
        }
        // Kalem barı
        egui::Area::new(egui::Id::unique("kalem-bari")).anchor(egui::Align2::CENTER_TOP, egui::vec2(0.0, 16.0)).show(vctx, |ui| {
            egui::Frame::new()
                .fill(tema::YUZEN)
                .stroke(Stroke::new(1.0, Color32::from_white_alpha(24)))
                .corner_radius(20)
                .inner_margin(egui::Margin::symmetric(12, 6))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        for (i, ad) in cizim::TUR_ADLARI.iter().enumerate() {
                            if ui.add(egui::Button::new(*ad).selected(self.tur == i)).on_hover_text(format!("{}", i + 1)).clicked() {
                                self.tur = i;
                                self.yazi = None;
                            }
                        }
                        ui.separator();
                        for (i, r) in cizim::RENKLER.iter().enumerate() {
                            let (alan, c) = ui.allocate_exact_size(egui::vec2(20.0, 20.0), egui::Sense::click());
                            ui.painter().circle_filled(alan.center(), 8.0, renk32(*r, 255));
                            if self.renk == i {
                                ui.painter().circle_stroke(alan.center(), 10.0, Stroke::new(1.5, Color32::WHITE));
                            }
                            if c.on_hover_text(cizim::RENK_ADLARI[i]).clicked() {
                                self.renk = i;
                            }
                        }
                        ui.separator();
                        for (i, ad) in cizim::KALINLIK_ADLARI.iter().enumerate() {
                            if ui.add(egui::Button::new(RichText::new(*ad).small()).selected(self.kalinlik == i)).clicked() {
                                self.kalinlik = i;
                            }
                        }
                        ui.separator();
                        if ui.button("Geri al").on_hover_text("Ctrl+Z").clicked() {
                            depo.geri_al();
                        }
                        if ui.button("Temizle").on_hover_text("Del").clicked() {
                            depo.temizle();
                        }
                        if ui.button("Bitti").on_hover_text("Esc").clicked() {
                            kapat = true;
                        }
                    });
                });
        });
        let _ = alan;
        kapat
    }
}
