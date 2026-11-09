//! İşlemci ölçümü: uygulamanın (ve FFmpeg alt süreçlerinin) harcadığı işlemciyi Görev Yöneticisi gibi
//! tüm çekirdeklere oranla ölçer. 30 sn'de bir log'a yazılır; Python sürümüyle karşılaştırma için.

use std::time::Instant;

#[derive(Default, Clone, Copy, Debug)]
pub struct Olcum {
    pub toplam: f64,
    pub uygulama: f64,
    pub ffmpeg: f64,
}

pub struct IslemciOlcer {
    onceki: (f64, f64),
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
        Olcum { toplam: u + f, uygulama: u, ffmpeg: f }
    }
}

/// (uygulamanın işlemci saniyesi, alt süreçlerin (FFmpeg) işlemci saniyesi)
#[cfg(windows)]
fn sureler() -> (f64, f64) {
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
        let pid = std::process::id();
        if let Ok(anlik) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) {
            let mut g = PROCESSENTRY32W { dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32, ..Default::default() };
            let mut ok = Process32FirstW(anlik, &mut g).is_ok();
            while ok {
                if g.th32ParentProcessID == pid {
                    if let Ok(h) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, g.th32ProcessID) {
                        cocuk += surec_suresi(h);
                        let _ = CloseHandle(h);
                    }
                }
                ok = Process32NextW(anlik, &mut g).is_ok();
            }
            let _ = CloseHandle(anlik);
        }
        (kendi, cocuk)
    }
}

#[cfg(not(windows))]
fn sureler() -> (f64, f64) {
    // /proc/self/stat: utime + stime (saat tıkı)
    let s = std::fs::read_to_string("/proc/self/stat").unwrap_or_default();
    let alanlar: Vec<&str> = s.rsplit(')').next().unwrap_or("").split_whitespace().collect();
    let t = |i: usize| alanlar.get(i).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0);
    ((t(11) + t(12)) / 100.0, (t(13) + t(14)) / 100.0)
}
