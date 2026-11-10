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

/// Rust panik olmayan çökmeler (erişim ihlali, yığın bozulması, yığın taşması) panik kancasına
/// düşmez; bunları kod, adres ve çağrı yığınıyla (modül + uzaklık) log'a yaz. Uzaklıklar CI'nın
/// yüklediği RizeOn.pdb ile satıra çevrilir. Bu kod çökme anında çalıştığı için bellek ayırmaz.
#[cfg(windows)]
mod yerel {
    use std::io::Write;
    use std::os::windows::io::AsRawHandle;
    use std::path::Path;
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::OnceLock;
    use windows::Win32::Foundation::{HANDLE, HMODULE};
    use windows::Win32::System::Console::{SetStdHandle, STD_ERROR_HANDLE};
    use windows::Win32::System::Diagnostics::Debug::{
        AddVectoredExceptionHandler, RtlCaptureStackBackTrace, SetUnhandledExceptionFilter, EXCEPTION_POINTERS,
    };
    use windows::Win32::System::LibraryLoader::{
        GetModuleFileNameW, GetModuleHandleExW, GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
    };

    static DOSYA: OnceLock<std::fs::File> = OnceLock::new();
    static HATA_CIKTISI: OnceLock<std::fs::File> = OnceLock::new();
    static YAZILAN: AtomicU32 = AtomicU32::new(0);

    /// Sadece uygulamayı bitiren türden kodlar (ilk şans istisnaları da buraya düşer; sıradan
    /// C++/RPC istisnalarını kaydetmeyiz).
    const OLUMCUL: [u32; 6] = [
        0xC0000005, // erişim ihlali
        0xC0000374, // yığın (heap) bozulması
        0xC00000FD, // yığın (stack) taşması
        0xC0000409, // güvenlik denetimi / __fastfail
        0xC000001D, // geçersiz komut
        0xC0000420, // assertion
    ];

    pub fn kur(klasor: &Path, yol: &Path) {
        if let Ok(f) = std::fs::OpenOptions::new().create(true).append(true).open(yol) {
            let _ = DOSYA.set(f);
        }
        // Yığın taşması gibi durumlarda Rust mesajı stderr'e yazar; pencere uygulamasında stderr yok,
        // o yüzden bir dosyaya yönlendir.
        let cikti = klasor.join("hata_ciktisi.txt");
        if std::fs::metadata(&cikti).map(|m| m.len() > 200_000).unwrap_or(false) {
            let _ = std::fs::remove_file(&cikti);
        }
        if let Ok(f) = std::fs::OpenOptions::new().create(true).append(true).open(&cikti) {
            unsafe {
                let _ = SetStdHandle(STD_ERROR_HANDLE, HANDLE(f.as_raw_handle()));
            }
            let _ = HATA_CIKTISI.set(f);
        }
        unsafe {
            AddVectoredExceptionHandler(1, Some(vektorel));
            SetUnhandledExceptionFilter(Some(filtre));
        }
    }

    /// `adres`i "modül+0xuzaklık" olarak yazar.
    fn modul_yaz(f: &mut &std::fs::File, adres: usize) {
        unsafe {
            let mut h = HMODULE::default();
            if GetModuleHandleExW(
                GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                windows::core::PCWSTR(adres as *const u16),
                &mut h,
            )
            .is_err()
            {
                let _ = write!(f, "0x{adres:x}");
                return;
            }
            let mut ad = [0u16; 260];
            let n = GetModuleFileNameW(Some(h), &mut ad) as usize;
            let ad = &ad[..n.min(260)];
            let bas = ad.iter().rposition(|&c| c == b'\\' as u16).map(|i| i + 1).unwrap_or(0);
            for c in char::decode_utf16(ad[bas..].iter().copied()) {
                let _ = write!(f, "{}", c.unwrap_or('?'));
            }
            let _ = write!(f, "+0x{:x}", adres - h.0 as usize);
        }
    }

    unsafe fn kaydet(bilgi: *const EXCEPTION_POINTERS, nereden: &str) {
        // Aynı çökme hem vektörel işleyiciye hem filtreye düşebilir; log'u şişirme.
        if YAZILAN.fetch_add(1, Ordering::SeqCst) >= 4 {
            return;
        }
        let Some(dosya) = DOSYA.get() else { return };
        let mut f = dosya;
        unsafe {
            let kayit = bilgi.as_ref().and_then(|b| b.ExceptionRecord.as_ref());
            let (kod, adres) = kayit.map(|k| (k.ExceptionCode.0 as u32, k.ExceptionAddress as usize)).unwrap_or((0, 0));
            let is = windows::Win32::System::Threading::GetCurrentThreadId();
            // chrono bellek ayırabilir; çökme anında Windows saatini doğrudan kullan.
            let t = windows::Win32::System::SystemInformation::GetLocalTime();
            let _ = write!(
                f,
                "{:04}-{:02}-{:02} {:02}:{:02}:{:02}.{:03} ERROR rizeon::gunluk: Uygulama çöktü ({nereden}): kod 0x{kod:08x}, adres ",
                t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond, t.wMilliseconds
            );
            modul_yaz(&mut f, adres);
            if let Some(k) = kayit {
                if kod == 0xC0000005 && k.NumberParameters >= 2 {
                    let tur = if k.ExceptionInformation[0] == 1 { "yazma" } else { "okuma" };
                    let _ = write!(f, ", {tur} 0x{:x}", k.ExceptionInformation[1]);
                }
            }
            let _ = write!(f, ", iş parçacığı {is}");
            if let Ok(p) = windows::Win32::System::Threading::GetThreadDescription(windows::Win32::System::Threading::GetCurrentThread()) {
                if !p.is_null() {
                    let _ = write!(f, " '");
                    for c in char::decode_utf16(p.as_wide().iter().copied()) {
                        let _ = write!(f, "{}", c.unwrap_or('?'));
                    }
                    let _ = write!(f, "'");
                }
            }
            let _ = writeln!(f, "\n  çağrı yığını:");
            let mut cerceve = [std::ptr::null_mut(); 48];
            let n = RtlCaptureStackBackTrace(0, &mut cerceve, None) as usize;
            for c in &cerceve[..n] {
                let _ = write!(f, "    ");
                modul_yaz(&mut f, *c as usize);
                let _ = writeln!(f);
            }
            let _ = f.flush();
        }
    }

    unsafe extern "system" fn vektorel(bilgi: *mut EXCEPTION_POINTERS) -> i32 {
        unsafe {
            let kod = bilgi.as_ref().and_then(|b| b.ExceptionRecord.as_ref()).map(|k| k.ExceptionCode.0 as u32).unwrap_or(0);
            if OLUMCUL.contains(&kod) {
                kaydet(bilgi, "vektörel");
            }
        }
        0 // EXCEPTION_CONTINUE_SEARCH
    }

    unsafe extern "system" fn filtre(bilgi: *const EXCEPTION_POINTERS) -> i32 {
        unsafe { kaydet(bilgi, "işlenmemiş") };
        0 // EXCEPTION_CONTINUE_SEARCH: Windows çökme işlemine devam etsin
    }
}
