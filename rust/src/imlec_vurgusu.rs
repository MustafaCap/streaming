//! İmleç vurgulama (Python overlay/cursor.py): imlecin etrafında yumuşak sarı bir halka,
//! tıklayınca genişleyen dalga.
//!
//! Sadece çıkış görüntüsüne çizilir (karşı taraf görür). Sol tık Windows'tan GetAsyncKeyState
//! ile okunur; video hattı her karede bir kez sorar.

use std::time::{Duration, Instant};

use crate::kare::{self, Kare};

pub const DALGA_SURESI: Duration = Duration::from_millis(500);
/// Sarı (#FFD43B)
const RENK: [u8; 3] = [255, 212, 59];

#[cfg(windows)]
fn sol_tus_basili() -> bool {
    unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(0x01) as u16 & 0x8000 != 0 }
}

#[cfg(not(windows))]
fn sol_tus_basili() -> bool {
    false
}

#[derive(Default)]
pub struct ImlecVurgusu {
    onceki_basili: bool,
    /// (x, y, başlangıç): kaynak (monitör) pikseli
    dalgalar: Vec<(f64, f64, Instant)>,
}

impl ImlecVurgusu {
    /// Her karede çağrılır: yeni tıklama varsa dalga başlatır. konum: monitör pikseli ya da None.
    pub fn guncelle(&mut self, konum: Option<(f32, f32)>) {
        self.guncelle_tusla(konum, sol_tus_basili(), Instant::now());
    }

    fn guncelle_tusla(&mut self, konum: Option<(f32, f32)>, basili: bool, simdi: Instant) {
        if basili && !self.onceki_basili {
            if let Some((x, y)) = konum {
                self.dalgalar.push((x as f64, y as f64, simdi));
            }
        }
        self.onceki_basili = basili;
        self.dalgalar.retain(|d| simdi.saturating_duration_since(d.2) < DALGA_SURESI);
        if self.dalgalar.len() > 5 {
            self.dalgalar.drain(..self.dalgalar.len() - 5);
        }
    }

    pub fn dalga_var(&self) -> bool {
        !self.dalgalar.is_empty()
    }

    /// Kareye halka ve dalgaları çizer. konum_cikis: imlecin çıkış karesindeki yeri;
    /// donusum: kaynak pikselinden çıkış pikseline.
    pub fn ciz(&self, kare: &mut Kare, konum_cikis: Option<(f32, f32)>, donusum: impl Fn(f64, f64) -> (f64, f64), olcek: f32) {
        let simdi = Instant::now();
        let r = (26.0 * olcek).floor().max(10.0);
        let [kr, kg, kb] = RENK;
        kare::tuval(kare, |p| {
            let mut boya = tiny_skia::Paint { anti_alias: true, ..Default::default() };
            if let Some((x, y)) = konum_cikis {
                if let Some(daire) = tiny_skia::PathBuilder::from_circle(x.floor(), y.floor(), r) {
                    boya.set_color(kare::skia_renk(kr, kg, kb, 64)); // %25 saydam dolgu
                    p.fill_path(&daire, &boya, tiny_skia::FillRule::Winding, tiny_skia::Transform::identity(), None);
                    boya.set_color(kare::skia_renk(kr, kg, kb, 255));
                    let cizgi = tiny_skia::Stroke { width: (2.0 * olcek).floor().max(1.0), ..Default::default() };
                    p.stroke_path(&daire, &boya, &cizgi, tiny_skia::Transform::identity(), None);
                }
            }
            for &(dx, dy, t0) in &self.dalgalar {
                let t = simdi.saturating_duration_since(t0).as_secs_f32() / DALGA_SURESI.as_secs_f32();
                if !(0.0..1.0).contains(&t) {
                    continue;
                }
                let (cx, cy) = donusum(dx, dy);
                let yaricap = (r * (0.6 + 1.6 * t)).floor();
                let kalin = (4.0 * olcek * (1.0 - t)).floor().max(1.0);
                // renk zamanla koyulaşır (Python ile aynı)
                let s = |c: u8| (c as f32 * (1.0 - t)) as u8;
                boya.set_color(kare::skia_renk(s(kr), s(kg), s(kb), 255));
                if let Some(daire) = tiny_skia::PathBuilder::from_circle(cx.floor() as f32, cy.floor() as f32, yaricap.max(1.0)) {
                    let cizgi = tiny_skia::Stroke { width: kalin, ..Default::default() };
                    p.stroke_path(&daire, &boya, &cizgi, tiny_skia::Transform::identity(), None);
                }
            }
        });
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn tiklama_dalga_baslatir_ve_soner() {
        let mut v = ImlecVurgusu::default();
        let t = Instant::now();
        v.guncelle_tusla(Some((10.0, 10.0)), false, t);
        assert!(!v.dalga_var());
        v.guncelle_tusla(Some((10.0, 10.0)), true, t);
        assert!(v.dalga_var());
        // basılı tutmak yeni dalga başlatmaz
        v.guncelle_tusla(Some((10.0, 10.0)), true, t);
        assert_eq!(v.dalgalar.len(), 1);
        v.guncelle_tusla(Some((10.0, 10.0)), false, t + Duration::from_millis(600));
        assert!(!v.dalga_var());
    }

    #[test]
    fn halka_cizilir() {
        let mut k = Kare::siyah(100, 100);
        let v = ImlecVurgusu::default();
        v.ciz(&mut k, Some((50.0, 50.0)), |x, y| (x, y), 1.0);
        let px = |x: u32, y: u32| k.piksel(x, y);
        // merkez: %25 sarı; halka üstü: tam sarı; uzak: siyah
        let m = px(50, 50);
        assert!(m[0] > 40 && m[0] < 90, "{m:?}");
        let h = px(50, 24);
        assert!(h[0] > 200, "{h:?}");
        assert_eq!(px(5, 5), [0, 0, 0]);
    }
}
