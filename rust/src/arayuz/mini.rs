//! Mini bar: her zaman üstte duran, sürüklenebilir küçük bar. Ekran yakalamaya girmez.
//! Python ui/mini_bar.py'nin karşılığı.
//!
//!   küçük (kayıtta) : tutma yeri · kırmızı nokta + süre · duraklat · genişlet ›
//!   genişletilmiş   : tutma yeri · Mikrofon · Sistem sesi · Kamera · Ekran görüntüsü | kayıt · küçült ‹
//!
//! Kayıt yokken genişletilmiş açılır; kayıt başlayınca kendiliğinden küçülür.

use std::sync::Arc;

use eframe::egui::{self, Color32, RichText, Stroke};

use rizeon::durum::Durum;
use rizeon::uygulama::{Komut, Uygulama};

use super::tema;

const BASLIK: &str = "RizeOn mini bar";

#[derive(Default)]
pub struct MiniBar {
    pub acik: bool,
    genis: bool,
    kayitta: bool,
    ilk_konum: Option<egui::Pos2>,
    gizlendi: bool,
    son_konum: Option<egui::Pos2>,
    surukleniyor: bool,
}

impl MiniBar {
    fn konum_yukle(uyg: &Uygulama) -> Option<egui::Pos2> {
        let a = uyg.ayarlar.lock().unwrap();
        let l = a.al("ui.mini_pos")?.as_array()?;
        Some(egui::pos2(l.first()?.as_f64()? as f32, l.get(1)?.as_f64()? as f32))
    }

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>, d: &Durum) {
        if !self.acik {
            if self.gizlendi {
                // kapanınca bir dahaki açılışta tekrar gizlensin (yeni pencere)
                self.gizlendi = false;
            }
            self.ilk_konum = None;
            return;
        }
        let kayitta = d.kayit == "açık";
        if self.ilk_konum.is_none() {
            // Açılışta: kayıt yokken genişletilmiş, kayıttayken küçük
            self.genis = !kayitta;
            self.kayitta = kayitta;
            self.ilk_konum = Some(Self::konum_yukle(uyg).unwrap_or(egui::pos2(500.0, 900.0)));
        }
        if kayitta != self.kayitta {
            self.kayitta = kayitta;
            if kayitta {
                self.genis = false; // kayıt başlayınca kendiliğinden küçülür
            }
        }
        let boyut = match (self.genis, kayitta) {
            (true, true) => [470.0, 46.0],
            (true, false) => [330.0, 46.0],
            (false, _) => [190.0, 42.0],
        };
        let mut vb = egui::ViewportBuilder::default()
            .with_title(BASLIK)
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_inner_size(boyut);
        if let Some(p) = self.ilk_konum {
            vb = vb.with_position(p);
        }
        let id = egui::ViewportId::from_hash_of("mini-bar");
        let mut kapat = false;
        let mut ana = false;
        ctx.show_viewport_immediate(id, vb, |ui, _sinif| {
            let vctx = ui.ctx().clone();
            vctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(egui::vec2(boyut[0], boyut[1])));
            if vctx.input(|i| i.viewport().close_requested()) {
                kapat = true;
            }
            if let Some(r) = vctx.input(|i| i.viewport().outer_rect) {
                self.son_konum = Some(r.min);
            }
            self.yakalamadan_gizle();
            let cerceve = egui::Frame::new()
                .fill(tema::YUZEN)
                .stroke(Stroke::new(1.0, Color32::from_white_alpha(24)))
                .corner_radius((boyut[1] / 2.0) as u8)
                .inner_margin(egui::Margin::symmetric(8, 5));
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ui, |ui| {
                cerceve.show(ui, |ui| {
                    ui.set_min_size(ui.available_size());
                    ui.horizontal_centered(|ui| {
                        ui.spacing_mut().item_spacing.x = 4.0;
                        ana |= self.tutma_yeri(ui, &vctx, uyg);
                        if self.genis {
                            self.araclar(ui, uyg, d);
                            ui.separator();
                        }
                        if kayitta {
                            self.kayit_grubu(ui, uyg, d);
                        } else if self.genis {
                            let hazir = uyg.kayitci.bitiyor();
                            let r = ui.add_enabled(!hazir, egui::Button::new(RichText::new("⏺ Kayıt").color(tema::KAYIT)).frame(false));
                            if r.on_hover_text("Kaydı başlat").clicked() {
                                let m = uyg.komut(Komut::Kayit);
                                if m.starts_with("Kayıt başlamadı") {
                                    uyg.bildir(&m, None, false);
                                }
                            }
                        }
                        // Kayıt yokken küçük bar boş kalırdı: küçültme sadece kayıtta var
                        if kayitta || !self.genis {
                            let (s, ipucu) = if self.genis { ("‹", "Küçült") } else { ("›", "Genişlet") };
                            if ui.add(egui::Button::new(RichText::new(s).size(16.0).color(tema::SOLUK)).frame(false)).on_hover_text(ipucu).clicked() {
                                self.genis = !self.genis;
                            }
                        }
                    });
                });
            });
            // sağ tık menüsü
            let tum = ui.max_rect();
            ui.interact(tum, egui::Id::unique("mini-sag"), egui::Sense::click()).context_menu(|ui| {
                if ui.button("Ana pencereyi göster").clicked() {
                    ana = true;
                    ui.close();
                }
                if kayitta && ui.button("Kaydı bitir").clicked() {
                    uyg.komut(Komut::Kayit);
                    ui.close();
                }
                if ui.button(if self.genis { "Küçült" } else { "Genişlet" }).clicked() {
                    self.genis = !self.genis;
                    ui.close();
                }
                if ui.button("Mini barı kapat").clicked() {
                    kapat = true;
                    ui.close();
                }
            });
        });
        if ana {
            uyg.arayuz_istekleri.lock().unwrap().push_back(Komut::AnaPencere);
            ctx.request_repaint();
        }
        if kapat {
            self.acik = false;
        }
        if kayitta {
            ctx.request_repaint_after(std::time::Duration::from_millis(500));
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

    /// Sürükleyince taşır; bırakınca konumu kaydeder. Çift tık: ana pencere.
    fn tutma_yeri(&mut self, ui: &mut egui::Ui, vctx: &egui::Context, uyg: &Uygulama) -> bool {
        let (r, cevap) = ui.allocate_exact_size(egui::vec2(12.0, 26.0), egui::Sense::click_and_drag());
        let p = ui.painter();
        for sira in 0..3 {
            for sutun in 0..2 {
                let c = egui::pos2(r.left() + 3.0 + sutun as f32 * 5.0, r.center().y - 6.0 + sira as f32 * 6.0);
                p.circle_filled(c, 1.3, tema::SOLUK);
            }
        }
        let cevap = cevap.on_hover_text("Taşı · çift tıkla: ana pencere");
        if cevap.drag_started() {
            vctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
            self.surukleniyor = true;
        }
        if self.surukleniyor && !ui.input(|i| i.pointer.any_down()) {
            self.surukleniyor = false;
            if let Some(k) = self.son_konum {
                uyg.ayarla("ui.mini_pos", serde_json::json!([k.x as i64, k.y as i64]));
                self.ilk_konum = Some(k);
            }
        }
        cevap.double_clicked()
    }

    fn arac(ui: &mut egui::Ui, simge: &str, acik: bool, kullanilabilir: bool, ipucu: &str) -> bool {
        let renk = if acik { tema::YAZI } else { tema::SOLUK };
        let mut b = egui::Button::new(RichText::new(simge).size(15.0).color(renk)).min_size(egui::vec2(34.0, 32.0));
        if !acik {
            b = b.fill(Color32::from_white_alpha(6));
        } else {
            b = b.frame(false);
        }
        let r = ui.add_enabled(kullanilabilir, b);
        if !acik {
            // kapalıyken çapraz çizgi
            let k = r.rect.shrink(9.0);
            ui.painter().line_segment([k.left_top(), k.right_bottom()], Stroke::new(1.5, tema::SOLUK));
        }
        let r = if kullanilabilir { r.on_hover_text(ipucu) } else { r.on_disabled_hover_text(ipucu) };
        r.clicked()
    }

    fn araclar(&mut self, ui: &mut egui::Ui, uyg: &Arc<Uygulama>, d: &Durum) {
        let mik = !d.mikrofon_sessiz;
        if Self::arac(ui, "🎤", mik, true, if mik { "Mikrofon açık, kapat" } else { "Mikrofon kapalı, aç" }) {
            uyg.komut(Komut::Mikrofon);
        }
        let sis = !d.sistem_sessiz;
        if Self::arac(ui, "🔊", sis, true, if sis { "Sistem sesi açık, kapat" } else { "Sistem sesi kapalı, aç" }) {
            uyg.komut(Komut::Sistem);
        }
        let sahnede = uyg.k.kamera_sahnede();
        let kam = uyg.kamera_gorunur_acik();
        // Sahnede kamera yokken "açık" görünmesin, basılamasın (seni çekiyor sanılmasın)
        let ipucu = if !sahnede {
            "Bu sahnede kamera yok"
        } else if kam {
            "Kamera açık, kapat"
        } else {
            "Kamera kapalı, aç"
        };
        if Self::arac(ui, "📷", kam, sahnede, ipucu) {
            uyg.komut(Komut::Kamera);
        }
        if ui
            .add(egui::Button::new(RichText::new("📸").size(15.0)).frame(false).min_size(egui::vec2(34.0, 32.0)))
            .on_hover_text("Ekran görüntüsü al")
            .clicked()
        {
            let m = uyg.komut(Komut::EkranGoruntusu);
            if m.starts_with("Ekran görüntüsü kaydedilemedi") {
                uyg.bildir(&m, None, false);
            }
        }
    }

    fn kayit_grubu(&mut self, ui: &mut egui::Ui, uyg: &Arc<Uygulama>, d: &Durum) {
        let durak = d.kayit_duraklatildi;
        let (r, _) = ui.allocate_exact_size(egui::vec2(10.0, 10.0), egui::Sense::hover());
        ui.painter().circle_filled(r.center(), 4.5, if durak { tema::SOLUK } else { tema::KAYIT });
        let sn = d.kayit_suresi;
        let sure = if sn >= 3600 { format!("{}:{:02}:{:02}", sn / 3600, sn / 60 % 60, sn % 60) } else { format!("{:02}:{:02}", sn / 60, sn % 60) };
        ui.label(RichText::new(sure).monospace().color(if durak { tema::SOLUK } else { tema::YAZI }));
        let (s, ipucu) = if durak { ("▶", "Devam et") } else { ("⏸", "Duraklat") };
        if ui.add(egui::Button::new(RichText::new(s).size(14.0)).frame(false).min_size(egui::vec2(30.0, 30.0))).on_hover_text(ipucu).clicked() {
            uyg.komut(Komut::KayitDuraklat);
        }
        if self.genis
            && ui
                .add(egui::Button::new(RichText::new("⏹").size(14.0)).frame(false).min_size(egui::vec2(30.0, 30.0)))
                .on_hover_text("Kaydı bitir")
                .clicked()
        {
            uyg.komut(Komut::Kayit);
        }
    }
}
