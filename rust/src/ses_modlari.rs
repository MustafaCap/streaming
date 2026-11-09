//! "Önde olan" ses modları: Sesim, Dengeli, Oyun (Python core/ses_modlari.py).
//!
//! Her mod mikrofon ve sistem/oyun sesi için bir yüzde çiftidir. Sürgü elle değişince hiçbir mod
//! seçili görünmez ve "<son mod>'e kaydet" bağlantısı çıkar; basılırsa yeni değerler o moda yazılır.

use serde_json::{json, Value};

use crate::ayarlar::Ayarlar;

pub const MODLAR: [&str; 3] = ["sesim", "dengeli", "oyun"];

pub fn etiket(ad: &str) -> &'static str {
    match ad {
        "sesim" => "Sesim",
        "oyun" => "Oyun",
        _ => "Dengeli",
    }
}

pub fn kaydet_etiketi(ad: &str) -> &'static str {
    match ad {
        "sesim" => "Sesim'e kaydet",
        "oyun" => "Oyun'a kaydet",
        _ => "Dengeli'ye kaydet",
    }
}

pub fn ipucu(ad: &str) -> &'static str {
    match ad {
        "sesim" => "Sesin önde, oyun/sistem sesi kısık",
        "oyun" => "Oyun sesi önde",
        _ => "İkisi aynı seviyede",
    }
}

pub fn varsayilan(ad: &str) -> [i32; 2] {
    match ad {
        "sesim" => [100, 45],
        "oyun" => [70, 100],
        _ => [80, 80],
    }
}

fn yuzde(v: &Value) -> Option<i32> {
    v.as_f64().map(|f| (f.round() as i64).clamp(0, 200) as i32)
}

/// Ayarlardaki modlar; eksik/bozuk olan varsayılandan tamamlanır.
pub fn modlar(a: &Ayarlar) -> [[i32; 2]; 3] {
    let kayitli = a.al("audio.modes");
    let mut sonuc = [[0; 2]; 3];
    for (i, ad) in MODLAR.iter().enumerate() {
        sonuc[i] = kayitli
            .and_then(|k| k.get(ad))
            .and_then(Value::as_array)
            .filter(|l| l.len() == 2)
            .and_then(|l| Some([yuzde(&l[0])?, yuzde(&l[1])?]))
            .unwrap_or_else(|| varsayilan(ad));
    }
    sonuc
}

/// Sürgüler bir modla aynıysa o modun sırası.
pub fn eslesen(mik: i32, sis: i32, tum: &[[i32; 2]; 3]) -> Option<usize> {
    tum.iter().position(|m| *m == [mik, sis])
}

pub fn son_mod(a: &Ayarlar) -> &'static str {
    let ad = a.metin("audio.last_mode");
    MODLAR.iter().find(|m| **m == ad).copied().unwrap_or("dengeli")
}

/// Modu seçer: kazançları ayarlara yazar ve (mik, sis) yüzdelerini döndürür.
pub fn uygula(a: &mut Ayarlar, ad: &str) -> (i32, i32) {
    let i = MODLAR.iter().position(|m| *m == ad).unwrap_or(1);
    let [mik, sis] = modlar(a)[i];
    if let Some(ses) = a.veri.get_mut("audio").and_then(Value::as_object_mut) {
        ses.insert("last_mode".into(), ad.into());
        ses.insert("mic_gain".into(), json!(mik as f64 / 100.0));
    } else {
        a.veri["audio"] = json!({"last_mode": ad, "mic_gain": mik as f64 / 100.0});
    }
    a.ayarla("audio.system_gain", json!(sis as f64 / 100.0));
    (mik, sis)
}

pub fn kaydet(a: &mut Ayarlar, ad: &str, mik: i32, sis: i32) {
    let mut tum = modlar(a);
    if let Some(i) = MODLAR.iter().position(|m| *m == ad) {
        tum[i] = [mik, sis];
    }
    if let Some(ses) = a.veri.get_mut("audio").and_then(Value::as_object_mut) {
        ses.insert("last_mode".into(), ad.into());
    }
    let deger: serde_json::Map<String, Value> = MODLAR.iter().zip(tum).map(|(ad, v)| (ad.to_string(), json!(v))).collect();
    a.ayarla("audio.modes", Value::Object(deger));
}

pub fn varsayilana_don(a: &mut Ayarlar) {
    let deger: serde_json::Map<String, Value> = MODLAR.iter().map(|ad| (ad.to_string(), json!(varsayilan(ad)))).collect();
    a.ayarla("audio.modes", Value::Object(deger));
}

/// Sistem sesinin altındaki "Zoom ve Discord hariç" gibi kısa açıklama.
pub fn haric_metni(a: &Ayarlar) -> String {
    let mod_ = a.al("audio.system_mode").and_then(Value::as_str).unwrap_or("auto").to_string();
    let dahil = a.metin("audio.include_app");
    if mod_ == "app" && !dahil.is_empty() {
        return format!("Sadece {}", dahil.trim_end_matches(".exe"));
    }
    if mod_ == "all" {
        return "Tüm sesler".into();
    }
    let mut adlar: Vec<String> = Vec::new();
    for x in a.al("audio.exclude_apps").and_then(Value::as_array).cloned().unwrap_or_default() {
        let s = x.as_str().unwrap_or("").to_string();
        let ad = s.trim_end_matches(".exe").trim_end_matches(".EXE").to_string();
        let ad = if ad == "ms-teams" { "Teams".to_string() } else { ad };
        if !ad.is_empty() && !adlar.contains(&ad) {
            adlar.push(ad);
        }
    }
    match adlar.len() {
        0 => "Tüm sesler".into(),
        1 | 2 => format!("{} hariç", adlar.join(" ve ")),
        n => format!("{}, {} +{} hariç", adlar[0], adlar[1], n - 2),
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn modlar_ve_eslesme() {
        let mut a = Ayarlar::bellekte(json!({}));
        let m = modlar(&a);
        assert_eq!(m[1], [80, 80]);
        assert_eq!(eslesen(80, 80, &m), Some(1));
        assert_eq!(eslesen(81, 80, &m), None);
        assert_eq!(uygula(&mut a, "sesim"), (100, 45));
        assert_eq!(son_mod(&a), "sesim");
        kaydet(&mut a, "sesim", 90, 45);
        assert_eq!(modlar(&a)[0], [90, 45]);
    }

    #[test]
    fn haric() {
        let a = Ayarlar::bellekte(json!({"audio": {"exclude_apps": ["Zoom.exe", "Discord.exe", "ms-teams.exe", "slack.exe"]}}));
        assert_eq!(haric_metni(&a), "Zoom, Discord +2 hariç");
        let a = Ayarlar::bellekte(json!({"audio": {"exclude_apps": ["Zoom.exe"]}}));
        assert_eq!(haric_metni(&a), "Zoom hariç");
    }
}
