//! DXGI Masaüstü Çoğaltma ile ekran yakalama (dxcam'in yaptığı iş, aracısız).

use windows::core::Interface;
use windows::Win32::Graphics::Direct3D::D3D_DRIVER_TYPE_UNKNOWN;
use windows::Win32::Graphics::Direct3D11::{
    D3D11CreateDevice, ID3D11Device, ID3D11DeviceContext, ID3D11Texture2D, D3D11_CPU_ACCESS_READ, D3D11_CREATE_DEVICE_BGRA_SUPPORT,
    D3D11_MAPPED_SUBRESOURCE, D3D11_MAP_READ, D3D11_SDK_VERSION, D3D11_TEXTURE2D_DESC, D3D11_USAGE_STAGING,
};
use windows::Win32::Graphics::Dxgi::{
    CreateDXGIFactory1, IDXGIAdapter1, IDXGIFactory1, IDXGIOutput, IDXGIOutput1, IDXGIOutputDuplication, IDXGIResource, DXGI_ERROR_NOT_FOUND,
    DXGI_ERROR_WAIT_TIMEOUT, DXGI_OUTDUPL_FRAME_INFO,
};

use super::ekran::Yakalayici;
use super::Monitor;
use crate::kare::{Kare, KareRef};

fn ciktilar() -> Vec<(IDXGIAdapter1, IDXGIOutput, Monitor)> {
    let mut l = vec![];
    unsafe {
        let Ok(fabrika) = CreateDXGIFactory1::<IDXGIFactory1>() else { return l };
        let mut a = 0;
        loop {
            let adaptor = match fabrika.EnumAdapters1(a) {
                Ok(x) => x,
                Err(e) if e.code() == DXGI_ERROR_NOT_FOUND => break,
                Err(_) => break,
            };
            let mut o = 0;
            while let Ok(cikti) = adaptor.EnumOutputs(o) {
                if let Ok(d) = cikti.GetDesc() {
                    if d.AttachedToDesktop.as_bool() {
                        let r = d.DesktopCoordinates;
                        let ad = String::from_utf16_lossy(&d.DeviceName).trim_end_matches('\0').to_string();
                        let m = Monitor { ad, sol: r.left, ust: r.top, w: (r.right - r.left) as u32, h: (r.bottom - r.top) as u32 };
                        l.push((adaptor.clone(), cikti, m));
                    }
                }
                o += 1;
            }
            a += 1;
        }
    }
    // Ana monitör (0,0) önce: Python/mss sırasıyla uyumlu ("monitör 0" = ana ekran)
    l.sort_by_key(|(_, _, m)| !(m.sol == 0 && m.ust == 0));
    l
}

pub fn monitorler() -> Vec<Monitor> {
    ciktilar().into_iter().map(|(_, _, m)| m).collect()
}

pub struct DxgiYakalayici {
    _cihaz: ID3D11Device,
    baglam: ID3D11DeviceContext,
    cogaltma: IDXGIOutputDuplication,
    hazirlik: Option<ID3D11Texture2D>,
    son: Option<KareRef>,
    w: u32,
    h: u32,
}

unsafe impl Send for DxgiYakalayici {}

impl DxgiYakalayici {
    pub fn yeni(monitor: usize) -> Result<Self, String> {
        let l = ciktilar();
        let (adaptor, cikti, m) = l.get(monitor).or_else(|| l.first()).ok_or("monitör bulunamadı")?.clone();
        unsafe {
            let mut cihaz = None;
            let mut baglam = None;
            D3D11CreateDevice(
                &adaptor,
                D3D_DRIVER_TYPE_UNKNOWN,
                Default::default(),
                D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                None,
                D3D11_SDK_VERSION,
                Some(&mut cihaz),
                None,
                Some(&mut baglam),
            )
            .map_err(|e| format!("D3D11 cihazı açılamadı: {e}"))?;
            let cihaz: ID3D11Device = cihaz.ok_or("D3D11 cihazı yok")?;
            let baglam = baglam.ok_or("D3D11 bağlamı yok")?;
            let c1: IDXGIOutput1 = cikti.cast().map_err(|e| e.to_string())?;
            let cogaltma = c1.DuplicateOutput(&cihaz).map_err(|e| format!("Masaüstü çoğaltma açılamadı: {e}"))?;
            Ok(DxgiYakalayici { _cihaz: cihaz, baglam, cogaltma, hazirlik: None, son: None, w: m.w, h: m.h })
        }
    }
}

impl Yakalayici for DxgiYakalayici {
    fn ad(&self) -> &'static str {
        "dxgi"
    }

    fn yakala(&mut self) -> Result<Option<KareRef>, String> {
        unsafe {
            let mut bilgi = DXGI_OUTDUPL_FRAME_INFO::default();
            let mut kaynak: Option<IDXGIResource> = None;
            match self.cogaltma.AcquireNextFrame(0, &mut bilgi, &mut kaynak) {
                Ok(()) => {}
                Err(e) if e.code() == DXGI_ERROR_WAIT_TIMEOUT => return Ok(self.son.clone()),
                Err(e) => return Err(e.to_string()),
            }
            let sonuc = (|| -> Result<(), String> {
                if bilgi.LastPresentTime == 0 && self.son.is_some() {
                    return Ok(()); // sadece fare hareket etti: görüntü aynı
                }
                let doku: ID3D11Texture2D = kaynak.as_ref().ok_or("kare yok")?.cast().map_err(|e| e.to_string())?;
                if self.hazirlik.is_none() {
                    let mut d = D3D11_TEXTURE2D_DESC::default();
                    doku.GetDesc(&mut d);
                    d.Usage = D3D11_USAGE_STAGING;
                    d.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
                    d.BindFlags = 0;
                    d.MiscFlags = 0;
                    d.MipLevels = 1;
                    d.ArraySize = 1;
                    let mut t = None;
                    self._cihaz.CreateTexture2D(&d, None, Some(&mut t)).map_err(|e| e.to_string())?;
                    self.hazirlik = t;
                    self.w = d.Width;
                    self.h = d.Height;
                }
                let hazirlik = self.hazirlik.as_ref().unwrap();
                self.baglam.CopyResource(hazirlik, &doku);
                let mut harita = D3D11_MAPPED_SUBRESOURCE::default();
                self.baglam.Map(hazirlik, 0, D3D11_MAP_READ, 0, Some(&mut harita)).map_err(|e| e.to_string())?;
                let (w, h) = (self.w as usize, self.h as usize);
                let mut veri = vec![0u8; w * h * 4];
                let kaynak = std::slice::from_raw_parts(harita.pData as *const u8, harita.RowPitch as usize * h);
                for y in 0..h {
                    let s = y * harita.RowPitch as usize;
                    veri[y * w * 4..(y + 1) * w * 4].copy_from_slice(&kaynak[s..s + w * 4]);
                }
                self.baglam.Unmap(hazirlik, 0);
                // DXGI alfa kanalını 0 bırakabilir; kareler opak olmalı (tiny-skia ve önizleme için)
                for p in veri.chunks_exact_mut(4) {
                    p[3] = 255;
                }
                self.son = Some(Kare::yeni(self.w, self.h, veri).arc());
                Ok(())
            })();
            let _ = self.cogaltma.ReleaseFrame();
            sonuc?;
            Ok(self.son.clone())
        }
    }
}
