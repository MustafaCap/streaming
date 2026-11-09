//! Karelere Türkçe karakter destekli yazı (bekleme ekranı, "Kamera yok", metin bandı).
//! Windows'un Segoe UI yazı tipi kullanılır; bulunamazsa Arial, Linux'ta (testler) DejaVu.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use ab_glyph::{Font, FontVec, PxScale, ScaleFont};

use crate::kare::{Kare, KareRef};

const FONTLAR: &[&str] = &[
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
];

pub const ZEMIN: [u8; 3] = [18, 20, 25];
pub const IKINCIL_YAZI: [u8; 3] = [163, 169, 184];
pub const ANA_YAZI: [u8; 3] = [232, 234, 240];

fn font() -> Option<&'static FontVec> {
    static F: OnceLock<Option<FontVec>> = OnceLock::new();
    F.get_or_init(|| FONTLAR.iter().find_map(|y| std::fs::read(y).ok().and_then(|v| FontVec::try_from_vec(v).ok())))
        .as_ref()
}

/// Bir satırın genişliği ve (üst, alt) sınırları piksel cinsinden.
fn satir_olc(f: &FontVec, boy: f32, metin: &str) -> f32 {
    let sf = f.as_scaled(PxScale::from(boy));
    let mut x = 0.0;
    let mut onceki = None;
    for c in metin.chars() {
        let id = sf.glyph_id(c);
        if let Some(o) = onceki {
            x += sf.kern(o, id);
        }
        x += sf.h_advance(id);
        onceki = Some(id);
    }
    x
}

/// Kareye ortalanmış (çok satırlı olabilir) yazı yazar, yerinde.
pub fn yazi_yaz(kare: &mut Kare, metin: &str, merkez: (i32, i32), boy: f32, renk: [u8; 3]) {
    let Some(f) = font() else { return };
    let sf = f.as_scaled(PxScale::from(boy));
    let satirlar: Vec<&str> = metin.split('\n').collect();
    let satir_h = sf.ascent() - sf.descent();
    let aralik = boy / 3.0;
    let toplam = satir_h * satirlar.len() as f32 + aralik * (satirlar.len() as f32 - 1.0);
    let mut y = merkez.1 as f32 - toplam / 2.0;
    let (kw, kh) = (kare.w as i32, kare.h as i32);
    let [r, g, b] = renk;
    for s in satirlar {
        let gen = satir_olc(f, boy, s);
        let mut x = merkez.0 as f32 - gen / 2.0;
        let taban = y + sf.ascent();
        let mut onceki = None;
        for c in s.chars() {
            let id = sf.glyph_id(c);
            if let Some(o) = onceki {
                x += sf.kern(o, id);
            }
            let glif = id.with_scale_and_position(PxScale::from(boy), ab_glyph::point(x, taban));
            if let Some(cizgi) = f.outline_glyph(glif) {
                let s = cizgi.px_bounds();
                cizgi.draw(|gx, gy, kapsam| {
                    let px = s.min.x as i32 + gx as i32;
                    let py = s.min.y as i32 + gy as i32;
                    if px < 0 || py < 0 || px >= kw || py >= kh || kapsam <= 0.0 {
                        return;
                    }
                    let i = ((py * kw + px) * 4) as usize;
                    let a = kapsam.min(1.0);
                    let p = &mut kare.veri[i..i + 3];
                    p[0] = (p[0] as f32 * (1.0 - a) + b as f32 * a) as u8;
                    p[1] = (p[1] as f32 * (1.0 - a) + g as f32 * a) as u8;
                    p[2] = (p[2] as f32 * (1.0 - a) + r as f32 * a) as u8;
                });
            }
            x += sf.h_advance(id);
            onceki = Some(id);
        }
        y += satir_h + aralik;
    }
}

fn onbellek() -> &'static Mutex<HashMap<(u32, u32, String, u32), KareRef>> {
    static O: OnceLock<Mutex<HashMap<(u32, u32, String, u32), KareRef>>> = OnceLock::new();
    O.get_or_init(Default::default)
}

/// Koyu zemin üzerinde ortalanmış yazı (kaynak yok, bekleme ekranı). Önbellekli, paylaşılan kare.
pub fn bilgi_karesi(w: u32, h: u32, metin: &str, boy: Option<u32>) -> KareRef {
    let boy = boy.unwrap_or_else(|| (36.0 * w as f32 / 1280.0).round().max(12.0) as u32);
    let anahtar = (w, h, metin.to_string(), boy);
    let mut o = onbellek().lock().unwrap();
    if let Some(k) = o.get(&anahtar) {
        return k.clone();
    }
    if o.len() > 32 {
        o.clear();
    }
    let mut k = Kare::dolu(w, h, ZEMIN);
    yazi_yaz(&mut k, metin, (w as i32 / 2, h as i32 / 2), boy as f32, IKINCIL_YAZI);
    let k = k.arc();
    o.insert(anahtar, k.clone());
    k
}

/// Bekleme ekranı: görsel verilmişse (ve açılabiliyorsa) o, yoksa yazı. Önbellekli.
pub fn bekleme_karesi(w: u32, h: u32, metin: &str, gorsel: &str) -> KareRef {
    static O: OnceLock<Mutex<Option<((u32, u32, String, String), KareRef)>>> = OnceLock::new();
    if gorsel.is_empty() {
        return bilgi_karesi(w, h, metin, None);
    }
    let anahtar = (w, h, gorsel.to_string(), metin.to_string());
    let mut o = O.get_or_init(Default::default).lock().unwrap();
    if let Some((a, k)) = o.as_ref() {
        if *a == anahtar {
            return k.clone();
        }
    }
    let Some(resim) = crate::kare::gorsel_oku(std::path::Path::new(gorsel)) else {
        return bilgi_karesi(w, h, metin, None);
    };
    let mut k = crate::kare::sigdir(&resim, w, h);
    if !metin.is_empty() {
        let boy = (30.0 * w as f32 / 1280.0).round().max(12.0);
        yazi_yaz(&mut k, metin, (w as i32 / 2, h as i32 - h as i32 / 10), boy, ANA_YAZI);
    }
    let k = k.arc();
    *o = Some((anahtar, k.clone()));
    k
}

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn bilgi_karesi_onbellekli() {
        let a = bilgi_karesi(320, 180, "Ekran yakalanamıyor", None);
        let b = bilgi_karesi(320, 180, "Ekran yakalanamıyor", None);
        assert!(std::sync::Arc::ptr_eq(&a, &b));
        assert_eq!(a.piksel(0, 0), ZEMIN);
    }
}
