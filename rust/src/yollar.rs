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

pub const VIDEO_UZANTILARI: [&str; 8] = ["mp4", "webm", "avi", "mov", "mkv", "gif", "wmv", "m4v"];

/// Bekleme ekranı ya da kaynak dosyası video mu (uzantıya göre).
pub fn video_mu(yol: &str) -> bool {
    !yol.is_empty()
        && Path::new(yol)
            .extension()
            .map(|u| VIDEO_UZANTILARI.contains(&u.to_string_lossy().to_lowercase().as_str()))
            .unwrap_or(false)
}

/// Video kaynakları veri klasörüne kopyalanır: kullanıcı dosyayı taşısa da kaynak bozulmaz.
pub fn video_kopyala(kaynak: &Path) -> std::io::Result<PathBuf> {
    let hedef_klasor = veri_klasoru().join("kaynaklar");
    std::fs::create_dir_all(&hedef_klasor)?;
    let ust = kaynak.canonicalize().ok().and_then(|p| p.parent().map(Path::to_path_buf));
    if ust.is_some() && ust == hedef_klasor.canonicalize().ok() {
        return Ok(kaynak.to_path_buf());
    }
    let ms = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
    let uzanti = kaynak.extension().map(|u| u.to_string_lossy().to_lowercase()).unwrap_or_default();
    let hedef = hedef_klasor.join(format!("video_{ms}.{uzanti}"));
    std::fs::copy(kaynak, &hedef)?;
    Ok(hedef)
}

#[cfg(test)]
mod testler {
    #[test]
    fn video_uzantisi() {
        assert!(super::video_mu("a/b.MP4"));
        assert!(!super::video_mu("a/b.png"));
        assert!(!super::video_mu(""));
    }
}
