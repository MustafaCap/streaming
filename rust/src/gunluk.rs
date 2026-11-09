//! Log dosyası: %APPDATA%\RizeOn\logs\rizeon.log (1 MB'ı geçince .1 olarak saklanır).
use std::io::Write;
use std::sync::Mutex;

struct Gunluk {
    dosya: Mutex<Option<std::fs::File>>,
}

impl log::Log for Gunluk {
    fn enabled(&self, m: &log::Metadata) -> bool {
        m.level() <= log::Level::Info || m.target().starts_with("rizeon")
    }
    fn log(&self, k: &log::Record) {
        if !self.enabled(k.metadata()) || !(k.target().starts_with("rizeon") || k.target().starts_with("RizeOn") || k.level() <= log::Level::Warn) {
            return;
        }
        let satir = format!("{} {:5} {}: {}\n", chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f"), k.level(), k.target(), k.args());
        if cfg!(debug_assertions) {
            eprint!("{satir}");
        }
        if let Some(f) = self.dosya.lock().unwrap().as_mut() {
            let _ = f.write_all(satir.as_bytes());
        }
    }
    fn flush(&self) {
        if let Some(f) = self.dosya.lock().unwrap().as_mut() {
            let _ = f.flush();
        }
    }
}

pub fn kur() {
    let klasor = crate::yollar::log_klasoru();
    let yol = klasor.join("rizeon.log");
    if std::fs::metadata(&yol).map(|m| m.len() > 1_000_000).unwrap_or(false) {
        let _ = std::fs::rename(&yol, klasor.join("rizeon.log.1"));
    }
    let dosya = std::fs::OpenOptions::new().create(true).append(true).open(&yol).ok();
    let g = Box::leak(Box::new(Gunluk { dosya: Mutex::new(dosya) }));
    let _ = log::set_logger(g);
    log::set_max_level(log::LevelFilter::Info);
    std::panic::set_hook(Box::new(|bilgi| {
        log::error!("Beklenmedik hata: {bilgi}\n{}", std::backtrace::Backtrace::force_capture());
        log::logger().flush();
    }));
}
