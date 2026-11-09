//! Tek bir pencereyi yakalama (Python capture/window.py karşılığı): yayında ya da kayıtta sadece
//! seçilen pencere görünür. PrintWindow (PW_RENDERFULLCONTENT) kullanılır: üstüne başka pencere
//! gelse de seçilen pencerenin kendisi yakalanır.
//!
//! Bazı programlar (bazı oyunlar, donanım hızlandırmalı video oynatıcılar) PrintWindow'a siyah verir;
//! üst üste siyah gelirse pencerenin ekrandaki yeri yakalanır ("ekrandan"). Pencere küçültülürse son
//! görüntü kalır; kapanırsa grab() None döner (önizlemede "koptu").

use windows::Win32::Foundation::{HWND, LPARAM, RECT};
use windows::Win32::Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS};
use windows::Win32::Graphics::Gdi::{
    BitBlt, CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, GetDC, ReleaseDC, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    CAPTUREBLT, DIB_RGB_COLORS, SRCCOPY,
};
use windows::Win32::Storage::Xps::{PrintWindow, PRINT_WINDOW_FLAGS};
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetWindow, GetWindowLongW, GetWindowRect, GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId, IsIconic,
    IsWindow, IsWindowVisible, GWL_EXSTYLE, GW_OWNER, WS_EX_TOOLWINDOW,
};
use windows_core::BOOL;

use crate::kare::{Kare, KareRef};

const SIYAH_ESIGI: u32 = 3;
const KUCUK: i32 = 40;
const PW_RENDERFULLCONTENT: u32 = 2;

#[derive(Clone, Debug)]
pub struct PencereBilgisi {
    pub hwnd: isize,
    pub baslik: String,
    pub program: String,
    pub pid: u32,
}

fn hwnd(h: isize) -> HWND {
    HWND(h as _)
}

/// (pencere dikdörtgeni, görünen çerçeve) ekran koordinatlarında
fn dikdortgenler(h: HWND) -> Option<(RECT, RECT)> {
    unsafe {
        let mut p = RECT::default();
        GetWindowRect(h, &mut p).ok()?;
        let mut c = RECT::default();
        if DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, &mut c as *mut _ as *mut _, std::mem::size_of::<RECT>() as u32).is_err() {
            c = p;
        }
        Some((p, c))
    }
}

/// Ekran ya da pencere DC'sinden 32 bit BGRA görüntü (kopyalayıcı DC'ye çizer).
unsafe fn dib_ile(w: i32, h: i32, ciz: impl FnOnce(windows::Win32::Graphics::Gdi::HDC) -> bool) -> Option<Vec<u8>> {
    let ekran = GetDC(None);
    let dc = CreateCompatibleDC(Some(ekran));
    let mut bi = BITMAPINFO::default();
    bi.bmiHeader = BITMAPINFOHEADER {
        biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
        biWidth: w,
        biHeight: -h,
        biPlanes: 1,
        biBitCount: 32,
        biCompression: BI_RGB.0,
        ..Default::default()
    };
    let mut bitler = std::ptr::null_mut();
    let sonuc = match CreateDIBSection(Some(dc), &bi, DIB_RGB_COLORS, &mut bitler, None, 0) {
        Ok(bmp) => {
            let eski = SelectObject(dc, bmp.into());
            let ok = ciz(dc);
            let veri = ok.then(|| {
                let mut v = std::slice::from_raw_parts(bitler as *const u8, (w * h * 4) as usize).to_vec();
                for p in v.chunks_exact_mut(4) {
                    p[3] = 255;
                }
                v
            });
            SelectObject(dc, eski);
            let _ = DeleteObject(bmp.into());
            veri
        }
        Err(_) => None,
    };
    let _ = DeleteDC(dc);
    ReleaseDC(None, ekran);
    sonuc
}

fn siyah_mi(k: &Kare) -> bool {
    let (w, h) = (k.w as usize, k.h as usize);
    (0..h).step_by(16).all(|y| (0..w).step_by(16).all(|x| {
        let i = (y * w + x) * 4;
        k.veri[i] == 0 && k.veri[i + 1] == 0 && k.veri[i + 2] == 0
    }))
}

/// PrintWindow'un verdiği tüm pencereyi (görünmez kenarlıklarla) görünen çerçeveye kırpar.
pub fn kirp_dikdortgeni(pencere: (i32, i32, i32, i32), cerceve: (i32, i32, i32, i32), w: i32, h: i32) -> (i32, i32, i32, i32) {
    let x0 = (cerceve.0 - pencere.0).clamp(0, w);
    let y0 = (cerceve.1 - pencere.1).clamp(0, h);
    let x1 = (cerceve.2 - pencere.0).clamp(x0, w);
    let y1 = (cerceve.3 - pencere.1).clamp(y0, h);
    if x1 - x0 < 2 || y1 - y0 < 2 {
        (0, 0, w, h)
    } else {
        (x0, y0, x1, y1)
    }
}

pub struct PencereKaynagi {
    pub hwnd: isize,
    pub baslik: String,
    son: Option<KareRef>,
    siyah: u32,
    pub ekrandan: bool,
    pub son_hata: String,
    /// görünen çerçeve (sol, üst, gen, yük); imleç için
    pub dikdortgen: Option<(i32, i32, i32, i32)>,
}

impl PencereKaynagi {
    pub fn yeni(hwnd: isize, baslik: &str) -> Self {
        PencereKaynagi { hwnd, baslik: baslik.into(), son: None, siyah: 0, ekrandan: false, son_hata: String::new(), dikdortgen: None }
    }

    pub fn yontem(&self) -> &'static str {
        if self.ekrandan {
            "pencere (ekrandan)"
        } else {
            "pencere"
        }
    }

    fn ekrandan_al(c: &RECT) -> Option<KareRef> {
        let (w, h) = ((c.right - c.left) & !1, (c.bottom - c.top) & !1);
        if w < 2 || h < 2 {
            return None;
        }
        let veri = unsafe { dib_ile(w, h, |dc| BitBlt(dc, 0, 0, w, h, Some(GetDC(None)), c.left, c.top, SRCCOPY | CAPTUREBLT).is_ok()) }?;
        Some(Kare::yeni(w as u32, h as u32, veri).arc())
    }

    /// Kare ya da pencere kapandıysa None. Hata fırlatmaz.
    pub fn grab(&mut self) -> Option<KareRef> {
        let h = hwnd(self.hwnd);
        unsafe {
            if !IsWindow(Some(h)).as_bool() {
                if self.son_hata.is_empty() {
                    log::info!("Yakalanan pencere kapandı: {}", self.baslik);
                }
                self.son_hata = "Pencere kapandı".into();
                return None;
            }
            if IsIconic(h).as_bool() {
                return self.son.clone(); // küçültülmüş: son görüntü kalsın
            }
        }
        let (p, c) = dikdortgenler(h)?;
        self.dikdortgen = Some((c.left, c.top, c.right - c.left, c.bottom - c.top));
        let kare = if self.ekrandan {
            Self::ekrandan_al(&c)
        } else {
            let (w, hh) = (p.right - p.left, p.bottom - p.top);
            if w < 2 || hh < 2 {
                return self.son.clone();
            }
            let tam = unsafe { dib_ile(w, hh, |dc| PrintWindow(h, dc, PRINT_WINDOW_FLAGS(PW_RENDERFULLCONTENT)).as_bool()) };
            let kare = tam.map(|v| {
                let (x0, y0, x1, y1) = kirp_dikdortgeni((p.left, p.top, p.right, p.bottom), (c.left, c.top, c.right, c.bottom), w, hh);
                let (kw, kh) = ((x1 - x0) & !1, (y1 - y0) & !1);
                let mut veri = Vec::with_capacity((kw * kh * 4) as usize);
                for y in y0..y0 + kh {
                    let i = ((y * w + x0) * 4) as usize;
                    veri.extend_from_slice(&v[i..i + (kw * 4) as usize]);
                }
                Kare::yeni(kw as u32, kh as u32, veri)
            });
            match kare {
                Some(k) if !siyah_mi(&k) => {
                    self.siyah = 0;
                    Some(k.arc())
                }
                _ => {
                    self.siyah += 1;
                    if self.siyah >= SIYAH_ESIGI {
                        log::info!("Pencere doğrudan yakalanamadı, ekrandan yakalanıyor: {}", self.baslik);
                        self.ekrandan = true;
                        Self::ekrandan_al(&c)
                    } else {
                        return self.son.clone();
                    }
                }
            }
        };
        if let Some(k) = &kare {
            self.son_hata.clear();
            self.son = Some(k.clone());
        }
        kare.or_else(|| self.son.clone())
    }

    pub fn imlec(&self) -> Option<(f32, f32)> {
        let (sol, ust, w, h) = self.dikdortgen?;
        let (x, y) = crate::win::fare_konumu()?;
        let (x, y) = (x - sol, y - ust);
        (x >= 0 && y >= 0 && x < w && y < h).then_some((x as f32, y as f32))
    }
}

/// Seçilebilecek açık pencereler (RizeOn'un kendi pencereleri, araç pencereleri ve gizliler hariç).
pub fn pencereler() -> Vec<PencereBilgisi> {
    let mut liste: Vec<PencereBilgisi> = Vec::new();
    unsafe extern "system" fn her_biri(h: HWND, l: LPARAM) -> BOOL {
        let liste = &mut *(l.0 as *mut Vec<PencereBilgisi>);
        if !IsWindowVisible(h).as_bool() || GetWindow(h, GW_OWNER).is_ok_and(|o| !o.is_invalid()) {
            return true.into();
        }
        if GetWindowLongW(h, GWL_EXSTYLE) as u32 & WS_EX_TOOLWINDOW.0 != 0 {
            return true.into();
        }
        let mut gizli = 0u32;
        if DwmGetWindowAttribute(h, DWMWA_CLOAKED, &mut gizli as *mut _ as *mut _, 4).is_ok() && gizli != 0 {
            return true.into();
        }
        let n = GetWindowTextLengthW(h);
        if n == 0 {
            return true.into();
        }
        let mut t = vec![0u16; n as usize + 1];
        let n = GetWindowTextW(h, &mut t);
        let baslik = String::from_utf16_lossy(&t[..n as usize]);
        let mut r = RECT::default();
        let _ = GetWindowRect(h, &mut r);
        if (r.right - r.left < KUCUK || r.bottom - r.top < KUCUK) && !IsIconic(h).as_bool() {
            return true.into();
        }
        let mut pid = 0u32;
        GetWindowThreadProcessId(h, Some(&mut pid));
        if pid == std::process::id() {
            return true.into();
        }
        let mut sinif = [0u16; 256];
        let n = GetClassNameW(h, &mut sinif);
        let sinif = String::from_utf16_lossy(&sinif[..n.max(0) as usize]);
        if matches!(sinif.as_str(), "Progman" | "Shell_TrayWnd" | "WorkerW") {
            return true.into();
        }
        liste.push(PencereBilgisi { hwnd: h.0 as isize, baslik, program: String::new(), pid });
        true.into()
    }
    unsafe {
        let _ = EnumWindows(Some(her_biri), LPARAM(&mut liste as *mut _ as isize));
    }
    let tablo = crate::ses::surec_sesi::surec_tablosu();
    for p in &mut liste {
        p.program = tablo.get(&p.pid).map(|(_, ad)| ad.clone()).unwrap_or_default();
    }
    liste
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn kirpma() {
        // Win10/11 görünmez kenarlık: 8 px sol/sağ/alt
        assert_eq!(kirp_dikdortgeni((0, 0, 816, 608), (8, 0, 808, 600), 816, 608), (8, 0, 808, 600));
        assert_eq!(kirp_dikdortgeni((0, 0, 100, 100), (500, 500, 600, 600), 100, 100), (0, 0, 100, 100));
    }
}
