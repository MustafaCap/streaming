//! Arayüz dili: Türkçe (kaynak metin) ve İngilizce.
//!
//! Koddaki metinler Türkçe yazılır ve `t("...")` / `trf!("... {}", x)` ile sarılır. Dil İngilizce ise
//! metin `en.rs` tablosundan bulunur; tabloda yoksa Türkçesi gösterilir (test, eksik çeviriyi yakalar).
//! Dil ayarı `ui.language`: "auto" (Windows görüntü dili Türkçe ise Türkçe, değilse İngilizce), "tr", "en".

use std::collections::HashMap;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::OnceLock;

mod en;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Dil {
    Turkce,
    Ingilizce,
}

static DIL: AtomicU8 = AtomicU8::new(0);

pub fn dil() -> Dil {
    if DIL.load(Ordering::Relaxed) == 1 {
        Dil::Ingilizce
    } else {
        Dil::Turkce
    }
}

pub fn ingilizce() -> bool {
    dil() == Dil::Ingilizce
}

pub fn ayarla(d: Dil) {
    DIL.store(if d == Dil::Ingilizce { 1 } else { 0 }, Ordering::Relaxed);
}

/// Ayar değerinden ("auto" | "tr" | "en") dili seçer.
pub fn ayardan(deger: &str) -> Dil {
    match deger {
        "tr" => Dil::Turkce,
        "en" => Dil::Ingilizce,
        _ => {
            if sistem_turkce() {
                Dil::Turkce
            } else {
                Dil::Ingilizce
            }
        }
    }
}

/// Windows görüntü dili Türkçe mi? (Windows dışında: LANG ortam değişkeni.)
pub fn sistem_turkce() -> bool {
    #[cfg(windows)]
    {
        use windows::Win32::Globalization::GetUserDefaultUILanguage;
        // Birincil dil kimliği: alt 10 bit. LANG_TURKISH = 0x1F.
        let kimlik = unsafe { GetUserDefaultUILanguage() };
        (kimlik & 0x3FF) == 0x1F
    }
    #[cfg(not(windows))]
    {
        std::env::var("LANG").map(|l| l.to_lowercase().starts_with("tr")).unwrap_or(true)
    }
}

fn tablo() -> &'static HashMap<&'static str, &'static str> {
    static T: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();
    T.get_or_init(|| en::EN.iter().copied().collect())
}

/// Türkçe metnin geçerli dildeki karşılığı. Bilinmeyen metin olduğu gibi döner
/// (kullanıcının verdiği sahne adı gibi metinler de bu yüzden güvenle geçirilebilir).
pub fn t(metin: &str) -> &str {
    if !ingilizce() {
        return metin;
    }
    tablo().get(metin).copied().unwrap_or(metin)
}

/// Sadece İngilizce karşılığı (dil ayarından bağımsız; testler ve bazı sabit yerler için).
pub fn ingilizcesi(metin: &str) -> Option<&'static str> {
    tablo().get(metin).copied()
}

/// Yüzde: Türkçede "%30", İngilizcede "30%".
pub fn yuzde(n: impl std::fmt::Display) -> String {
    if ingilizce() {
        format!("{n}%")
    } else {
        format!("%{n}")
    }
}

/// "{}" yer tutucularını sırayla doldurur.
pub fn bicimle(kalip: &str, degerler: &[&dyn std::fmt::Display]) -> String {
    let mut sonuc = String::with_capacity(kalip.len() + 16);
    let mut kalan = kalip;
    let mut i = 0;
    while let Some(k) = kalan.find("{}") {
        sonuc.push_str(&kalan[..k]);
        if let Some(d) = degerler.get(i) {
            sonuc.push_str(&d.to_string());
        }
        i += 1;
        kalan = &kalan[k + 2..];
    }
    sonuc.push_str(kalan);
    sonuc
}

/// Çevrilip biçimlenen metin: `trf!("Mikrofon: {}", durum)`. Kalıpta sadece "{}" kullanılır.
#[macro_export]
macro_rules! trf {
    ($kalip:literal $(, $d:expr)* $(,)?) => {
        $crate::dil::bicimle($crate::dil::t($kalip), &[$(&$d as &dyn ::std::fmt::Display),*])
    };
}

#[cfg(test)]
mod testler {
    use super::*;
    use std::collections::HashSet;
    use std::path::Path;

    fn dosyalar(k: &Path, v: &mut Vec<std::path::PathBuf>) {
        for g in std::fs::read_dir(k).unwrap().flatten() {
            let p = g.path();
            if p.is_dir() {
                dosyalar(&p, v);
            } else if p.extension().is_some_and(|e| e == "rs") {
                v.push(p);
            }
        }
    }

    /// Rust dize sabitini (tırnaktan sonrası) çözer; kapanış tırnağına kadar.
    fn dize_coz(s: &str) -> Option<String> {
        let mut c = s.chars().peekable();
        let mut o = String::new();
        while let Some(ch) = c.next() {
            match ch {
                '"' => return Some(o),
                '\\' => match c.next()? {
                    'n' => o.push('\n'),
                    't' => o.push('\t'),
                    '"' => o.push('"'),
                    '\\' => o.push('\\'),
                    '\'' => o.push('\''),
                    'u' => {
                        c.next(); // {
                        let mut h = String::new();
                        for x in c.by_ref() {
                            if x == '}' {
                                break;
                            }
                            h.push(x);
                        }
                        o.push(char::from_u32(u32::from_str_radix(&h, 16).ok()?)?);
                    }
                    '\n' => {
                        while c.peek().is_some_and(|x| x.is_whitespace()) {
                            c.next();
                        }
                    }
                    x => o.push(x),
                },
                x => o.push(x),
            }
        }
        None
    }

    /// Kaynakta t("...") ve trf!("...") ile sarılmış bütün metinler.
    fn sarilmis_metinler() -> Vec<(String, String)> {
        let mut v = Vec::new();
        dosyalar(&Path::new(env!("CARGO_MANIFEST_DIR")).join("src"), &mut v);
        let mut sonuc = Vec::new();
        for f in v {
            if f.ends_with("dil/en.rs") || f.ends_with("dil/mod.rs") {
                continue;
            }
            // Windows checkout CRLF olabilir; derleyici "\\" + CRLF satır devamını da tanır
            let m = std::fs::read_to_string(&f).unwrap().replace("\r\n", "\n");
            for kalip in ["t(", "trf!("] {
                let mut bas = 0;
                while let Some(k) = m[bas..].find(kalip) {
                    let i = bas + k;
                    bas = i + kalip.len();
                    let onceki = m[..i].chars().last();
                    if kalip == "t(" && onceki.is_some_and(|c| c.is_alphanumeric() || c == '_') {
                        continue;
                    }
                    // "(" ile tırnak arasında boşluk/satır sonu olabilir
                    let bosluk = m[bas..].len() - m[bas..].trim_start().len();
                    if !m[bas + bosluk..].starts_with('"') {
                        continue;
                    }
                    bas += bosluk + 1;
                    if let Some(d) = dize_coz(&m[bas..]) {
                        sonuc.push((f.display().to_string(), d));
                    }
                }
            }
        }
        sonuc
    }

    #[test]
    fn her_metnin_ingilizcesi_var() {
        let eksik: Vec<String> = sarilmis_metinler()
            .into_iter()
            .filter(|(_, m)| ingilizcesi(m).is_none())
            .map(|(f, m)| format!("{f}: {m:?}"))
            .collect::<HashSet<_>>()
            .into_iter()
            .collect();
        assert!(eksik.is_empty(), "İngilizcesi olmayan metinler:\n{}", eksik.join("\n"));
    }

    #[test]
    fn tablo_tekrarsiz_ve_yer_tutucular_esit() {
        let mut gorulen = HashSet::new();
        for (tr, en) in en::EN {
            assert!(gorulen.insert(*tr), "tabloda iki kez: {tr:?}");
            assert_eq!(tr.matches("{}").count(), en.matches("{}").count(), "yer tutucu sayısı farklı: {tr:?}");
            assert!(!en.is_empty(), "boş çeviri: {tr:?}");
        }
    }

    #[test]
    fn tabloda_kullanilmayan_yok() {
        let kullanilan: HashSet<String> = sarilmis_metinler().into_iter().map(|(_, m)| m).collect();
        let fazla: Vec<&str> = en::EN.iter().map(|(t, _)| *t).filter(|t| !kullanilan.contains(*t) && !en::DOGRUDAN.contains(t)).collect();
        assert!(fazla.is_empty(), "Tabloda olup kodda kullanılmayan metinler:\n{}", fazla.join("\n"));
    }

    #[test]
    fn bicimle_sirayla_doldurur() {
        assert_eq!(bicimle("{} / {} sn", &[&3, &"x"]), "3 / x sn");
        assert_eq!(bicimle("yok", &[]), "yok");
    }
}
