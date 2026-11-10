//! RizeOn — başlangıç noktası (Rust sürümü).
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod arayuz;

use rizeon::{ayarlar::Ayarlar, gunluk, surum, tek_kopya::TekKopya, uygulama::Uygulama, yollar};

fn main() {
    let argumanlar: Vec<String> = std::env::args().collect();
    if argumanlar.len() == 3 && argumanlar[1] == "--duman-testi" {
        std::process::exit(duman_testi(&argumanlar[2]));
    }
    if argumanlar.len() >= 3 && argumanlar[1] == "--olcum" {
        let sn = argumanlar[2].parse().unwrap_or(30);
        std::process::exit(olcum(sn, argumanlar.get(3).map(String::as_str)));
    }
    gunluk::kur();
    let Some(tek) = TekKopya::al() else {
        // Uygulama zaten çalışıyor (belki tepside): onun penceresi öne gelir.
        log::info!("Uygulama zaten açık; çalışan pencere öne getiriliyor");
        return;
    };
    log::info!("Uygulama başlıyor (Rust sürümü {}, derleme {})", surum::SURUM, surum::DERLEME);
    let ayarlar = Ayarlar::ac(yollar::ayar_dosyasi());
    let uyg = Uygulama::kur(ayarlar);
    uyg.baslat();
    if let Err(e) = arayuz::calistir(uyg.clone(), tek) {
        log::error!("Arayüz açılamadı: {e}");
        acilis_hatasi_goster(&e.to_string());
    }
    // Kapanış takılırsa (bir sürücü cevap vermezse) süreç arkada kalmasın: kamera/mikrofon açık kalırdı.
    std::thread::spawn(|| {
        std::thread::sleep(std::time::Duration::from_secs(75));
        log::error!("Kapanış zamanında bitmedi; uygulama zorla kapatılıyor");
        log::logger().flush();
        std::process::exit(1);
    });
    uyg.kapat();
    log::logger().flush();
}

fn acilis_hatasi_goster(hata: &str) {
    let metin = format!("RizeOn açılamadı.\n\n{hata}\n\nAyrıntılar log dosyasında:\n{}", yollar::log_klasoru().display());
    #[cfg(windows)]
    unsafe {
        use windows::core::HSTRING;
        use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
        MessageBoxW(None, &HSTRING::from(metin), &HSTRING::from("RizeOn"), MB_OK | MB_ICONERROR);
    }
    #[cfg(not(windows))]
    eprintln!("{metin}");
}

/// `RizeOn.exe --olcum 60 [sonuc.txt]`: pencere açmadan hattı ve sesi (anlık tekrar dahil) çalıştırıp
/// işlemci kullanımını ölçer. Python sürümünün log'daki "CPU (30 sn)" satırıyla karşılaştırmak için.
fn olcum(sn: u64, sonuc: Option<&str>) -> i32 {
    gunluk::kur();
    let uyg = Uygulama::kur(Ayarlar::ac(yollar::ayar_dosyasi()));
    uyg.baslat();
    std::thread::sleep(std::time::Duration::from_secs(5)); // ısınma (kodlayıcı seçimi, cihazlar)
    let mut o = rizeon::islemci::IslemciOlcer::new();
    o.olc();
    std::thread::sleep(std::time::Duration::from_secs(sn.max(5)));
    let s = o.olc();
    let d = uyg.depo.al();
    let metin = format!(
        "RizeOn {} · {} sn · toplam CPU %{:.1} (uygulama %{:.1}, ffmpeg %{:.1}, {} alt süreç) · {:.0} fps · kare {:.1} ms · yakalama: {} · tekrar: {}\n",
        surum::SURUM,
        sn,
        s.toplam,
        s.uygulama,
        s.ffmpeg,
        s.alt_surec,
        d.fps,
        d.kare_suresi_ms,
        d.yakalama_yontemi,
        if uyg.tekrar.acik() {
            format!("açık, {:.0} sn / {:.0} MB tutuluyor", uyg.tekrar.tutulan_sure(), uyg.tekrar.bellek() as f64 / 1e6)
        } else {
            format!("kapalı ({})", uyg.tekrar.son_hata())
        }
    );
    log::info!("Ölçüm: {}", metin.trim());
    print!("{metin}");
    if let Some(y) = sonuc {
        let _ = std::fs::write(y, &metin);
    }
    uyg.kapat();
    log::logger().flush();
    0
}

/// `RizeOn.exe --duman-testi sonuc.txt`: pencere açmadan exe'nin çalıştığını denetler (CI).
fn duman_testi(sonuc: &str) -> i32 {
    let (metin, kod) = match rizeon::ffmpeg::ffmpeg_bul() {
        Some(f) => {
            let kod = rizeon::ffmpeg::kodlayici_sec(&f, "auto");
            let k = rizeon::kare::Kare::dolu(1280, 720, [10, 20, 30]);
            let t = std::time::Instant::now();
            for _ in 0..30 {
                let _ = rizeon::kare::olcekle(&k, 640, 360);
            }
            (
                format!(
                    "tamam · sürüm {} · ffmpeg: {} · kodlayıcı: {kod} · monitör: {} · 30 ölçekleme {} ms\n",
                    surum::SURUM,
                    f.display(),
                    rizeon::yakalama::monitorler().len(),
                    t.elapsed().as_millis()
                ),
                0,
            )
        }
        None => ("ffmpeg\\ffmpeg.exe bulunamadı\n".to_string(), 1),
    };
    let _ = std::fs::write(sonuc, metin);
    kod
}
