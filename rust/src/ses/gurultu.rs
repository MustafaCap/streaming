//! Gürültü azaltma: RNNoise'un saf Rust hali (nnnoiseless, BSD-3-Clause). Klavye, fan ve uğultu
//! sesini bastırır. 48 kHz mono sesi 480 örneklik (10 ms) bloklarla işler; 10 ms gecikme ekler.
//! Python sürümü rnnoise.dll yüklüyordu; burada DLL yok, model exe'nin içinde.

use nnnoiseless::DenoiseState;

pub const CERCEVE: usize = DenoiseState::FRAME_SIZE; // 480
const OLCEK: f32 = 32768.0; // RNNoise 16 bit aralığında float bekler

pub struct GurultuAzaltici {
    durum: Box<DenoiseState<'static>>,
    giris: Vec<f32>,
    cikis: Vec<f32>,
    cerceve_cikis: Vec<f32>,
    ilk: bool,
}

impl Default for GurultuAzaltici {
    fn default() -> Self {
        Self::new()
    }
}

impl GurultuAzaltici {
    pub fn new() -> Self {
        GurultuAzaltici { durum: DenoiseState::new(), giris: Vec::new(), cikis: Vec::new(), cerceve_cikis: vec![0.0; CERCEVE], ilk: true }
    }

    /// İç içe (interleaved) çok kanallı blok alır, aynı uzunlukta temizlenmiş blok döndürür.
    /// Kanallar mono'ya indirilip işlenir, sonra tüm kanallara aynı ses yazılır.
    pub fn isle(&mut self, blok: &[f32], kanal: usize) -> Vec<f32> {
        let kanal = kanal.max(1);
        let n = blok.len() / kanal;
        for i in 0..n {
            let mut t = 0.0;
            for c in 0..kanal {
                t += blok[i * kanal + c];
            }
            self.giris.push(t / kanal as f32 * OLCEK);
        }
        while self.giris.len() >= CERCEVE {
            let cerceve: Vec<f32> = self.giris.drain(..CERCEVE).collect();
            self.durum.process_frame(&mut self.cerceve_cikis, &cerceve);
            if self.ilk {
                // ilk çerçevede model ısınıyor; çıktısı tıkırtı yapabilir
                self.ilk = false;
                self.cikis.extend(std::iter::repeat_n(0.0, CERCEVE));
            } else {
                self.cikis.extend(self.cerceve_cikis.iter().map(|v| (v / OLCEK).clamp(-1.0, 1.0)));
            }
        }
        // Çıkış hazır değilse (ilk 10 ms) sessizlik: uzunluk korunur, gecikme sabit kalır
        let hazir = self.cikis.len().min(n);
        let eksik = n - hazir;
        let mut sonuc = Vec::with_capacity(n * kanal);
        for _ in 0..eksik {
            sonuc.extend(std::iter::repeat_n(0.0, kanal));
        }
        for v in self.cikis.drain(..hazir) {
            sonuc.extend(std::iter::repeat_n(v, kanal));
        }
        sonuc
    }

    pub fn sifirla(&mut self) {
        *self = Self::new();
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn uzunluk_korunur_ve_gurultu_azalir() {
        let mut g = GurultuAzaltici::new();
        let mut tohum = 12345u32;
        let mut rastgele = || {
            tohum = tohum.wrapping_mul(1664525).wrapping_add(1013904223);
            (tohum >> 8) as f32 / (1u32 << 24) as f32 - 0.5
        };
        let mut giris_enerji = 0.0;
        let mut cikis_enerji = 0.0;
        for blok_no in 0..200 {
            let blok: Vec<f32> = (0..960).map(|_| rastgele() * 0.2).collect(); // 480 kare stereo
            let c = g.isle(&blok, 2);
            assert_eq!(c.len(), blok.len());
            if blok_no > 50 {
                giris_enerji += blok.iter().map(|v| v * v).sum::<f32>();
                cikis_enerji += c.iter().map(|v| v * v).sum::<f32>();
            }
        }
        assert!(cikis_enerji < giris_enerji * 0.5, "beyaz gürültü bastırılmalı: {cikis_enerji} / {giris_enerji}");
    }
}
