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
    #[cfg(windows)]
    yerel::kur(&klasor, &yol);
}

/// Rust panik olmayan çökmeler (erişim ihlali, yığın taşması) panik kancasına düşmez; bunları da kaydet.
#[cfg(windows)]
mod yerel {
    use std::io::Write;
    use std::os::windows::io::AsRawHandle;
    use std::path::Path;
    use std::sync::OnceLock;
    use windows::Win32::Foundation::{HANDLE, HMODULE};
    use windows::Win32::System::Console::{SetStdHandle, STD_ERROR_HANDLE};
    use windows::Win32::System::Diagnostics::Debug::{
        SetUnhandledExceptionFilter, EXCEPTION_POINTERS,
    };
    use windows::Win32::System::LibraryLoader::{
        GetModuleFileNameW, GetModuleHandleExW, GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
    };

    static DOSYA: OnceLock<std::fs::File> = OnceLock::new();
    static HATA_CIKTISI: OnceLock<std::fs::File> = OnceLock::new();

    pub fn kur(klasor: &Path, yol: &Path) {
        if let Ok(f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(yol)
        {
            let _ = DOSYA.set(f);
        }
        // Yığın taşması gibi durumlarda Rust mesajı stderr'e yazar; pencere uygulamasında stderr yok,
        // o yüzden bir dosyaya yönlendir.
        let cikti = klasor.join("hata_ciktisi.txt");
        if std::fs::metadata(&cikti)
            .map(|m| m.len() > 200_000)
            .unwrap_or(false)
        {
            let _ = std::fs::remove_file(&cikti);
        }
        if let Ok(f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&cikti)
        {
            unsafe {
                let _ = SetStdHandle(STD_ERROR_HANDLE, HANDLE(f.as_raw_handle()));
            }
            let _ = HATA_CIKTISI.set(f);
        }
        unsafe {
            SetUnhandledExceptionFilter(Some(filtre));
        }
    }

    fn modul(adres: usize) -> String {
        unsafe {
            let mut h = HMODULE::default();
            if GetModuleHandleExW(
                GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                    | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                windows::core::PCWSTR(adres as *const u16),
                &mut h,
            )
            .is_err()
            {
                return "?".into();
            }
            let mut ad = [0u16; 260];
            let n = GetModuleFileNameW(Some(h), &mut ad) as usize;
            let ad = String::from_utf16_lossy(&ad[..n]);
            let kisa = ad.rsplit('\\').next().unwrap_or(&ad).to_string();
            format!("{kisa} + 0x{:x}", adres - h.0 as usize)
        }
    }

    unsafe extern "system" fn filtre(bilgi: *const EXCEPTION_POINTERS) -> i32 {
        unsafe {
            let kayit = bilgi.as_ref().and_then(|b| b.ExceptionRecord.as_ref());
            let (kod, adres, ek) = match kayit {
                Some(k) => (
                    k.ExceptionCode.0 as u32,
                    k.ExceptionAddress as usize,
                    k.ExceptionInformation[..k.NumberParameters.min(2) as usize].to_vec(),
                ),
                None => (0, 0, Vec::new()),
            };
            let is = windows::Win32::System::Threading::GetCurrentThreadId();
            let is_adi = windows::Win32::System::Threading::GetThreadDescription(
                windows::Win32::System::Threading::GetCurrentThread(),
            )
            .ok()
            .and_then(|p| p.to_string().ok())
            .unwrap_or_default();
            let satir = format!(
                "{} ERROR rizeon: Uygulama çöktü: kod 0x{kod:08x}, adres 0x{adres:x} ({}), ek {ek:x?}, iş parçacığı {is} '{is_adi}'\n",
                chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f"),
                modul(adres),
            );
            if let Some(mut f) = DOSYA.get() {
                let _ = f.write_all(satir.as_bytes());
                let _ = f.flush();
            }
        }
        0 // EXCEPTION_CONTINUE_SEARCH: Windows çökme işlemine devam etsin
    }
}

