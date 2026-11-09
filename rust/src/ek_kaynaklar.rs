//! Ek kaynakların canlı yakalayıcıları (Python scenes/kaynaklar.py): ikinci monitör, pencere,
//! ekran bölgesi, ikinci kamera, görsel ve video.
//!
//! Video hattı her karede aktif sahneyi verir; bu yapı sahnedeki görünür ek kaynakların son
//! karelerini {kaynak kimliği: kare} olarak döndürür. Sahnede olmayan (ya da gizlenen) kaynakların
//! yakalayıcıları kapatılır; böylece başka sahnedeki ikinci kamera boşuna açık kalmaz.
//! Ana ekran ve ana webcam burada değil, video hattının kendisinde.
//!
//! Ekran, pencere, bölge ve video kareleri çıkış boyutuna sığdırılmış verilir ve kaynak karesi
//! değişmedikçe (aynı Arc) yeniden ölçeklenmez.

use std::collections::HashMap;
#[cfg(windows)]
use std::time::{Duration, Instant};

use serde_json::Value;

use crate::kare::{self, Kare, KareRef};
use crate::sahne::{Kaynak, Sahne};
use crate::video_oynatici::VideoOynatici;
use crate::yakalama::ekran::EkranKaynagi;

#[cfg(windows)]
const PENCERE_ARAMA: Duration = Duration::from_secs(3);

/// Pencereyi başlığına göre bulur (uygulama yeniden açılınca pencere numarası değişir).
#[cfg(windows)]
struct PencereArayici {
    baslik: String,
    kaynak: Option<crate::yakalama::pencere::PencereKaynagi>,
    son_arama: Option<Instant>,
}

#[cfg(windows)]
impl PencereArayici {
    fn bul(&self) -> Option<crate::yakalama::pencere::PencereKaynagi> {
        use crate::yakalama::pencere::{pencereler, PencereKaynagi};
        let adaylar = pencereler();
        if let Some(p) = adaylar.iter().find(|p| p.baslik == self.baslik) {
            return Some(PencereKaynagi::yeni(p.hwnd, &p.baslik));
        }
        // başlık biraz değişmiş olabilir (ör. sekme adı)
        adaylar
            .iter()
            .find(|p| !self.baslik.is_empty() && (p.baslik.contains(&self.baslik) || self.baslik.contains(&p.baslik)))
            .map(|p| PencereKaynagi::yeni(p.hwnd, &p.baslik))
    }

    fn grab(&mut self) -> Option<KareRef> {
        if self.kaynak.is_none() {
            if self.son_arama.is_some_and(|t| t.elapsed() < PENCERE_ARAMA) {
                return None;
            }
            self.son_arama = Some(Instant::now());
            self.kaynak = self.bul();
        }
        let k = self.kaynak.as_mut()?;
        let kare = k.grab();
        if kare.is_none() && k.son_hata == "Pencere kapandı" {
            self.kaynak = None;
        }
        kare
    }
}

enum Yakalayici {
    Ekran(EkranKaynagi),
    Bolge(EkranKaynagi, [f64; 4]),
    #[cfg(windows)]
    Pencere(PencereArayici),
    #[cfg(windows)]
    Kamera(crate::yakalama::kamera::WebcamKaynagi),
    Video(VideoOynatici, String),
    Gorsel(Option<KareRef>),
    Yok,
}

struct Acik {
    imza: String,
    yakalayici: Yakalayici,
    /// (kaynak karesi, sığdırılmış hali): kaynak değişmedikçe yeniden ölçeklenmez
    onbellek: Option<(KareRef, KareRef)>,
}

impl Drop for Acik {
    fn drop(&mut self) {
        match &mut self.yakalayici {
            Yakalayici::Ekran(e) | Yakalayici::Bolge(e, _) => e.kapat(),
            #[cfg(windows)]
            Yakalayici::Kamera(k) => k.durdur(false),
            Yakalayici::Video(v, _) => v.kapat(),
            _ => {}
        }
    }
}

pub struct EkKaynaklar {
    genislik: u32,
    yukseklik: u32,
    fps: u32,
    acik: HashMap<String, Acik>,
}

fn sayi(k: &Kaynak, a: &str, v: i64) -> i64 {
    k.ayar.get(a).and_then(Value::as_f64).map(|f| f as i64).unwrap_or(v)
}

/// Yakalayıcıyı yeniden açmayı gerektiren ayarlar (konum ve köşe boyutu hariç).
fn imza(k: &Kaynak) -> String {
    let mut ciftler: Vec<(String, String)> = k
        .ayar
        .iter()
        .filter(|(a, _)| !matches!(a.as_str(), "position" | "corner" | "size" | "yer"))
        .map(|(a, v)| (a.clone(), v.to_string()))
        .collect();
    ciftler.sort();
    format!("{}|{ciftler:?}", k.tur)
}

impl EkKaynaklar {
    pub fn yeni(genislik: u32, yukseklik: u32, fps: u32) -> Self {
        EkKaynaklar { genislik, yukseklik, fps, acik: HashMap::new() }
    }

    fn olustur(&self, k: &Kaynak) -> Yakalayici {
        match k.tur.as_str() {
            "ekran" => Yakalayici::Ekran(EkranKaynagi::yeni(sayi(k, "monitor", 0).max(0) as usize, "mss")),
            "bolge" => {
                let r: Vec<f64> = k.ayar.get("rect").and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_f64).collect()).unwrap_or_default();
                let r = if r.len() == 4 { [r[0], r[1], r[2], r[3]] } else { [0.0, 0.0, 1.0, 1.0] };
                Yakalayici::Bolge(EkranKaynagi::yeni(sayi(k, "monitor", 0).max(0) as usize, "mss"), r)
            }
            #[cfg(windows)]
            "pencere" => Yakalayici::Pencere(PencereArayici { baslik: k.metin("title"), kaynak: None, son_arama: None }),
            #[cfg(windows)]
            "kamera" => {
                Yakalayici::Kamera(crate::yakalama::kamera::WebcamKaynagi::yeni(sayi(k, "device", 1).max(0) as usize, self.genislik, self.yukseklik, self.fps, false))
            }
            "video" => Yakalayici::Video(VideoOynatici::yeni(self.fps), k.metin("path")),
            "gorsel" => Yakalayici::Gorsel(kare::gorsel_oku(std::path::Path::new(&k.metin("path"))).map(Kare::arc)),
            _ => Yakalayici::Yok,
        }
    }

    /// Sahnedeki görünür ek kaynakların son kareleri. Her karede video hattından çağrılır.
    /// `kamera_acik`: kamera açık istenmiş ve şu an kullanılıyor (önizleme ya da kayıt var).
    pub fn kareler(&mut self, sahne: &Sahne, kamera_acik: bool) -> HashMap<String, KareRef> {
        let istenen: Vec<&Kaynak> = sahne
            .kaynaklar
            .iter()
            .filter(|k| k.gorunur && !k.ana() && !matches!(k.tur.as_str(), "bekleme" | "kalem" | "imlec" | "metin"))
            .collect();
        self.acik.retain(|kimlik, a| istenen.iter().any(|k| &k.kimlik == kimlik && imza(k) == a.imza));
        let (w, h) = (self.genislik, self.yukseklik);
        let mut sonuc = HashMap::new();
        for k in istenen {
            if !self.acik.contains_key(&k.kimlik) {
                let y = self.olustur(k);
                self.acik.insert(k.kimlik.clone(), Acik { imza: imza(k), yakalayici: y, onbellek: None });
            }
            let a = self.acik.get_mut(&k.kimlik).unwrap();
            let (ham, sigdir): (Option<KareRef>, bool) = match &mut a.yakalayici {
                Yakalayici::Ekran(e) => (e.grab(), true),
                Yakalayici::Bolge(e, r) => {
                    let ham = e.grab();
                    // bölge: kaynak değişmediyse önbellekteki kırpılmış kare
                    let kare = ham.map(|ham| match &a.onbellek {
                        Some((o, c)) if std::sync::Arc::ptr_eq(o, &ham) => c.clone(),
                        _ => {
                            let (hw, hh) = (ham.w as f64, ham.h as f64);
                            let b = ((r[0] * hw).max(0.0), (r[1] * hh).max(0.0), (r[2] * hw).min(hw), (r[3] * hh).min(hh));
                            let c = if b.2 < 2.0 || b.3 < 2.0 { kare::sigdir(&ham, w, h).arc() } else { kare::sigdir_bolge(&ham, b, w, h).arc() };
                            a.onbellek = Some((ham, c.clone()));
                            c
                        }
                    });
                    (kare, false)
                }
                #[cfg(windows)]
                Yakalayici::Pencere(p) => (p.grab(), true),
                #[cfg(windows)]
                Yakalayici::Kamera(c) => {
                    if kamera_acik && !c.acik() {
                        c.baslat();
                    } else if !kamera_acik && c.acik() {
                        c.durdur(false);
                    }
                    (if kamera_acik { c.son_kare() } else { None }, false)
                }
                Yakalayici::Video(v, yol) => (v.kare(yol, w, h), false),
                Yakalayici::Gorsel(g) => (g.clone(), false),
                Yakalayici::Yok => (None, false),
            };
            let kare = match ham {
                Some(ham) if sigdir && ham.boyut() != (w, h) => match &a.onbellek {
                    Some((o, c)) if std::sync::Arc::ptr_eq(o, &ham) => Some(c.clone()),
                    _ => {
                        let c = kare::sigdir(&ham, w, h).arc();
                        a.onbellek = Some((ham, c.clone()));
                        Some(c)
                    }
                },
                diger => diger,
            };
            if let Some(kare) = kare {
                sonuc.insert(k.kimlik.clone(), kare);
            }
        }
        let _ = kamera_acik;
        sonuc
    }

    pub fn kapat(&mut self) {
        self.acik.clear();
    }
}

#[cfg(test)]
mod testler {
    use super::*;
    use serde_json::json;

    fn kaynak(tur: &str, ayar: Value) -> Kaynak {
        let mut d = ayar.as_object().cloned().unwrap_or_default();
        d.insert("type".into(), tur.into());
        Kaynak::sozlukten(&d).unwrap()
    }

    #[test]
    fn sahneden_cikan_kaynak_kapanir() {
        let mut ek = EkKaynaklar::yeni(64, 36, 30);
        let v = kaynak("video", json!({"path": "/yok/video.mp4"}));
        let mut sahne = Sahne { ad: "S".into(), kaynaklar: vec![v.clone()] };
        let k = ek.kareler(&sahne, true);
        assert!(k.is_empty()); // dosya yok: kare yok ama yakalayıcı açık
        assert_eq!(ek.acik.len(), 1);
        sahne.kaynaklar[0].gorunur = false;
        ek.kareler(&sahne, true);
        assert!(ek.acik.is_empty());
    }

    #[test]
    fn konum_degisince_yeniden_acilmaz() {
        let a = kaynak("kamera", json!({"device": 1, "yer": "kose", "position": [0.1, 0.1]}));
        let mut b = a.clone();
        b.ayar.insert("position".into(), json!([0.5, 0.5]));
        assert_eq!(imza(&a), imza(&b));
        b.ayar.insert("device".into(), json!(2));
        assert_ne!(imza(&a), imza(&b));
    }
}
