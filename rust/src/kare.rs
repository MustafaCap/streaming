//! Kare (görüntü) ve yardımcıları. İç biçim BGRA (piksel başına 4 bayt): DXGI ekran yakalama ve
//! Media Foundation kamera bu biçimi doğrudan verir, ayrıca dönüştürme yapılmaz.
//!
//! Kareler `Arc<Kare>` olarak paylaşılır ve paylaşıldıktan sonra değiştirilmez. NV12 hali ilk
//! istendiğinde bir kez hesaplanıp karenin içinde saklanır: aynı kare sanal kameraya, kayda ve anlık
//! tekrara gittiğinde (ya da ekran değişmediği için hat aynı kareyi tekrar verdiğinde) yeniden
//! çevrilmez. Python sürümündeki `frames.nv12` önbelleğinin karşılığı.

use std::cell::RefCell;
use std::sync::{Arc, OnceLock};

use fast_image_resize as fr;

pub type KareRef = Arc<Kare>;

pub struct Kare {
    pub w: u32,
    pub h: u32,
    /// BGRA, satır satır, boşluksuz (stride = w*4)
    pub veri: Vec<u8>,
    nv12: OnceLock<Vec<u8>>,
}

impl Kare {
    pub fn yeni(w: u32, h: u32, veri: Vec<u8>) -> Kare {
        debug_assert_eq!(veri.len(), (w * h * 4) as usize);
        Kare { w, h, veri, nv12: OnceLock::new() }
    }

    pub fn dolu(w: u32, h: u32, renk: [u8; 3]) -> Kare {
        let [r, g, b] = renk;
        let mut v = Vec::with_capacity((w * h * 4) as usize);
        for _ in 0..w * h {
            v.extend_from_slice(&[b, g, r, 255]);
        }
        Kare::yeni(w, h, v)
    }

    pub fn siyah(w: u32, h: u32) -> Kare {
        Kare::dolu(w, h, [0, 0, 0])
    }

    pub fn arc(self) -> KareRef {
        Arc::new(self)
    }

    /// Paylaşılan karenin yazılabilir kopyası (NV12 önbelleği kopyalanmaz).
    pub fn kopya(&self) -> Kare {
        Kare::yeni(self.w, self.h, self.veri.clone())
    }

    pub fn boyut(&self) -> (u32, u32) {
        (self.w, self.h)
    }

    /// NV12 (BT.601 sınırlı aralık) hali; ilk çağrıda hesaplanır. Tek boyutlu, w*h*3/2 bayt.
    pub fn nv12(&self) -> &[u8] {
        self.nv12.get_or_init(|| {
            let mut hedef = vec![0u8; (self.w * self.h * 3 / 2) as usize];
            bgra_nv12(&self.veri, self.w as usize, self.h as usize, &mut hedef);
            hedef
        })
    }

    /// Piksel (r, g, b) — testler için.
    pub fn piksel(&self, x: u32, y: u32) -> [u8; 3] {
        let i = ((y * self.w + x) * 4) as usize;
        [self.veri[i + 2], self.veri[i + 1], self.veri[i]]
    }

    /// Kareyi PNG olarak kaydeder (ekran görüntüsü).
    pub fn png_kaydet(&self, yol: &std::path::Path) -> Result<(), String> {
        let mut rgb = Vec::with_capacity((self.w * self.h * 3) as usize);
        for p in self.veri.chunks_exact(4) {
            rgb.extend_from_slice(&[p[2], p[1], p[0]]);
        }
        image::save_buffer(yol, &rgb, self.w, self.h, image::ColorType::Rgb8).map_err(|e| e.to_string())
    }
}

/// BGRA -> NV12 (Y düzlemi + iç içe UV), BT.601 sınırlı aralık. Tek sayılı boyutlarda son satır/sütun
/// renk için yok sayılır (FFmpeg'e tek boyutlarda zaten RGB gider).
pub fn bgra_nv12(bgra: &[u8], w: usize, h: usize, hedef: &mut [u8]) {
    let (y_duz, uv) = hedef.split_at_mut(w * h);
    for (satir, ys) in bgra.chunks_exact(w * 4).zip(y_duz.chunks_exact_mut(w)) {
        for (p, y) in satir.chunks_exact(4).zip(ys.iter_mut()) {
            let (b, g, r) = (p[0] as i32, p[1] as i32, p[2] as i32);
            *y = (((66 * r + 129 * g + 25 * b + 128) >> 8) + 16) as u8;
        }
    }
    let (w2, h2) = (w / 2, h / 2);
    for j in 0..h2 {
        let s0 = &bgra[(2 * j) * w * 4..(2 * j + 1) * w * 4];
        let s1 = &bgra[(2 * j + 1) * w * 4..(2 * j + 2) * w * 4];
        let uvs = &mut uv[j * w2 * 2..(j + 1) * w2 * 2];
        for i in 0..w2 {
            let a = i * 8;
            let b = (s0[a] as i32 + s0[a + 4] as i32 + s1[a] as i32 + s1[a + 4] as i32 + 2) >> 2;
            let g = (s0[a + 1] as i32 + s0[a + 5] as i32 + s1[a + 1] as i32 + s1[a + 5] as i32 + 2) >> 2;
            let r = (s0[a + 2] as i32 + s0[a + 6] as i32 + s1[a + 2] as i32 + s1[a + 6] as i32 + 2) >> 2;
            uvs[2 * i] = (((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128).clamp(0, 255) as u8;
            uvs[2 * i + 1] = (((112 * r - 94 * g - 18 * b + 128) >> 8) + 128).clamp(0, 255) as u8;
        }
    }
}

thread_local! {
    static OLCEKLEYICI: RefCell<fr::Resizer> = RefCell::new(fr::Resizer::new());
}

/// Kaynağın (x, y, w, h) bölgesini tam olarak `w x h` boyutuna ölçekler (en-boy oranına bakmaz).
/// Küçültmede filtre ölçeğe göre genişler (alan ortalaması gibi), yazılar keskin kalır.
pub fn olcekle_bolge(kaynak: &Kare, bolge: (f64, f64, f64, f64), w: u32, h: u32) -> Kare {
    let w = w.max(1);
    let h = h.max(1);
    let (bx, by, bw, bh) = bolge;
    if bx == 0.0 && by == 0.0 && bw as u32 == kaynak.w && bh as u32 == kaynak.h && (kaynak.w, kaynak.h) == (w, h) {
        return kaynak.kopya();
    }
    let mut hedef = fr::images::Image::new(w, h, fr::PixelType::U8x4);
    let src = fr::images::ImageRef::new(kaynak.w, kaynak.h, &kaynak.veri, fr::PixelType::U8x4).expect("kare boyutu");
    let ayar = fr::ResizeOptions::new()
        .resize_alg(fr::ResizeAlg::Convolution(fr::FilterType::Bilinear))
        .use_alpha(false)
        .crop(bx, by, bw, bh);
    OLCEKLEYICI.with(|r| {
        let _ = r.borrow_mut().resize(&src, &mut hedef, &ayar);
    });
    Kare::yeni(w, h, hedef.into_vec())
}

pub fn olcekle(kaynak: &Kare, w: u32, h: u32) -> Kare {
    olcekle_bolge(kaynak, (0.0, 0.0, kaynak.w as f64, kaynak.h as f64), w, h)
}

/// sigdir()'in ölçeği ve kaydırması: kaynak (x, y) -> çıkış (x*olcek + dx, y*olcek + dy).
pub fn sigdir_donusumu(w: u32, h: u32, genislik: u32, yukseklik: u32) -> (f64, i64, i64) {
    let olcek = (genislik as f64 / w as f64).min(yukseklik as f64 / h as f64);
    let yw = ((w as f64 * olcek).round() as i64).max(1);
    let yh = ((h as f64 * olcek).round() as i64).max(1);
    (olcek, (genislik as i64 - yw) / 2, (yukseklik as i64 - yh) / 2)
}

/// En-boy oranını bozmadan sığdırır; boşluklar siyah kalır (21:9 monitör 16:9 çıkışta bantlı).
pub fn sigdir(kaynak: &Kare, genislik: u32, yukseklik: u32) -> Kare {
    if kaynak.boyut() == (genislik, yukseklik) {
        return kaynak.kopya();
    }
    let (olcek, dx, dy) = sigdir_donusumu(kaynak.w, kaynak.h, genislik, yukseklik);
    let yw = ((kaynak.w as f64 * olcek).round() as u32).max(1);
    let yh = ((kaynak.h as f64 * olcek).round() as u32).max(1);
    let kucuk = olcekle(kaynak, yw, yh);
    if (yw, yh) == (genislik, yukseklik) {
        return kucuk;
    }
    let mut tuval = Kare::siyah(genislik, yukseklik);
    yapistir(&mut tuval, &kucuk, dx as i32, dy as i32);
    tuval
}

/// Kaynağın bir bölgesini (x, y, w, h; kaynak pikselinde) çıkışa en-boy oranını koruyarak sığdırır
/// (bölge seçme / yakınlaştırma). Bölge kaynağın dışına taşarsa içine çekilir.
pub fn sigdir_bolge(kaynak: &Kare, bolge: (f64, f64, f64, f64), genislik: u32, yukseklik: u32) -> Kare {
    let (bx, by, bw, bh) = bolge_sinirla(kaynak, bolge);
    let (olcek, dx, dy) = sigdir_donusumu(bw.round() as u32, bh.round() as u32, genislik, yukseklik);
    let yw = ((bw * olcek).round() as u32).clamp(1, genislik);
    let yh = ((bh * olcek).round() as u32).clamp(1, yukseklik);
    let kucuk = olcekle_bolge(kaynak, (bx, by, bw, bh), yw, yh);
    if (yw, yh) == (genislik, yukseklik) {
        return kucuk;
    }
    let mut tuval = Kare::siyah(genislik, yukseklik);
    yapistir(&mut tuval, &kucuk, dx as i32, dy as i32);
    tuval
}

/// Bölgeyi kaynağın içine çeker; en az 16x16.
pub fn bolge_sinirla(kaynak: &Kare, (bx, by, bw, bh): (f64, f64, f64, f64)) -> (f64, f64, f64, f64) {
    let (kw, kh) = (kaynak.w as f64, kaynak.h as f64);
    let bw = bw.clamp(16.0_f64.min(kw), kw);
    let bh = bh.clamp(16.0_f64.min(kh), kh);
    (bx.clamp(0.0, kw - bw), by.clamp(0.0, kh - bh), bw, bh)
}

/// w x h alanı tam dolduracak şekilde ortadan kırpar ve ölçekler.
pub fn kirp_doldur(kaynak: &Kare, w: u32, h: u32) -> Kare {
    let (kw, kh) = (kaynak.w as f64, kaynak.h as f64);
    let olcek = (w as f64 / kw).max(h as f64 / kh);
    let kes_w = kw.min((w as f64 / olcek).round());
    let kes_h = kh.min((h as f64 / olcek).round());
    let x0 = ((kw - kes_w) / 2.0).floor();
    let y0 = ((kh - kes_h) / 2.0).floor();
    olcekle_bolge(kaynak, (x0, y0, kes_w, kes_h), w, h)
}

/// `parca`yı tuvalin (x, y) noktasına kopyalar (taşan kısım kesilir, alfa yok sayılır).
pub fn yapistir(tuval: &mut Kare, parca: &Kare, x: i32, y: i32) {
    let (tw, th) = (tuval.w as i32, tuval.h as i32);
    let x0 = x.max(0);
    let x1 = (x + parca.w as i32).min(tw);
    if x1 <= x0 {
        return;
    }
    for py in 0..parca.h as i32 {
        let ty = y + py;
        if ty < 0 || ty >= th {
            continue;
        }
        let ks = ((py * parca.w as i32 + (x0 - x)) * 4) as usize;
        let ke = ks + ((x1 - x0) * 4) as usize;
        let hs = ((ty * tw + x0) * 4) as usize;
        tuval.veri[hs..hs + (ke - ks)].copy_from_slice(&parca.veri[ks..ke]);
    }
}

/// Alfa kanalını kullanarak üstüne koyar (logo gibi saydam görseller).
pub fn alfa_yapistir(tuval: &mut Kare, parca: &Kare, x: i32, y: i32) {
    let (tw, th) = (tuval.w as i32, tuval.h as i32);
    for py in 0..parca.h as i32 {
        let ty = y + py;
        if ty < 0 || ty >= th {
            continue;
        }
        for px in 0..parca.w as i32 {
            let tx = x + px;
            if tx < 0 || tx >= tw {
                continue;
            }
            let k = ((py * parca.w as i32 + px) * 4) as usize;
            let t = ((ty * tw + tx) * 4) as usize;
            let a = parca.veri[k + 3] as u32;
            if a == 255 {
                tuval.veri[t..t + 3].copy_from_slice(&parca.veri[k..k + 3]);
            } else if a > 0 {
                for c in 0..3 {
                    let v = (parca.veri[k + c] as u32 * a + tuval.veri[t + c] as u32 * (255 - a) + 127) / 255;
                    tuval.veri[t + c] = v as u8;
                }
            }
        }
    }
}

/// a'dan b'ye geçiş: t=0 -> a, t=1 -> b.
pub fn karistir(a: &KareRef, b: &KareRef, t: f32) -> KareRef {
    if t <= 0.0 || a.boyut() != b.boyut() {
        return if t <= 0.0 { a.clone() } else { b.clone() };
    }
    if t >= 1.0 {
        return b.clone();
    }
    let tb = (t * 256.0) as u32;
    let ta = 256 - tb;
    let veri = a.veri.iter().zip(b.veri.iter()).map(|(&x, &y)| ((x as u32 * ta + y as u32 * tb) >> 8) as u8).collect();
    Kare::yeni(a.w, a.h, veri).arc()
}

/// Dikdörtgeni karartır ve renk ekler (metin bandı): v = v*carpan + ek
pub fn karart(tuval: &mut Kare, x: u32, y: u32, w: u32, h: u32, carpan: f32, ek: [u8; 3]) {
    let c = (carpan * 256.0) as u32;
    let [r, g, b] = ek;
    let ekler = [b as u32, g as u32, r as u32];
    for yy in y..(y + h).min(tuval.h) {
        let s = ((yy * tuval.w + x) * 4) as usize;
        let e = ((yy * tuval.w + (x + w).min(tuval.w)) * 4) as usize;
        for p in tuval.veri[s..e].chunks_exact_mut(4) {
            for k in 0..3 {
                p[k] = (((p[k] as u32 * c) >> 8) + ekler[k]).min(255) as u8;
            }
        }
    }
}

/// tiny-skia için renk: kare BGRA olduğu için kırmızı ile mavi yer değiştirir.
pub fn skia_renk(r: u8, g: u8, b: u8, a: u8) -> tiny_skia::Color {
    tiny_skia::Color::from_rgba8(b, g, r, a)
}

/// Kareye tiny-skia ile çizim yapmak için (kareler opak olduğu için önceden çarpılmış alfa sorun değil).
pub fn tuval<R>(kare: &mut Kare, f: impl FnOnce(&mut tiny_skia::PixmapMut) -> R) -> Option<R> {
    let mut p = tiny_skia::PixmapMut::from_bytes(&mut kare.veri, kare.w, kare.h)?;
    Some(f(&mut p))
}

// Klasik ok imleci (sol üst ucu 0,0), 1 birim = 1 piksel @ 19 piksel boy
const IMLEC: [(f32, f32); 7] = [(0.0, 0.0), (0.0, 16.0), (4.0, 12.0), (7.0, 19.0), (10.0, 18.0), (7.0, 11.0), (12.0, 11.0)];

/// Beyaz dolgulu, siyah kenarlı fare oku (DXGI imleci yakalamaz; kendimiz çizeriz).
pub fn imlec_ciz(kare: &mut Kare, x: f32, y: f32, boy: f32) {
    let o = boy / 19.0;
    let mut pb = tiny_skia::PathBuilder::new();
    for (i, (px, py)) in IMLEC.iter().enumerate() {
        let (qx, qy) = (x + px * o, y + py * o);
        if i == 0 {
            pb.move_to(qx, qy)
        } else {
            pb.line_to(qx, qy)
        }
    }
    pb.close();
    let Some(yol) = pb.finish() else { return };
    tuval(kare, |p| {
        let mut boya = tiny_skia::Paint::default();
        boya.anti_alias = true;
        boya.set_color(skia_renk(255, 255, 255, 255));
        p.fill_path(&yol, &boya, tiny_skia::FillRule::Winding, tiny_skia::Transform::identity(), None);
        boya.set_color(skia_renk(0, 0, 0, 255));
        let cizgi = tiny_skia::Stroke { width: 1.0, ..Default::default() };
        p.stroke_path(&yol, &boya, &cizgi, tiny_skia::Transform::identity(), None);
    });
}

/// Dikdörtgen kenarı (kamera kutusunun çerçevesi).
pub fn cerceve(kare: &mut Kare, x: f32, y: f32, w: f32, h: f32, kalinlik: f32, renk: [u8; 3]) {
    let Some(r) = tiny_skia::Rect::from_xywh(x, y, w, h) else { return };
    let yol = tiny_skia::PathBuilder::from_rect(r);
    tuval(kare, |p| {
        let mut boya = tiny_skia::Paint::default();
        boya.set_color(skia_renk(renk[0], renk[1], renk[2], 255));
        let cizgi = tiny_skia::Stroke { width: kalinlik, ..Default::default() };
        p.stroke_path(&yol, &boya, &cizgi, tiny_skia::Transform::identity(), None);
    });
}

/// Resim dosyasını açar (PNG/JPEG/BMP/WebP), alfa korunur. Türkçe karakterli yollar sorun değil.
pub fn gorsel_oku(yol: &std::path::Path) -> Option<Kare> {
    let resim = image::open(yol).ok()?.into_rgba8();
    let (w, h) = resim.dimensions();
    let mut v = resim.into_raw();
    for p in v.chunks_exact_mut(4) {
        p.swap(0, 2);
    }
    Some(Kare::yeni(w, h, v))
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn nv12_beyaz_siyah() {
        let k = Kare::dolu(4, 2, [255, 255, 255]);
        let n = k.nv12();
        assert_eq!(n.len(), 12);
        assert_eq!(n[0], 235);
        assert_eq!(n[8], 128);
        let s = Kare::siyah(4, 2);
        assert_eq!(s.nv12()[0], 16);
    }

    #[test]
    fn nv12_kirmizi_bt601() {
        let k = Kare::dolu(2, 2, [255, 0, 0]);
        let n = k.nv12();
        assert_eq!(n[0], 82);
        assert_eq!(n[4], 90);
        assert_eq!(n[5], 240);
    }

    #[test]
    fn sigdir_bantli() {
        let k = Kare::dolu(2560, 1080, [200, 100, 50]);
        let s = sigdir(&k, 1280, 720);
        assert_eq!(s.boyut(), (1280, 720));
        assert_eq!(s.piksel(640, 5), [0, 0, 0]);
        assert_eq!(s.piksel(640, 360), [200, 100, 50]);
    }

    #[test]
    fn olcekle_ayni_renk() {
        let k = Kare::dolu(1920, 1080, [10, 20, 30]);
        let s = olcekle(&k, 1280, 720);
        assert_eq!(s.piksel(100, 100), [10, 20, 30]);
    }

    #[test]
    fn kirp_doldur_boyut() {
        let k = Kare::dolu(640, 480, [1, 2, 3]);
        let s = kirp_doldur(&k, 320, 180);
        assert_eq!(s.boyut(), (320, 180));
    }

    #[test]
    fn karistir_yarim() {
        let a = Kare::dolu(2, 2, [0, 0, 0]).arc();
        let b = Kare::dolu(2, 2, [200, 200, 200]).arc();
        let c = karistir(&a, &b, 0.5);
        assert_eq!(c.piksel(0, 0), [100, 100, 100]);
    }

    #[test]
    fn imlec_cizilir() {
        let mut k = Kare::siyah(40, 40);
        imlec_ciz(&mut k, 5.0, 5.0, 22.0);
        assert_eq!(k.piksel(7, 15), [255, 255, 255]);
    }

    #[test]
    fn yapistir_tasan_kesilir() {
        let mut t = Kare::siyah(10, 10);
        let p = Kare::dolu(5, 5, [9, 9, 9]);
        yapistir(&mut t, &p, 8, -2);
        assert_eq!(t.piksel(9, 0), [9, 9, 9]);
        assert_eq!(t.piksel(7, 0), [0, 0, 0]);
    }
}
