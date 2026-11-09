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
