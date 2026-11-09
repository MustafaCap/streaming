//! GDI ile ekran yakalama (yavaş ama her yerde çalışır; DXGI açılamazsa yedek).

use windows::Win32::Graphics::Gdi::{
    BitBlt, CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, GetDC, ReleaseDC, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    CAPTUREBLT, DIB_RGB_COLORS, HBITMAP, HDC, SRCCOPY,
};

use super::ekran::Yakalayici;
use super::Monitor;
use crate::kare::{Kare, KareRef};

pub struct GdiYakalayici {
    m: Monitor,
}

impl GdiYakalayici {
    pub fn yeni(m: Monitor) -> Self {
        GdiYakalayici { m }
    }
}

impl Yakalayici for GdiYakalayici {
    fn ad(&self) -> &'static str {
        "gdi"
    }

    fn yakala(&mut self) -> Result<Option<KareRef>, String> {
        let (w, h) = (self.m.w as i32, self.m.h as i32);
        unsafe {
            let ekran = GetDC(None);
            if ekran.is_invalid() {
                return Err("GetDC başarısız".into());
            }
            let dc: HDC = CreateCompatibleDC(Some(ekran));
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
            let bmp: HBITMAP = CreateDIBSection(Some(dc), &bi, DIB_RGB_COLORS, &mut bitler, None, 0).map_err(|e| e.to_string())?;
            let eski = SelectObject(dc, bmp.into());
            let ok = BitBlt(dc, 0, 0, w, h, Some(ekran), self.m.sol, self.m.ust, SRCCOPY | CAPTUREBLT).is_ok();
            let mut veri = Vec::new();
            if ok {
                veri = std::slice::from_raw_parts(bitler as *const u8, (w * h * 4) as usize).to_vec();
                for p in veri.chunks_exact_mut(4) {
                    p[3] = 255;
                }
            }
            SelectObject(dc, eski);
            let _ = DeleteObject(bmp.into());
            let _ = DeleteDC(dc);
            ReleaseDC(None, ekran);
            if !ok {
                return Err("BitBlt başarısız".into());
            }
            Ok(Some(Kare::yeni(w as u32, h as u32, veri).arc()))
        }
    }
}
