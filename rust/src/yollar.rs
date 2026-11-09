//! Uygulamanın dosya yolları. Ayarlar ve loglar %APPDATA%\RizeOn içinde (Python sürümüyle aynı yer).

use std::path::{Path, PathBuf};

pub const UYGULAMA_ADI: &str = "RizeOn";
pub const ESKI_AD: &str = "YayinUygulamasi";

/// Programın kendi dosyalarının (ffmpeg\, config\) bulunduğu klasör: exe'nin yanı.
pub fn uygulama_klasoru() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn ev() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Kullanıcıya özel yazılabilir klasör: %APPDATA%\RizeOn (testlerde YAYIN_VERI_KLASORU ile değişir).
pub fn veri_klasoru() -> PathBuf {
    let taban = std::env::var_os("YAYIN_VERI_KLASORU")
        .or_else(|| std::env::var_os("APPDATA"))
        .map(PathBuf::from)
        .unwrap_or_else(|| ev().join(".config"));
    let yol = taban.join(UYGULAMA_ADI);
    if !yol.exists() {
        let eski = taban.join(ESKI_AD);
        if eski.is_dir() {
            if std::fs::rename(&eski, &yol).is_ok() {
                log::info!("Eski veri klasörü yeni ada taşındı: {} -> {}", eski.display(), yol.display());
            }
        }
    }
    let _ = std::fs::create_dir_all(&yol);
    yol
}

pub fn ayar_dosyasi() -> PathBuf {
    veri_klasoru().join("settings.json")
}

pub fn log_klasoru() -> PathBuf {
    let yol = veri_klasoru().join("logs");
    let _ = std::fs::create_dir_all(&yol);
    yol
}

/// Kayıtların varsayılan klasörü: Videolar\RizeOn
pub fn varsayilan_kayit_klasoru() -> PathBuf {
    #[cfg(windows)]
    if let Some(v) = crate::win::bilinen_klasor_videolar() {
        return v.join(UYGULAMA_ADI);
    }
    ev().join("Videos").join(UYGULAMA_ADI)
}
