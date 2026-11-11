//! FFmpeg yardımcıları: ffmpeg.exe'yi bulma, kodlayıcı seçme, parçaları MP4'te birleştirme.
//! Komutlar Python sürümüyle (core/recorder.py) aynı. Uygulamayla gelen FFmpeg LGPL sürümüdür.

use crate::dil::t;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

pub const KODLAYICILAR: &[&str] = &["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf", "mpeg4"];
pub const SES_HIZI: u32 = 48000;
pub const SES_KANALI: u32 = 2;

pub fn kodlayici_ayarlari(kod: &str) -> &'static [&'static str] {
    match kod {
        "h264_nvenc" => &["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"],
        "h264_qsv" => &["-preset", "medium", "-global_quality", "23"],
        "h264_amf" => &["-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24"],
        "h264_mf" => &["-b:v", "8M", "-hw_encoding", "1"],
        "mpeg4" => &["-q:v", "4"],
        _ => &[],
    }
}

/// Siyah konsol penceresi açmadan çalışacak komut.
pub fn komut(program: &Path) -> Command {
    #[allow(unused_mut)]
    let mut k = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        k.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    k
}

/// Uygulamanın yanındaki ffmpeg\ffmpeg.exe. Geliştirme derlemesinde depo kökündeki ffmpeg\ ve PATH de denenir.
pub fn ffmpeg_bul() -> Option<PathBuf> {
    let ad = if cfg!(windows) { "ffmpeg.exe" } else { "ffmpeg" };
    let paketteki = crate::yollar::uygulama_klasoru().join("ffmpeg").join(ad);
    if paketteki.exists() {
        return Some(paketteki);
    }
    if cfg!(debug_assertions) || std::env::var_os("RIZEON_GELISTIRME").is_some() {
        let depo = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("ffmpeg").join(ad);
        if depo.exists() {
            return Some(depo);
        }
        if let Some(yol) = std::env::var_os("PATH") {
            for d in std::env::split_paths(&yol) {
                let a = d.join(ad);
                if a.is_file() {
                    return Some(a);
                }
            }
        }
    }
    None
}

/// Komutu zaman aşımıyla çalıştırır: (başarılı mı, hata çıktısı).
pub fn calistir(mut k: Command, zaman_asimi: Duration) -> (bool, String) {
    k.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::piped());
    let mut surec = match k.spawn() {
        Ok(s) => s,
        Err(e) => return (false, e.to_string()),
    };
    let mut hata = surec.stderr.take();
    let okuyucu = std::thread::spawn(move || {
        let mut s = String::new();
        if let Some(h) = hata.as_mut() {
            use std::io::Read;
            let _ = h.read_to_string(&mut s);
        }
        s
    });
    let bitis = std::time::Instant::now() + zaman_asimi;
    loop {
        match surec.try_wait() {
            Ok(Some(d)) => {
                let cikti = okuyucu.join().unwrap_or_default();
                return (d.success(), cikti);
            }
            Ok(None) if std::time::Instant::now() < bitis => std::thread::sleep(Duration::from_millis(30)),
            _ => {
                let _ = surec.kill();
                let _ = surec.wait();
                return (false, t("FFmpeg zaman aşımına uğradı").into());
            }
        }
    }
}

fn onbellek() -> &'static Mutex<HashMap<(PathBuf, String), String>> {
    static O: OnceLock<Mutex<HashMap<(PathBuf, String), String>>> = OnceLock::new();
    O.get_or_init(Default::default)
}

/// Bu bilgisayarda gerçekten çalışan ilk kodlayıcı (küçük bir deneme kodlamasıyla).
/// NVIDIA -> Intel QSV -> AMD -> Media Foundation -> mpeg4.
pub fn kodlayici_sec(ffmpeg: &Path, tercih: &str) -> String {
    let anahtar = (ffmpeg.to_path_buf(), tercih.to_string());
    if let Some(k) = onbellek().lock().unwrap().get(&anahtar) {
        return k.clone();
    }
    let mut sira: Vec<&str> = Vec::new();
    if !tercih.is_empty() && tercih != "auto" {
        sira.push(tercih);
    }
    sira.extend(KODLAYICILAR.iter().filter(|k| **k != tercih));
    let mut secilen = "mpeg4".to_string();
    for k in sira {
        let mut c = komut(ffmpeg);
        c.args(["-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30", "-frames:v", "5"])
            .args(["-pix_fmt", if k != "mpeg4" { "nv12" } else { "yuv420p" }, "-c:v", k, "-f", "null", "-"]);
        let (ok, hata) = calistir(c, Duration::from_secs(15));
        if ok {
            secilen = k.to_string();
            break;
        }
        log::info!("Kodlayıcı kullanılamıyor: {k} ({})", hata.trim().chars().take(200).collect::<String>());
    }
    log::info!("Kayıt kodlayıcısı: {secilen}");
    onbellek().lock().unwrap().insert(anahtar, secilen.clone());
    secilen
}

/// FFmpeg'e gönderilen ham karenin biçimi: çift boyutlarda NV12 (RGB'nin yarısı veri), yoksa BGRA.
pub fn girdi_bicimi(w: u32, h: u32) -> &'static str {
    if w % 2 == 0 && h % 2 == 0 {
        "nv12"
    } else {
        "bgra"
    }
}

/// Kareyi FFmpeg'in stdin'ine yazılacak hale getirir (kopyasız).
pub fn kare_baytlari<'a>(kare: &'a crate::kare::Kare, bicim: &str) -> &'a [u8] {
    if bicim == "nv12" {
        kare.nv12()
    } else {
        &kare.veri
    }
}

/// Geçici dosyalar Kayıtlar klasöründe görünmesin.
pub fn gizle(yol: &Path) {
    #[cfg(windows)]
    crate::win::dosyayi_gizle(yol);
    #[cfg(not(windows))]
    let _ = yol;
}

fn concat_satiri(yol: &Path) -> String {
    format!("file '{}'\n", yol.to_string_lossy().replace('\\', "/").replace('\'', "'\\''"))
}

/// Geçici görüntü parça(lar)ını (MKV) + ham sesi (PCM) tek MP4'te birleştirir (görüntü yeniden kodlanmaz).
pub fn birlestir(ffmpeg: &Path, parcalar: &[PathBuf], ses: Option<&Path>, hedef: &Path) -> Result<(), String> {
    let mut liste = None;
    let mut c = komut(ffmpeg);
    c.args(["-y", "-hide_banner", "-loglevel", "error"]);
    if parcalar.len() == 1 {
        c.arg("-i").arg(&parcalar[0]);
    } else {
        let ad = format!(".{}.liste.txt", hedef.file_stem().unwrap_or_default().to_string_lossy());
        let l = hedef.with_file_name(ad);
        std::fs::write(&l, parcalar.iter().map(|p| concat_satiri(p)).collect::<String>()).map_err(|e| e.to_string())?;
        c.args(["-f", "concat", "-safe", "0", "-i"]).arg(&l);
        liste = Some(l);
    }
    if let Some(s) = ses {
        c.args(["-f", "s16le", "-ar", &SES_HIZI.to_string(), "-ac", &SES_KANALI.to_string(), "-i"]).arg(s);
        c.args(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-shortest"]);
    } else {
        c.args(["-map", "0:v"]);
    }
    c.args(["-c:v", "copy", "-movflags", "+faststart"]).arg(hedef);
    let (ok, hata) = calistir(c, Duration::from_secs(1800));
    if let Some(l) = liste {
        let _ = std::fs::remove_file(l);
    }
    let boyut = std::fs::metadata(hedef).map(|m| m.len()).unwrap_or(0);
    if !ok || boyut == 0 {
        let _ = std::fs::remove_file(hedef);
        let h = hata.trim();
        return Err(h[h.len().saturating_sub(300)..].to_string());
    }
    Ok(())
}

/// float -1..1 stereo örnekleri 16 bit küçük-sonlu PCM'e çevirir.
pub fn pcm16(blok: &[f32], hedef: &mut Vec<u8>) {
    hedef.reserve(blok.len() * 2);
    for &s in blok {
        let v = (s.clamp(-1.0, 1.0) * 32767.0) as i16;
        hedef.extend_from_slice(&v.to_le_bytes());
    }
}

#[cfg(test)]
mod testler {
    use super::*;
    #[test]
    fn concat_tirnak() {
        assert_eq!(concat_satiri(Path::new("C:\\a'b.mkv")), "file 'C:/a'\\''b.mkv'\n");
    }
    #[test]
    fn pcm_sinirlanir() {
        let mut v = Vec::new();
        pcm16(&[2.0, -2.0, 0.0], &mut v);
        assert_eq!(v, [0xff, 0x7f, 0x01, 0x80, 0, 0]);
    }
}
