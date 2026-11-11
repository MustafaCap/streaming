//! Windows'a özel yardımcılar (windows crate ile).
#![allow(clippy::missing_safety_doc)]

pub mod kisayol;

use std::path::{Path, PathBuf};

use windows::core::{HSTRING, PCWSTR};
use windows::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, HANDLE, HWND, INVALID_HANDLE_VALUE, POINT};
use windows::Win32::Storage::FileSystem::{SetFileAttributesW, FILE_ATTRIBUTE_HIDDEN};
use windows::Win32::System::Memory::{
    CreateFileMappingW, MapViewOfFile, OpenFileMappingW, UnmapViewOfFile, FILE_MAP_ALL_ACCESS, FILE_MAP_READ, MEMORY_MAPPED_VIEW_ADDRESS,
    PAGE_READWRITE,
};
use windows::Win32::System::Registry::{RegCloseKey, RegOpenKeyExW, HKEY, HKEY_CLASSES_ROOT, KEY_READ, KEY_WOW64_32KEY, KEY_WOW64_64KEY};
use windows::Win32::UI::Shell::{SHGetKnownFolderPath, FOLDERID_Pictures, FOLDERID_Videos, KNOWN_FOLDER_FLAG};
use windows::Win32::UI::WindowsAndMessaging::{GetCursorInfo, SetWindowDisplayAffinity, CURSORINFO, CURSOR_SHOWING, WDA_EXCLUDEFROMCAPTURE, WDA_NONE};

fn bilinen_klasor(id: &windows::core::GUID) -> Option<PathBuf> {
    unsafe {
        let p = SHGetKnownFolderPath(id, KNOWN_FOLDER_FLAG(0), None).ok()?;
        let s = p.to_string().ok();
        windows::Win32::System::Com::CoTaskMemFree(Some(p.0 as _));
        s.map(PathBuf::from)
    }
}

pub fn bilinen_klasor_videolar() -> Option<PathBuf> {
    bilinen_klasor(&FOLDERID_Videos)
}
pub fn bilinen_klasor_resimler() -> Option<PathBuf> {
    bilinen_klasor(&FOLDERID_Pictures)
}

pub fn dosyayi_gizle(yol: &Path) {
    unsafe {
        let _ = SetFileAttributesW(&HSTRING::from(yol.as_os_str()), FILE_ATTRIBUTE_HIDDEN);
    }
}

/// HKCR\CLSID\{...} kayıtlı mı (64 ve 32 bit görünüm).
pub fn clsid_kayitli(clsid: &str) -> bool {
    let yol = HSTRING::from(format!("CLSID\\{clsid}"));
    for gorunum in [KEY_READ | KEY_WOW64_64KEY, KEY_READ | KEY_WOW64_32KEY] {
        let mut k = HKEY::default();
        unsafe {
            if RegOpenKeyExW(HKEY_CLASSES_ROOT, &yol, Some(0), gorunum, &mut k).is_ok() {
                let _ = RegCloseKey(k);
                return true;
            }
        }
    }
    false
}

/// Adlandırılmış paylaşılan bellek (OBS sanal kamera için).
pub struct PaylasilanBellek {
    tutamak: HANDLE,
    adres: MEMORY_MAPPED_VIEW_ADDRESS,
}

unsafe impl Send for PaylasilanBellek {}

impl PaylasilanBellek {
    pub fn olustur(ad: &str, boyut: usize) -> Result<Self, String> {
        let ad = HSTRING::from(ad);
        unsafe {
            if let Ok(mevcut) = OpenFileMappingW(FILE_MAP_READ.0, false, &ad) {
                let _ = CloseHandle(mevcut);
                return Err("OBS sanal kamerası şu an başka bir programda açık (OBS'nin kendisi olabilir)".into());
            }
            let tutamak = CreateFileMappingW(INVALID_HANDLE_VALUE, None, PAGE_READWRITE, (boyut as u64 >> 32) as u32, boyut as u32, &ad)
                .map_err(|e| format!("Paylaşılan bellek oluşturulamadı ({e})"))?;
            if GetLastError() == ERROR_ALREADY_EXISTS {
                let _ = CloseHandle(tutamak);
                return Err("OBS sanal kamerası şu an başka bir programda açık".into());
            }
            let adres = MapViewOfFile(tutamak, FILE_MAP_ALL_ACCESS, 0, 0, 0);
            if adres.Value.is_null() {
                let e = GetLastError();
                let _ = CloseHandle(tutamak);
                return Err(format!("Paylaşılan bellek açılamadı (Windows hata kodu {})", e.0));
            }
            Ok(PaylasilanBellek { tutamak, adres })
        }
    }

    pub fn adres(&self) -> *mut u8 {
        self.adres.Value as *mut u8
    }
}

impl Drop for PaylasilanBellek {
    fn drop(&mut self) {
        unsafe {
            let _ = UnmapViewOfFile(self.adres);
            let _ = CloseHandle(self.tutamak);
        }
    }
}

/// Fare imlecinin ekrandaki konumu; imleç gizliyse (ör. oyunda) None.
pub fn fare_konumu() -> Option<(i32, i32)> {
    let mut b = CURSORINFO { cbSize: std::mem::size_of::<CURSORINFO>() as u32, ..Default::default() };
    unsafe {
        GetCursorInfo(&mut b).ok()?;
    }
    if b.flags.0 & CURSOR_SHOWING.0 == 0 {
        return None;
    }
    let POINT { x, y } = b.ptScreenPos;
    Some((x, y))
}

/// Pencereyi ekran yakalamadan gizler (kendi pencerelerimiz yayına/kayda girmesin).
pub fn yakalamadan_gizle(hwnd: isize, gizle: bool) -> bool {
    unsafe { SetWindowDisplayAffinity(HWND(hwnd as _), if gizle { WDA_EXCLUDEFROMCAPTURE } else { WDA_NONE }).is_ok() }
}

/// Ana ekranın çalışma alanı (görev çubuğu hariç), fiziksel piksel: (sol, üst, sağ, alt).
pub fn calisma_alani() -> Option<(i32, i32, i32, i32)> {
    use windows::Win32::Foundation::RECT;
    use windows::Win32::UI::WindowsAndMessaging::{SystemParametersInfoW, SPI_GETWORKAREA, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS};
    let mut r = RECT::default();
    unsafe { SystemParametersInfoW(SPI_GETWORKAREA, 0, Some(&mut r as *mut RECT as *mut _), SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0)) }.ok()?;
    (r.right > r.left && r.bottom > r.top).then_some((r.left, r.top, r.right, r.bottom))
}

/// Önde bir oyun özel tam ekranda (exclusive fullscreen) mı çalışıyor? O modda saydam pencereler
/// oyunun üstünde görünmeyebilir; kalem çizimleri yine yayına gider ama kullanıcı ekranda görmez.
pub fn ozel_tam_ekran_mi() -> bool {
    use windows::Win32::UI::Shell::{SHQueryUserNotificationState, QUNS_RUNNING_D3D_FULL_SCREEN};
    unsafe { SHQueryUserNotificationState() }.map(|d| d == QUNS_RUNNING_D3D_FULL_SCREEN).unwrap_or(false)
}

/// Windows 11: çerçevesiz pencerenin köşeleri de sistem gibi yuvarlak olsun (8 px).
pub fn koseleri_yuvarla(hwnd: isize) -> bool {
    use windows::Win32::Graphics::Dwm::{DwmSetWindowAttribute, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND};
    let deger = DWMWCP_ROUND;
    unsafe {
        DwmSetWindowAttribute(HWND(hwnd as _), DWMWA_WINDOW_CORNER_PREFERENCE, &deger as *const _ as *const _, std::mem::size_of_val(&deger) as u32)
            .is_ok()
    }
}

/// Windows'un dosya açma penceresi. `filtre`: (ad, "*.png;*.jpg").
pub fn dosya_sec(baslik: &str, filtre: &[(&str, &str)]) -> Option<PathBuf> {
    use windows::Win32::System::Com::{CoCreateInstance, CLSCTX_INPROC_SERVER};
    use windows::Win32::UI::Shell::Common::COMDLG_FILTERSPEC;
    use windows::Win32::UI::Shell::{FileOpenDialog, IFileOpenDialog, SIGDN_FILESYSPATH};
    com_baslat();
    unsafe {
        let d: IFileOpenDialog = CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER).ok()?;
        let adlar: Vec<HSTRING> = filtre.iter().map(|(a, _)| HSTRING::from(*a)).collect();
        let desenler: Vec<HSTRING> = filtre.iter().map(|(_, d)| HSTRING::from(*d)).collect();
        let ozler: Vec<COMDLG_FILTERSPEC> = adlar
            .iter()
            .zip(&desenler)
            .map(|(a, d)| COMDLG_FILTERSPEC { pszName: PCWSTR(a.as_ptr()), pszSpec: PCWSTR(d.as_ptr()) })
            .collect();
        if !ozler.is_empty() {
            let _ = d.SetFileTypes(&ozler);
        }
        let _ = d.SetTitle(&HSTRING::from(baslik));
        d.Show(None).ok()?;
        let oge = d.GetResult().ok()?;
        let yol = oge.GetDisplayName(SIGDN_FILESYSPATH).ok()?;
        let s = yol.to_string().ok();
        windows::Win32::System::Com::CoTaskMemFree(Some(yol.0 as *const _));
        s.map(PathBuf::from)
    }
}

/// Klasör seçme penceresi (Windows'un kendi penceresi).
pub fn klasor_sec(baslik: &str, baslangic: Option<&Path>) -> Option<PathBuf> {
    use windows::Win32::System::Com::{CoCreateInstance, CLSCTX_INPROC_SERVER};
    use windows::Win32::UI::Shell::{FileOpenDialog, IFileOpenDialog, IShellItem, SHCreateItemFromParsingName, FOS_PICKFOLDERS, SIGDN_FILESYSPATH};
    com_baslat();
    unsafe {
        let d: IFileOpenDialog = CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER).ok()?;
        let s = d.GetOptions().unwrap_or_default();
        let _ = d.SetOptions(s | FOS_PICKFOLDERS);
        let _ = d.SetTitle(&HSTRING::from(baslik));
        if let Some(b) = baslangic.filter(|b| b.is_dir()) {
            if let Ok(oge) = SHCreateItemFromParsingName::<_, _, IShellItem>(&HSTRING::from(b.as_os_str()), None) {
                let _ = d.SetFolder(&oge);
            }
        }
        d.Show(None).ok()?;
        let oge = d.GetResult().ok()?;
        let yol = oge.GetDisplayName(SIGDN_FILESYSPATH).ok()?;
        let s = yol.to_string().ok();
        windows::Win32::System::Com::CoTaskMemFree(Some(yol.0 as *const _));
        s.map(PathBuf::from)
    }
}

/// Ana pencerenin tutamacı (ilk karede kaydedilir); Ayarlar gibi pencereler ona bağlanır.
pub static ANA_PENCERE: std::sync::atomic::AtomicIsize = std::sync::atomic::AtomicIsize::new(0);

/// Pencereyi ana pencereye bağlar (sahip): hep onun önünde durur, arkasına düşmez (Qt'de
/// ebeveynli QDialog gibi). Ana pencere henüz bilinmiyorsa false.
pub fn ana_pencereye_bagla(hwnd: isize) -> bool {
    use windows::Win32::UI::WindowsAndMessaging::{SetWindowLongPtrW, GWLP_HWNDPARENT};
    let ana = ANA_PENCERE.load(std::sync::atomic::Ordering::Relaxed);
    if ana == 0 || ana == hwnd {
        return false;
    }
    unsafe { SetWindowLongPtrW(HWND(hwnd as _), GWLP_HWNDPARENT, ana) };
    true
}

/// Bu süreçteki, başlığı verilen üst düzey pencereyi bulur.
pub fn pencere_bul(baslik: &str) -> Option<isize> {
    use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, GetWindowThreadProcessId};
    let h = unsafe { FindWindowW(PCWSTR::null(), &HSTRING::from(baslik)) }.ok()?;
    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(h, Some(&mut pid)) };
    (pid == std::process::id()).then_some(h.0 as isize)
}

/// Dosyayı Gezgin'de seçili gösterir.
pub fn klasorde_goster(dosya: &Path) {
    let _ = std::process::Command::new("explorer").arg("/select,").arg(dosya).spawn();
}

/// Dosya ya da klasörü varsayılan programla açar.
pub fn ac(yol: &Path) {
    use windows::Win32::UI::Shell::ShellExecuteW;
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    unsafe {
        ShellExecuteW(None, &HSTRING::from("open"), &HSTRING::from(yol.as_os_str()), PCWSTR::null(), PCWSTR::null(), SW_SHOWNORMAL);
    }
}

/// COM'u bu iş parçacığında başlatır (çok iş parçacıklı daire).
pub fn com_baslat() {
    use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
    }
}
