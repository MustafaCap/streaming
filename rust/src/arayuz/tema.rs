//! Renkler ve yazı (Python ui/theme.py ile aynı gri tema). Renk sadece anlam taşıdığı yerde:
//! kayıt kırmızısı (kayıt sürerken küçük nokta) ve ses yeşili (canlı ses seviyesi).

use eframe::egui::{self, Color32, CornerRadius, Stroke};

pub const ZEMIN: Color32 = Color32::from_rgb(0x14, 0x14, 0x17);
pub const PANEL: Color32 = Color32::from_rgb(0x1a, 0x1a, 0x1e);
pub const YUZEN: Color32 = Color32::from_rgb(0x1f, 0x1f, 0x23);
pub const ONIZLEME: Color32 = Color32::from_rgb(0x1c, 0x1c, 0x20);
pub const IZ: Color32 = Color32::from_rgb(0x26, 0x26, 0x2b);
pub const YAZI: Color32 = Color32::from_rgb(0xe4, 0xe4, 0xe7);
pub const YAZI2: Color32 = Color32::from_rgb(0xa1, 0xa1, 0xaa);
pub const SOLUK: Color32 = Color32::from_rgb(0x8b, 0x8b, 0x94);
pub const KAYIT: Color32 = Color32::from_rgb(0xe5, 0x48, 0x4d);
pub const SES: Color32 = Color32::from_rgb(0x10, 0xb9, 0x81);

pub fn kur(ctx: &egui::Context) {
    let mut fontlar = egui::FontDefinitions::default();
    for (ad, yol) in [("segoe", "C:/Windows/Fonts/segoeui.ttf"), ("segoe-kalin", "C:/Windows/Fonts/segoeuib.ttf")] {
        if let Ok(v) = std::fs::read(yol) {
            fontlar.font_data.insert(ad.into(), std::sync::Arc::new(egui::FontData::from_owned(v)));
            if ad == "segoe" {
                fontlar.families.entry(egui::FontFamily::Proportional).or_default().insert(0, ad.into());
            }
        }
    }
    ctx.set_fonts(fontlar);
    let mut g = egui::Visuals::dark();
    g.panel_fill = PANEL;
    g.window_fill = YUZEN;
    g.extreme_bg_color = ZEMIN;
    g.override_text_color = Some(YAZI);
    g.window_corner_radius = CornerRadius::same(10);
    g.widgets.noninteractive.bg_stroke = Stroke::new(1.0, Color32::from_white_alpha(20));
    g.widgets.inactive.weak_bg_fill = Color32::from_white_alpha(10);
    g.widgets.inactive.bg_fill = Color32::from_white_alpha(10);
    g.widgets.hovered.weak_bg_fill = Color32::from_white_alpha(18);
    g.widgets.active.weak_bg_fill = Color32::from_white_alpha(26);
    g.selection.bg_fill = Color32::from_white_alpha(26);
    g.selection.stroke = Stroke::new(1.0, YAZI);
    for w in [&mut g.widgets.inactive, &mut g.widgets.hovered, &mut g.widgets.active] {
        w.corner_radius = CornerRadius::same(8);
    }
    ctx.set_visuals(g);
    ctx.global_style_mut(|s| {
        s.spacing.item_spacing = egui::vec2(8.0, 6.0);
        s.spacing.button_padding = egui::vec2(10.0, 6.0);
        for (t, boy) in [
            (egui::TextStyle::Body, 13.5),
            (egui::TextStyle::Button, 13.5),
            (egui::TextStyle::Small, 11.5),
            (egui::TextStyle::Heading, 17.0),
        ] {
            if let Some(f) = s.text_styles.get_mut(&t) {
                f.size = boy;
            }
        }
    });
}
