//! Simgeler (Python ui/icons.py): ince çizgili SVG simgeler ve uygulama logosu.
//!
//! Çizimler Lucide simge setinin çizgi diliyle aynı (ISC lisansı): 24×24 alan, 1.75 kalınlık,
//! yuvarlak uçlar. SVG'ler resvg ile istenen boyutta ve renkte çizilip doku olarak saklanır.
//! Kapalı durumda simgenin üstüne çapraz çizgi eklenir (renk tek başına durum anlatmasın).

use std::collections::HashMap;
use std::sync::Mutex;

use eframe::egui::{self, Color32, Pos2, Rect, TextureHandle, Vec2};

const CIZGI: &str = r#"fill="none" stroke="currentColor" stroke-width="{k}" stroke-linecap="round" stroke-linejoin="round""#;

pub fn govde(ad: &str) -> &'static str {
    match ad {
        "mikrofon" => r#"<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>"#,
        "ses" => r#"<path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>"#,
        "kamera" => r#"<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>"#,
        "bolge" => r#"<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>"#,
        "kalem" => r#"<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>"#,
        "fosforlu" => r#"<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>"#,
        "ok" => r#"<path d="M7 17 17 7M8 7h9v9"/>"#,
        "kare" => r#"<rect x="4" y="6" width="16" height="12" rx="1.5"/>"#,
        "yazi" => r#"<path d="M5 6V4h14v2M12 4v16M9 20h6"/>"#,
        "lazer" => r#"<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>"#,
        "silgi" => r#"<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/>"#,
        "temizle" => r#"<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>"#,
        "foto" => r#"<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13.5" r="3.5"/>"#,
        "kayit" => r#"<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>"#,
        "duraklat" => r#"<path d="M8 5v14M16 5v14" stroke-width="3"/>"#,
        "oynat" => r#"<path d="M7 4.5l13 7.5-13 7.5Z" fill="currentColor" stroke="none"/>"#,
        "bitir" => r#"<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>"#,
        "ileri" => r#"<path d="M9 6l6 6-6 6" stroke-width="2"/>"#,
        "geri" => r#"<path d="M15 6l-6 6 6 6" stroke-width="2"/>"#,
        "asagi" => r#"<path d="m6 9 6 6 6-6" stroke-width="2"/>"#,
        "arti" => r#"<path d="M12 5v14M5 12h14" stroke-width="2"/>"#,
        "kapat" => r#"<path d="M6 6l12 12M18 6 6 18"/>"#,
        "ayarlar" => r#"<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>"#,
        "kucult" => r#"<path d="M5 12h14"/>"#,
        "buyut" => r#"<rect x="4" y="4" width="16" height="16" rx="2"/>"#,
        "geri_yukle" => r#"<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>"#,
        "goz" => r#"<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><path d="M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/>"#,
        "goz_kapali" => r#"<path d="M2 12s3-7 10-7c1.6 0 3 .4 4.2 1M22 12s-3 7-10 7c-1.6 0-3-.4-4.2-1M3 3l18 18"/>"#,
        _ => "",
    }
}

fn capraz(ad: &str) -> &'static str {
    if ad == "kamera" {
        r#"<path d="M2 2l20 20"/>"#
    } else {
        r#"<path d="M3 3l18 18"/>"#
    }
}

fn hex(c: Color32) -> String {
    format!("#{:02x}{:02x}{:02x}", c.r(), c.g(), c.b())
}

pub fn svg(ad: &str, renk: Color32, cizgili: bool) -> String {
    let r = hex(renk);
    let mut g = govde(ad).to_string();
    if cizgili {
        g.push_str(capraz(ad));
    }
    format!(
        r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="{r}" {}>{}</svg>"#,
        CIZGI.replace("{k}", "1.75"),
        g
    )
    .replace("currentColor", &r)
}

/// SVG'yi `px` × `px` RGBA olarak çizer (önceden çarpılmamış alfa).
pub fn ciz(svg: &str, px: u32) -> Option<egui::ColorImage> {
    let agac = resvg::usvg::Tree::from_str(svg, &resvg::usvg::Options::default()).ok()?;
    let mut pm = resvg::tiny_skia::Pixmap::new(px.max(1), px.max(1))?;
    let o = px as f32 / agac.size().width();
    resvg::render(&agac, resvg::tiny_skia::Transform::from_scale(o, o), &mut pm.as_mut());
    let mut rgba = Vec::with_capacity((px * px * 4) as usize);
    for p in pm.pixels() {
        let c = p.demultiply();
        rgba.extend_from_slice(&[c.red(), c.green(), c.blue(), c.alpha()]);
    }
    Some(egui::ColorImage::from_rgba_unmultiplied([px as usize, px as usize], &rgba))
}

type Anahtar = (&'static str, [u8; 4], u32, bool);

static ONBELLEK: Mutex<Option<HashMap<Anahtar, TextureHandle>>> = Mutex::new(None);

fn doku(ctx: &egui::Context, ad: &'static str, renk: Color32, px: u32, cizgili: bool) -> Option<TextureHandle> {
    let anahtar = (ad, renk.to_array(), px, cizgili);
    let mut g = ONBELLEK.lock().unwrap();
    let harita = g.get_or_insert_with(HashMap::new);
    if let Some(t) = harita.get(&anahtar) {
        return Some(t.clone());
    }
    let resim = ciz(&svg(ad, renk, cizgili), px)?;
    let t = ctx.load_texture(format!("simge-{ad}-{px}-{cizgili}-{:?}", renk.to_array()), resim, egui::TextureOptions::LINEAR);
    harita.insert(anahtar, t.clone());
    Some(t)
}

/// Simgeyi `boyut` (mantıksal px) kare içinde `sol_ust`'e çizer.
pub fn simge(ui: &egui::Ui, ad: &'static str, renk: Color32, boyut: f32, sol_ust: Pos2, cizgili: bool) {
    let px = (boyut * ui.ctx().pixels_per_point()).round() as u32;
    if let Some(t) = doku(ui.ctx(), ad, renk, px, cizgili) {
        let r = Rect::from_min_size(sol_ust, Vec2::splat(boyut));
        ui.painter().image(t.id(), r, Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)), Color32::WHITE);
    }
}

/// Simgeyi bir dikdörtgenin ortasına çizer.
pub fn ortaya(ui: &egui::Ui, ad: &'static str, renk: Color32, boyut: f32, r: Rect, cizgili: bool) {
    let sol_ust = Pos2::new((r.center().x - boyut / 2.0).round(), (r.center().y - boyut / 2.0).round());
    simge(ui, ad, renk, boyut, sol_ust, cizgili);
}

pub const LOGO_PNG: &[u8] = include_bytes!("../../varliklar/logo.png");

static LOGO: Mutex<Option<TextureHandle>> = Mutex::new(None);

pub fn logo(ctx: &egui::Context) -> Option<TextureHandle> {
    let mut g = LOGO.lock().unwrap();
    if g.is_none() {
        let r = image::load_from_memory(LOGO_PNG).ok()?.into_rgba8();
        let (w, h) = r.dimensions();
        let resim = egui::ColorImage::from_rgba_unmultiplied([w as usize, h as usize], &r.into_raw());
        *g = Some(ctx.load_texture("logo", resim, egui::TextureOptions::LINEAR));
    }
    g.clone()
}

pub fn logo_ikonu() -> Option<egui::IconData> {
    let r = image::load_from_memory(LOGO_PNG).ok()?.into_rgba8();
    let (w, h) = r.dimensions();
    Some(egui::IconData { rgba: r.into_raw(), width: w, height: h })
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn tum_simgeler_cizilir() {
        for ad in [
            "mikrofon", "ses", "kamera", "bolge", "kalem", "fosforlu", "ok", "kare", "yazi", "lazer", "silgi", "temizle", "foto", "kayit",
            "duraklat", "oynat", "bitir", "ileri", "geri", "asagi", "arti", "kapat", "ayarlar", "kucult", "buyut", "geri_yukle", "goz",
            "goz_kapali",
        ] {
            let r = ciz(&svg(ad, Color32::WHITE, ad == "kamera"), 36).unwrap_or_else(|| panic!("{ad} çizilemedi"));
            assert!(r.pixels.iter().any(|p| p.a() > 0), "{ad} boş");
        }
    }
}
