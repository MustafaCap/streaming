//! RizeOn (Rust sürümü) — kütüphane kısmı. Arayüz `main.rs` + `arayuz/` içinde.
//!
//! Python sürümüyle (2.0.x) aynı ayar dosyasını (%APPDATA%\RizeOn\settings.json), aynı kayıt klasörünü
//! ve aynı FFmpeg komutlarını kullanır; iki sürüm aynı bilgisayarda sırayla çalıştırılabilir.
//! Hiçbir ağ kodu yoktur (Rust'ta ağ kitaplığı bağımlılığı da yok).

pub mod ayarlar;
pub mod durum;
pub mod ffmpeg;
pub mod gunluk;
pub mod kare;
pub mod kayit;
pub mod kisayol;
pub mod obs_kamera;
pub mod sahne;
pub mod ses;
pub mod surum;
pub mod tekrar;
pub mod tek_kopya;
pub mod yakalama;
pub mod yazi;
pub mod yollar;
pub mod hat;
pub mod islemci;

#[cfg(windows)]
pub mod win;
