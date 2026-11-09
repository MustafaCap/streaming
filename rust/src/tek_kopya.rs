//! Tek kopya: uygulama ikinci kez açılırsa ilkinin penceresi öne gelir (Python core/tek_kopya.py ile
//! aynı adlar; Python ve Rust sürümü aynı anda açılıp sanal kamerayı kapışmaz).

pub const MUTEX_ADI: &str = "Local\\RizeOn_TekKopya";
pub const OLAY_ADI: &str = "Local\\RizeOn_PencereyiGoster";

pub struct TekKopya {
    #[cfg(windows)]
    _mutex: windows::Win32::Foundation::HANDLE,
    #[cfg(windows)]
    olay: windows::Win32::Foundation::HANDLE,
}

unsafe impl Send for TekKopya {}
unsafe impl Sync for TekKopya {}

impl TekKopya {
    /// İlk kopyaysa Some; başka bir kopya çalışıyorsa ona "pencereni göster" der ve None döner.
    #[cfg(windows)]
    pub fn al() -> Option<TekKopya> {
        use windows::core::HSTRING;
        use windows::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS};
        use windows::Win32::System::Threading::{CreateEventW, CreateMutexW, OpenEventW, SetEvent, EVENT_MODIFY_STATE};
        unsafe {
            let m = CreateMutexW(None, false, &HSTRING::from(MUTEX_ADI)).ok()?;
            if GetLastError() == ERROR_ALREADY_EXISTS {
                if let Ok(o) = OpenEventW(EVENT_MODIFY_STATE, false, &HSTRING::from(OLAY_ADI)) {
                    let _ = SetEvent(o);
                    let _ = CloseHandle(o);
                }
                let _ = CloseHandle(m);
                return None;
            }
            let olay = CreateEventW(None, false, false, &HSTRING::from(OLAY_ADI)).ok()?;
            Some(TekKopya { _mutex: m, olay })
        }
    }

    #[cfg(not(windows))]
    pub fn al() -> Option<TekKopya> {
        Some(TekKopya {})
    }

    /// Başka bir kopya "pencereni göster" dedi mi (beklemeden bakar).
    pub fn goster_istendi(&self) -> bool {
        #[cfg(windows)]
        unsafe {
            use windows::Win32::Foundation::WAIT_OBJECT_0;
            use windows::Win32::System::Threading::WaitForSingleObject;
            return WaitForSingleObject(self.olay, 0) == WAIT_OBJECT_0;
        }
        #[cfg(not(windows))]
        false
    }
}
