//! Çizim kalemi (Python overlay/drawing.py): çizimlerin kendisi ve çıkış karesine çizilmesi.
//!
//! Çizimler monitöre oranla (0..1) saklanır ve iki yerde gösterilir:
//!   1) ekrandaki saydam katmanda (sen görürsün; katman ekran yakalamaya girmez)
//!   2) video hattında, çıkış karesinin üstüne (karşı taraf görür)
//! İkincisi sayesinde tam ekran oyunlarda katman görünmese bile çizim yayına gider; bölge
//! seçilince (yakınlaştırınca) çizimler de doğru yerde kalır.

use std::sync::Mutex;
use std::time::Instant;

use crate::kare::{self, Kare};

pub const TURLER: [&str; 7] = ["kalem", "fosforlu", "ok", "kare", "yazi", "lazer", "silgi"];
pub const TUR_ADLARI: [&str; 7] = ["Kalem", "Fosforlu", "Ok", "Kare", "Yazı", "Lazer", "Silgi"];
/// Çizim renkleri (kullanıcının içeriği): beyaz, kırmızı, sarı, mavi
pub const RENKLER: [[u8; 3]; 4] = [[0xF4, 0xF4, 0xF5], [0xEF, 0x44, 0x44], [0xFA, 0xCC, 0x15], [0x3B, 0x82, 0xF6]];
pub const RENK_ADLARI: [&str; 4] = ["Beyaz", "Kırmızı", "Sarı", "Mavi"];
pub const VARSAYILAN_RENK: usize = 1;
pub const KALINLIK_CARPANI: [f32; 3] = [0.6, 1.0, 1.8];
pub const KALINLIK_ADLARI: [&str; 3] = ["İnce", "Orta", "Kalın"];
pub const LAZER_OMRU: f32 = 1.6;
pub const FOSFOR_SAYDAMLIK: f32 = 0.4;
const SILGI_YARICAPI: f32 = 0.012;

/// Kalınlık monitör yüksekliğine oranla (1080p'de piksel / 1080).
pub fn kalinlik(tur: &str) -> f32 {
    (match tur {
        "kalem" => 4.0,
        "fosforlu" => 22.0,
        "ok" => 5.0,
        "kare" => 4.0,
        "yazi" => 34.0,
        "lazer" => 7.0,
        _ => 4.0,
    }) / 1080.0
}

#[derive(Clone, Debug, PartialEq)]
pub struct Sekil {
    pub tur: &'static str,
    pub renk: [u8; 3],
    pub noktalar: Vec<(f32, f32)>,
    pub metin: String,
    pub carpan: f32,
}

impl Sekil {
    pub fn kalinlik(&self) -> f32 {
        kalinlik(self.tur) * self.carpan
    }
}

fn parca_uzakligi(p: (f32, f32), a: (f32, f32), b: (f32, f32)) -> f32 {
    let (dx, dy) = (b.0 - a.0, b.1 - a.1);
    let uz = dx * dx + dy * dy;
    let t = if uz == 0.0 { 0.0 } else { (((p.0 - a.0) * dx + (p.1 - a.1) * dy) / uz).clamp(0.0, 1.0) };
    let (qx, qy) = (a.0 + t * dx, a.1 + t * dy);
    ((p.0 - qx).powi(2) + (p.1 - qy).powi(2)).sqrt()
}

/// Silgi (x, y) noktasında şekle değiyor mu. oran: monitör en/boy (x'i y ölçeğine çevirir).
pub fn sekle_degiyor_mu(s: &Sekil, x: f32, y: f32, yaricap: f32, oran: f32) -> bool {
    let u = |p: (f32, f32)| (p.0 * oran, p.1);
    let p = u((x, y));
    let pay = yaricap + s.kalinlik() / 2.0;
    match s.tur {
        "kalem" | "fosforlu" => {
            let pts: Vec<_> = s.noktalar.iter().map(|n| u(*n)).collect();
            if pts.len() == 1 {
                return ((p.0 - pts[0].0).powi(2) + (p.1 - pts[0].1).powi(2)).sqrt() <= pay;
            }
            pts.windows(2).any(|w| parca_uzakligi(p, w[0], w[1]) <= pay)
        }
        "ok" => parca_uzakligi(p, u(s.noktalar[0]), u(s.noktalar[1])) <= pay,
        "kare" => {
            let ((x0, y0), (x1, y1)) = (u(s.noktalar[0]), u(s.noktalar[1]));
            let k = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))];
            k.iter().any(|(a, b)| parca_uzakligi(p, *a, *b) <= pay)
        }
        "yazi" => {
            let (x0, y0) = u(s.noktalar[0]);
            let w = s.metin.chars().count() as f32 * s.kalinlik() * 0.55;
            let h = s.kalinlik() * 1.3;
            x0 - yaricap <= p.0 && p.0 <= x0 + w + yaricap && y0 - yaricap <= p.1 && p.1 <= y0 + h + yaricap
        }
        _ => false,
    }
}

enum Gecmis {
    Ekle,
    Sil(Vec<(usize, Sekil)>),
}

#[derive(Default)]
struct Ic {
    sekiller: Vec<Sekil>,
    aktif: Option<Sekil>,
    lazer: Vec<(f32, f32, Instant)>,
    lazer_rengi: [u8; 3],
    gecmis: Vec<Gecmis>,
    siliyor: Option<Vec<(usize, Sekil)>>,
    surum: u64,
    oran: f32,
}

/// Çizimlerin tek kaynağı; arayüz yazar, video hattı okur (iş parçacığı güvenli).
pub struct CizimDeposu {
    ic: Mutex<Ic>,
}

impl Default for CizimDeposu {
    fn default() -> Self {
        Self::new()
    }
}

impl CizimDeposu {
    pub fn new() -> Self {
        CizimDeposu { ic: Mutex::new(Ic { lazer_rengi: RENKLER[VARSAYILAN_RENK], oran: 16.0 / 9.0, ..Default::default() }) }
    }

    /// Monitörün en/boy oranı (silginin yatay mesafesi için).
    pub fn oran_ayarla(&self, oran: f32) {
        self.ic.lock().unwrap().oran = oran.max(0.1);
    }

    pub fn surum(&self) -> u64 {
        self.ic.lock().unwrap().surum
    }

    pub fn bos(&self) -> bool {
        let i = self.ic.lock().unwrap();
        i.sekiller.is_empty() && i.aktif.is_none() && i.lazer.is_empty()
    }

    pub fn lazer_var(&self) -> bool {
        !self.ic.lock().unwrap().lazer.is_empty()
    }

    fn sil(i: &mut Ic, x: f32, y: f32) {
        let oran = i.oran;
        let mut kalan = Vec::with_capacity(i.sekiller.len());
        for (n, s) in std::mem::take(&mut i.sekiller).into_iter().enumerate() {
            if sekle_degiyor_mu(&s, x, y, SILGI_YARICAPI, oran) {
                if let Some(l) = i.siliyor.as_mut() {
                    l.push((n, s));
                }
            } else {
                kalan.push(s);
            }
        }
        i.sekiller = kalan;
    }

    pub fn basla(&self, tur: &'static str, renk: [u8; 3], x: f32, y: f32, carpan: f32) {
        let mut i = self.ic.lock().unwrap();
        match tur {
            "lazer" => {
                i.lazer_rengi = renk;
                i.lazer.push((x, y, Instant::now()));
            }
            "silgi" => {
                i.siliyor = Some(vec![]);
                Self::sil(&mut i, x, y);
            }
            _ => {
                let noktalar = if matches!(tur, "kalem" | "fosforlu") { vec![(x, y)] } else { vec![(x, y), (x, y)] };
                i.aktif = Some(Sekil { tur, renk, noktalar, metin: String::new(), carpan });
            }
        }
        i.surum += 1;
    }

    pub fn surukle(&self, x: f32, y: f32) {
        let mut i = self.ic.lock().unwrap();
        if i.siliyor.is_some() {
            Self::sil(&mut i, x, y);
        } else if let Some(a) = i.aktif.as_mut() {
            if matches!(a.tur, "kalem" | "fosforlu") {
                let son = *a.noktalar.last().unwrap();
                if (son.0 - x).abs() + (son.1 - y).abs() > 0.0008 {
                    a.noktalar.push((x, y));
                }
            } else {
                *a.noktalar.last_mut().unwrap() = (x, y);
            }
        } else {
            i.lazer.push((x, y, Instant::now()));
            let n = i.lazer.len();
            if n > 400 {
                i.lazer.drain(..n - 400);
            }
        }
        i.surum += 1;
    }

    pub fn bitir(&self) {
        let mut i = self.ic.lock().unwrap();
        if let Some(l) = i.siliyor.take() {
            if !l.is_empty() {
                i.gecmis.push(Gecmis::Sil(l));
            }
        }
        if let Some(s) = i.aktif.take() {
            let anlamli = match s.tur {
                "ok" | "kare" => (s.noktalar[1].0 - s.noktalar[0].0).abs() + (s.noktalar[1].1 - s.noktalar[0].1).abs() > 0.005,
                _ => true,
            };
            if anlamli {
                i.sekiller.push(s);
                i.gecmis.push(Gecmis::Ekle);
            }
        }
        i.surum += 1;
    }

    pub fn yazi_ekle(&self, renk: [u8; 3], x: f32, y: f32, metin: &str, carpan: f32) {
        if metin.trim().is_empty() {
            return;
        }
        let mut i = self.ic.lock().unwrap();
        i.sekiller.push(Sekil { tur: "yazi", renk, noktalar: vec![(x, y)], metin: metin.into(), carpan });
        i.gecmis.push(Gecmis::Ekle);
        i.surum += 1;
    }

    /// Son çizimi geri alır; son işlem silgiyse silinenleri geri getirir.
    pub fn geri_al(&self) -> bool {
        let mut i = self.ic.lock().unwrap();
        let Some(g) = i.gecmis.pop() else { return false };
        match g {
            Gecmis::Ekle => {
                i.sekiller.pop();
            }
            Gecmis::Sil(l) => {
                for (n, s) in l {
                    let n = n.min(i.sekiller.len());
                    i.sekiller.insert(n, s);
                }
            }
        }
        i.surum += 1;
        true
    }

    pub fn temizle(&self) {
        let mut i = self.ic.lock().unwrap();
        i.sekiller.clear();
        i.aktif = None;
        i.lazer.clear();
        i.gecmis.clear();
        i.siliyor = None;
        i.surum += 1;
    }

    /// Çizilecekler: (kalıcı şekiller + çizilmekte olan, lazer izi [(x, y, yaş sn)], lazer rengi).
    /// Ömrü dolan lazer noktaları burada atılır.
    pub fn anlik(&self) -> (Vec<Sekil>, Vec<(f32, f32, f32)>, [u8; 3]) {
        let mut i = self.ic.lock().unwrap();
        let simdi = Instant::now();
        let once = i.lazer.len();
        i.lazer.retain(|(_, _, t)| simdi.duration_since(*t).as_secs_f32() < LAZER_OMRU);
        if i.lazer.len() != once {
            i.surum += 1;
        }
        let mut l = i.sekiller.clone();
        if let Some(a) = &i.aktif {
            l.push(a.clone());
        }
        let lazer = i.lazer.iter().map(|(x, y, t)| (*x, *y, simdi.duration_since(*t).as_secs_f32())).collect();
        (l, lazer, i.lazer_rengi)
    }
}

/// Şekilleri kareye çizer. `donustur(x, y)`: monitöre oranlı noktayı kare pikseline çevirir;
/// `olcek`: monitör yüksekliğine oranlı kalınlığı piksele çevirir.
pub fn ciz(kare: &mut Kare, sekiller: &[Sekil], lazer: &[(f32, f32, f32)], lazer_rengi: [u8; 3], donustur: impl Fn(f32, f32) -> (f32, f32), olcek: f32) {
    use tiny_skia::{LineCap, LineJoin, Paint, PathBuilder, Stroke, Transform};
    let mut yazilar = vec![];
    kare::tuval(kare, |p| {
        for s in sekiller {
            let [r, g, b] = s.renk;
            let alfa = if s.tur == "fosforlu" { (FOSFOR_SAYDAMLIK * 255.0) as u8 } else { 255 };
            let mut boya = Paint::default();
            boya.set_color(kare::skia_renk(r, g, b, alfa));
            boya.anti_alias = true;
            let kalin = (s.kalinlik() * olcek).max(1.0);
            let cizgi = Stroke { width: kalin, line_cap: LineCap::Round, line_join: LineJoin::Round, ..Default::default() };
            let pts: Vec<(f32, f32)> = s.noktalar.iter().map(|(x, y)| donustur(*x, *y)).collect();
            match s.tur {
                "kalem" | "fosforlu" => {
                    let mut pb = PathBuilder::new();
                    pb.move_to(pts[0].0, pts[0].1);
                    if pts.len() == 1 {
                        pb.line_to(pts[0].0 + 0.1, pts[0].1);
                    }
                    for q in &pts[1..] {
                        pb.line_to(q.0, q.1);
                    }
                    if let Some(yol) = pb.finish() {
                        p.stroke_path(&yol, &boya, &cizgi, Transform::identity(), None);
                    }
                }
                "ok" => {
                    let ((x0, y0), (x1, y1)) = (pts[0], pts[1]);
                    let aci = (y1 - y0).atan2(x1 - x0);
                    let uc = (kalin * 4.0).max(10.0);
                    let mut pb = PathBuilder::new();
                    pb.move_to(x0, y0);
                    pb.line_to(x1, y1);
                    for d in [2.6f32, -2.6] {
                        pb.move_to(x1, y1);
                        pb.line_to(x1 + uc * (aci + d).cos(), y1 + uc * (aci + d).sin());
                    }
                    if let Some(yol) = pb.finish() {
                        p.stroke_path(&yol, &boya, &cizgi, Transform::identity(), None);
                    }
                }
                "kare" => {
                    let ((x0, y0), (x1, y1)) = (pts[0], pts[1]);
                    if let Some(r) = tiny_skia::Rect::from_ltrb(x0.min(x1), y0.min(y1), x0.max(x1), y0.max(y1)) {
                        let yol = PathBuilder::from_rect(r);
                        p.stroke_path(&yol, &boya, &Stroke { line_join: LineJoin::Miter, ..cizgi }, Transform::identity(), None);
                    }
                }
                "yazi" => yazilar.push((s.metin.clone(), pts[0], (s.kalinlik() * olcek).max(8.0), s.renk)),
                _ => {}
            }
        }
        // Lazer: kuyruk incelir ve solar
        if lazer.len() >= 2 {
            let [r, g, b] = lazer_rengi;
            let kalin = (kalinlik("lazer") * olcek).max(2.0);
            for w in lazer.windows(2) {
                let omur = 1.0 - (w[1].2 / LAZER_OMRU).clamp(0.0, 1.0);
                let mut boya = Paint::default();
                boya.set_color(kare::skia_renk(r, g, b, (omur * 255.0) as u8));
                boya.anti_alias = true;
                let (a, bb) = (donustur(w[0].0, w[0].1), donustur(w[1].0, w[1].1));
                let mut pb = PathBuilder::new();
                pb.move_to(a.0, a.1);
                pb.line_to(bb.0, bb.1);
                if let Some(yol) = pb.finish() {
                    let c = Stroke { width: kalin * (0.4 + 0.6 * omur), line_cap: LineCap::Round, ..Default::default() };
                    p.stroke_path(&yol, &boya, &c, Transform::identity(), None);
                }
            }
        }
    });
    for (m, (x, y), boy, renk) in yazilar {
        crate::yazi::yazi_sol_ust(kare, &m, (x, y), boy, renk);
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn ciz_geri_al_sil() {
        let d = CizimDeposu::new();
        d.basla("kalem", RENKLER[1], 0.1, 0.1, 1.0);
        d.surukle(0.5, 0.5);
        d.bitir();
        d.basla("ok", RENKLER[0], 0.2, 0.8, 1.0);
        d.surukle(0.2, 0.8); // çok kısa: eklenmez
        d.bitir();
        assert_eq!(d.anlik().0.len(), 1);
        d.basla("silgi", RENKLER[0], 0.3, 0.3, 1.0);
        d.bitir();
        assert_eq!(d.anlik().0.len(), 0);
        assert!(d.geri_al()); // silgiyi geri al
        assert_eq!(d.anlik().0.len(), 1);
        assert!(d.geri_al());
        assert!(d.anlik().0.is_empty());
    }

    #[test]
    fn kareye_cizer() {
        let d = CizimDeposu::new();
        d.basla("kare", RENKLER[1], 0.25, 0.25, 1.0);
        d.surukle(0.75, 0.75);
        d.bitir();
        let mut k = Kare::siyah(200, 100);
        let (s, l, r) = d.anlik();
        ciz(&mut k, &s, &l, r, |x, y| (x * 200.0, y * 100.0), 1080.0);
        let p = k.piksel(50, 50); // sol kenar
        assert!(p[0] > 200 && p[1] < 100, "kırmızı kenar bekleniyordu: {p:?}");
    }
}
