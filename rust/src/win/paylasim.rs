//! Toplantı modu: kalem çizimleri, yazılar ve bölge vurgusu ekranın üstünde, ekran yakalamaya
//! GİREN ayrı bir katmanda da çizilir. Zoom/Meet/Teams'te "Tüm ekran" paylaşılınca karşı taraf
//! bunları görür.
//!
//! Kalem/bölge katmanının kendisi (egui, saydam OpenGL penceresi) yakalamaya kapalı kalır: hem
//! kalem barı ve tutamaklar karşı tarafa gitmez, hem de saydam OpenGL pencereleri bazı ekran
//! yakalama yöntemlerinde (tarayıcıdaki Zoom) simsiyah görünür. Bu katman ise klasik "layered"
//! Win32 penceresidir (UpdateLayeredWindow, piksel başına alfa): her yakalama yönteminde doğru
//! görünür, tıklamaları alttaki pencerelere geçirir, odak almaz.
//!
//! Kendi iş parçacığında çalışır; sadece çizim ya da bölge değişince yeniden çizer (lazer
//! sönerken saniyede ~30 kez).

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use windows::core::{w, HSTRING, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, SIZE, WPARAM};
use windows::Win32::Graphics::Gdi::{
    CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, GetDC, ReleaseDC, SelectObject, AC_SRC_ALPHA, AC_SRC_OVER, BITMAPINFO,
    BITMAPINFOHEADER, BI_RGB, BLENDFUNCTION, DIB_RGB_COLORS, HBITMAP, HDC, HGDIOBJ,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::*;

use crate::bolge::VURGULA;
use crate::durum::DurumDeposu;
use crate::hat::HatKontrol;
use crate::kare::Kare;

pub const BASLIK: &str = "RizeOn paylaşım katmanı";
const SINIF: PCWSTR = w!("RizeOnPaylasimKatmani");
/// Vurgulanan bölgenin dışı ne kadar kararır (0-255); kalem katmanındaki karartmayla aynı
const KARARTMA_ALFA: u8 = 140;

/// Çalışan katman; düşürülünce (ya da `durdur`) pencere kapanır.
pub struct PaylasimKatmani {
    dur: Arc<AtomicBool>,
}

impl PaylasimKatmani {
    pub fn baslat(k: Arc<HatKontrol>, depo: DurumDeposu) -> PaylasimKatmani {
        let dur = Arc::new(AtomicBool::new(false));
        let d2 = dur.clone();
        let _ = std::thread::Builder::new().name("paylasim-katmani".into()).spawn(move || {
            if let Err(e) = calistir(&k, &depo, &d2) {
                log::warn!("Paylaşım katmanı açılamadı: {e}");
            }
        });
        PaylasimKatmani { dur }
    }
}

impl Drop for PaylasimKatmani {
    fn drop(&mut self) {
        self.dur.store(true, Ordering::SeqCst);
    }
}

unsafe extern "system" fn yordam(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    match msg {
        // her yerden tıklama geçsin
        WM_NCHITTEST => LRESULT(HTTRANSPARENT as isize),
        WM_MOUSEACTIVATE => LRESULT(MA_NOACTIVATE as isize),
        _ => DefWindowProcW(hwnd, msg, wp, lp),
    }
}

/// Ekranda ne çizilecek: (monitör, çizimler var mı, vurgu bölgesi)
#[derive(Clone, PartialEq)]
struct Imza {
    monitor: (i32, i32, u32, u32),
    cizim_surumu: u64,
    vurgu: Option<[i64; 4]>,
}

/// Çizim yüzeyi (monitör boyutunda DIB)
struct Yuzey {
    dc: HDC,
    bmp: HBITMAP,
    eski: HGDIOBJ,
    bitler: *mut u8,
    w: u32,
    h: u32,
}

impl Yuzey {
    fn yeni(w: u32, h: u32) -> Option<Yuzey> {
        unsafe {
            let ekran = GetDC(None);
            let dc = CreateCompatibleDC(Some(ekran));
            ReleaseDC(None, ekran);
            let bmi = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: w as i32,
                    biHeight: -(h as i32),
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };
            let mut bitler: *mut core::ffi::c_void = std::ptr::null_mut();
            let bmp = CreateDIBSection(Some(dc), &bmi, DIB_RGB_COLORS, &mut bitler, None, 0).ok()?;
            if bitler.is_null() {
                let _ = DeleteDC(dc);
                return None;
            }
            let eski = SelectObject(dc, bmp.into());
            Some(Yuzey { dc, bmp, eski, bitler: bitler as *mut u8, w, h })
        }
    }
}

impl Drop for Yuzey {
    fn drop(&mut self) {
        unsafe {
            SelectObject(self.dc, self.eski);
            let _ = DeleteObject(self.bmp.into());
            let _ = DeleteDC(self.dc);
        }
    }
}

/// Vurgunun dışını karartır, çizimleri üstüne çizer. Sonuç: önceden çarpılmış alfalı BGRA.
pub fn katmani_ciz(w: u32, h: u32, k: &HatKontrol, vurgu: Option<[f64; 4]>) -> Kare {
    let mut kare = Kare::yeni(w, h, vec![0u8; (w * h * 4) as usize]);
    if let Some([bx, by, bw, bh]) = vurgu {
        let x0 = ((bx * w as f64).round() as i64).clamp(0, w as i64) as u32;
        let y0 = ((by * h as f64).round() as i64).clamp(0, h as i64) as u32;
        let x1 = (((bx + bw) * w as f64).round() as i64).clamp(0, w as i64) as u32;
        let y1 = (((by + bh) * h as f64).round() as i64).clamp(0, h as i64) as u32;
        for y in 0..h {
            let satir = &mut kare.veri[(y * w * 4) as usize..((y + 1) * w * 4) as usize];
            for x in 0..w {
                if y >= y0 && y < y1 && x >= x0 && x < x1 {
                    continue;
                }
                satir[(x * 4 + 3) as usize] = KARARTMA_ALFA;
            }
        }
    }
    let (sekiller, lazer, lazer_rengi) = k.cizim.anlik();
    if !sekiller.is_empty() || !lazer.is_empty() {
        let (fw, fh) = (w as f32, h as f32);
        crate::cizim::ciz(&mut kare, &sekiller, &lazer, lazer_rengi, |x, y| (x * fw, y * fh), fh);
    }
    kare
}

fn calistir(k: &HatKontrol, depo: &DurumDeposu, dur: &AtomicBool) -> Result<(), String> {
    unsafe {
        let ornek = GetModuleHandleW(None).map_err(|e| e.to_string())?;
        let sinif = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            lpfnWndProc: Some(yordam),
            hInstance: ornek.into(),
            lpszClassName: SINIF,
            ..Default::default()
        };
        RegisterClassExW(&sinif);
        let hwnd = CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            SINIF,
            &HSTRING::from(BASLIK),
            WS_POPUP,
            0,
            0,
            1,
            1,
            None,
            None,
            Some(ornek.into()),
            None,
        )
        .map_err(|e| e.to_string())?;

        let mut son: Option<Imza> = None;
        let mut gorunur = false;
        let mut yuzey: Option<Yuzey> = None;
        while !dur.load(Ordering::SeqCst) {
            let mut m = MSG::default();
            while PeekMessageW(&mut m, None, 0, 0, PM_REMOVE).as_bool() {
                let _ = TranslateMessage(&m);
                DispatchMessageW(&m);
            }
            let imza = durum_imzasi(k, depo);
            match imza {
                None => {
                    if gorunur {
                        let _ = ShowWindow(hwnd, SW_HIDE);
                        gorunur = false;
                    }
                    son = None;
                }
                Some(i) if son.as_ref() != Some(&i) || k.cizim.lazer_var() => {
                    let (sol, ust, w, h) = i.monitor;
                    if yuzey.as_ref().is_none_or(|y| (y.w, y.h) != (w, h)) {
                        yuzey = Yuzey::yeni(w, h);
                    }
                    if let Some(y) = &yuzey {
                        let vurgu = i.vurgu.and(k.bolge.bolge());
                        let kare = katmani_ciz(w, h, k, vurgu);
                        std::ptr::copy_nonoverlapping(kare.veri.as_ptr(), y.bitler, kare.veri.len());
                        let hedef = POINT { x: sol, y: ust };
                        let boyut = SIZE { cx: w as i32, cy: h as i32 };
                        let kaynak = POINT { x: 0, y: 0 };
                        let karisim = BLENDFUNCTION { BlendOp: AC_SRC_OVER as u8, BlendFlags: 0, SourceConstantAlpha: 255, AlphaFormat: AC_SRC_ALPHA as u8 };
                        let ekran = GetDC(None);
                        let _ = UpdateLayeredWindow(hwnd, Some(ekran), Some(&hedef), Some(&boyut), Some(y.dc), Some(&kaynak), Default::default(), Some(&karisim), ULW_ALPHA);
                        ReleaseDC(None, ekran);
                        if !gorunur {
                            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
                            gorunur = true;
                        }
                        // kalem katmanı açılınca da en üstte kalsın (o yakalamaya girmediği için
                        // ekranda ikisinin sırası fark etmez)
                        let _ = SetWindowPos(hwnd, Some(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
                    }
                    son = Some(i);
                }
                _ => {}
            }
            std::thread::sleep(Duration::from_millis(33));
        }
        drop(yuzey);
        let _ = DestroyWindow(hwnd);
    }
    Ok(())
}

/// Katmanın şu an göstermesi gereken şeyin özeti; None: gösterilecek bir şey yok.
fn durum_imzasi(k: &HatKontrol, depo: &DurumDeposu) -> Option<Imza> {
    if depo.al().kaynak_turu == "pencere" {
        return None; // tek pencere gösterilirken kalem ve bölge kapalı
    }
    let vurgu = (k.bolge.mod_() == Some(VURGULA)).then(|| k.bolge.bolge()).flatten();
    let cizim_var = !k.cizim.bos();
    if vurgu.is_none() && !cizim_var {
        return None;
    }
    let sira = k.ayar.lock().map(|a| a.monitor).unwrap_or(0);
    let mon = crate::yakalama::monitorler();
    let m = mon.get(sira).or(mon.first())?;
    Some(Imza {
        monitor: (m.sol, m.ust, m.w, m.h),
        cizim_surumu: k.cizim.surum(),
        vurgu: vurgu.map(|v| v.map(|x| (x * 10000.0).round() as i64)),
    })
}
