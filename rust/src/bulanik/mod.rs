//! Webcam arka plan bulanıklaştırma (Python capture/background_blur.py).
//!
//! Google MediaPipe'ın "Selfie Segmentation" modeli (Apache 2.0, models/ klasöründe; exe'ye gömülü)
//! kendi küçük TFLite yorumlayıcımızla (tflite.rs) çalışır. Model kişiyi (1) ve arka planı (0)
//! ayıran 256x144'lük bir maske verir; maske yumuşatılıp büyütülür, arka plan küçük çözünürlükte
//! bulanıklaştırılıp kişiyle birleştirilir. Webcam'in kendi iş parçacığında çalışır.
//! Model yüklenemezse görüntü olduğu gibi geçer.

pub mod tflite;

use crate::trf;
use crate::kare::{olcekle, Kare};
use fast_image_resize as fr;

const MODEL: &[u8] = include_bytes!("../../../models/selfie_segmentation_landscape.tflite");
const GIRIS_W: usize = 256;
const GIRIS_H: usize = 144;

pub struct ArkaPlanBulaniklastirici {
    /// bulanıklık (büyüdükçe daha bulanık; Python'daki gibi 21)
    pub guc: u32,
    /// model her N karede bir çalışır (işlemci tasarrufu)
    pub her_n_karede: u32,
    model: Option<tflite::Model>,
    yuklenemedi: bool,
    maske: Option<Vec<f32>>,
    sayac: u32,
    pub hata: String,
}

impl Default for ArkaPlanBulaniklastirici {
    fn default() -> Self {
        Self::new()
    }
}

impl ArkaPlanBulaniklastirici {
    pub fn new() -> Self {
        ArkaPlanBulaniklastirici { guc: 21, her_n_karede: 2, model: None, yuklenemedi: false, maske: None, sayac: 0, hata: String::new() }
    }

    fn yukle(&mut self) -> bool {
        if self.model.is_some() {
            return true;
        }
        if self.yuklenemedi {
            return false;
        }
        match tflite::Model::yukle(MODEL) {
            Ok(m) => {
                self.model = Some(m);
                true
            }
            Err(e) => {
                self.yuklenemedi = true;
                self.hata = trf!("Bulanıklaştırma modeli yüklenemedi: {}", e);
                log::warn!("{}", self.hata);
                false
            }
        }
    }

    /// 0..1 arası kişi maskesi (GIRIS_H x GIRIS_W).
    pub fn maske(&mut self, kare: &Kare) -> Option<Vec<f32>> {
        if !self.yukle() {
            return None;
        }
        let kucuk = olcekle(kare, GIRIS_W as u32, GIRIS_H as u32);
        let mut giris = Vec::with_capacity(GIRIS_W * GIRIS_H * 3);
        for p in kucuk.veri.chunks_exact(4) {
            // BGRA -> RGB, 0..1
            giris.extend_from_slice(&[p[2] as f32 / 255.0, p[1] as f32 / 255.0, p[0] as f32 / 255.0]);
        }
        match self.model.as_ref().unwrap().calistir(&giris) {
            Ok(m) => Some(m.into_iter().map(|v| v.clamp(0.0, 1.0)).collect()),
            Err(e) => {
                self.hata = trf!("Bulanıklaştırma hatası: {}", e);
                log::warn!("{}", self.hata);
                self.yuklenemedi = true;
                self.model = None;
                None
            }
        }
    }

    pub fn isle(&mut self, kare: Kare) -> Kare {
        self.sayac = self.sayac.wrapping_add(1);
        if self.maske.is_none() || self.sayac % self.her_n_karede.max(1) == 0 {
            let Some(mut yeni) = self.maske(&kare) else {
                return kare;
            };
            // kenarları küçük maskede yumuşat, zamanla yumuşat (kenarlar titremesin)
            bulanik_f32(&mut yeni, GIRIS_W, GIRIS_H, 1);
            if let Some(eski) = &self.maske {
                for (y, e) in yeni.iter_mut().zip(eski) {
                    *y = 0.6 * *y + 0.4 * e;
                }
            }
            self.maske = Some(yeni);
        }
        let maske = self.maske.as_ref().unwrap();
        let (w, h) = (kare.w, kare.h);
        if w < 8 || h < 8 {
            return kare;
        }
        let m = maske_buyut(maske, w, h);
        // arka planı küçük çözünürlükte bulanıklaştır (hızlı), sonra büyüt
        let mut kucuk = olcekle(&kare, (w / 4).max(1), (h / 4).max(1));
        let yaricap = (self.guc as f32 / 4.0 * 0.85).round().max(1.0) as usize;
        bulanik_bgra(&mut kucuk, yaricap);
        let arka = olcekle(&kucuk, w, h);
        let mut cikis = kare;
        for ((p, a), &m) in cikis.veri.chunks_exact_mut(4).zip(arka.veri.chunks_exact(4)).zip(&m) {
            let m = m as u32;
            let t = 255 - m;
            for k in 0..3 {
                p[k] = ((p[k] as u32 * m + a[k] as u32 * t + 127) / 255) as u8;
            }
        }
        cikis
    }
}

fn maske_buyut(maske: &[f32], w: u32, h: u32) -> Vec<u8> {
    let bayt: Vec<u8> = maske.iter().map(|v| (v * 255.0).round() as u8).collect();
    let src = fr::images::ImageRef::new(GIRIS_W as u32, GIRIS_H as u32, &bayt, fr::PixelType::U8).expect("maske boyutu");
    let mut hedef = fr::images::Image::new(w, h, fr::PixelType::U8);
    let ayar = fr::ResizeOptions::new().resize_alg(fr::ResizeAlg::Convolution(fr::FilterType::Bilinear));
    let _ = fr::Resizer::new().resize(&src, &mut hedef, &ayar);
    hedef.into_vec()
}

/// Üç geçişli kutu bulanıklığı (Gauss'a yakın), yatay + dikey.
fn kutu_1b(veri: &mut [f32], adim: usize, n: usize, r: usize, tmp: &mut Vec<f32>) {
    if n < 2 || r == 0 {
        return;
    }
    tmp.clear();
    tmp.extend((0..n).map(|i| veri[i * adim]));
    let al = |i: isize| tmp[i.clamp(0, n as isize - 1) as usize];
    let ri = r as isize;
    let mut t: f32 = (-ri..=ri).map(al).sum();
    let bol = (2 * r + 1) as f32;
    for i in 0..n as isize {
        veri[i as usize * adim] = t / bol;
        t += al(i + ri + 1) - al(i - ri);
    }
}

fn bulanik_f32(veri: &mut [f32], w: usize, h: usize, r: usize) {
    let mut tmp = Vec::new();
    for _ in 0..3 {
        for y in 0..h {
            kutu_1b(&mut veri[y * w..(y + 1) * w], 1, w, r, &mut tmp);
        }
        for x in 0..w {
            kutu_1b(&mut veri[x..], w, h, r, &mut tmp);
        }
    }
}

fn bulanik_bgra(kare: &mut Kare, r: usize) {
    let (w, h) = (kare.w as usize, kare.h as usize);
    for k in 0..3 {
        let mut kanal: Vec<f32> = kare.veri.chunks_exact(4).map(|p| p[k] as f32).collect();
        bulanik_f32(&mut kanal, w, h, r);
        for (p, v) in kare.veri.chunks_exact_mut(4).zip(kanal) {
            p[k] = v.round().clamp(0.0, 255.0) as u8;
        }
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn model_yuklenir_ve_calisir() {
        let m = tflite::Model::yukle(MODEL).expect("model");
        assert_eq!(m.giris_sekli(), &[1, 144, 256, 3]);
        assert_eq!(m.cikis_sekli(), &[1, 144, 256, 1]);
        let giris: Vec<f32> = (0..GIRIS_W * GIRIS_H * 3).map(|i| ((i * 7919) % 255) as f32 / 255.0).collect();
        let c = m.calistir(&giris).unwrap();
        assert_eq!(c.len(), GIRIS_W * GIRIS_H);
        assert!(c.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)));
    }

    #[test]
    fn kare_boyutu_korunur() {
        let mut b = ArkaPlanBulaniklastirici::new();
        let k = Kare::dolu(320, 180, [120, 80, 40]);
        let c = b.isle(k);
        assert_eq!((c.w, c.h), (320, 180));
        // düz renkte bulanıklık rengi değiştirmez
        let p = c.piksel(100, 100);
        assert!((p[0] as i32 - 120).abs() <= 2 && (p[2] as i32 - 40).abs() <= 2, "{p:?}");
    }
}

