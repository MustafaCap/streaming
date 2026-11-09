//! Arayüzün ortak parçaları (Python ui/bilesenler.py): karo düğme, simge düğmesi, hap düğme,
//! Windows 11 anahtarı, canlı ses çizgisi, seçim grubu, sürgü, tutma yeri, kayıt grubu,
//! iki satırlı menü öğesi. Hepsi tema.rs'deki kurallarla elle çizilir.

use eframe::egui::{self, Align2, Color32, CornerRadius, Pos2, Rect, Response, Sense, Stroke, StrokeKind, Ui, Vec2};

use super::simge;
use super::tema::{self, beyaz};

pub fn ipucu(ad: &str, tus: &str) -> String {
    if tus.is_empty() {
        ad.to_string()
    } else {
        format!("{ad} · {tus}")
    }
}

pub fn sure_metni(sn: u64) -> String {
    let (s, d, n) = (sn / 3600, sn / 60 % 60, sn % 60);
    if s > 0 {
        format!("{s}:{d:02}:{n:02}")
    } else {
        format!("{d:02}:{n:02}")
    }
}

pub fn kisalt(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        s.chars().take(n - 1).collect::<String>() + "…"
    }
}

/// Düğme zemini: seçili / kapalı / üzerine gelme / basılı (Python _Dugme._zemin).
pub fn zemin(ui: &Ui, r: Rect, yaricap: f32, secili: bool, kapali: bool, resp: &Response, etkin: bool) {
    let mut alfa = if secili {
        tema::A_SECILI
    } else if kapali {
        tema::A_KAPALI
    } else {
        0.0
    };
    if resp.hovered() && etkin {
        alfa = alfa.max(tema::A_UZERINE) + if secili || kapali { 0.03 } else { 0.0 };
    }
    if etkin && resp.is_pointer_button_down_on() {
        alfa += 0.04;
    }
    if alfa > 0.0 {
        ui.painter().rect_filled(r, yaricap, beyaz(alfa));
    }
    if resp.has_focus() {
        ui.painter().rect_stroke(r.shrink(1.0), yaricap, Stroke::new(1.0, beyaz(0.5)), StrokeKind::Inside);
    }
}

fn imlec(resp: Response, etkin: bool) -> Response {
    if etkin {
        resp.on_hover_cursor(egui::CursorIcon::PointingHand)
    } else {
        resp
    }
}

fn duyu(etkin: bool) -> Sense {
    if etkin {
        Sense::click()
    } else {
        Sense::hover()
    }
}

/// Kontrol barı karosu: simge + altında kısa etiket (76×60).
pub fn karo(ui: &mut Ui, simge_adi: Option<&'static str>, metin: &str, kapali: bool, secili: bool, etkin: bool) -> Response {
    let (r, resp) = ui.allocate_exact_size(Vec2::new(tema::KARO.0, tema::KARO.1), duyu(etkin));
    let resp = imlec(resp, etkin);
    zemin(ui, r, 8.0, secili, kapali, &resp, etkin);
    let mut renk = if kapali {
        tema::YAZI2
    } else if secili {
        tema::BEYAZ
    } else {
        tema::YAZI
    };
    if !etkin {
        renk = tema::SOLUK;
    }
    match simge_adi {
        Some(s) => {
            simge::simge(ui, s, renk, 18.0, Pos2::new((r.center().x - 9.0).round(), r.top() + 12.0), kapali);
            ui.painter().text(Pos2::new(r.center().x, r.top() + 34.0), Align2::CENTER_TOP, metin, tema::yazi(tema::EN_KUCUK_PX), renk);
        }
        None => {
            ui.painter().text(r.center(), Align2::CENTER_CENTER, metin, tema::yazi(tema::EN_KUCUK_PX), renk);
        }
    }
    resp
}

#[derive(Clone)]
pub struct SimgeDugme {
    pub simge: &'static str,
    pub boyut: f32,
    pub simge_boyu: f32,
    pub renk: Option<Color32>,
    pub kapali: bool,
    pub secili: bool,
    pub yaricap: Option<f32>,
    /// yeri durur ama üzerine gelinmedikçe çizilmez (kaynak satırındaki ×)
    pub gizli: bool,
    pub etkin: bool,
}

impl SimgeDugme {
    pub fn new(simge: &'static str) -> Self {
        SimgeDugme { simge, boyut: 36.0, simge_boyu: 16.0, renk: None, kapali: false, secili: false, yaricap: None, gizli: false, etkin: true }
    }
    pub fn boyut(mut self, boyut: f32, simge_boyu: f32) -> Self {
        self.boyut = boyut;
        self.simge_boyu = simge_boyu;
        self
    }
    pub fn renk(mut self, c: Color32) -> Self {
        self.renk = Some(c);
        self
    }
    pub fn kapali(mut self, k: bool) -> Self {
        self.kapali = k;
        self
    }
    pub fn secili(mut self, s: bool) -> Self {
        self.secili = s;
        self
    }
    pub fn yaricap(mut self, y: f32) -> Self {
        self.yaricap = Some(y);
        self
    }
    pub fn gizli(mut self, g: bool) -> Self {
        self.gizli = g;
        self
    }
    pub fn etkin(mut self, e: bool) -> Self {
        self.etkin = e;
        self
    }

    pub fn goster(self, ui: &mut Ui) -> Response {
        let (r, resp) = ui.allocate_exact_size(Vec2::splat(self.boyut), duyu(self.etkin));
        let resp = imlec(resp, self.etkin);
        if self.gizli && !resp.hovered() {
            return resp;
        }
        zemin(ui, r, self.yaricap.unwrap_or(r.height() / 2.0), self.secili, self.kapali, &resp, self.etkin);
        let mut renk = if self.kapali {
            tema::SOLUK
        } else {
            self.renk.unwrap_or(if self.secili { tema::BEYAZ } else { tema::YAZI })
        };
        if !self.etkin {
            renk = tema::SOLUK;
        }
        simge::ortaya(ui, self.simge, renk, self.simge_boyu, r, self.kapali);
        resp
    }
}

/// Başlık çubuğundaki yazılı yuvarlak düğme (28 px, Qt QPushButton teması).
pub fn hap(ui: &mut Ui, metin: &str, secili: bool, etkin: bool) -> Response {
    let font = tema::yazi(tema::KUCUK_PX);
    // "☰ " ile başlıyorsa simge elle çizilir (yazı tiplerinde ☰ her zaman yok)
    let (menu, metin) = match metin.strip_prefix("☰ ") {
        Some(m) => (true, m),
        None => (false, metin),
    };
    let menu_gen = if menu { 12.0 } else { 0.0 };
    let galeri = ui.painter().layout_no_wrap(metin.to_string(), font, Color32::WHITE);
    let boyut = Vec2::new(galeri.size().x + 24.0 + menu_gen, 28.0);
    let (r, resp) = ui.allocate_exact_size(boyut, duyu(etkin));
    let resp = imlec(resp, etkin);
    let uzerinde = resp.hovered() && etkin;
    if secili {
        ui.painter().rect_filled(r, 14.0, beyaz(tema::A_SECILI));
    } else if uzerinde {
        ui.painter().rect_filled(r, 14.0, beyaz(tema::A_UZERINE));
    }
    let renk = if !etkin {
        tema::SOLUK
    } else if secili || uzerinde {
        tema::BEYAZ
    } else {
        tema::DUGME
    };
    if menu {
        let x = r.left() + 12.0;
        for dy in [-3.0, 0.0, 3.0] {
            let y = (r.center().y + dy).round() + 0.5;
            ui.painter().line_segment([Pos2::new(x, y), Pos2::new(x + 8.0, y)], Stroke::new(1.0, renk));
        }
    }
    ui.painter().galley(Pos2::new(r.left() + 12.0 + menu_gen, r.center().y - galeri.size().y / 2.0), galeri, renk);
    resp
}

/// Diyalog düğmesi (QPushButton#dialog): ince çerçeve, 8 px köşe, 32 px yükseklik.
pub fn diyalog_dugmesi(ui: &mut Ui, metin: &str, varsayilan: bool) -> Response {
    let font = tema::yazi(tema::KUCUK_PX);
    let galeri = ui.painter().layout_no_wrap(metin.to_string(), font, Color32::WHITE);
    let boyut = Vec2::new((galeri.size().x + 32.0).max(72.0), 32.0);
    let (r, resp) = ui.allocate_exact_size(boyut, Sense::click());
    let resp = imlec(resp, true);
    let mut alfa = if varsayilan { tema::A_SECILI } else { 0.0 };
    if resp.hovered() {
        alfa = alfa.max(tema::A_UZERINE);
    }
    if alfa > 0.0 {
        ui.painter().rect_filled(r, 8.0, beyaz(alfa));
    }
    ui.painter().rect_stroke(r, 8.0, Stroke::new(1.0, beyaz(tema::A_KENARLIK)), StrokeKind::Inside);
    let renk = if resp.hovered() { tema::BEYAZ } else { tema::YAZI };
    ui.painter().galley(Pos2::new(r.center().x - galeri.size().x / 2.0, r.center().y - galeri.size().y / 2.0), galeri, renk);
    resp
}

/// Bağlantı gibi küçük düğme (QPushButton#baglanti); `alti_cizili` ile altı çizili.
pub fn baglanti(ui: &mut Ui, metin: &str, px: f32, renk: Color32, alti_cizili: bool) -> Response {
    let font = tema::yazi(px);
    let galeri = ui.painter().layout_no_wrap(metin.to_string(), font, Color32::WHITE);
    let (r, resp) = ui.allocate_exact_size(Vec2::new(galeri.size().x + 16.0, 22.0), Sense::click());
    let resp = imlec(resp, true);
    if resp.hovered() {
        ui.painter().rect_filled(r, 11.0, beyaz(tema::A_UZERINE));
    }
    let c = if resp.hovered() { tema::BEYAZ } else { renk };
    let sol_ust = Pos2::new(r.left() + 8.0, r.center().y - galeri.size().y / 2.0);
    let alt = sol_ust.y + galeri.size().y - 1.5;
    let gen = galeri.size().x;
    ui.painter().galley(sol_ust, galeri, c);
    if alti_cizili {
        ui.painter().line_segment([Pos2::new(sol_ust.x, alt), Pos2::new(sol_ust.x + gen, alt)], Stroke::new(1.0, c));
    }
    resp
}

/// Windows 11 tarzı aç/kapa anahtarı (40×24, iç 36×20).
pub fn anahtar(ui: &mut Ui, acik: &mut bool, etkin: bool) -> Response {
    let (alan, resp) = ui.allocate_exact_size(Vec2::new(40.0, 24.0), duyu(etkin));
    let mut resp = imlec(resp, etkin);
    if etkin && resp.clicked() {
        *acik = !*acik;
        resp.mark_changed();
    }
    let r = Rect::from_min_size(alan.min + Vec2::new(2.0, 2.0), Vec2::new(36.0, 20.0));
    let uzerinde = resp.hovered() && etkin;
    let p = ui.painter();
    let ic = r.shrink(0.5);
    if *acik {
        p.rect_filled(ic, 10.0, if uzerinde { tema::BEYAZ } else { tema::DUGME });
        p.rect_stroke(ic, 10.0, Stroke::new(1.0, tema::DUGME), StrokeKind::Middle);
        p.circle_filled(Pos2::new(r.left() + 19.0 + 0.5 + 6.0, r.top() + 10.0), 6.0, tema::ZEMIN);
    } else {
        p.rect_stroke(ic, 10.0, Stroke::new(1.0, if uzerinde { tema::YAZI2 } else { tema::NOKTA }), StrokeKind::Middle);
        p.circle_filled(Pos2::new(r.left() + 3.0 + 6.0, r.top() + 10.0), 6.0, tema::SOLUK);
    }
    if !etkin {
        p.rect_filled(alan, 0.0, tema::saydam(tema::PANEL, 0.5));
    }
    resp
}

/// İnce yeşil canlı ses seviyesi çizgisi (0..1). Yeşil sadece burada.
pub fn ses_cizgisi(ui: &mut Ui, deger: f32) {
    let (r, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 4.0), Sense::hover());
    ui.painter().rect_filled(r, 2.0, tema::IZ);
    let w = r.width() * deger.clamp(0.0, 1.0);
    if w > 0.5 {
        let mut d = r;
        d.set_width(w);
        ui.painter().rect_filled(d, CornerRadius::same(2), tema::SES);
    }
}

/// Seviyeyi (doğrusal) çizgi değerine çevirir; düşüşte yumuşar (Python SesCizgisi.ayarla).
pub fn seviye_yumusat(onceki: f32, seviye: f32) -> f32 {
    let hedef = if seviye > 0.0 { ((rizeon::ses::db(seviye) + 60.0) / 60.0).max(0.0) } else { 0.0 };
    if hedef > onceki {
        hedef
    } else {
        onceki * 0.8 + hedef * 0.2
    }
}

/// Gri sürgü (Qt QSlider teması): 4 px iz, dolu kısım gri, 14 px tutamak. `deger` 0..=ust.
pub fn surgu(ui: &mut Ui, deger: &mut i32, ust: i32) -> Response {
    surgu_aralik(ui, deger, 0, ust)
}

/// `min..=max` aralığında kaydırıcı (Python QSlider karşılığı).
pub fn surgu_aralik(ui: &mut Ui, deger: &mut i32, min: i32, max: i32) -> Response {
    let aralik = (max - min).max(1);
    let (r, mut resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 20.0), Sense::click_and_drag());
    resp = imlec(resp, true);
    let sol = r.left() + 7.0;
    let sag = r.right() - 7.0;
    if let Some(p) = resp.interact_pointer_pos() {
        if resp.dragged() || resp.clicked() || resp.is_pointer_button_down_on() {
            let oran = ((p.x - sol) / (sag - sol).max(1.0)).clamp(0.0, 1.0);
            let yeni = min + (oran * aralik as f32).round() as i32;
            if yeni != *deger {
                *deger = yeni;
                resp.mark_changed();
            }
        }
    }
    if resp.hovered() {
        let tekerlek = ui.input(|i| i.smooth_scroll_delta.y);
        if tekerlek.abs() > 0.5 {
            let yeni = (*deger + if tekerlek > 0.0 { 1 } else { -1 }).clamp(min, max);
            if yeni != *deger {
                *deger = yeni;
                resp.mark_changed();
            }
        }
    }
    let y = r.center().y;
    let iz = Rect::from_min_max(Pos2::new(r.left(), y - 2.0), Pos2::new(r.right(), y + 2.0));
    ui.painter().rect_filled(iz, 2.0, tema::IZ);
    let oran = ((*deger - min) as f32 / aralik as f32).clamp(0.0, 1.0);
    let x = sol + (sag - sol) * oran;
    ui.painter().rect_filled(Rect::from_min_max(iz.min, Pos2::new(x, iz.max.y)), 2.0, tema::NOKTA);
    ui.painter().circle_filled(Pos2::new(x, y), 7.0, if resp.hovered() || resp.dragged() { tema::BEYAZ } else { tema::DUGME });
    resp
}

/// Yan yana seçenekler (Sesim / Dengeli / Oyun). `secili` < 0: hiçbiri. Basılanın sırasını döndürür.
pub fn secim_grubu(ui: &mut Ui, secenekler: &[&str], ipuclari: &[&str], secili: i32, kucuk: bool, zemin_rengi: Option<Color32>) -> Option<usize> {
    let yukseklik = if kucuk { 26.0 } else { 30.0 };
    let font = tema::yazi(tema::KUCUK_PX);
    let genislikler: Vec<f32> = secenekler.iter().map(|m| ui.painter().layout_no_wrap(m.to_string(), font.clone(), Color32::WHITE).size().x + 24.0).collect();
    let toplam = if kucuk { genislikler.iter().sum::<f32>() + 2.0 * (secenekler.len() as f32 - 1.0) + 6.0 } else { ui.available_width() };
    let (r, _) = ui.allocate_exact_size(Vec2::new(toplam, yukseklik + 6.0), Sense::hover());
    let ry = (yukseklik + 6.0) / 2.0;
    ui.painter().rect_filled(r, ry, zemin_rengi.unwrap_or(tema::ZEMIN));
    if kucuk {
        ui.painter().rect_stroke(r, ry, Stroke::new(1.0, beyaz(tema::A_KENARLIK)), StrokeKind::Inside);
    }
    let ic = r.shrink(3.0);
    let n = secenekler.len() as f32;
    let mut x = ic.left();
    let mut sonuc = None;
    for (i, m) in secenekler.iter().enumerate() {
        let w = if kucuk { genislikler[i] } else { (ic.width() - 2.0 * (n - 1.0)) / n };
        let dr = Rect::from_min_size(Pos2::new(x, ic.top()), Vec2::new(w, yukseklik));
        x += w + 2.0;
        let id = ui.scope_id().with(("secim", m, i));
        let mut resp = imlec(ui.interact(dr, id, Sense::click()), true);
        if let Some(t) = ipuclari.get(i) {
            resp = resp.on_hover_text(*t);
        }
        let sec = secili == i as i32;
        if sec {
            ui.painter().rect_filled(dr, yukseklik / 2.0, beyaz(tema::A_SECILI));
        } else if resp.hovered() {
            ui.painter().rect_filled(dr, yukseklik / 2.0, beyaz(tema::A_UZERINE));
        }
        let renk = if sec || resp.hovered() {
            tema::BEYAZ
        } else if kucuk {
            tema::DUGME
        } else {
            tema::YAZI2
        };
        ui.painter().text(dr.center(), Align2::CENTER_CENTER, *m, font.clone(), renk);
        if resp.clicked() {
            sonuc = Some(i);
        }
    }
    sonuc
}

/// 6 noktalı tutma yeri.
pub fn tutma_yeri(ui: &mut Ui, dikey_bosluk: f32) -> Response {
    let (r, resp) = ui.allocate_exact_size(Vec2::new(20.0, 20.0 + dikey_bosluk), Sense::click_and_drag());
    let suruklenen = resp.dragged();
    let resp = resp.on_hover_cursor(if suruklenen { egui::CursorIcon::Grabbing } else { egui::CursorIcon::Grab }).on_hover_text("Taşı");
    let x0 = r.left() + (r.width() - 9.0) / 2.0;
    let y0 = r.top() + (r.height() - 15.0) / 2.0;
    for satir in 0..3 {
        for sutun in 0..2 {
            ui.painter().circle_filled(Pos2::new(x0 + sutun as f32 * 6.0 + 1.5, y0 + satir as f32 * 6.0 + 1.5), 1.5, tema::NOKTA);
        }
    }
    resp
}

pub struct KayitGrubuSonucu {
    pub duraklat: bool,
    pub bitir: bool,
}

/// `kayit_grubu`nun genişliği (kontrol barını ortalamak için önceden gerekir).
pub fn kayit_grubu_genisligi(p: &egui::Painter, saniye: u64, dugme_boyu: f32, bitir: bool, zeminli: bool) -> f32 {
    let sg = p.layout_no_wrap(sure_metni(saniye), tema::yazi(tema::GOVDE_PX), Color32::WHITE);
    let nokta = if dugme_boyu >= 40.0 { 7.0 } else { 6.0 };
    let (sol, sag) = if zeminli { (8.0, 4.0) } else { (2.0, 0.0) };
    sol + 4.0 + nokta + 6.0 + 6.0 + sg.size().x + 6.0 + 2.0 + dugme_boyu + if bitir { 2.0 + dugme_boyu } else { 0.0 } + sag
}

/// Kayıt sürerken: kırmızı nokta + süre, duraklat/devam et, bitir (kare).
pub fn kayit_grubu(ui: &mut Ui, saniye: u64, duraklatildi: bool, dugme_boyu: f32, bitir: bool, zeminli: bool, tus_duraklat: &str, tus_bitir: &str) -> KayitGrubuSonucu {
    let font = tema::yazi(tema::GOVDE_PX);
    let sure = sure_metni(saniye);
    let sg = ui.painter().layout_no_wrap(sure.clone(), font.clone(), Color32::WHITE);
    let nokta = if dugme_boyu >= 40.0 { 7.0 } else { 6.0 };
    let sol_bosluk = if zeminli { 8.0 } else { 2.0 };
    let sag_bosluk = if zeminli { 4.0 } else { 0.0 };
    let gen = sol_bosluk + 4.0 + nokta + 6.0 + 6.0 + sg.size().x + 6.0 + 2.0 + dugme_boyu + if bitir { 2.0 + dugme_boyu } else { 0.0 } + sag_bosluk;
    let yuk = if zeminli { 60.0 } else { dugme_boyu };
    let (r, _) = ui.allocate_exact_size(Vec2::new(gen, yuk), Sense::hover());
    if zeminli {
        ui.painter().rect_filled(r, 8.0, beyaz(tema::A_GRUP));
    }
    let mut x = r.left() + sol_bosluk + 4.0;
    ui.painter().circle_filled(Pos2::new(x + nokta / 2.0, r.center().y), nokta / 2.0, if duraklatildi { tema::NOKTA } else { tema::KAYIT });
    x += nokta + 6.0 + 6.0;
    ui.painter().galley(Pos2::new(x, r.center().y - sg.size().y / 2.0), sg.clone(), if duraklatildi { tema::SOLUK } else { tema::YAZI });
    x += sg.size().x + 6.0 + 2.0;
    let yaricap = if dugme_boyu >= 40.0 { Some(8.0) } else { None };
    let mut sonuc = KayitGrubuSonucu { duraklat: false, bitir: false };
    let dugme = |ui: &mut Ui, x: f32, simge_adi: &'static str, ad: String| -> bool {
        let dr = Rect::from_min_size(Pos2::new(x, r.center().y - dugme_boyu / 2.0), Vec2::splat(dugme_boyu));
        let mut alt = ui.new_child(egui::UiBuilder::new().max_rect(dr));
        let mut d = SimgeDugme::new(simge_adi).boyut(dugme_boyu, 12.0);
        if let Some(y) = yaricap {
            d = d.yaricap(y);
        }
        d.goster(&mut alt).on_hover_text(ad).clicked()
    };
    let (ds, da) = if duraklatildi { ("oynat", "Kayda devam et") } else { ("duraklat", "Kaydı duraklat") };
    sonuc.duraklat = dugme(ui, x, ds, ipucu(da, tus_duraklat));
    if bitir {
        sonuc.bitir = dugme(ui, x + dugme_boyu + 2.0, "bitir", ipucu("Kaydı bitir", tus_bitir));
    }
    sonuc
}

/// Panel çerçevesi (QFrame#panel): koyu gri zemin, ince kenarlık, 12 px köşe.
pub fn panel(ic: f32) -> egui::Frame {
    egui::Frame::new()
        .fill(tema::PANEL)
        .stroke(Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)))
        .corner_radius(12)
        .inner_margin(egui::Margin::same(ic as i8))
}

pub fn panel_kenarli(sol: f32, ust: f32, sag: f32, alt: f32) -> egui::Frame {
    egui::Frame::new()
        .fill(tema::PANEL)
        .stroke(Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)))
        .corner_radius(12)
        .inner_margin(egui::Margin { left: sol as i8, right: sag as i8, top: ust as i8, bottom: alt as i8 })
}

/// Etiket: renk ve boyutla.
pub fn etiket(ui: &mut Ui, metin: &str, px: f32, renk: Color32) -> Response {
    ui.add(egui::Label::new(egui::RichText::new(metin).font(tema::yazi(px)).color(renk)).selectable(false))
}

/// Menü satırı (QMenu::item): 36 px, 12 px iç boşluk, 6 px köşe.
pub fn menu_satiri(ui: &mut Ui, metin: &str, etkin: bool) -> Response {
    let w = ui.available_width().max(160.0);
    let (r, resp) = ui.allocate_exact_size(Vec2::new(w, 36.0), duyu(etkin));
    if resp.hovered() && etkin {
        ui.painter().rect_filled(r, 6.0, beyaz(tema::A_UZERINE));
    }
    let renk = if !etkin {
        tema::SOLUK
    } else if resp.hovered() {
        tema::BEYAZ
    } else {
        tema::YAZI
    };
    ui.painter().text(Pos2::new(r.left() + 12.0, r.center().y), Align2::LEFT_CENTER, metin, tema::yazi(tema::GOVDE_PX), renk);
    if resp.clicked() {
        ui.close();
    }
    resp
}

/// Menü ayracı.
pub fn menu_ayraci(ui: &mut Ui) {
    let (r, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 9.0), Sense::hover());
    ui.painter().line_segment([Pos2::new(r.left() + 6.0, r.center().y), Pos2::new(r.right() - 6.0, r.center().y)], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
}

/// İki satırlı menü öğesi: ad + altında soluk açıklama (Göster ve kaynak ekleme menüleri).
pub fn menu_ogesi(ui: &mut Ui, baslik: &str, aciklama: &str, secili: bool) -> Response {
    let w = ui.available_width().max(220.0);
    let (r, resp) = ui.allocate_exact_size(Vec2::new(w, 44.0), Sense::click());
    let mut alfa = if secili { tema::A_SECILI } else { 0.0 };
    if resp.hovered() {
        alfa = alfa.max(tema::A_UZERINE);
    }
    if alfa > 0.0 {
        ui.painter().rect_filled(r, 6.0, beyaz(alfa));
    }
    if aciklama.is_empty() {
        ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y), Align2::LEFT_CENTER, baslik, tema::yazi(tema::GOVDE_PX), tema::YAZI);
    } else {
        ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y - 1.0), Align2::LEFT_BOTTOM, baslik, tema::yazi(tema::GOVDE_PX), tema::YAZI);
        ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y + 1.0), Align2::LEFT_TOP, aciklama, tema::yazi(tema::EN_KUCUK_PX), tema::SOLUK);
    }
    if resp.clicked() {
        ui.close();
    }
    resp
}

/// Açılır menü çerçevesi (QMenu teması).
pub fn menu_cercevesi() -> egui::Frame {
    egui::Frame::new()
        .fill(tema::YUZEN)
        .stroke(Stroke::new(1.0, beyaz(tema::A_KENARLIK_MENU)))
        .corner_radius(10)
        .inner_margin(4)
        .shadow(egui::Shadow { offset: [0, 6], blur: 18, spread: 0, color: Color32::from_black_alpha(90) })
}

/// Yatay ince ayraç (kontrol barındaki dikey ayraç için `dikey_ayrac`).
pub fn dikey_ayrac(ui: &mut Ui, yukseklik: f32) {
    let (r, _) = ui.allocate_exact_size(Vec2::new(9.0, yukseklik), Sense::hover());
    let x = r.center().x.round() + 0.5;
    ui.painter().line_segment([Pos2::new(x, r.top() + 10.0), Pos2::new(x, r.bottom() - 10.0)], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
}
