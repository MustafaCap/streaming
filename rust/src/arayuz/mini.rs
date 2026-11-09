//! Mini bar: her zaman üstte duran, sürüklenebilir küçük bar. Ekran yakalamaya girmez.
//! Python ui/mini_bar.py'nin karşılığı.
//!
//!   kayıtta (küçük)   : tutma yeri · kırmızı nokta + süre · duraklat · genişlet ›
//!   duraklatıldı      : gri nokta, soluk süre, ▶
//!   genişletilmiş     : tutma yeri · Mikrofon · Sistem sesi · Kamera · Bölge · Kalem · Ekran görüntüsü |
//!                       kayıt grubu (nokta + süre · duraklat · bitir) ya da Kayıt · küçült ‹
//!
//! Kayıt yokken genişletilmiş açılır; kayıt başlayınca kendiliğinden küçülür. Kapalı mikrofon ve
//! kamera sönük gri zemin + çapraz çizgili simgeyle görünür. Aktif sahnede kamera kaynağı yoksa
//! Kamera düğmesi kapalı görünür ve basılamaz. Panik ve "Son 15 sn" barda yok (kısayolları var).
//! Sağ tık: ana pencere, kaydı bitir. Tutma yerine çift tık: ana pencere.

use std::sync::Arc;

use eframe::egui::{self, Pos2, Stroke, Vec2};

use rizeon::durum::Durum;
use rizeon::uygulama::{Komut, Uygulama};

use super::bilesen::{self, ipucu, SimgeDugme};
use super::tema::{self, beyaz};

const BASLIK: &str = "RizeOn mini bar";
const ARAC: f32 = 36.0;

#[derive(Default)]
pub struct MiniBar {
    pub acik: bool,
    genis: bool,
    kayitta: bool,
    ilk_konum: Option<Pos2>,
    gizlendi: bool,
    son_konum: Option<Pos2>,
    surukleniyor: bool,
}

fn tus(uyg: &Uygulama, komut: &str) -> String {
    let a = uyg.ayarlar.lock().unwrap();
    a.veri.get("hotkeys").and_then(|h| h.get(komut)).and_then(|v| v.as_str()).map(rizeon::kisayol::tus_metni).unwrap_or_default()
}

impl MiniBar {
    fn konum_yukle(uyg: &Uygulama) -> Option<Pos2> {
        let a = uyg.ayarlar.lock().unwrap();
        let l = a.al("ui.mini_pos")?.as_array()?;
        let p = egui::pos2(l.first()?.as_f64()? as f32, l.get(1)?.as_f64()? as f32);
        // kayıtlı yer artık bir ekranın içinde değilse (monitör çıkarıldı) varsayılana dön
        let icinde = rizeon::yakalama::monitorler().iter().any(|m| {
            let (x, y) = (p.x as i32, p.y as i32);
            x >= m.sol && y >= m.ust && x < m.sol + m.w as i32 && y < m.ust + m.h as i32
        });
        icinde.then_some(p)
    }

    /// Ana ekranın altında ortalı (görev çubuğunun üstünde).
    fn varsayilan_konum(ctx: &egui::Context, boyut: Vec2) -> Pos2 {
        let ppp = ctx.native_pixels_per_point().unwrap_or(1.0).max(0.5);
        match rizeon::yakalama::monitorler().first() {
            Some(m) => egui::pos2(
                m.sol as f32 / ppp + (m.w as f32 / ppp - boyut.x) / 2.0,
                (m.ust + m.h as i32) as f32 / ppp - 48.0 - boyut.y - 60.0,
            ),
            None => egui::pos2(500.0, 900.0),
        }
    }

    /// Barın boyutu (Python'daki yerleşimin ölçüleriyle): kenar 4, aralık 2, kenarlık 1.
    fn boyut(&self, ctx: &egui::Context, d: &Durum) -> Vec2 {
        let p = egui::Painter::new(ctx.clone(), egui::LayerId::background(), egui::Rect::EVERYTHING);
        let kayitta = d.kayit == "açık";
        let boy = if self.genis { 36.0 } else { 32.0 };
        let mut parcalar: Vec<f32> = vec![20.0];
        if self.genis {
            parcalar.push(6.0 * ARAC + 5.0 * 2.0 + 2.0 + 13.0);
            if !kayitta {
                parcalar.push(ARAC);
            }
        }
        if kayitta {
            parcalar.push(bilesen::kayit_grubu_genisligi(&p, d.kayit_suresi, boy, self.genis, false));
        }
        if kayitta || !self.genis {
            parcalar.push(boy);
        }
        let w = 1.0 + 4.0 + parcalar.iter().sum::<f32>() + 2.0 * (parcalar.len() as f32 - 1.0) + 4.0 + 1.0;
        Vec2::new(w.ceil(), if self.genis { 44.0 } else { 40.0 })
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
        let boyut = {
            if self.ilk_konum.is_none() {
                // Açılışta: kayıt yokken genişletilmiş, kayıttayken küçük
                self.genis = !kayitta;
                self.kayitta = kayitta;
            }
            if kayitta != self.kayitta {
                self.kayitta = kayitta;
                if kayitta {
                    self.genis = false; // kayıt başlayınca kendiliğinden küçülür
                }
            }
            self.boyut(ctx, d)
        };
        if self.ilk_konum.is_none() {
            self.ilk_konum = Some(Self::konum_yukle(uyg).unwrap_or_else(|| Self::varsayilan_konum(ctx, boyut)));
        }
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
        let mut ana = false;
        ctx.show_viewport_immediate(id, vb, |ui, _sinif| {
            let vctx = ui.ctx().clone();
            vctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(boyut));
            if vctx.input(|i| i.viewport().close_requested()) {
                vctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            }
            if let Some(r) = vctx.input(|i| i.viewport().outer_rect) {
                self.son_konum = Some(r.min);
            }
            self.yakalamadan_gizle();
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ui, |ui| {
                let r = ui.max_rect();
                let yaricap = (r.height() / 2.0).floor();
                ui.painter().rect(r.shrink(0.5), yaricap, tema::YUZEN, Stroke::new(1.0, beyaz(tema::A_KENARLIK)), egui::StrokeKind::Middle);
                // sağ tık menüsü (arkaya; düğmeler üstte kalır)
                let arka = ui.interact(r, egui::Id::unique("mini-sag"), egui::Sense::click());
                egui::Popup::context_menu(&arka).frame(bilesen::menu_cercevesi()).show(|ui| {
                    ui.set_min_width(180.0);
                    if bilesen::menu_satiri(ui, "Ana pencereyi göster", true).clicked() {
                        ana = true;
                    }
                    if kayitta && bilesen::menu_satiri(ui, "Kaydı bitir", true).clicked() {
                        uyg.komut(Komut::Kayit);
                    }
                    if bilesen::menu_satiri(ui, if self.genis { "Küçült" } else { "Genişlet" }, true).clicked() {
                        self.genis = !self.genis;
                    }
                });
                let ic = r.shrink2(Vec2::new(5.0, 1.0));
                let mut ui = ui.new_child(egui::UiBuilder::new().max_rect(ic).layout(egui::Layout::left_to_right(egui::Align::Center)));
                let ui = &mut ui;
                ui.spacing_mut().item_spacing.x = 2.0;
                ana |= self.tutma_yeri(ui, &vctx, uyg);
                if self.genis {
                    self.araclar(ui, uyg, d);
                    let (a, _) = ui.allocate_exact_size(Vec2::new(13.0, 20.0), egui::Sense::hover());
                    let x = a.left() + 6.5;
                    ui.painter().line_segment([Pos2::new(x, a.top()), Pos2::new(x, a.bottom())], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
                }
                let boy = if self.genis { 36.0 } else { 32.0 };
                if kayitta {
                    let s = bilesen::kayit_grubu(ui, d.kayit_suresi, d.kayit_duraklatildi, boy, self.genis, false, &tus(uyg, "kayit.duraklat"), &tus(uyg, "kayit.ac_kapat"));
                    if s.duraklat {
                        uyg.komut(Komut::KayitDuraklat);
                    }
                    if s.bitir {
                        uyg.komut(Komut::Kayit);
                    }
                } else if self.genis {
                    let hazir = uyg.kayitci.bitiyor();
                    let r = SimgeDugme::new("kayit").boyut(ARAC, 16.0).etkin(!hazir).goster(ui).on_hover_text(ipucu("Kaydı başlat", &tus(uyg, "kayit.ac_kapat")));
                    if r.clicked() {
                        let m = uyg.komut(Komut::Kayit);
                        if m.starts_with("Kayıt başlamadı") {
                            uyg.bildir(&m, None, false);
                        }
                    }
                }
                // Kayıt yokken küçük bar boş kalırdı: küçültme sadece kayıtta var
                if kayitta || !self.genis {
                    let (s, ad) = if self.genis { ("geri", "Küçült") } else { ("ileri", "Genişlet") };
                    if SimgeDugme::new(s).boyut(boy, 14.0).renk(tema::SOLUK).goster(ui).on_hover_text(ad).clicked() {
                        self.genis = !self.genis;
                    }
                }
            });
        });
        if ana {
            uyg.arayuz_istekleri.lock().unwrap().push_back(Komut::AnaPencere);
            ctx.request_repaint();
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
        let cevap = bilesen::tutma_yeri(ui, 4.0).on_hover_text("Taşı · çift tıkla: ana pencere");
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

    fn araclar(&mut self, ui: &mut egui::Ui, uyg: &Arc<Uygulama>, d: &Durum) {
        let arac = |ui: &mut egui::Ui, simge: &'static str, kapali: bool, secili: bool, etkin: bool, ad: String| -> bool {
            SimgeDugme::new(simge).boyut(ARAC, 16.0).kapali(kapali).secili(secili).etkin(etkin).goster(ui).on_hover_text(ad).clicked()
        };
        let mik = d.mikrofon_sessiz;
        if arac(ui, "mikrofon", mik, false, true, ipucu(if mik { "Mikrofon kapalı, aç" } else { "Mikrofon açık, kapat" }, &tus(uyg, "ses.mikrofon"))) {
            uyg.komut(Komut::Mikrofon);
        }
        let sis = d.sistem_sessiz;
        if arac(ui, "ses", sis, false, true, ipucu(if sis { "Sistem sesi kapalı, aç" } else { "Sistem sesi açık, kapat" }, &tus(uyg, "ses.sistem"))) {
            uyg.komut(Komut::Sistem);
        }
        let sahnede = uyg.k.kamera_sahnede();
        let kam = uyg.kamera_gorunur_acik();
        // Sahnede kamera yokken "açık" görünmesin, basılamasın (seni çekiyor sanılmasın)
        let ad = if !sahnede {
            "Bu sahnede kamera yok".to_string()
        } else {
            ipucu(if kam { "Kamera açık, kapat" } else { "Kamera kapalı, aç" }, &tus(uyg, "kamera.ac_kapat"))
        };
        if arac(ui, "kamera", !kam, false, sahnede, ad) {
            uyg.komut(Komut::Kamera);
        }
        if arac(ui, "bolge", false, !d.bolge.is_empty(), true, ipucu("Bölge seç", &tus(uyg, "bolge.sec"))) {
            let m = uyg.komut(Komut::Bolge);
            if !m.is_empty() {
                uyg.bildir(&m, None, false);
            }
        }
        if arac(ui, "kalem", false, d.kalem_acik, true, ipucu("Kalem", &tus(uyg, "kalem.ac_kapat"))) {
            uyg.komut(Komut::Kalem);
        }
        if arac(ui, "foto", false, false, true, ipucu("Ekran görüntüsü al", &tus(uyg, "ekran.goruntusu"))) {
            let m = uyg.komut(Komut::EkranGoruntusu);
            if m.starts_with("Ekran görüntüsü kaydedilemedi") {
                uyg.bildir(&m, None, false);
            }
        }
    }
}
