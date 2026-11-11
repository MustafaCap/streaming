//! Toplantı penceresi: RizeOn'un çıkışını (sanal kameraya giden görüntünün aynısını) çerçevesiz bir
//! pencerede gösterir. Zoom, Meet, Teams gibi uygulamalarda bu pencere "Ekran paylaş > Pencere" ile
//! paylaşılır. Toplantı uygulamaları kameraya düşük çözünürlük ve bant ayırır (yüz için), ekran
//! paylaşımına ise yüksek çözünürlük ve keskinlik ayırır; ekran bölgesi, kalem ve yazı bu yüzden
//! paylaşımda çok daha net görünür.
//!
//! Kendi iş parçacığında, düz Win32 penceresidir (egui değil): ana pencere tepsideyken de çalışır,
//! arayüzü her karede yeniden çizdirmez. Pencere boyutu = paylaşılan görüntünün boyutu (fiziksel
//! piksel). Kare değişmediyse yeniden çizilmez.
//!
//!   sürükle: taşı · kenarlar: boyutlandır (oran korunur) · çift tık: 1280×720 ↔ 1920×1080
//!   sağ tık: boyut seç, kapat
//!
//! Bilerek ekran yakalamadan GİZLENMEZ (diğer RizeOn pencerelerinin tersine): gizlenirse toplantı
//! uygulaması da onu siyah görür. Yakalanan ekranın üstünde görünür durursa görüntü kendi içine
//! yansır; bu yüzden birden fazla monitör varsa yakalanmayan monitörde açılır.

use std::cell::RefCell;
use std::sync::atomic::{AtomicIsize, Ordering};
use std::sync::Arc;

use windows::core::{w, HSTRING, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, RECT, WPARAM};
use windows::Win32::Graphics::Gdi::{
    BeginPaint, EndPaint, FillRect, GetStockObject, InvalidateRect, ScreenToClient, SetDIBitsToDevice, BITMAPINFO, BITMAPINFOHEADER, BI_RGB,
    BLACK_BRUSH, DIB_RGB_COLORS, HBRUSH, PAINTSTRUCT,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::WindowsAndMessaging::*;

use crate::hat::HatKontrol;
use crate::kare::{self, KareRef};

pub const BASLIK: &str = "RizeOn Toplantı";
const SINIF: PCWSTR = w!("RizeOnToplantiPenceresi");
const KENAR: i32 = 8;
const ZAMANLAYICI: usize = 1;
const MENU_720: usize = 1;
const MENU_1080: usize = 2;
const MENU_KAPAT: usize = 3;

/// Açık toplantı penceresinin tutamağı. `kapat()` ya da kullanıcı kapatınca iş parçacığı biter.
pub struct ToplantiPenceresi {
    hwnd: Arc<AtomicIsize>,
}

impl ToplantiPenceresi {
    /// Pencereyi açar. `kapaninca`: pencere kapandığında (hangi yoldan olursa olsun) bir kez çağrılır.
    pub fn ac(k: Arc<HatKontrol>, kapaninca: Box<dyn FnOnce() + Send>) -> ToplantiPenceresi {
        let hwnd = Arc::new(AtomicIsize::new(0));
        let h2 = hwnd.clone();
        let _ = std::thread::Builder::new().name("toplanti-penceresi".into()).spawn(move || {
            if let Err(e) = calistir(k, &h2) {
                log::warn!("Toplantı penceresi açılamadı: {e}");
            }
            h2.store(0, Ordering::SeqCst);
            kapaninca();
        });
        ToplantiPenceresi { hwnd }
    }

    pub fn kapat(&self) {
        let h = self.hwnd.load(Ordering::SeqCst);
        if h != 0 {
            unsafe {
                let _ = PostMessageW(Some(HWND(h as _)), WM_CLOSE, WPARAM(0), LPARAM(0));
            }
        }
    }

    /// Pencereyi öne getirir (zaten açıkken düğmeye yeniden basılırsa değil; tepsiden "göster" için).
    pub fn one_getir(&self) {
        let h = self.hwnd.load(Ordering::SeqCst);
        if h != 0 {
            unsafe {
                let _ = SetForegroundWindow(HWND(h as _));
            }
        }
    }
}

/// Pencere iş parçacığının durumu (pencere yordamı aynı iş parçacığında çalışır).
struct Ic {
    k: Arc<HatKontrol>,
    /// Son çizilen kaynak kare (değişmediyse yeniden çizilmez)
    son: Option<KareRef>,
    /// Pencere boyutuna sığdırılmış hali
    olcekli: Option<KareRef>,
}

thread_local! {
    static IC: RefCell<Option<Ic>> = const { RefCell::new(None) };
}

/// Çıkış oranı (genişlik / yükseklik)
fn oran(k: &HatKontrol) -> f64 {
    k.genislik.max(1) as f64 / k.yukseklik.max(1) as f64
}

/// Başlangıç yeri: yakalanmayan bir monitör varsa onun ortası (görüntü kendi içine yansımasın),
/// yoksa ana ekranın çalışma alanının ortası.
fn baslangic_yeri(k: &HatKontrol, w: i32, h: i32) -> (i32, i32) {
    let yakalanan = k.ayar.lock().map(|a| a.monitor).unwrap_or(0);
    let mon = crate::yakalama::monitorler();
    if mon.len() > 1 {
        if let Some((_, m)) = mon.iter().enumerate().find(|(i, _)| *i != yakalanan) {
            return (m.sol + (m.w as i32 - w).max(0) / 2, m.ust + (m.h as i32 - h).max(0) / 2);
        }
    }
    match super::calisma_alani() {
        Some((l, t, r, b)) => (l + ((r - l) - w).max(0) / 2, t + ((b - t) - h).max(0) / 2),
        None => (100, 100),
    }
}

fn calistir(k: Arc<HatKontrol>, hwnd_yeri: &AtomicIsize) -> Result<(), String> {
    unsafe {
        let ornek = GetModuleHandleW(None).map_err(|e| e.to_string())?;
        // exe'ye gömülü uygulama simgesi (winresource ilk simge kaynağı)
        let simge = LoadIconW(Some(ornek.into()), PCWSTR(1 as _)).unwrap_or_default();
        let sinif = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            style: CS_DBLCLKS,
            lpfnWndProc: Some(yordam),
            hInstance: ornek.into(),
            hIcon: simge,
            hIconSm: simge,
            hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
            hbrBackground: HBRUSH(GetStockObject(BLACK_BRUSH).0),
            lpszClassName: SINIF,
            ..Default::default()
        };
        // ikinci açılışta sınıf zaten kayıtlı olabilir; hata önemli değil
        RegisterClassExW(&sinif);

        let h = 720;
        let w = (h as f64 * oran(&k)).round() as i32;
        let (x, y) = baslangic_yeri(&k, w, h);
        let fps = k.fps.clamp(5, 60);
        IC.with(|ic| *ic.borrow_mut() = Some(Ic { k, son: None, olcekli: None }));
        let hwnd = CreateWindowExW(
            WS_EX_APPWINDOW,
            SINIF,
            &HSTRING::from(BASLIK),
            WS_POPUP | WS_VISIBLE,
            x,
            y,
            w,
            h,
            None,
            None,
            Some(ornek.into()),
            None,
        )
        .map_err(|e| e.to_string())?;
        hwnd_yeri.store(hwnd.0 as isize, Ordering::SeqCst);
        super::koseleri_yuvarla(hwnd.0 as isize);
        SetTimer(Some(hwnd), ZAMANLAYICI, 1000 / fps, None);
        let mut m = MSG::default();
        while GetMessageW(&mut m, None, 0, 0).as_bool() {
            let _ = TranslateMessage(&m);
            DispatchMessageW(&m);
        }
        IC.with(|ic| *ic.borrow_mut() = None);
    }
    Ok(())
}

/// İstemci alanı boyutu
fn istemci(hwnd: HWND) -> (i32, i32) {
    let mut r = RECT::default();
    unsafe {
        let _ = GetClientRect(hwnd, &mut r);
    }
    (r.right - r.left, r.bottom - r.top)
}

/// Pencereyi oranı koruyarak verilen yüksekliğe getirir (ortası yerinde kalır).
fn boyutlandir(hwnd: HWND, yukseklik: i32) {
    let o = IC.with(|ic| ic.borrow().as_ref().map(|i| oran(&i.k))).unwrap_or(16.0 / 9.0);
    let (h, w) = (yukseklik, (yukseklik as f64 * o).round() as i32);
    let mut r = RECT::default();
    unsafe {
        let _ = GetWindowRect(hwnd, &mut r);
        let (cx, cy) = ((r.left + r.right) / 2, (r.top + r.bottom) / 2);
        let _ = SetWindowPos(hwnd, None, cx - w / 2, cy - h / 2, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
    }
}

fn menu_goster(hwnd: HWND, x: i32, y: i32) {
    unsafe {
        let Ok(menu) = CreatePopupMenu() else { return };
        let (_, h) = istemci(hwnd);
        let isaret = |n: i32| if h == n { MF_CHECKED } else { MF_UNCHECKED };
        let _ = AppendMenuW(menu, MF_STRING | isaret(720), MENU_720, w!("1280 × 720"));
        let _ = AppendMenuW(menu, MF_STRING | isaret(1080), MENU_1080, w!("1920 × 1080"));
        let _ = AppendMenuW(menu, MF_SEPARATOR, 0, PCWSTR::null());
        let _ = AppendMenuW(menu, MF_STRING, MENU_KAPAT, w!("Toplantı penceresini kapat"));
        let _ = SetForegroundWindow(hwnd);
        let secim = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, x, y, Some(0), hwnd, None);
        let _ = DestroyMenu(menu);
        match secim.0 as usize {
            MENU_720 => boyutlandir(hwnd, 720),
            MENU_1080 => boyutlandir(hwnd, 1080),
            MENU_KAPAT => {
                let _ = PostMessageW(Some(hwnd), WM_CLOSE, WPARAM(0), LPARAM(0));
            }
            _ => {}
        }
    }
}

/// Zamanlayıcı: hattın yeni bir karesi varsa yeniden çizdir.
fn yeni_kare_var() -> bool {
    IC.with(|ic| {
        let b = ic.borrow();
        let Some(i) = b.as_ref() else { return false };
        let kare = i.k.son_kare();
        i.son.as_ref().is_none_or(|s| !Arc::ptr_eq(s, &kare))
    })
}

fn ciz(hwnd: HWND) {
    unsafe {
        let mut ps = PAINTSTRUCT::default();
        let hdc = BeginPaint(hwnd, &mut ps);
        let (w, h) = istemci(hwnd);
        let kare = IC.with(|ic| {
            let mut b = ic.borrow_mut();
            let i = b.as_mut()?;
            let kaynak = i.k.son_kare();
            let ayni_kaynak = i.son.as_ref().is_some_and(|s| Arc::ptr_eq(s, &kaynak));
            let ayni_boyut = i.olcekli.as_ref().is_some_and(|o| o.boyut() == (w as u32, h as u32));
            if !(ayni_kaynak && ayni_boyut) {
                let olcekli = if kaynak.boyut() == (w as u32, h as u32) || w <= 0 || h <= 0 {
                    kaynak.clone()
                } else {
                    kare::sigdir(&kaynak, w as u32, h as u32).arc()
                };
                i.olcekli = Some(olcekli);
                i.son = Some(kaynak);
            }
            i.olcekli.clone()
        });
        match kare {
            Some(k) if k.w > 0 && k.h > 0 => {
                let bmi = BITMAPINFO {
                    bmiHeader: BITMAPINFOHEADER {
                        biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                        biWidth: k.w as i32,
                        biHeight: -(k.h as i32), // yukarıdan aşağı
                        biPlanes: 1,
                        biBitCount: 32,
                        biCompression: BI_RGB.0,
                        ..Default::default()
                    },
                    ..Default::default()
                };
                // kare pencereden küçükse (boyutlandırma sırasında) geri kalanı siyah
                let (kw, kh) = (k.w as i32, k.h as i32);
                if kw < w || kh < h {
                    let siyah = HBRUSH(GetStockObject(BLACK_BRUSH).0);
                    FillRect(hdc, &RECT { left: kw, top: 0, right: w, bottom: h }, siyah);
                    FillRect(hdc, &RECT { left: 0, top: kh, right: kw, bottom: h }, siyah);
                }
                SetDIBitsToDevice(hdc, 0, 0, k.w, k.h, 0, 0, 0, k.h, k.veri.as_ptr() as *const _, &bmi, DIB_RGB_COLORS);
            }
            _ => {
                FillRect(hdc, &ps.rcPaint, HBRUSH(GetStockObject(BLACK_BRUSH).0));
            }
        }
        let _ = EndPaint(hwnd, &ps);
    }
}

/// Fare nerede: kenar (boyutlandır) ya da gövde (sürükle).
fn isabet(hwnd: HWND, lp: LPARAM) -> u32 {
    let mut p = POINT { x: (lp.0 & 0xFFFF) as i16 as i32, y: ((lp.0 >> 16) & 0xFFFF) as i16 as i32 };
    unsafe {
        let _ = ScreenToClient(hwnd, &mut p);
    }
    let (w, h) = istemci(hwnd);
    let (sol, sag, ust, alt) = (p.x < KENAR, p.x >= w - KENAR, p.y < KENAR, p.y >= h - KENAR);
    match (sol, sag, ust, alt) {
        (true, _, true, _) => HTTOPLEFT,
        (_, true, true, _) => HTTOPRIGHT,
        (true, _, _, true) => HTBOTTOMLEFT,
        (_, true, _, true) => HTBOTTOMRIGHT,
        (true, ..) => HTLEFT,
        (_, true, ..) => HTRIGHT,
        (_, _, true, _) => HTTOP,
        (.., true) => HTBOTTOM,
        _ => HTCAPTION,
    }
}

/// Boyutlandırırken oranı korur.
fn oran_koru(wp: WPARAM, lp: LPARAM) {
    let o = IC.with(|ic| ic.borrow().as_ref().map(|i| oran(&i.k))).unwrap_or(16.0 / 9.0);
    let r = unsafe { &mut *(lp.0 as *mut RECT) };
    let kenar = wp.0 as u32;
    let (w, h) = (r.right - r.left, r.bottom - r.top);
    let yatay = matches!(kenar, WMSZ_LEFT | WMSZ_RIGHT);
    if yatay {
        r.bottom = r.top + ((w as f64 / o).round() as i32).max(90);
    } else {
        let yeni_w = ((h as f64 * o).round() as i32).max(160);
        if matches!(kenar, WMSZ_LEFT | WMSZ_TOPLEFT | WMSZ_BOTTOMLEFT) {
            r.left = r.right - yeni_w;
        } else {
            r.right = r.left + yeni_w;
        }
        if matches!(kenar, WMSZ_TOP | WMSZ_BOTTOM) {
            r.bottom = r.top + ((r.right - r.left) as f64 / o).round() as i32;
        }
    }
}

unsafe extern "system" fn yordam(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    match msg {
        WM_TIMER => {
            if yeni_kare_var() {
                let _ = InvalidateRect(Some(hwnd), None, false);
            }
            LRESULT(0)
        }
        WM_PAINT => {
            ciz(hwnd);
            LRESULT(0)
        }
        WM_ERASEBKGND => LRESULT(1),
        WM_SIZE => {
            let _ = InvalidateRect(Some(hwnd), None, false);
            LRESULT(0)
        }
        WM_NCHITTEST => LRESULT(isabet(hwnd, lp) as isize),
        WM_SIZING => {
            oran_koru(wp, lp);
            LRESULT(1)
        }
        WM_NCLBUTTONDBLCLK if wp.0 as u32 == HTCAPTION => {
            let (_, h) = istemci(hwnd);
            boyutlandir(hwnd, if h >= 1080 { 720 } else { 1080 });
            LRESULT(0)
        }
        WM_NCRBUTTONUP | WM_CONTEXTMENU => {
            let mut p = POINT::default();
            let _ = GetCursorPos(&mut p);
            menu_goster(hwnd, p.x, p.y);
            LRESULT(0)
        }
        // Simge durumuna küçültülen pencereyi toplantı uygulaması boş (donmuş) görür; küçültülmesin
        WM_SYSCOMMAND if (wp.0 & 0xFFF0) as u32 == SC_MINIMIZE => LRESULT(0),
        WM_KEYDOWN if wp.0 as u16 == 0x1B => {
            // Esc: kapat
            let _ = PostMessageW(Some(hwnd), WM_CLOSE, WPARAM(0), LPARAM(0));
            LRESULT(0)
        }
        WM_DESTROY => {
            let _ = KillTimer(Some(hwnd), ZAMANLAYICI);
            PostQuitMessage(0);
            LRESULT(0)
        }
        _ => DefWindowProcW(hwnd, msg, wp, lp),
    }
}
