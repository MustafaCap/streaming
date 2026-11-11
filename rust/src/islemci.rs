//! İşlemci ölçümü: uygulamanın (ve FFmpeg alt süreçlerinin) harcadığı işlemciyi Görev Yöneticisi gibi
//! tüm çekirdeklere oranla ölçer. 30 sn'de bir log'a yazılır; Python sürümüyle karşılaştırma için.

use std::time::Instant;

#[derive(Default, Clone, Copy, Debug)]
pub struct Olcum {
    pub toplam: f64,
    pub uygulama: f64,
    pub ffmpeg: f64,
    /// ölçüm anında çalışan alt süreç (FFmpeg) sayısı
    pub alt_surec: usize,
}

pub struct IslemciOlcer {
    onceki: (f64, f64, usize),
    zaman: Instant,
    cekirdek: f64,
}

impl Default for IslemciOlcer {
    fn default() -> Self {
        Self::new()
    }
}

impl IslemciOlcer {
    pub fn new() -> Self {
        IslemciOlcer {
            onceki: sureler(),
            zaman: Instant::now(),
            cekirdek: std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1) as f64,
        }
    }

    /// Son çağrıdan bu yana yüzde.
    pub fn olc(&mut self) -> Olcum {
        let simdi = sureler();
        let gecen = self.zaman.elapsed().as_secs_f64().max(1e-3);
        let u = ((simdi.0 - self.onceki.0) / gecen / self.cekirdek * 100.0).max(0.0);
        let f = ((simdi.1 - self.onceki.1) / gecen / self.cekirdek * 100.0).max(0.0);
        self.onceki = simdi;
        self.zaman = Instant::now();
        Olcum { toplam: u + f, uygulama: u, ffmpeg: f, alt_surec: simdi.2 }
    }
}

/// (uygulamanın işlemci saniyesi, alt süreçlerin (FFmpeg) işlemci saniyesi, alt süreç sayısı)
#[cfg(windows)]
fn sureler() -> (f64, f64, usize) {
    use windows::Win32::Foundation::{CloseHandle, FILETIME};
    use windows::Win32::System::Diagnostics::ToolHelp::{CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS};
    use windows::Win32::System::Threading::{GetCurrentProcess, GetProcessTimes, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};
    fn sn(f: FILETIME) -> f64 {
        (((f.dwHighDateTime as u64) << 32) | f.dwLowDateTime as u64) as f64 / 1e7
    }
    unsafe fn surec_suresi(h: windows::Win32::Foundation::HANDLE) -> f64 {
        let (mut a, mut b, mut c, mut d) = Default::default();
        if GetProcessTimes(h, &mut a, &mut b, &mut c, &mut d).is_ok() {
            sn(c) + sn(d)
        } else {
            0.0
        }
    }
    unsafe {
        let kendi = surec_suresi(GetCurrentProcess());
        let mut cocuk = 0.0;
        let mut sayi = 0;
        let pid = std::process::id();
        if let Ok(anlik) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) {
            let mut g = PROCESSENTRY32W { dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32, ..Default::default() };
            let mut ok = Process32FirstW(anlik, &mut g).is_ok();
            while ok {
                if g.th32ParentProcessID == pid {
                    if let Ok(h) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, g.th32ProcessID) {
                        cocuk += surec_suresi(h);
                        sayi += 1;
                        let _ = CloseHandle(h);
                    }
                }
                ok = Process32NextW(anlik, &mut g).is_ok();
            }
            let _ = CloseHandle(anlik);
        }
        (kendi, cocuk, sayi)
    }
}

#[cfg(not(windows))]
fn sureler() -> (f64, f64, usize) {
    // /proc/<pid>/stat: utime + stime (saat tıkı); alt süreçler ppid'den bulunur
    fn oku(yol: &std::path::Path) -> Option<(i64, f64)> {
        let s = std::fs::read_to_string(yol).ok()?;
        let a: Vec<&str> = s.rsplit(')').next()?.split_whitespace().collect();
        let t = |i: usize| a.get(i).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0);
        Some((a.get(1)?.parse().ok()?, (t(11) + t(12)) / 100.0))
    }
    let kendi = oku(std::path::Path::new("/proc/self/stat")).map(|x| x.1).unwrap_or(0.0);
    let pid = std::process::id() as i64;
    let (mut cocuk, mut sayi) = (0.0, 0);
    if let Ok(d) = std::fs::read_dir("/proc") {
        for g in d.flatten() {
            if let Some((ppid, t)) = oku(&g.path().join("stat")) {
                if ppid == pid {
                    cocuk += t;
                    sayi += 1;
                }
            }
        }
    }
    (kendi, cocuk, sayi)
}

/// Ekran kartı kullanımı: Windows performans sayaçlarından 3D motorlarının kullanımı (Görev
/// Yöneticisi'ndeki "GPU" sütunuyla aynı kaynak). Sayaç yoksa `oku` None döner, arayüz "GPU –" yazar.
pub struct GpuSayaci {
    #[cfg(windows)]
    sorgu: windows::Win32::System::Performance::PDH_HQUERY,
    #[cfg(windows)]
    sayac: windows::Win32::System::Performance::PDH_HCOUNTER,
}

// PDH tutamaçları iş parçacığına bağlı değildir
unsafe impl Send for GpuSayaci {}

impl GpuSayaci {
    #[cfg(windows)]
    pub fn new() -> Option<Self> {
        use windows::core::w;
        use windows::Win32::System::Performance::*;
        unsafe {
            let mut sorgu = PDH_HQUERY::default();
            if PdhOpenQueryW(windows::core::PCWSTR::null(), 0, &mut sorgu) != 0 {
                return None;
            }
            let mut sayac = PDH_HCOUNTER::default();
            if PdhAddEnglishCounterW(sorgu, w!("\\GPU Engine(*engtype_3D)\\Utilization Percentage"), 0, &mut sayac) != 0 {
                PdhCloseQuery(sorgu);
                return None;
            }
            PdhCollectQueryData(sorgu); // ilk örnek (oran için iki örnek gerekir)
            Some(GpuSayaci { sorgu, sayac })
        }
    }

    #[cfg(not(windows))]
    pub fn new() -> Option<Self> {
        None
    }

    /// Yüzde (aynı motoru kullanan işlemler toplanır; en yoğun motor, en çok %100).
    #[cfg(windows)]
    pub fn oku(&mut self) -> Option<f64> {
        use windows::Win32::System::Performance::*;
        unsafe {
            if PdhCollectQueryData(self.sorgu) != 0 {
                return None;
            }
            let (mut boyut, mut adet) = (0u32, 0u32);
            let kod = PdhGetFormattedCounterArrayW(self.sayac, PDH_FMT_DOUBLE, &mut boyut, &mut adet, None);
            if kod != PDH_MORE_DATA || boyut == 0 {
                return None;
            }
            // 8 bayt hizalı tampon
            let mut tampon = vec![0u64; (boyut as usize).div_ceil(8)];
            let p = tampon.as_mut_ptr() as *mut PDH_FMT_COUNTERVALUE_ITEM_W;
            if PdhGetFormattedCounterArrayW(self.sayac, PDH_FMT_DOUBLE, &mut boyut, &mut adet, Some(p)) != 0 {
                return None;
            }
            let mut motorlar: std::collections::HashMap<String, f64> = std::collections::HashMap::new();
            for i in 0..adet as usize {
                let o = &*p.add(i);
                if o.FmtValue.CStatus != 0 {
                    continue;
                }
                let ad = o.szName.to_string().unwrap_or_default();
                let motor = ad.find("luid_").map(|n| ad[n..].to_string()).unwrap_or(ad);
                *motorlar.entry(motor).or_default() += o.FmtValue.Anonymous.doubleValue;
            }
            Some(motorlar.values().cloned().fold(0.0, f64::max).min(100.0))
        }
    }

    #[cfg(not(windows))]
    pub fn oku(&mut self) -> Option<f64> {
        None
    }
}

impl Drop for GpuSayaci {
    fn drop(&mut self) {
        #[cfg(windows)]
        unsafe {
            windows::Win32::System::Performance::PdhCloseQuery(self.sorgu);
        }
    }
}

/// Alt satırdaki "CPU %x · GPU %y · n FPS" (Python core/sistem_olcer.py).
pub fn alt_bilgi_metni(cpu: Option<f64>, gpu: Option<f64>, fps: f32) -> String {
    let c = cpu.map(|c| format!("CPU {}", crate::dil::yuzde(format!("{:.0}", c.min(100.0))))).unwrap_or_else(|| "CPU –".into());
    let g = gpu.map(|g| format!("GPU {}", crate::dil::yuzde(format!("{g:.0}")))).unwrap_or_else(|| "GPU –".into());
    format!("{c} · {g} · {fps:.0} FPS")
}
