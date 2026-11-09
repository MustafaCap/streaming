//! Tasarım kuralları (Python ui/theme.py): renkler, yazı ve ölçüler tek yerde.
//!
//! Arayüz tek renk gri. Renk sadece anlam taşıdığı iki yerde var:
//!   - kayıt kırmızısı : yalnızca kayıt sürerken küçük nokta (duraklatınca gri olur)
//!   - ses yeşili      : yalnızca canlı ses seviyesi çizgileri
//! Kapalı durumlar kırmızı değil: sönük gri zemin + çapraz çizgili simge.

use eframe::egui::{self, Color32, CornerRadius, FontFamily, FontId, Margin, Shadow, Stroke};

pub const ZEMIN: Color32 = Color32::from_rgb(0x14, 0x14, 0x17); // ana pencere
pub const PANEL: Color32 = Color32::from_rgb(0x1a, 0x1a, 0x1e); // sahneler, kaynaklar, mikser, anahtarlar, kontrol barı
pub const YUZEN: Color32 = Color32::from_rgb(0x1f, 0x1f, 0x23); // mini bar, kalem barı, menüler, bildirimler
pub const ONIZLEME: Color32 = Color32::from_rgb(0x1c, 0x1c, 0x20);
pub const IZ: Color32 = Color32::from_rgb(0x26, 0x26, 0x2b); // sürgü ve seviye çizgisinin boş kısmı
pub const YAZI: Color32 = Color32::from_rgb(0xe4, 0xe4, 0xe7);
pub const YAZI2: Color32 = Color32::from_rgb(0xa1, 0xa1, 0xaa); // başlıklar, etiketler
pub const SOLUK: Color32 = Color32::from_rgb(0x8b, 0x8b, 0x94); // açıklamalar, kısayol ipuçları
pub const NOKTA: Color32 = Color32::from_rgb(0x71, 0x71, 0x7a); // tutma yeri, duraklatılmış kayıt noktası
pub const DUGME: Color32 = Color32::from_rgb(0xd4, 0xd4, 0xd8); // başlık çubuğu yazılı düğmeleri, sürgü tutamağı
pub const BEYAZ: Color32 = Color32::WHITE;
pub const KAYIT: Color32 = Color32::from_rgb(0xe5, 0x48, 0x4d);
pub const SES: Color32 = Color32::from_rgb(0x10, 0xb9, 0x81);
pub const KAPAT: Color32 = Color32::from_rgb(0xc4, 0x2b, 0x1c); // pencere kapat düğmesi üzerine gelince

// Saydam beyaz katmanlar (alfa 0..1)
pub const A_KENARLIK_INCE: f32 = 0.06;
pub const A_KENARLIK: f32 = 0.08;
pub const A_KENARLIK_MENU: f32 = 0.10;
pub const A_UZERINE: f32 = 0.07;
pub const A_SECILI: f32 = 0.10;
pub const A_KAPALI: f32 = 0.07;
pub const A_GRUP: f32 = 0.05;

pub const GOVDE_PX: f32 = 13.0;
pub const KUCUK_PX: f32 = 12.0;
pub const EN_KUCUK_PX: f32 = 11.0;

pub const KARO: (f32, f32) = (76.0, 60.0);

/// Saydam beyaz (Qt'deki rgba(255,255,255,a) ile aynı: alfa 0..255'e yuvarlanır).
pub fn beyaz(alfa: f32) -> Color32 {
    Color32::from_white_alpha((alfa * 255.0).round().clamp(0.0, 255.0) as u8)
}

pub fn saydam(c: Color32, alfa: f32) -> Color32 {
    Color32::from_rgba_unmultiplied(c.r(), c.g(), c.b(), (alfa * 255.0).round().clamp(0.0, 255.0) as u8)
}

pub fn yazi(px: f32) -> FontId {
    FontId::new(px, FontFamily::Proportional)
}

/// Yarı kalın (Qt'deki DemiBold).
pub fn kalin(px: f32) -> FontId {
    FontId::new(px, FontFamily::Name("kalin".into()))
}

fn yazi_tipleri() -> (Option<Vec<u8>>, Option<Vec<u8>>) {
    let oku = |yollar: &[&str]| yollar.iter().find_map(|y| std::fs::read(y).ok());
    let duz = oku(&[
        "C:/Windows/Fonts/SegUIVar.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
    ]);
    let kalin = oku(&[
        "C:/Windows/Fonts/seguisb.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
    ]);
    (duz, kalin)
}

pub fn kur(ctx: &egui::Context) {
    let mut fontlar = egui::FontDefinitions::default();
    let (duz, kalin) = yazi_tipleri();
    if let Some(v) = duz {
        fontlar.font_data.insert("duz".into(), std::sync::Arc::new(egui::FontData::from_owned(v)));
        fontlar.families.entry(FontFamily::Proportional).or_default().insert(0, "duz".into());
    }
    let mut kalin_ailesi = Vec::new();
    if let Some(v) = kalin {
        fontlar.font_data.insert("kalin".into(), std::sync::Arc::new(egui::FontData::from_owned(v)));
        kalin_ailesi.push("kalin".to_string());
    }
    kalin_ailesi.extend(fontlar.families.get(&FontFamily::Proportional).cloned().unwrap_or_default());
    fontlar.families.insert(FontFamily::Name("kalin".into()), kalin_ailesi);
    ctx.set_fonts(fontlar);

    let mut g = egui::Visuals::dark();
    g.panel_fill = ZEMIN;
    g.window_fill = YUZEN;
    g.window_stroke = Stroke::new(1.0, beyaz(A_KENARLIK_MENU));
    g.window_corner_radius = CornerRadius::same(10);
    g.window_shadow = Shadow { offset: [0, 6], blur: 20, spread: 0, color: Color32::from_black_alpha(90) };
    g.popup_shadow = Shadow { offset: [0, 6], blur: 18, spread: 0, color: Color32::from_black_alpha(90) };
    g.menu_corner_radius = CornerRadius::same(10);
    g.extreme_bg_color = PANEL; // metin kutularının zemini
    g.faint_bg_color = PANEL;
    g.code_bg_color = PANEL;
    g.override_text_color = None;
    g.hyperlink_color = YAZI2;
    g.selection.bg_fill = beyaz(0.2);
    g.selection.stroke = Stroke::new(1.0, BEYAZ);
    g.text_cursor.stroke = Stroke::new(1.5, YAZI);
    let w = &mut g.widgets;
    w.noninteractive.bg_fill = PANEL;
    w.noninteractive.weak_bg_fill = PANEL;
    w.noninteractive.bg_stroke = Stroke::new(1.0, beyaz(A_KENARLIK));
    w.noninteractive.fg_stroke = Stroke::new(1.0, YAZI);
    w.inactive.bg_fill = PANEL;
    w.inactive.weak_bg_fill = Color32::TRANSPARENT;
    w.inactive.bg_stroke = Stroke::new(1.0, beyaz(A_KENARLIK));
    w.inactive.fg_stroke = Stroke::new(1.0, DUGME);
    w.hovered.bg_fill = PANEL;
    w.hovered.weak_bg_fill = beyaz(A_UZERINE);
    w.hovered.bg_stroke = Stroke::new(1.0, beyaz(0.16));
    w.hovered.fg_stroke = Stroke::new(1.0, BEYAZ);
    w.active.bg_fill = PANEL;
    w.active.weak_bg_fill = beyaz(A_SECILI);
    w.active.bg_stroke = Stroke::new(1.0, beyaz(0.3));
    w.active.fg_stroke = Stroke::new(1.0, BEYAZ);
    w.open.weak_bg_fill = beyaz(A_SECILI);
    w.open.bg_fill = PANEL;
    w.open.bg_stroke = Stroke::new(1.0, beyaz(0.16));
    w.open.fg_stroke = Stroke::new(1.0, BEYAZ);
    for x in [&mut w.noninteractive, &mut w.inactive, &mut w.hovered, &mut w.active, &mut w.open] {
        x.corner_radius = CornerRadius::same(6);
        x.expansion = 0.0;
    }
    ctx.set_visuals(g);
    ctx.global_style_mut(|s| {
        s.spacing.item_spacing = egui::vec2(8.0, 6.0);
        s.spacing.button_padding = egui::vec2(12.0, 6.0);
        s.spacing.interact_size.y = 28.0;
        s.spacing.menu_margin = Margin::same(4);
        s.spacing.window_margin = Margin::same(12);
        s.spacing.tooltip_width = 360.0;
        s.interaction.tooltip_delay = 0.5;
        s.interaction.show_tooltips_only_when_still = false;
        for (t, boy) in [
            (egui::TextStyle::Body, GOVDE_PX),
            (egui::TextStyle::Button, KUCUK_PX),
            (egui::TextStyle::Small, EN_KUCUK_PX),
            (egui::TextStyle::Heading, 16.0),
            (egui::TextStyle::Monospace, GOVDE_PX),
        ] {
            if let Some(f) = s.text_styles.get_mut(&t) {
                f.size = boy;
            }
        }
    });
}
