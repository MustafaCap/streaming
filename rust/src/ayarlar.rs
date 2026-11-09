//! settings.json okuma/yazma (Python sürümüyle aynı dosya ve aynı kurallar).
//!
//! - Varsayılanlar config/settings.default.json'dan derlemeye gömülür.
//! - Kullanıcı dosyasında eksik alanlar varsayılandan tamamlanır.
//! - Dosya bozuksa yedeği alınır (settings.bozuk.json), varsayılanlarla devam edilir.
//! - Yanlış türde değer (ör. genişliğe metin) o alanı varsayılana döndürür.
//! - Yazılamazsa (OneDrive/antivirüs kilidi) uygulama çökmez.

use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

pub const SURUM: i64 = 5;
pub const VARSAYILAN_JSON: &str = include_str!("../../config/settings.default.json");

pub fn varsayilan() -> Value {
    serde_json::from_str(VARSAYILAN_JSON).expect("gömülü varsayılan ayarlar geçerli JSON olmalı")
}

fn ayni_tur(varsayilan: &Value, deger: &Value) -> Option<Value> {
    match varsayilan {
        Value::Null => Some(deger.clone()), // türü serbest alan (ör. camera.position)
        Value::Bool(_) => deger.is_boolean().then(|| deger.clone()),
        Value::Number(n) if n.is_i64() || n.is_u64() => match deger {
            Value::Number(d) => {
                let f = d.as_f64()?;
                (f.fract() == 0.0).then(|| Value::from(f as i64))
            }
            _ => None,
        },
        Value::Number(_) => match deger {
            Value::Number(d) => Some(Value::from(d.as_f64()?)),
            _ => None,
        },
        Value::String(_) => deger.is_string().then(|| deger.clone()),
        Value::Array(_) => deger.is_array().then(|| deger.clone()),
        Value::Object(_) => deger.is_object().then(|| deger.clone()),
    }
}

/// Kullanıcı değerlerini varsayılanın üstüne yazar; iç içe nesneleri de birleştirir, türleri denetler.
pub fn birlestir(varsayilan: &Value, kullanici: &Value, onek: &str) -> Value {
    let mut sonuc = varsayilan.clone();
    let (Some(s), Some(k)) = (sonuc.as_object_mut(), kullanici.as_object()) else {
        return sonuc;
    };
    for (anahtar, deger) in k {
        let yol = format!("{onek}{anahtar}");
        match s.get(anahtar) {
            Some(v @ Value::Object(_)) if deger.is_object() => {
                let yeni = birlestir(v, deger, &format!("{yol}."));
                s.insert(anahtar.clone(), yeni);
            }
            Some(v) => match ayni_tur(v, deger) {
                Some(uygun) => {
                    s.insert(anahtar.clone(), uygun);
                }
                None => log::warn!("Ayar {yol} geçersiz ({deger}); varsayılan değer kullanılıyor: {v}"),
            },
            None => {
                s.insert(anahtar.clone(), deger.clone());
            }
        }
    }
    sonuc
}

/// Karşılaştırma için tuşun tek biçimi ("ctrl + shift+m" == "Ctrl+Shift+M").
fn tus_anahtari(t: &Value) -> String {
    t.as_str().unwrap_or("").replace(' ', "").to_lowercase()
}

/// Eski sürümlerin kısayollarını taşır (Python core/settings.py:kisayollari_tasi ile aynı).
fn kisayollari_tasi(tuslar: &mut Map<String, Value>, eski: &Map<String, Value>, tasima: &[(&str, &str, &str)], yeniler: &[(&str, &str)]) {
    let mut adaylar: Vec<(String, String)> = Vec::new();
    for (komut, es, yeni) in tasima {
        match eski.get(*komut) {
            None => adaylar.push((komut.to_string(), yeni.to_string())),
            Some(d) if tus_anahtari(d) == es.to_lowercase() => adaylar.push((komut.to_string(), yeni.to_string())),
            _ => {}
        }
    }
    for (komut, yeni) in yeniler {
        if !eski.contains_key(*komut) {
            adaylar.push((komut.to_string(), yeni.to_string()));
        }
    }
    let mut kullanilan: std::collections::HashSet<String> = tuslar
        .iter()
        .filter(|(k, _)| !adaylar.iter().any(|(a, _)| a == *k))
        .map(|(_, t)| tus_anahtari(t))
        .filter(|t| !t.is_empty())
        .collect();
    for (komut, yeni) in adaylar {
        let a = yeni.replace(' ', "").to_lowercase();
        if kullanilan.contains(&a) {
            tuslar.insert(komut, Value::from(""));
        } else {
            tuslar.insert(komut, Value::from(yeni));
            kullanilan.insert(a);
        }
    }
}

fn tasi(veri: &mut Value, eski_surum: i64, kullanici: &Value) {
    if eski_surum < 2 {
        if let Some(t) = veri.get_mut("hotkeys").and_then(Value::as_object_mut) {
            if t.get("panik").map(tus_anahtari).as_deref() == Some("f12") {
                t.insert("panik".into(), "Ctrl+Alt+P".into());
            }
        }
    }
    if eski_surum < 3 {
        let mut eski = kullanici.get("hotkeys").and_then(Value::as_object).cloned().unwrap_or_default();
        if eski_surum < 2 && eski.get("panik").map(tus_anahtari).as_deref() == Some("f12") {
            eski.insert("panik".into(), "Ctrl+Alt+P".into());
        }
        let tasima: &[(&str, &str, &str)] = &[
            ("bolge.sec", "F6", "Ctrl+Shift+S"),
            ("kalem.ac_kapat", "F7", "Ctrl+Shift+D"),
            ("ses.mikrofon", "F8", "Ctrl+Shift+M"),
            ("ses.sistem", "F9", "Ctrl+Shift+A"),
            ("kamera.ac_kapat", "F10", "Ctrl+Shift+C"),
            ("anlik_kayit.kaydet", "F11", "Ctrl+Shift+B"),
            ("panik", "Ctrl+Alt+P", "Ctrl+Shift+P"),
            ("sahne.sec:1", "Ctrl+1", "Ctrl+Shift+1"),
            ("sahne.sec:2", "Ctrl+2", "Ctrl+Shift+2"),
            ("sahne.sec:3", "Ctrl+3", "Ctrl+Shift+3"),
            ("sahne.sec:4", "Ctrl+4", "Ctrl+Shift+4"),
            ("kayit.duraklat", "Ctrl+Alt+D", "Ctrl+Shift+K"),
        ];
        let yeniler: &[(&str, &str)] = &[
            ("sahne.sec:5", "Ctrl+Shift+5"),
            ("sahne.sec:6", "Ctrl+Shift+6"),
            ("sahne.sec:7", "Ctrl+Shift+7"),
            ("sahne.sec:8", "Ctrl+Shift+8"),
            ("sahne.sec:9", "Ctrl+Shift+9"),
            ("ekran.goruntusu", "Ctrl+Shift+G"),
            ("kalem.temizle", "Ctrl+Shift+X"),
        ];
        let mut ptt = false;
        if let Some(t) = veri.get_mut("hotkeys").and_then(Value::as_object_mut) {
            kisayollari_tasi(t, &eski, tasima, yeniler);
            ptt = t.get("bas_konus").and_then(Value::as_str).is_some_and(|s| !s.is_empty());
        }
        if ptt {
            if let Some(a) = veri.get_mut("audio").and_then(Value::as_object_mut) {
                a.insert("ptt".into(), true.into());
            }
        }
        let eski_kalem = kullanici.get("pen_hotkeys").and_then(Value::as_object).cloned().unwrap_or_default();
        if let Some(k) = veri.get_mut("pen_hotkeys").and_then(Value::as_object_mut) {
            kisayollari_tasi(k, &eski_kalem, &[], &[("kalem.tur:7", "7"), ("kalem.kapat", "Esc")]);
        }
    }
    if eski_surum < 4 {
        if let Some(u) = veri.get_mut("ui").and_then(Value::as_object_mut) {
            u.insert("advanced".into(), true.into());
        }
    }
    if eski_surum < 5 {
        if let Some(k) = veri.get_mut("record").and_then(Value::as_object_mut) {
            if k.get("replay_seconds").and_then(Value::as_i64) == Some(120) {
                k.insert("replay_seconds".into(), 15.into());
            }
        }
    }
}

pub struct Ayarlar {
    pub dosya: PathBuf,
    pub veri: Value,
}

impl Ayarlar {
    pub fn ac(dosya: PathBuf) -> Self {
        let mut a = Ayarlar { dosya, veri: Value::Null };
        a.yukle();
        a
    }

    pub fn yukle(&mut self) {
        let varsayilan = varsayilan();
        let mut kullanici = Value::Object(Map::new());
        if self.dosya.exists() {
            let okunan = std::fs::read_to_string(&self.dosya)
                .map_err(|e| e.to_string())
                .and_then(|m| serde_json::from_str::<Value>(m.trim_start_matches('\u{feff}')).map_err(|e| e.to_string()))
                .and_then(|v| if v.is_object() { Ok(v) } else { Err("ayar dosyası bir JSON nesnesi değil".into()) });
            match okunan {
                Ok(v) => kullanici = v,
                Err(e) => {
                    let yedek = self.dosya.with_extension("bozuk.json");
                    log::warn!("Ayar dosyası okunamadı ({e}); {} olarak yedeklendi", yedek.display());
                    let _ = std::fs::rename(&self.dosya, &yedek);
                }
            }
        }
        let bos = kullanici.as_object().is_none_or(Map::is_empty);
        let eski_surum = if bos { SURUM } else { kullanici.get("version").and_then(Value::as_i64).unwrap_or(1) };
        self.veri = birlestir(&varsayilan, &kullanici, "");
        tasi(&mut self.veri, eski_surum, &kullanici);
        self.veri["version"] = SURUM.into();
        if (!bos && eski_surum != SURUM) || !self.dosya.exists() {
            self.kaydet();
        }
    }

    pub fn kaydet(&self) -> bool {
        let yaz = || -> std::io::Result<()> {
            if let Some(p) = self.dosya.parent() {
                std::fs::create_dir_all(p)?;
            }
            let gecici = self.dosya.with_extension("tmp");
            std::fs::write(&gecici, serde_json::to_string_pretty(&self.veri).unwrap_or_default())?;
            std::fs::rename(&gecici, &self.dosya)
        };
        match yaz() {
            Ok(()) => true,
            Err(e) => {
                log::warn!("Ayarlar kaydedilemedi: {e}");
                false
            }
        }
    }

    /// "video.fps" gibi noktalı yolla okur.
    pub fn al(&self, yol: &str) -> Option<&Value> {
        let mut d = &self.veri;
        for p in yol.split('.') {
            d = d.as_object()?.get(p)?;
        }
        Some(d)
    }

    pub fn sayi(&self, yol: &str, v: i64) -> i64 {
        self.al(yol).and_then(Value::as_i64).unwrap_or(v)
    }
    pub fn ondalik(&self, yol: &str, v: f64) -> f64 {
        self.al(yol).and_then(Value::as_f64).unwrap_or(v)
    }
    pub fn mantik(&self, yol: &str, v: bool) -> bool {
        self.al(yol).and_then(Value::as_bool).unwrap_or(v)
    }
    pub fn metin(&self, yol: &str) -> String {
        self.al(yol).and_then(Value::as_str).unwrap_or("").to_string()
    }

    pub fn ayarla(&mut self, yol: &str, deger: Value) {
        let parcalar: Vec<&str> = yol.split('.').collect();
        let mut d = &mut self.veri;
        for p in &parcalar[..parcalar.len() - 1] {
            if !d.get(*p).is_some_and(Value::is_object) {
                d[*p] = Value::Object(Map::new());
            }
            d = d.get_mut(*p).unwrap();
        }
        d[parcalar[parcalar.len() - 1]] = deger;
        self.kaydet();
    }
}

pub fn dosya_yolu(p: &Path) -> String {
    p.to_string_lossy().into_owned()
}

#[cfg(test)]
mod testler {
    use super::*;

    fn gecici(ad: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("rizeon-test-{ad}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d.join("settings.json")
    }

    #[test]
    fn yoksa_varsayilan_yazilir() {
        let f = gecici("yok");
        let a = Ayarlar::ac(f.clone());
        assert!(f.exists());
        assert_eq!(a.sayi("video.fps", 0), 30);
        assert_eq!(a.sayi("version", 0), SURUM);
    }

    #[test]
    fn yanlis_tur_varsayilana_doner() {
        let f = gecici("tur");
        std::fs::write(&f, r#"{"version":5,"video":{"width":"çok","fps":24.0},"bilinmeyen":1}"#).unwrap();
        let a = Ayarlar::ac(f);
        assert_eq!(a.sayi("video.width", 0), 1280);
        assert_eq!(a.sayi("video.fps", 0), 24);
        assert_eq!(a.sayi("bilinmeyen", 0), 1);
    }

    #[test]
    fn bozuk_dosya_yedeklenir() {
        let f = gecici("bozuk");
        std::fs::write(&f, "{bozuk").unwrap();
        let a = Ayarlar::ac(f.clone());
        assert!(f.with_extension("bozuk.json").exists());
        assert_eq!(a.sayi("video.height", 0), 720);
    }

    #[test]
    fn eski_kisayollar_tasinir_ve_tekrar_15_sn() {
        let f = gecici("tasi");
        std::fs::write(&f, r#"{"version":2,"hotkeys":{"bolge.sec":"F6","ses.mikrofon":"Ctrl+Q"},"record":{"replay_seconds":120}}"#).unwrap();
        let a = Ayarlar::ac(f);
        assert_eq!(a.veri["hotkeys"]["bolge.sec"], "Ctrl+Shift+S");
        assert_eq!(a.veri["hotkeys"]["ses.mikrofon"], "Ctrl+Q");
        assert_eq!(a.sayi("record.replay_seconds", 0), 15);
        assert!(a.mantik("ui.advanced", false));
    }
}
