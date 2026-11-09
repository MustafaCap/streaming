//! Küçük pencereler (Python ui/hakkinda.py, ui/yardim.py, ui/pencere_secici.py, ui/toast.py):
//! Hakkında, "Nasıl düzeltilir?" yardımı, pencere seçici ve sağ alttaki bildirim.
//! Hepsi ayrı, küçük işletim sistemi pencereleridir ve ekran yakalamaya girmez.

use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui::{self, text::LayoutJob, Align2, Color32, FontId, Pos2, Rect, Sense, Stroke, TextFormat, Ui, Vec2};

use rizeon::uygulama::{Bildirim, BildirimEylemi, Uygulama};

use super::bilesen;
use super::simge;
use super::tema::{self, beyaz};

/// Penceresini başlığıyla bulup ekran yakalamadan gizler (bir kez).
fn yakalamadan_gizle(baslik: &str, yapildi: &mut bool) {
    #[cfg(windows)]
    if !*yapildi {
        if let Some(h) = rizeon::win::pencere_bul(baslik) {
            rizeon::win::yakalamadan_gizle(h, true);
            *yapildi = true;
        }
    }
    let _ = (baslik, yapildi);
}

// ------------------------------------------------------------------ zengin metin

/// Qt'deki küçük HTML parçalarının karşılığı. Satır biçimi:
///   "### Başlık"  · "1. madde" (numaralı liste) · boş satır: paragraf arası · "**kalın**", "_eğik_"
/// Aynı paragraftaki ardışık satırlar alt satıra geçer (<br>).
pub fn zengin_metin(ui: &mut Ui, metin: &str, genislik: f32) {
    ui.vertical(|ui| {
        ui.spacing_mut().item_spacing.y = 0.0;
        zengin_ic(ui, metin, genislik);
    });
}

fn zengin_ic(ui: &mut Ui, metin: &str, genislik: f32) {
    let paragraflar: Vec<Vec<&str>> = metin.split("\n\n").map(|p| p.lines().filter(|l| !l.trim().is_empty()).collect()).filter(|p: &Vec<&str>| !p.is_empty()).collect();
    for (i, p) in paragraflar.iter().enumerate() {
        if i > 0 {
            ui.add_space(12.0);
        }
        if let Some(b) = p[0].strip_prefix("### ") {
            galeri(ui, satir_isi(b, 16.0, genislik, true));
            continue;
        }
        if p.iter().all(|l| l.split_once(". ").is_some_and(|(n, _)| n.parse::<u32>().is_ok())) {
            for l in p {
                let (n, govde) = l.split_once(". ").unwrap();
                let g = ui.painter().layout_job(satir_isi(govde, tema::GOVDE_PX, genislik - 40.0, false));
                let (r, _) = ui.allocate_exact_size(Vec2::new(genislik, g.size().y), Sense::hover());
                ui.painter().text(Pos2::new(r.left() + 34.0, r.top()), Align2::RIGHT_TOP, format!("{n}."), tema::yazi(tema::GOVDE_PX), tema::YAZI);
                ui.painter().galley(Pos2::new(r.left() + 40.0, r.top()), g, tema::YAZI);
            }
            continue;
        }
        galeri(ui, satir_isi(&p.join("\n"), tema::GOVDE_PX, genislik, false));
    }
}

fn galeri(ui: &mut Ui, job: LayoutJob) {
    let g = ui.painter().layout_job(job);
    let (r, _) = ui.allocate_exact_size(g.size(), Sense::hover());
    ui.painter().galley(r.min, g, tema::YAZI);
}

fn satir_isi(metin: &str, px: f32, genislik: f32, baslik: bool) -> LayoutJob {
    let mut job = LayoutJob { wrap: egui::text::TextWrapping { max_width: genislik, ..Default::default() }, ..Default::default() };
    let mut kalin = baslik;
    let mut egik = false;
    let mut parca = String::new();
    let ekle = |job: &mut LayoutJob, s: &mut String, kalin: bool, egik: bool| {
        if s.is_empty() {
            return;
        }
        let font = if kalin { tema::kalin(px) } else { FontId::proportional(px) };
        job.append(s, 0.0, TextFormat { font_id: font, color: if kalin { tema::BEYAZ } else { tema::YAZI }, italics: egik, line_height: Some((px * 1.25).round()), ..Default::default() });
        s.clear();
    };
    let mut kalan = metin;
    while !kalan.is_empty() {
        if let Some(r) = kalan.strip_prefix("**") {
            ekle(&mut job, &mut parca, kalin, egik);
            kalin = !kalin || baslik;
            kalan = r;
        } else if let Some(r) = kalan.strip_prefix('_').filter(|_| parca.is_empty() || parca.ends_with(' ') || egik) {
            ekle(&mut job, &mut parca, kalin, egik);
            egik = !egik;
            kalan = r;
        } else {
            let c = kalan.chars().next().unwrap();
            parca.push(c);
            kalan = &kalan[c.len_utf8()..];
        }
    }
    ekle(&mut job, &mut parca, kalin, egik);
    job
}

fn kapat_istendi(ui: &Ui) -> bool {
    ui.input(|i| i.viewport().close_requested() || i.key_pressed(egui::Key::Escape))
}

// ------------------------------------------------------------------ Hakkında

pub const KAYNAK: &str = "https://github.com/MustafaCap/streaming";

pub fn hakkinda_metni() -> String {
    format!(
        "### RizeOn {}\n\n\
         Telif hakkı © 2026 Mustafa\n\n\
         Bu program özgür yazılımdır. **GNU Genel Kamu Lisansı sürüm 3 (GPLv3)** koşullarıyla \
         kullanabilir, değiştirebilir ve dağıtabilirsiniz. Program **hiçbir garanti olmadan**, \
         \"olduğu gibi\" sunulur.\n\n\
         Kaynak kod ve yeni sürümler:\n{KAYNAK}\n\n\
         Uygulama internete bağlanmaz. Kullandığı açık kaynak kütüphanelerin (egui, FFmpeg ve \
         diğerleri) lisansları _lisanslar_ klasöründedir.",
        rizeon::surum::SURUM
    )
}

/// Kurulu pakette 'lisanslar' klasörü, yoksa exe'nin yanındaki LICENSE.txt.
#[cfg_attr(not(windows), allow(dead_code))]
pub fn lisans_yolu() -> std::path::PathBuf {
    let kok = rizeon::yollar::uygulama_klasoru();
    if kok.join("lisanslar").is_dir() {
        kok.join("lisanslar")
    } else {
        kok.join("LICENSE.txt")
    }
}

#[derive(Default)]
pub struct Hakkinda {
    pub acik: bool,
    gizlendi: bool,
    logo: Option<egui::TextureHandle>,
}

impl Hakkinda {
    pub fn goster(&mut self, ctx: &egui::Context) {
        if !self.acik {
            self.gizlendi = false;
            return;
        }
        let vp = egui::ViewportBuilder::default()
            .with_title("Hakkında")
            .with_inner_size([460.0, 340.0])
            .with_resizable(false)
            .with_minimize_button(false)
            .with_maximize_button(false);
        let mut kapat = false;
        ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("hakkinda"), vp, |ui, _| {
            yakalamadan_gizle("Hakkında", &mut self.gizlendi);
            kapat |= kapat_istendi(ui);
            if self.logo.is_none() {
                self.logo = simge::logo(ui.ctx());
            }
            egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(11)).show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 6.0;
                if let Some(l) = &self.logo {
                    ui.add(egui::Image::new((l.id(), Vec2::splat(72.0))));
                }
                let w = ui.available_width();
                zengin_metin(ui, &hakkinda_metni(), w);
                ui.with_layout(egui::Layout::bottom_up(egui::Align::Max), |ui| {
                    ui.horizontal(|ui| {
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if bilesen::hap(ui, "Kapat", false, true).clicked() {
                                kapat = true;
                            }
                            if bilesen::hap(ui, "Lisansları göster", false, true).clicked() {
                                #[cfg(windows)]
                                rizeon::win::ac(&lisans_yolu());
                            }
                        });
                    });
                });
            });
        });
        if kapat {
            self.acik = false;
        }
    }
}

// ------------------------------------------------------------------ Yardım

/// Durumdan kısa sorun metni ("" = sorun yok). Duraklatılmış çıkış sorun sayılmaz.
pub fn cikis_sorunu(sanal_kamera: &str, sanal_mikrofon: &str) -> String {
    let kamera = match sanal_kamera {
        "yok" => "bulunamadı",
        "hata" => "açılamadı",
        "koptu" => "koptu",
        _ => "",
    };
    let mikrofon = sanal_mikrofon == "yok";
    if kamera == "bulunamadı" && mikrofon {
        "Sanal kamera ve mikrofon bulunamadı".into()
    } else if !kamera.is_empty() {
        format!("Sanal kamera {kamera}")
    } else if mikrofon {
        "Sanal mikrofon bulunamadı".into()
    } else {
        String::new()
    }
}

pub fn yardim_metni(sorun: &str) -> String {
    let kamera = "### Sanal kamera (OBS Virtual Camera)\n\n\
        1. OBS Studio'yu kur (obsproject.com).\n\
        2. OBS'yi aç, **Sanal Kamerayı Başlat**'a bir kez bas ve OBS'yi kapat.\n\
        3. RizeOn birkaç saniye içinde kendiliğinden bağlanır; yeniden başlatman gerekmez.\n\n\
        OBS açıkken kendi sanal kamerası çalışıyorsa RizeOn bağlanamaz: OBS'de \
        **Sanal Kamerayı Durdur**'a bas ya da OBS'yi kapat.";
    let mikrofon = "### Sanal mikrofon (VB-Cable)\n\n\
        1. VB-Cable'ı indir (vb-audio.com/Cable) ve zip'i bir klasöre çıkar.\n\
        2. **VBCABLE_Setup_x64.exe**'ye sağ tıkla, **Yönetici olarak çalıştır**, **Install Driver**'a bas.\n\
        3. Bilgisayarı yeniden başlat.\n\n\
        Windows'un varsayılan mikrofonu gerçek mikrofonun kalsın. **CABLE Output**'u sadece \
        Zoom, Meet ya da Discord'un içinde mikrofon olarak seç.";
    let govde = if sorun.starts_with("Sanal mikrofon") {
        mikrofon.to_string()
    } else if sorun.starts_with("Sanal kamera") && !sorun.contains("mikrofon") {
        kamera.to_string()
    } else {
        format!("{kamera}\n\n{mikrofon}")
    };
    let bas = if sorun.is_empty() { String::new() } else { format!("**{sorun}.**\n\n") };
    format!(
        "{bas}{govde}\n\nGörüntülü görüşme uygulamasında kamera **OBS Virtual Camera**, mikrofon \
         **CABLE Output (VB-Audio Virtual Cable)** olmalı."
    )
}

#[derive(Default)]
pub struct Yardim {
    pub acik: bool,
    pub sorun: String,
    gizlendi: bool,
}

impl Yardim {
    pub fn ac(&mut self, sorun: &str) {
        self.sorun = sorun.to_string();
        self.acik = true;
    }

    pub fn goster(&mut self, ctx: &egui::Context) {
        if !self.acik {
            self.gizlendi = false;
            return;
        }
        let iki = !self.sorun.starts_with("Sanal mikrofon") && !(self.sorun.starts_with("Sanal kamera") && !self.sorun.contains("mikrofon"));
        let yuk = if iki { 420.0 } else { 260.0 } + if self.sorun.is_empty() { 0.0 } else { 30.0 };
        let vp = egui::ViewportBuilder::default()
            .with_title("Nasıl düzeltilir?")
            .with_inner_size([480.0, yuk])
            .with_resizable(false)
            .with_minimize_button(false)
            .with_maximize_button(false);
        let mut kapat = false;
        ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("yardim"), vp, |ui, _| {
            yakalamadan_gizle("Nasıl düzeltilir?", &mut self.gizlendi);
            kapat |= kapat_istendi(ui);
            let cerceve = egui::Frame::new().fill(tema::ZEMIN).inner_margin(egui::Margin { left: 20, right: 20, top: 16, bottom: 16 });
            egui::CentralPanel::default().frame(cerceve).show(ui, |ui| {
                zengin_metin(ui, &yardim_metni(&self.sorun), 440.0);
                ui.with_layout(egui::Layout::bottom_up(egui::Align::Max), |ui| {
                    if bilesen::hap(ui, "Kapat", false, true).clicked() {
                        kapat = true;
                    }
                });
            });
        });
        if kapat {
            self.acik = false;
        }
    }
}

// ------------------------------------------------------------------ Pencere seçici

#[derive(Clone)]
struct Oge {
    /// None: "Tüm ekran"
    hwnd: Option<isize>,
    baslik: String,
    metin: String,
}

#[derive(Default)]
pub struct PencereSecici {
    acik: bool,
    liste: Vec<Oge>,
    secili: usize,
    /// true: seçilen pencere Göster'e değil, sahneye kaynak olarak eklenir ("Tüm ekran" satırı yok)
    kaynak_icin: bool,
    pub secilen_kaynak: Option<String>,
    gizlendi: bool,
}

impl PencereSecici {
    pub fn ac(&mut self) {
        self.kaynak_ac(false);
    }

    pub fn kaynak_ac(&mut self, kaynak_icin: bool) {
        self.kaynak_icin = kaynak_icin;
        self.acik = true;
        self.yenile();
    }

    fn yenile(&mut self) {
        self.liste.clear();
        if !self.kaynak_icin {
            self.liste.push(Oge { hwnd: None, baslik: String::new(), metin: "Tüm ekran".into() });
        }
        #[cfg(windows)]
        for p in rizeon::yakalama::pencere::pencereler() {
            let metin = if p.program.is_empty() { p.baslik.clone() } else { format!("{}  ·  {}", p.baslik, p.program) };
            self.liste.push(Oge { hwnd: Some(p.hwnd), baslik: p.baslik.clone(), metin });
        }
        self.secili = 0;
    }

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) {
        if !self.acik {
            self.gizlendi = false;
            return;
        }
        let vp = egui::ViewportBuilder::default().with_title("Pencere seç").with_inner_size([520.0, 440.0]).with_min_inner_size([360.0, 260.0]);
        let mut kapat = false;
        let mut sec: Option<Oge> = None;
        ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("pencere-secici"), vp, |ui, _| {
            yakalamadan_gizle("Pencere seç", &mut self.gizlendi);
            kapat |= kapat_istendi(ui);
            egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(16)).show(ui, |ui| {
                ui.spacing_mut().item_spacing.y = 10.0;
                let w = ui.available_width();
                ui.add(
                    egui::Label::new(
                        egui::RichText::new("Bir pencere seçersen yayında ve kayıtta sadece o pencere görünür. Üstüne başka pencere gelse de o pencere gösterilir.")
                            .font(tema::yazi(tema::KUCUK_PX))
                            .color(tema::YAZI2),
                    )
                    .wrap(),
                );
                let bos = self.liste.len() == usize::from(!self.kaynak_icin);
                let alt_yuk = 32.0 + 10.0 + if bos { 26.0 } else { 0.0 };
                let liste_yuk = (ui.available_height() - alt_yuk).max(80.0);
                let (lr, _) = ui.allocate_exact_size(Vec2::new(w, liste_yuk), Sense::hover());
                ui.painter().rect(lr, 6.0, tema::PANEL, Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)), egui::StrokeKind::Inside);
                let mut lu = ui.new_child(egui::UiBuilder::new().max_rect(lr.shrink(4.0)));
                egui::ScrollArea::vertical().auto_shrink(false).show(&mut lu, |ui| {
                    ui.spacing_mut().item_spacing.y = 0.0;
                    for (i, o) in self.liste.iter().enumerate() {
                        let (r, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 36.0), Sense::click());
                        let secili = i == self.secili;
                        if secili {
                            ui.painter().rect_filled(r, 6.0, beyaz(tema::A_SECILI));
                        } else if resp.hovered() {
                            ui.painter().rect_filled(r, 6.0, beyaz(tema::A_UZERINE));
                        }
                        let metin = bilesen::kisalt(&o.metin, ((r.width() - 16.0) / 6.5) as usize);
                        ui.painter().text(Pos2::new(r.left() + 8.0, r.center().y), Align2::LEFT_CENTER, metin, tema::yazi(tema::GOVDE_PX), if secili { tema::BEYAZ } else { tema::YAZI });
                        let resp = if o.baslik.is_empty() { resp } else { resp.on_hover_text(&o.baslik) };
                        if resp.clicked() {
                            self.secili = i;
                        }
                        if resp.double_clicked() {
                            sec = Some(o.clone());
                        }
                    }
                });
                if bos {
                    bilesen::etiket(ui, "Başka açık pencere bulunamadı.", tema::KUCUK_PX, tema::YAZI2);
                }
                ui.horizontal(|ui| {
                    if bilesen::diyalog_dugmesi(ui, "Yenile", false).clicked() {
                        self.yenile();
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if bilesen::diyalog_dugmesi(ui, "Göster", true).clicked() || ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                            sec = self.liste.get(self.secili).cloned();
                        }
                        if bilesen::diyalog_dugmesi(ui, "Vazgeç", false).clicked() {
                            kapat = true;
                        }
                    });
                });
            });
        });
        if let Some(o) = sec {
            match (o.hwnd, self.kaynak_icin) {
                (Some(_), true) => self.secilen_kaynak = Some(o.baslik),
                (Some(h), false) => {
                    uyg.pencere_sec(h, &o.baslik);
                }
                (None, _) => {
                    uyg.tam_ekran();
                }
            }
            kapat = true;
        }
        if kapat {
            self.acik = false;
        }
    }
}

// ------------------------------------------------------------------ Bildirim

const SURE: Duration = Duration::from_millis(1800);
const EYLEMLI_SURE: Duration = Duration::from_millis(5000);
const SONME: f32 = 0.25;

/// Sağ altta tek, gri bildirim kartı. Odak almaz, ekran yakalamaya girmez; fare üstündeyken kaybolmaz.
#[derive(Default)]
pub struct BildirimPenceresi {
    simdiki: Option<Bildirim>,
    bitis: Option<Instant>,
    gizlendi: bool,
    /// tıklanan eylem (ana pencere yapar: yardım, ayarlar)
    pub istenen: Option<BildirimEylemi>,
}

impl BildirimPenceresi {
    fn boyut(ctx: &egui::Context, b: &Bildirim) -> Vec2 {
        let p = egui::Painter::new(ctx.clone(), egui::LayerId::background(), Rect::EVERYTHING);
        let olc = |s: &str, px: f32| p.layout_no_wrap(s.to_string(), tema::yazi(px), Color32::WHITE).size().x;
        let mut w = 14.0 + olc(&b.metin, 13.0) + 12.0;
        let eylem = b.eylem.as_ref().map(eylem_adi);
        if !b.tus.is_empty() || eylem.is_some() {
            w += 6.0 + olc("·", 13.0);
        }
        if !b.tus.is_empty() {
            w += 6.0 + olc(&b.tus, 12.0);
        }
        if let Some(e) = eylem {
            w += 6.0 + olc(e, 13.0) + 8.0;
        }
        Vec2::new(w.ceil() + 2.0, 38.0)
    }

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) {
        // en yenisi gösterilir; kısayol bildirimleri ayar kapalıyken gösterilmez (eylemliler her zaman)
        let yeni: Vec<Bildirim> = uyg.bildirimler.lock().unwrap().drain(..).collect();
        if let Some(b) = yeni.into_iter().rev().find(|b| b.eylem.is_some() || !b.kisayol || uyg.ayarlar.lock().unwrap().mantik("ui.toasts", true)) {
            self.bitis = Some(Instant::now() + if b.eylem.is_some() { EYLEMLI_SURE } else { SURE });
            self.simdiki = Some(b);
        }
        let Some(b) = self.simdiki.clone() else {
            self.gizlendi = false;
            return;
        };
        let simdi = Instant::now();
        let bitis = self.bitis.unwrap_or(simdi);
        let opaklik = if simdi < bitis { 1.0 } else { 1.0 - (simdi - bitis).as_secs_f32() / SONME };
        if opaklik <= 0.0 {
            self.simdiki = None;
            return;
        }
        let boyut = Self::boyut(ctx, &b);
        let ppp = ctx.native_pixels_per_point().unwrap_or(1.0).max(0.5);
        let _ = ppp;
        let konum = calisma_alani(ctx).map(|g| Pos2::new(g.right() - boyut.x - 16.0, g.bottom() - boyut.y - 16.0));
        let mut vp = egui::ViewportBuilder::default()
            .with_title("RizeOn bildirim")
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_active(false)
            .with_mouse_passthrough(b.eylem.is_none())
            .with_inner_size(boyut);
        if let Some(k) = konum {
            vp = vp.with_position(k);
        }
        let mut eylem_basildi = false;
        ctx.show_viewport_immediate(egui::ViewportId::from_hash_of("bildirim"), vp, |ui, _| {
            yakalamadan_gizle("RizeOn bildirim", &mut self.gizlendi);
            let vctx = ui.ctx().clone();
            vctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(boyut));
            if let Some(k) = konum {
                vctx.send_viewport_cmd(egui::ViewportCommand::OuterPosition(k));
            }
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ui, |ui| {
                ui.set_opacity(opaklik);
                let r = ui.max_rect();
                // fare üstündeyken kaybolmaz; çıkınca 1,5 sn sonra
                if ui.rect_contains_pointer(r) {
                    self.bitis = Some(Instant::now() + Duration::from_millis(1500));
                }
                ui.painter().rect(r.shrink(0.5), 10.0, tema::YUZEN, Stroke::new(1.0, beyaz(tema::A_KENARLIK_MENU)), egui::StrokeKind::Middle);
                let mut ic = ui.new_child(egui::UiBuilder::new().max_rect(r.shrink2(Vec2::new(0.0, 0.0))).layout(egui::Layout::left_to_right(egui::Align::Center)));
                ic.spacing_mut().item_spacing.x = 6.0;
                ic.add_space(14.0 - 6.0);
                bilesen::etiket(&mut ic, &b.metin, 13.0, tema::YAZI);
                let eylem = b.eylem.as_ref().map(eylem_adi);
                if !b.tus.is_empty() || eylem.is_some() {
                    bilesen::etiket(&mut ic, "·", 13.0, tema::SOLUK);
                }
                if !b.tus.is_empty() {
                    bilesen::etiket(&mut ic, &b.tus, 12.0, tema::SOLUK);
                }
                if let Some(e) = eylem {
                    let g = ic.painter().layout_no_wrap(e.to_string(), tema::yazi(13.0), tema::YAZI);
                    let (er, resp) = ic.allocate_exact_size(Vec2::new(g.size().x + 8.0, 22.0), Sense::click());
                    let resp = resp.on_hover_cursor(egui::CursorIcon::PointingHand);
                    let renk = if resp.hovered() { tema::BEYAZ } else { tema::YAZI };
                    let sol = Pos2::new(er.left() + 4.0, er.center().y - g.size().y / 2.0);
                    let alt = sol.y + g.size().y - 1.5;
                    let gw = g.size().x;
                    ic.painter().galley(sol, g, renk);
                    ic.painter().line_segment([Pos2::new(sol.x, alt), Pos2::new(sol.x + gw, alt)], Stroke::new(1.0, renk));
                    eylem_basildi = resp.clicked();
                }
            });
        });
        if eylem_basildi {
            match b.eylem.clone() {
                #[cfg(windows)]
                Some(BildirimEylemi::Ac(d)) => rizeon::win::ac(&d),
                #[cfg(windows)]
                Some(BildirimEylemi::KlasordeGoster(d)) => rizeon::win::klasorde_goster(&d),
                Some(e @ (BildirimEylemi::Yardim | BildirimEylemi::Ayarlar(_))) => self.istenen = Some(e),
                _ => {}
            }
            self.simdiki = None;
        }
        ctx.request_repaint_after(Duration::from_millis(if opaklik < 1.0 { 16 } else { 200 }));
    }
}

/// Ana ekranın çalışma alanı (görev çubuğu hariç; Qt availableGeometry karşılığı), nokta cinsinden.
pub fn calisma_alani(ctx: &egui::Context) -> Option<egui::Rect> {
    let ppp = ctx.native_pixels_per_point().unwrap_or(1.0).max(0.5);
    #[cfg(windows)]
    if let Some((l, t, r, b)) = rizeon::win::calisma_alani() {
        return Some(egui::Rect::from_min_max(Pos2::new(l as f32 / ppp, t as f32 / ppp), Pos2::new(r as f32 / ppp, b as f32 / ppp)));
    }
    let m = rizeon::yakalama::monitorler().into_iter().next()?;
    Some(egui::Rect::from_min_size(Pos2::new(m.sol as f32 / ppp, m.ust as f32 / ppp), Vec2::new(m.w as f32 / ppp, m.h as f32 / ppp - 48.0)))
}

fn eylem_adi(e: &BildirimEylemi) -> &'static str {
    match e {
        BildirimEylemi::Ac(_) => "Aç",
        BildirimEylemi::KlasordeGoster(_) => "Klasörde göster",
        BildirimEylemi::Yardim => "Nasıl düzeltilir?",
        BildirimEylemi::Ayarlar(_) => "Ayarlar",
    }
}
