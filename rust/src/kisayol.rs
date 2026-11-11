//! Global kısayollar (Python core/hotkeys.py). Windows'un RegisterHotKey'i kullanılır: klavye kancası yok
//! (antivirüsler sevmez, tuşları oyundan çalabilir). Kayıt yapan iş parçacığının kendi mesaj döngüsü var.

use crate::dil::t;
use crate::trf;

pub const MOD_ALT: u32 = 0x1;
pub const MOD_CONTROL: u32 = 0x2;
pub const MOD_SHIFT: u32 = 0x4;
pub const MOD_WIN: u32 = 0x8;
pub const MOD_NOREPEAT: u32 = 0x4000;

#[derive(Debug, PartialEq)]
pub struct GecersizTus(pub String);

fn ozel_tus(k: &str) -> Option<u32> {
    Some(match k {
        // Fare tuşları (orta tuş, yan tuşlar): RegisterHotKey desteklemez, durumları yoklanır
        "fare3" | "mouse3" => 0x04,
        "fare4" | "mouse4" => 0x05,
        "fare5" | "mouse5" => 0x06,
        "del" | "delete" => 0x2E,
        "ins" | "insert" => 0x2D,
        "enter" => 0x0D,
        "esc" | "escape" => 0x1B,
        "space" => 0x20,
        "tab" => 0x09,
        "backspace" => 0x08,
        "home" => 0x24,
        "end" => 0x23,
        "pageup" => 0x21,
        "pagedown" => 0x22,
        "pause" => 0x13,
        "up" => 0x26,
        "down" => 0x28,
        "left" => 0x25,
        "right" => 0x27,
        "printscreen" => 0x2C,
        "scrolllock" => 0x91,
        _ => return None,
    })
}

/// "Ctrl+Shift+R" -> (MOD_CONTROL|MOD_SHIFT, 0x52)
pub fn tus_coz(metin: &str) -> Result<(u32, u32), GecersizTus> {
    let temiz = metin.replace(' ', "");
    if temiz.is_empty() {
        return Err(GecersizTus(t("Boş tuş").into()));
    }
    let parcalar: Vec<&str> = temiz.split('+').collect();
    if parcalar.iter().any(|p| p.is_empty()) {
        return Err(GecersizTus(trf!("Geçersiz tuş: {}", metin)));
    }
    let mut m = 0;
    for p in &parcalar[..parcalar.len() - 1] {
        m |= match p.to_lowercase().as_str() {
            "ctrl" | "control" => MOD_CONTROL,
            "alt" => MOD_ALT,
            "shift" => MOD_SHIFT,
            "win" => MOD_WIN,
            _ => return Err(GecersizTus(trf!("Bilinmeyen değiştirici: {}", p))),
        };
    }
    let tus = parcalar[parcalar.len() - 1];
    let k = tus.to_lowercase();
    let c: Vec<char> = tus.chars().collect();
    if c.len() == 1 && c[0].is_ascii_alphanumeric() {
        return Ok((m, c[0].to_ascii_uppercase() as u32));
    }
    if let Some(n) = k.strip_prefix('f').and_then(|n| n.parse::<u32>().ok()).filter(|n| (1..=24).contains(n)) {
        if n == 12 && m == 0 {
            return Err(GecersizTus(t("F12 tek başına kullanılamaz (Windows'a ayrılmış); Ctrl/Alt/Shift ile birlikte kullan").into()));
        }
        return Ok((m, 0x70 + n - 1));
    }
    if let Some(n) = k.strip_prefix("num").filter(|n| n.len() == 1).and_then(|n| n.parse::<u32>().ok()) {
        return Ok((m, 0x60 + n));
    }
    if let Some(v) = ozel_tus(&k) {
        return Ok((m, v));
    }
    Err(GecersizTus(trf!("Bilinmeyen tuş: {}", tus)))
}

/// Bildirimlerde göstermek için: "ctrl+1" -> "Ctrl+1"
pub fn tus_metni(metin: &str) -> String {
    metin
        .split('+')
        .map(str::trim)
        .filter(|p| !p.is_empty())
        .map(|p| {
            if p.chars().count() > 1 {
                let mut c = p.chars();
                c.next().map(|f| f.to_uppercase().collect::<String>() + &c.as_str().to_lowercase()).unwrap_or_default()
            } else {
                p.to_uppercase()
            }
        })
        .collect::<Vec<_>>()
        .join("+")
}

/// Fare tuşu mu (VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2)?
pub fn fare_tusu(vk: u32) -> bool {
    matches!(vk, 0x04..=0x06)
}

/// Tuş (değiştiricileriyle) şu an basılı mı? `basili(vk)` tek bir sanal tuşun durumunu verir.
/// Değiştiriciler tam eşleşmeli: Ctrl+Fare4 için Ctrl basılı olmalı, Shift basılı olmamalı.
pub fn birlesim_basili(mods: u32, vk: u32, basili: impl Fn(u32) -> bool) -> bool {
    let istenen = [(MOD_CONTROL, 0x11), (MOD_ALT, 0x12), (MOD_SHIFT, 0x10)];
    let win = basili(0x5B) || basili(0x5C);
    basili(vk) && istenen.iter().all(|(m, v)| (mods & m != 0) == basili(*v)) && ((mods & MOD_WIN != 0) == win)
}

#[cfg(windows)]
pub use crate::win::kisayol::{BasKonus, KisayolYoneticisi};

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn cozumleme() {
        assert_eq!(tus_coz("Ctrl+Shift+R"), Ok((MOD_CONTROL | MOD_SHIFT, 0x52)));
        assert_eq!(tus_coz("Fare4"), Ok((0, 0x05)));
        assert!(fare_tusu(tus_coz("Ctrl+Fare5").unwrap().1));
        let basili = |vk: u32| vk == 0x05 || vk == 0x11;
        assert!(birlesim_basili(MOD_CONTROL, 0x05, basili));
        assert!(!birlesim_basili(0, 0x05, basili));
        assert!(!birlesim_basili(MOD_CONTROL | MOD_SHIFT, 0x05, basili));
        assert_eq!(tus_coz("ctrl + shift+1"), Ok((MOD_CONTROL | MOD_SHIFT, 0x31)));
        assert_eq!(tus_coz("F6"), Ok((0, 0x75)));
        assert_eq!(tus_coz("Del"), Ok((0, 0x2E)));
        assert_eq!(tus_coz("Num5"), Ok((0, 0x65)));
        assert!(tus_coz("F12").is_err());
        assert!(tus_coz("Ctrl+F12").is_ok());
        assert!(tus_coz("Hyper+A").is_err());
        assert!(tus_coz("").is_err());
        assert_eq!(tus_metni("ctrl+shift+m"), "Ctrl+Shift+M");
    }
}
