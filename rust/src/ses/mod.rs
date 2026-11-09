//! Ses: mikser (cihazsız, test edilebilir) ve Windows ses motoru (WASAPI).
pub mod karistirici;
#[cfg(windows)]
pub mod motor;
#[cfg(windows)]
pub mod wasapi;
#[cfg(windows)]
pub mod surec_sesi;
pub mod surec_secimi;

pub const ORNEKLEME: u32 = 48000;
pub const KANAL: usize = 2;
/// 10 ms
pub const BLOK: usize = 480;

/// 0..1 tepe değerini desibele çevirir (gösterge için). 0 -> -60 dB.
pub fn db(seviye: f32) -> f32 {
    (20.0 * seviye.max(1e-6).log10()).max(-60.0)
}
