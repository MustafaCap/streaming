//! Anlık kare seçme (Python capture/region.py): yumuşak yakınlaştırma ve vurgulama modu.
//!
//! Seçilen bölge monitöre oranla (0..1) tutulur; böylece çözünürlükten bağımsızdır.
//!   - yakınlaştırma: çıkışta sadece seçilen kare görünür; tam ekrandan kareye animasyonla
//!     geçilir (geri dönerken de animasyonlu)
//!   - vurgulama: ekranın tamamı görünür ama seçilen yerin dışı kararır
//!
//! Video hattı her karede `gorunum()` ile o anki durumu sorar.

use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::kare::{self, Kare};

pub const TAM: [f64; 4] = [0.0, 0.0, 1.0, 1.0];
pub const YAKINLASTIR: &str = "yakinlastir";
pub const VURGULA: &str = "vurgula";

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Gorunum {
    /// monitörün hangi kısmı çıkışa gidiyor (x, y, w, h)
    pub kirpma: [f64; 4],
    /// kararmayan bölge (monitöre oranla) ya da None
    pub vurgu: Option<[f64; 4]>,
    /// 0 = hiç, 1 = tam karartma gücü
    pub karartma: f64,
}

impl Gorunum {
    const TAM_EKRAN: Gorunum = Gorunum { kirpma: TAM, vurgu: None, karartma: 0.0 };

    /// Görünüm hiçbir şey değiştirmiyor mu (tam ekran, karartma yok)
    pub fn tam_mi(&self) -> bool {
        self.kirpma == TAM && self.vurgu.is_none()
    }

    /// Önbellek imzası (onbinde bir hassasiyet)
    pub fn imza(&self) -> [i64; 9] {
        let q = |v: f64| (v * 10000.0).round() as i64;
        let v = self.vurgu.unwrap_or([-1.0; 4]);
        [q(self.kirpma[0]), q(self.kirpma[1]), q(self.kirpma[2]), q(self.kirpma[3]), q(v[0]), q(v[1]), q(v[2]), q(v[3]), q(self.karartma)]
    }
}

fn yumusat(t: f64) -> f64 {
    let t = t.clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn ara(a: [f64; 4], b: [f64; 4], t: f64) -> [f64; 4] {
    [0, 1, 2, 3].map(|i| a[i] + (b[i] - a[i]) * t)
}

/// Taşanları kırpar, en az %2 boyut bırakır.
pub fn normalize([x, y, w, h]: [f64; 4]) -> [f64; 4] {
    let (x0, y0) = (x.clamp(0.0, 1.0), y.clamp(0.0, 1.0));
    let (x1, y1) = ((x + w).clamp(0.0, 1.0), (y + h).clamp(0.0, 1.0));
    let (w, h) = ((x1 - x0).max(0.02), (y1 - y0).max(0.02));
    [x0.min(1.0 - w), y0.min(1.0 - h), w, h]
}

struct Ic {
    mod_: Option<&'static str>,
    bolge: Option<[f64; 4]>,
    bas: Gorunum,
    hedef: Gorunum,
    t0: Option<Instant>,
}

pub struct BolgeSecimi {
    sure: Duration,
    pub karartma_gucu: f64,
    ic: Mutex<Ic>,
}

impl Default for BolgeSecimi {
    fn default() -> Self {
        Self::yeni(450, 0.65)
    }
}

impl BolgeSecimi {
    pub fn yeni(sure_ms: u64, karartma_gucu: f64) -> Self {
        BolgeSecimi {
            sure: Duration::from_millis(sure_ms),
            karartma_gucu,
            ic: Mutex::new(Ic { mod_: None, bolge: None, bas: Gorunum::TAM_EKRAN, hedef: Gorunum::TAM_EKRAN, t0: None }),
        }
    }

    pub fn aktif(&self) -> bool {
        self.ic.lock().unwrap().mod_.is_some()
    }

    /// None | "yakinlastir" | "vurgula"
    pub fn mod_(&self) -> Option<&'static str> {
        self.ic.lock().unwrap().mod_
    }

    /// Son seçilen bölge (monitöre oranla)
    pub fn bolge(&self) -> Option<[f64; 4]> {
        self.ic.lock().unwrap().bolge
    }

    fn su_an(&self, i: &Ic, simdi: Instant) -> Gorunum {
        let Some(t0) = i.t0 else { return i.hedef };
        if self.sure.is_zero() {
            return i.hedef;
        }
        let t = yumusat(simdi.saturating_duration_since(t0).as_secs_f64() / self.sure.as_secs_f64());
        if t >= 1.0 {
            return i.hedef;
        }
        let (b, h) = (i.bas, i.hedef);
        let vurgu = match (b.vurgu, h.vurgu) {
            (Some(a), Some(c)) => Some(ara(a, c, t)),
            (a, c) => c.or(a),
        };
        Gorunum { kirpma: ara(b.kirpma, h.kirpma, t), vurgu, karartma: b.karartma + (h.karartma - b.karartma) * t }
    }

    pub fn sec(&self, bolge: [f64; 4], mod_: &str) {
        self.sec_zamanla(bolge, mod_, Instant::now());
    }

    fn sec_zamanla(&self, bolge: [f64; 4], mod_: &str, simdi: Instant) {
        let bolge = normalize(bolge);
        let (mod_, hedef) = if mod_ == VURGULA {
            (VURGULA, Gorunum { kirpma: TAM, vurgu: Some(bolge), karartma: 1.0 })
        } else {
            (YAKINLASTIR, Gorunum { kirpma: bolge, vurgu: None, karartma: 0.0 })
        };
        let mut i = self.ic.lock().unwrap();
        i.bas = self.su_an(&i, simdi);
        i.hedef = hedef;
        i.t0 = Some(simdi);
        i.mod_ = Some(mod_);
        i.bolge = Some(bolge);
    }

    pub fn temizle(&self) {
        self.temizle_zamanla(Instant::now());
    }

    fn temizle_zamanla(&self, simdi: Instant) {
        let mut i = self.ic.lock().unwrap();
        i.bas = self.su_an(&i, simdi);
        // vurgulamadan çıkarken karartma kaybolsun ama bölge çerçevesi kaybolana kadar yerinde kalsın
        i.hedef = Gorunum { kirpma: TAM, vurgu: i.bas.vurgu, karartma: 0.0 };
        i.t0 = Some(simdi);
        i.mod_ = None;
    }

    pub fn gorunum(&self) -> Gorunum {
        self.gorunum_zamanla(Instant::now())
    }

    fn gorunum_zamanla(&self, simdi: Instant) -> Gorunum {
        let i = self.ic.lock().unwrap();
        let g = self.su_an(&i, simdi);
        if g.karartma <= 0.001 {
            Gorunum { kirpma: g.kirpma, vurgu: None, karartma: 0.0 }
        } else {
            g
        }
    }
}

/// Ham monitör karesine görünümü uygular ve çıkış boyutuna sığdırır.
/// Döndürür: (kare, (x0, y0, ölçek, dx, dy)); monitör pikseli (x, y) çıkışta
/// ((x - x0) * ölçek + dx, (y - y0) * ölçek + dy) olur (fare imleci ve çizimler için).
pub fn uygula(ham: &Kare, g: &Gorunum, genislik: u32, yukseklik: u32, karartma_gucu: f64) -> (Kare, (f64, f64, f64, f64, f64)) {
    let (ww, hh) = (ham.w as f64, ham.h as f64);
    let [kx, ky, kw, kh] = g.kirpma;
    let (x0, y0) = ((kx * ww).round(), (ky * hh).round());
    let (x1, y1) = (((kx + kw) * ww).round().max(x0 + 1.0), ((ky + kh) * hh).round().max(y0 + 1.0));
    let (bw, bh) = ((x1 - x0).max(1.0), (y1 - y0).max(1.0));
    let (olcek, dx, dy) = kare::sigdir_donusumu(bw as u32, bh as u32, genislik, yukseklik);
    let mut cikis = if x0 == 0.0 && y0 == 0.0 && x1 >= ww && y1 >= hh {
        kare::sigdir(ham, genislik, yukseklik)
    } else {
        kare::sigdir_bolge(ham, (x0, y0, bw, bh), genislik, yukseklik)
    };
    let donusum = (x0, y0, olcek, dx as f64, dy as f64);
    if let (Some([vx, vy, vw, vh]), true) = (g.vurgu, g.karartma > 0.0) {
        let d = |x: f64, y: f64| ((x - x0) * olcek + dx as f64, (y - y0) * olcek + dy as f64);
        let (ax, ay) = d(vx * ww, vy * hh);
        let (bx, by) = d((vx + vw) * ww, (vy + vh) * hh);
        let (ax, ay) = (ax.max(0.0) as u32, ay.max(0.0) as u32);
        let (bx, by) = ((bx as i64).clamp(0, genislik as i64) as u32, (by as i64).clamp(0, yukseklik as i64) as u32);
        karart(&mut cikis, (ax, ay, bx, by), 1.0 - karartma_gucu * g.karartma);
        if bx > ax && by > ay {
            // ince açık gri çerçeve (arayüzle aynı dil)
            let c = (228.0 * g.karartma) as u8;
            kare::cerceve(&mut cikis, ax as f32 + 0.5, ay as f32 + 0.5, (bx - ax) as f32 - 1.0, (by - ay) as f32 - 1.0, 1.0, [c, c, c]);
        }
    }
    (cikis, donusum)
}

/// (ax, ay, bx, by) dikdörtgeninin dışını `carpan` ile koyulaştırır.
fn karart(k: &mut Kare, (ax, ay, bx, by): (u32, u32, u32, u32), carpan: f64) {
    let c = (carpan.clamp(0.0, 1.0) * 256.0) as u32;
    let w = k.w as usize;
    for y in 0..k.h {
        let satir = &mut k.veri[y as usize * w * 4..(y as usize + 1) * w * 4];
        let icinde_satir = y >= ay && y < by;
        for (x, p) in satir.chunks_exact_mut(4).enumerate() {
            let x = x as u32;
            if icinde_satir && x >= ax && x < bx {
                continue;
            }
            p[0] = ((p[0] as u32 * c) >> 8) as u8;
            p[1] = ((p[1] as u32 * c) >> 8) as u8;
            p[2] = ((p[2] as u32 * c) >> 8) as u8;
        }
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn normalize_tasanlari_kirpar() {
        assert_eq!(normalize([-0.1, 0.5, 0.5, 0.8]), [0.0, 0.5, 0.4, 0.5]);
        let n = normalize([0.99, 0.99, 0.001, 0.001]);
        assert!(n[2] >= 0.02 && n[0] + n[2] <= 1.0);
    }

    #[test]
    fn yakinlastirma_animasyonlu() {
        let b = BolgeSecimi::yeni(400, 0.65);
        let t = Instant::now();
        b.sec_zamanla([0.5, 0.5, 0.5, 0.5], YAKINLASTIR, t);
        assert_eq!(b.mod_(), Some(YAKINLASTIR));
        let yari = b.gorunum_zamanla(t + Duration::from_millis(200));
        assert!(yari.kirpma[0] > 0.1 && yari.kirpma[0] < 0.4, "{yari:?}");
        let son = b.gorunum_zamanla(t + Duration::from_millis(500));
        assert_eq!(son.kirpma, [0.5, 0.5, 0.5, 0.5]);
        b.temizle_zamanla(t + Duration::from_millis(500));
        assert!(!b.aktif());
        assert_eq!(b.gorunum_zamanla(t + Duration::from_millis(1000)).kirpma, TAM);
    }

    #[test]
    fn vurgulama_disini_karartir() {
        let b = BolgeSecimi::yeni(0, 0.65);
        b.sec([0.25, 0.25, 0.5, 0.5], VURGULA);
        let g = b.gorunum();
        assert_eq!(g.kirpma, TAM);
        let ham = Kare::dolu(100, 100, [200, 200, 200]);
        let (k, _) = uygula(&ham, &g, 100, 100, 0.65);
        assert_eq!(k.piksel(50, 50), [200, 200, 200]);
        let dis = k.piksel(5, 5);
        assert!(dis[0] < 80, "{dis:?}");
        b.temizle();
        assert!(b.gorunum().vurgu.is_none());
    }

    #[test]
    fn yakinlastirma_donusumu() {
        let ham = Kare::dolu(200, 100, [10, 10, 10]);
        let g = Gorunum { kirpma: [0.5, 0.5, 0.5, 0.5], vurgu: None, karartma: 0.0 };
        let (k, (x0, y0, o, dx, dy)) = uygula(&ham, &g, 200, 100, 0.65);
        assert_eq!(k.boyut(), (200, 100));
        // bölgenin sol üstü çıkışın sol üstüne gelir
        assert_eq!(((100.0 - x0) * o + dx, (50.0 - y0) * o + dy), (0.0, 0.0));
    }
}
