//! Küçük bir TFLite yorumlayıcısı: sadece selfie segmentation modelinin kullandığı işlemler.
//!
//! Python sürümü modeli OpenCV'nin DNN modülüyle çalıştırıyordu; Rust'ta OpenCV ya da TensorFlow
//! taşımamak için .tflite dosyası (FlatBuffers) burada doğrudan okunur ve işlemler elle hesaplanır.
//! Model küçük (≈250 KB, 256x144 giriş), tek iş parçacığında birkaç milisaniye sürer.
//!
//! Desteklenen işlemler: CONV_2D, DEPTHWISE_CONV_2D, ADD, MUL, RELU, HARD_SWISH, LOGISTIC, MEAN,
//! RESIZE_BILINEAR, DEQUANTIZE (float16 sabitler, yüklerken açılır) ve MediaPipe'ın özel
//! Convolution2DTransposeBias işlemi. Düzen NHWC, toplu iş boyutu 1.

// ---- FlatBuffers okuma (şemasız, alan sıra numarasıyla) ----

#[derive(Clone, Copy)]
struct Tablo<'a> {
    b: &'a [u8],
    konum: usize,
}

fn u16_(b: &[u8], i: usize) -> Result<u16, String> {
    b.get(i..i + 2).map(|s| u16::from_le_bytes([s[0], s[1]])).ok_or_else(|| "model bozuk".to_string())
}
fn u32_(b: &[u8], i: usize) -> Result<u32, String> {
    b.get(i..i + 4).map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]])).ok_or_else(|| "model bozuk".to_string())
}

impl<'a> Tablo<'a> {
    fn kok(b: &'a [u8]) -> Result<Self, String> {
        Ok(Tablo { b, konum: u32_(b, 0)? as usize })
    }

    /// Alanın tablodaki mutlak konumu (alan yoksa None).
    fn alan(&self, no: usize) -> Result<Option<usize>, String> {
        let vt = (self.konum as i64 - u32_(self.b, self.konum)? as i32 as i64) as usize;
        let vt_boy = u16_(self.b, vt)? as usize;
        let yer = 4 + no * 2;
        if yer + 2 > vt_boy {
            return Ok(None);
        }
        let o = u16_(self.b, vt + yer)? as usize;
        Ok(if o == 0 { None } else { Some(self.konum + o) })
    }

    fn i32_(&self, no: usize, varsayilan: i32) -> Result<i32, String> {
        Ok(match self.alan(no)? {
            Some(i) => u32_(self.b, i)? as i32,
            None => varsayilan,
        })
    }
    fn i8_(&self, no: usize, varsayilan: i8) -> Result<i8, String> {
        Ok(match self.alan(no)? {
            Some(i) => *self.b.get(i).ok_or("model bozuk")? as i8,
            None => varsayilan,
        })
    }
    fn bool_(&self, no: usize) -> Result<bool, String> {
        Ok(self.i8_(no, 0)? != 0)
    }

    fn dolayli(&self, no: usize) -> Result<Option<usize>, String> {
        Ok(match self.alan(no)? {
            Some(i) => Some(i + u32_(self.b, i)? as usize),
            None => None,
        })
    }

    fn tablo(&self, no: usize) -> Result<Option<Tablo<'a>>, String> {
        Ok(self.dolayli(no)?.map(|konum| Tablo { b: self.b, konum }))
    }

    /// Vektörün (eleman sayısı, ilk elemanın konumu).
    fn vektor(&self, no: usize) -> Result<(usize, usize), String> {
        Ok(match self.dolayli(no)? {
            Some(i) => (u32_(self.b, i)? as usize, i + 4),
            None => (0, 0),
        })
    }

    fn baytlar(&self, no: usize) -> Result<&'a [u8], String> {
        let (n, i) = self.vektor(no)?;
        if n == 0 {
            return Ok(&[]);
        }
        self.b.get(i..i + n).ok_or_else(|| "model bozuk".to_string())
    }

    fn i32ler(&self, no: usize) -> Result<Vec<i32>, String> {
        let (n, i) = self.vektor(no)?;
        (0..n).map(|k| u32_(self.b, i + k * 4).map(|v| v as i32)).collect()
    }

    fn tablolar(&self, no: usize) -> Result<Vec<Tablo<'a>>, String> {
        let (n, i) = self.vektor(no)?;
        (0..n)
            .map(|k| {
                let yer = i + k * 4;
                Ok(Tablo { b: self.b, konum: yer + u32_(self.b, yer)? as usize })
            })
            .collect()
    }

    fn metin(&self, no: usize) -> Result<String, String> {
        Ok(String::from_utf8_lossy(self.baytlar(no)?).into_owned())
    }
}

fn f16_den_f32(h: u16) -> f32 {
    let isaret = ((h >> 15) as u32) << 31;
    let us = ((h >> 10) & 0x1f) as u32;
    let kesir = (h & 0x3ff) as u32;
    let bit = if us == 0 {
        if kesir == 0 {
            isaret
        } else {
            // normal olmayan sayı: normalleştir
            let mut e = 127 - 15 + 1;
            let mut k = kesir;
            while k & 0x400 == 0 {
                k <<= 1;
                e -= 1;
            }
            isaret | ((e as u32) << 23) | ((k & 0x3ff) << 13)
        }
    } else if us == 31 {
        isaret | 0x7f80_0000 | (kesir << 13)
    } else {
        isaret | ((us + 127 - 15) << 23) | (kesir << 13)
    };
    f32::from_bits(bit)
}

// ---- Model ----

#[derive(Clone, Copy, Debug, PartialEq)]
enum Etkin {
    Yok,
    Relu,
    Relu6,
}

fn etkin(kod: i8) -> Result<Etkin, String> {
    match kod {
        0 => Ok(Etkin::Yok),
        1 => Ok(Etkin::Relu),
        3 => Ok(Etkin::Relu6),
        k => Err(format!("desteklenmeyen etkinleştirme {k}")),
    }
}

#[derive(Debug)]
enum Islem {
    Conv { giris: usize, agirlik: usize, sapma: Option<usize>, cikis: usize, ayni: bool, adim: (usize, usize), etkin: Etkin },
    Derinlik { giris: usize, agirlik: usize, sapma: Option<usize>, cikis: usize, ayni: bool, adim: (usize, usize), carpan: usize, etkin: Etkin },
    Topla { a: usize, b: usize, cikis: usize, etkin: Etkin },
    Carp { a: usize, b: usize, cikis: usize, etkin: Etkin },
    Relu { giris: usize, cikis: usize },
    HardSwish { giris: usize, cikis: usize },
    Sigmoid { giris: usize, cikis: usize },
    /// sadece yükseklik+genişlik ortalaması (eksen 1,2), boyutlar korunur
    Ortalama { giris: usize, cikis: usize },
    Buyut { giris: usize, cikis: usize, hizali: bool, yarim: bool },
    TersConv { giris: usize, agirlik: usize, sapma: usize, cikis: usize, adim: (usize, usize), ayni: bool },
}

pub struct Model {
    sekiller: Vec<Vec<usize>>,
    sabitler: Vec<Option<Vec<f32>>>,
    islemler: Vec<Islem>,
    giris: usize,
    cikis: usize,
}

const ADD: i32 = 0;
const CONV_2D: i32 = 3;
const DEPTHWISE_CONV_2D: i32 = 4;
const DEQUANTIZE: i32 = 6;
const LOGISTIC: i32 = 14;
const MUL: i32 = 18;
const RELU: i32 = 19;
const RESIZE_BILINEAR: i32 = 23;
const CUSTOM: i32 = 32;
const MEAN: i32 = 40;
const HARD_SWISH: i32 = 117;

impl Model {
    pub fn yukle(b: &[u8]) -> Result<Model, String> {
        if b.len() < 8 || &b[4..8] != b"TFL3" {
            return Err("TFLite dosyası değil".into());
        }
        let model = Tablo::kok(b)?;
        let kodlar: Vec<(i32, String)> = model
            .tablolar(1)?
            .iter()
            .map(|k| {
                let eski = k.i8_(0, 0)? as i32;
                let yeni = k.i32_(3, 0)?;
                Ok((eski.max(yeni), k.metin(1)?))
            })
            .collect::<Result<_, String>>()?;
        let tamponlar = model.tablolar(4)?;
        let alt = model.tablolar(2)?.into_iter().next().ok_or("modelde alt çizge yok")?;
        let tensorler = alt.tablolar(0)?;
        let mut sekiller = Vec::with_capacity(tensorler.len());
        let mut sabitler: Vec<Option<Vec<f32>>> = Vec::with_capacity(tensorler.len());
        let mut turler = Vec::with_capacity(tensorler.len());
        for t in &tensorler {
            let sekil: Vec<usize> = t.i32ler(0)?.into_iter().map(|v| v.max(0) as usize).collect();
            let tur = t.i8_(1, 0)?;
            let tampon = t.i32_(2, 0)? as usize;
            let veri = match tamponlar.get(tampon) {
                Some(tb) => tb.baytlar(0)?,
                None => &[],
            };
            let sabit = if veri.is_empty() {
                None
            } else {
                Some(match tur {
                    0 => veri.chunks_exact(4).map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]])).collect(),
                    1 => veri.chunks_exact(2).map(|c| f16_den_f32(u16::from_le_bytes([c[0], c[1]]))).collect(),
                    2 => veri.chunks_exact(4).map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f32).collect(),
                    t => return Err(format!("desteklenmeyen tensör türü {t}")),
                })
            };
            sekiller.push(sekil);
            sabitler.push(sabit);
            turler.push(tur);
        }
        let giris = *alt.i32ler(1)?.first().ok_or("giriş yok")? as usize;
        let cikis = *alt.i32ler(2)?.first().ok_or("çıkış yok")? as usize;

        let mut islemler = Vec::new();
        for o in alt.tablolar(3)? {
            let (kod, ozel) = kodlar.get(o.i32_(0, 0)? as usize).cloned().ok_or("işlem kodu yok")?;
            let gir = o.i32ler(1)?;
            let cik = o.i32ler(2)?;
            let g = |i: usize| -> Result<usize, String> {
                gir.get(i).copied().filter(|&v| v >= 0).map(|v| v as usize).ok_or_else(|| format!("işlem {kod}: giriş {i} yok"))
            };
            let s = |i: usize| -> Option<usize> { gir.get(i).copied().filter(|&v| v >= 0).map(|v| v as usize) };
            let c = *cik.first().ok_or("işlem çıkışı yok")? as usize;
            let sec = o.tablo(4)?;
            let sec_i8 = |no: usize, v: i8| -> Result<i8, String> { sec.map(|t| t.i8_(no, v)).unwrap_or(Ok(v)) };
            let sec_i32 = |no: usize, v: i32| -> Result<i32, String> { sec.map(|t| t.i32_(no, v)).unwrap_or(Ok(v)) };
            islemler.push(match kod {
                DEQUANTIZE => {
                    // float16 sabit -> float32 sabit: yüklerken yapılır
                    let v = sabitler[g(0)?].clone().ok_or("DEQUANTIZE girişi sabit değil")?;
                    sabitler[c] = Some(v);
                    continue;
                }
                CONV_2D => {
                    if sec_i32(4, 1)? != 1 || sec_i32(5, 1)? != 1 {
                        return Err("genişletilmiş evrişim desteklenmiyor".into());
                    }
                    Islem::Conv {
                        giris: g(0)?,
                        agirlik: g(1)?,
                        sapma: s(2),
                        cikis: c,
                        ayni: sec_i8(0, 0)? == 0,
                        adim: (sec_i32(2, 1)?.max(1) as usize, sec_i32(1, 1)?.max(1) as usize),
                        etkin: etkin(sec_i8(3, 0)?)?,
                    }
                }
                DEPTHWISE_CONV_2D => {
                    if sec_i32(5, 1)? != 1 || sec_i32(6, 1)? != 1 {
                        return Err("genişletilmiş evrişim desteklenmiyor".into());
                    }
                    Islem::Derinlik {
                        giris: g(0)?,
                        agirlik: g(1)?,
                        sapma: s(2),
                        cikis: c,
                        ayni: sec_i8(0, 0)? == 0,
                        adim: (sec_i32(2, 1)?.max(1) as usize, sec_i32(1, 1)?.max(1) as usize),
                        carpan: sec_i32(3, 1)?.max(1) as usize,
                        etkin: etkin(sec_i8(4, 0)?)?,
                    }
                }
                ADD => Islem::Topla { a: g(0)?, b: g(1)?, cikis: c, etkin: etkin(sec_i8(0, 0)?)? },
                MUL => Islem::Carp { a: g(0)?, b: g(1)?, cikis: c, etkin: etkin(sec_i8(0, 0)?)? },
                RELU => Islem::Relu { giris: g(0)?, cikis: c },
                HARD_SWISH => Islem::HardSwish { giris: g(0)?, cikis: c },
                LOGISTIC => Islem::Sigmoid { giris: g(0)?, cikis: c },
                MEAN => {
                    let eksen = sabitler[g(1)?].clone().unwrap_or_default();
                    if eksen != [1.0, 2.0] || !sec.map(|t| t.bool_(0)).unwrap_or(Ok(false))? {
                        return Err("MEAN sadece yükseklik+genişlik için destekleniyor".into());
                    }
                    Islem::Ortalama { giris: g(0)?, cikis: c }
                }
                RESIZE_BILINEAR => Islem::Buyut {
                    giris: g(0)?,
                    cikis: c,
                    hizali: sec.map(|t| t.bool_(2)).unwrap_or(Ok(false))?,
                    yarim: sec.map(|t| t.bool_(3)).unwrap_or(Ok(false))?,
                },
                CUSTOM if ozel == "Convolution2DTransposeBias" => {
                    // özel seçenekler: TfLiteTransposeConvParams { padding: i32, stride_w: i32, stride_h: i32 }
                    let p = o.baytlar(5)?;
                    if p.len() < 12 {
                        return Err("Convolution2DTransposeBias seçenekleri eksik".into());
                    }
                    let oku = |i: usize| i32::from_le_bytes([p[i], p[i + 1], p[i + 2], p[i + 3]]);
                    // TfLitePadding: 1 = SAME, 2 = VALID
                    Islem::TersConv {
                        giris: g(0)?,
                        agirlik: g(1)?,
                        sapma: g(2)?,
                        cikis: c,
                        ayni: oku(0) == 1,
                        adim: (oku(8).max(1) as usize, oku(4).max(1) as usize),
                    }
                }
                k => return Err(format!("desteklenmeyen işlem: {k} {ozel}")),
            });
        }
        let _ = turler;
        // Evrişim ağırlıkları [O, KH, KW, I] -> [KH, KW, I, O]: iç döngü çıkış kanalları üzerinde
        // ardışık olur ve derleyici SIMD kullanır.
        let mut cevrildi = std::collections::HashSet::new();
        for islem in &islemler {
            if let Islem::Conv { agirlik, .. } = *islem {
                if !cevrildi.insert(agirlik) {
                    continue;
                }
                let sk = sekiller[agirlik].clone();
                let w = sabitler[agirlik].as_ref().ok_or("evrişim ağırlığı sabit değil")?;
                let (o, kh, kw, i) = (sk[0], sk[1], sk[2], sk[3]);
                let mut t = vec![0f32; w.len()];
                for a in 0..o {
                    for y in 0..kh {
                        for x in 0..kw {
                            for c in 0..i {
                                t[((y * kw + x) * i + c) * o + a] = w[((a * kh + y) * kw + x) * i + c];
                            }
                        }
                    }
                }
                sabitler[agirlik] = Some(t);
            }
        }
        Ok(Model { sekiller, sabitler, islemler, giris, cikis })
    }

    pub fn giris_sekli(&self) -> &[usize] {
        &self.sekiller[self.giris]
    }

    pub fn cikis_sekli(&self) -> &[usize] {
        &self.sekiller[self.cikis]
    }

    /// Girişi (NHWC, float) çalıştırır, çıkışı döndürür.
    pub fn calistir(&self, giris: &[f32]) -> Result<Vec<f32>, String> {
        let n: usize = self.giris_sekli().iter().product();
        if giris.len() != n {
            return Err(format!("giriş boyutu {} olmalı, {} geldi", n, giris.len()));
        }
        let mut deger: Vec<Option<Vec<f32>>> = vec![None; self.sekiller.len()];
        deger[self.giris] = Some(giris.to_vec());
        for islem in &self.islemler {
            let (cikis, v) = self.isle(islem, &deger)?;
            deger[cikis] = Some(v);
        }
        deger[self.cikis].take().ok_or_else(|| "çıkış hesaplanmadı".into())
    }

    fn al<'b>(&'b self, deger: &'b [Option<Vec<f32>>], i: usize) -> Result<&'b [f32], String> {
        deger[i].as_deref().or(self.sabitler[i].as_deref()).ok_or_else(|| format!("tensör {i} hazır değil"))
    }

    fn hwc(&self, i: usize) -> (usize, usize, usize) {
        let s = &self.sekiller[i];
        match s.len() {
            4 => (s[1], s[2], s[3]),
            1 => (1, 1, s[0]),
            _ => (1, 1, s.iter().product()),
        }
    }

    fn isle(&self, islem: &Islem, d: &[Option<Vec<f32>>]) -> Result<(usize, Vec<f32>), String> {
        Ok(match *islem {
            Islem::Conv { giris, agirlik, sapma, cikis, ayni, adim, etkin } => {
                let x = self.al(d, giris)?;
                let w = self.al(d, agirlik)?;
                let ws = &self.sekiller[agirlik]; // şekil [O, KH, KW, I], veri [KH, KW, I, O] (yüklerken çevrildi)
                let b = match sapma {
                    Some(s) => Some(self.al(d, s)?),
                    None => None,
                };
                let (ih, iw, ic) = self.hwc(giris);
                let (oh, ow, oc) = self.hwc(cikis);
                (cikis, conv(x, (ih, iw, ic), w, (ws[1], ws[2]), b, (oh, ow, oc), adim, ayni, etkin))
            }
            Islem::Derinlik { giris, agirlik, sapma, cikis, ayni, adim, carpan, etkin } => {
                let x = self.al(d, giris)?;
                let w = self.al(d, agirlik)?;
                let ws = &self.sekiller[agirlik]; // [1, KH, KW, C*m]
                let b = match sapma {
                    Some(s) => Some(self.al(d, s)?),
                    None => None,
                };
                let (ih, iw, ic) = self.hwc(giris);
                let (oh, ow, oc) = self.hwc(cikis);
                (cikis, derinlik(x, (ih, iw, ic), w, (ws[1], ws[2]), b, (oh, ow, oc), adim, ayni, carpan, etkin))
            }
            Islem::Topla { a, b, cikis, etkin } => (cikis, ikili(self.al(d, a)?, self.al(d, b)?, |p, q| p + q, etkin)),
            Islem::Carp { a, b, cikis, etkin } => (cikis, ikili(self.al(d, a)?, self.al(d, b)?, |p, q| p * q, etkin)),
            Islem::Relu { giris, cikis } => (cikis, self.al(d, giris)?.iter().map(|&v| v.max(0.0)).collect()),
            Islem::HardSwish { giris, cikis } => {
                (cikis, self.al(d, giris)?.iter().map(|&v| v * (v + 3.0).clamp(0.0, 6.0) / 6.0).collect())
            }
            Islem::Sigmoid { giris, cikis } => (cikis, self.al(d, giris)?.iter().map(|&v| 1.0 / (1.0 + (-v).exp())).collect()),
            Islem::Ortalama { giris, cikis } => {
                let x = self.al(d, giris)?;
                let (h, w, c) = self.hwc(giris);
                let mut t = vec![0f32; c];
                for p in x.chunks_exact(c) {
                    for (a, &v) in t.iter_mut().zip(p) {
                        *a += v;
                    }
                }
                let n = (h * w) as f32;
                (cikis, t.into_iter().map(|v| v / n).collect())
            }
            Islem::Buyut { giris, cikis, hizali, yarim } => {
                let x = self.al(d, giris)?;
                (cikis, buyut(x, self.hwc(giris), self.hwc(cikis), hizali, yarim))
            }
            Islem::TersConv { giris, agirlik, sapma, cikis, adim, ayni } => {
                let x = self.al(d, giris)?;
                let w = self.al(d, agirlik)?;
                let ws = &self.sekiller[agirlik]; // [O, KH, KW, I]
                let b = self.al(d, sapma)?;
                let (ih, iw, ic) = self.hwc(giris);
                let (oh, ow, oc) = self.hwc(cikis);
                (cikis, ters_conv(x, (ih, iw, ic), w, (ws[1], ws[2]), b, (oh, ow, oc), adim, ayni))
            }
        })
    }
}

/// İç çarpım; 8 ayrı toplayıcı derleyicinin SIMD kullanmasına izin verir (sıralı toplama vektörleşmez).
#[inline]
fn nokta(a: &[f32], b: &[f32]) -> f32 {
    let mut t = [0f32; 8];
    let (ac, ar) = a.split_at(a.len() / 8 * 8);
    let (bc, br) = b.split_at(ac.len());
    for (x, y) in ac.chunks_exact(8).zip(bc.chunks_exact(8)) {
        for k in 0..8 {
            t[k] += x[k] * y[k];
        }
    }
    let mut s = (t[0] + t[4]) + (t[1] + t[5]) + (t[2] + t[6]) + (t[3] + t[7]);
    for (x, y) in ar.iter().zip(br) {
        s += x * y;
    }
    s
}

fn uygula(v: f32, e: Etkin) -> f32 {
    match e {
        Etkin::Yok => v,
        Etkin::Relu => v.max(0.0),
        Etkin::Relu6 => v.clamp(0.0, 6.0),
    }
}

/// TensorFlow SAME dolgusu: baştaki dolgu (fazlası sona gider).
fn bas_dolgu(giris: usize, cikis: usize, cekirdek: usize, adim: usize, ayni: bool) -> usize {
    if !ayni {
        return 0;
    }
    (((cikis - 1) * adim + cekirdek).saturating_sub(giris)) / 2
}

#[allow(clippy::too_many_arguments)]
fn conv(
    x: &[f32],
    (ih, iw, ic): (usize, usize, usize),
    w: &[f32],
    (kh, kw): (usize, usize),
    b: Option<&[f32]>,
    (oh, ow, oc): (usize, usize, usize),
    (sh, sw): (usize, usize),
    ayni: bool,
    e: Etkin,
) -> Vec<f32> {
    let mut y = vec![0f32; oh * ow * oc];
    let (py, px) = (bas_dolgu(ih, oh, kh, sh, ayni), bas_dolgu(iw, ow, kw, sw, ayni));
    let mut topla = vec![0f32; oc];
    for oy in 0..oh {
        for ox in 0..ow {
            match b {
                Some(b) => topla.copy_from_slice(&b[..oc]),
                None => topla.fill(0.0),
            }
            for ky in 0..kh {
                let iy = (oy * sh + ky) as isize - py as isize;
                if iy < 0 || iy >= ih as isize {
                    continue;
                }
                for kx in 0..kw {
                    let ix = (ox * sw + kx) as isize - px as isize;
                    if ix < 0 || ix >= iw as isize {
                        continue;
                    }
                    let p = &x[(iy as usize * iw + ix as usize) * ic..][..ic];
                    let wb = &w[(ky * kw + kx) * ic * oc..][..ic * oc];
                    for (&a, wr) in p.iter().zip(wb.chunks_exact(oc)) {
                        for (t, &k) in topla.iter_mut().zip(wr) {
                            *t += a * k;
                        }
                    }
                }
            }
            let cik = &mut y[(oy * ow + ox) * oc..][..oc];
            for (c, t) in cik.iter_mut().zip(&topla) {
                *c = uygula(*t, e);
            }
        }
    }
    y
}

#[allow(clippy::too_many_arguments)]
fn derinlik(
    x: &[f32],
    (ih, iw, ic): (usize, usize, usize),
    w: &[f32],
    (kh, kw): (usize, usize),
    b: Option<&[f32]>,
    (oh, ow, oc): (usize, usize, usize),
    (sh, sw): (usize, usize),
    ayni: bool,
    m: usize,
    e: Etkin,
) -> Vec<f32> {
    let mut y = vec![0f32; oh * ow * oc];
    let (py, px) = (bas_dolgu(ih, oh, kh, sh, ayni), bas_dolgu(iw, ow, kw, sw, ayni));
    for oy in 0..oh {
        for ox in 0..ow {
            let cik = &mut y[(oy * ow + ox) * oc..][..oc];
            match b {
                Some(b) => cik.copy_from_slice(&b[..oc]),
                None => cik.fill(0.0),
            }
            for ky in 0..kh {
                let iy = (oy * sh + ky) as isize - py as isize;
                if iy < 0 || iy >= ih as isize {
                    continue;
                }
                for kx in 0..kw {
                    let ix = (ox * sw + kx) as isize - px as isize;
                    if ix < 0 || ix >= iw as isize {
                        continue;
                    }
                    let p = &x[(iy as usize * iw + ix as usize) * ic..][..ic];
                    let wk = &w[(ky * kw + kx) * oc..][..oc];
                    if m == 1 {
                        for ((c, a), k) in cik.iter_mut().zip(p).zip(wk) {
                            *c += a * k;
                        }
                    } else {
                        for (o, c) in cik.iter_mut().enumerate() {
                            *c += p[o / m] * wk[o];
                        }
                    }
                }
            }
            for c in cik.iter_mut() {
                *c = uygula(*c, e);
            }
        }
    }
    y
}

/// Eleman eleman işlem; b, a'nın son ekseniyle aynı boydaysa (ör. [1,1,1,C]) yayılır.
fn ikili(a: &[f32], b: &[f32], f: impl Fn(f32, f32) -> f32, e: Etkin) -> Vec<f32> {
    let (uzun, kisa, ters) = if a.len() >= b.len() { (a, b, false) } else { (b, a, true) };
    if kisa.is_empty() || uzun.len() % kisa.len() != 0 {
        return a.to_vec();
    }
    let mut y = Vec::with_capacity(uzun.len());
    for p in uzun.chunks_exact(kisa.len()) {
        if ters {
            y.extend(kisa.iter().zip(p).map(|(&p, &q)| uygula(f(p, q), e)));
        } else {
            y.extend(p.iter().zip(kisa).map(|(&p, &q)| uygula(f(p, q), e)));
        }
    }
    y
}

fn buyut(x: &[f32], (ih, iw, c): (usize, usize, usize), (oh, ow, _): (usize, usize, usize), hizali: bool, yarim: bool) -> Vec<f32> {
    let olcek = |i: usize, o: usize| -> f32 {
        if hizali && o > 1 {
            (i - 1) as f32 / (o - 1) as f32
        } else {
            i as f32 / o as f32
        }
    };
    let (oy_, ox_) = (olcek(ih, oh), olcek(iw, ow));
    let kaynak = |d: usize, s: f32, n: usize| -> (usize, usize, f32) {
        let f = if yarim { (d as f32 + 0.5) * s - 0.5 } else { d as f32 * s };
        let alt = f.floor();
        let i0 = (alt.max(0.0) as usize).min(n - 1);
        let i1 = (f.ceil().max(0.0) as usize).min(n - 1);
        (i0, i1, f - alt)
    };
    let mut y = vec![0f32; oh * ow * c];
    for oy in 0..oh {
        let (y0, y1, dy) = kaynak(oy, oy_, ih);
        for ox in 0..ow {
            let (x0, x1, dx) = kaynak(ox, ox_, iw);
            let p00 = &x[(y0 * iw + x0) * c..][..c];
            let p01 = &x[(y0 * iw + x1) * c..][..c];
            let p10 = &x[(y1 * iw + x0) * c..][..c];
            let p11 = &x[(y1 * iw + x1) * c..][..c];
            let cik = &mut y[(oy * ow + ox) * c..][..c];
            for k in 0..c {
                let ust = p00[k] + (p01[k] - p00[k]) * dx;
                let alt = p10[k] + (p11[k] - p10[k]) * dx;
                cik[k] = ust + (alt - ust) * dy;
            }
        }
    }
    y
}

#[allow(clippy::too_many_arguments)]
fn ters_conv(
    x: &[f32],
    (ih, iw, ic): (usize, usize, usize),
    w: &[f32],
    (kh, kw): (usize, usize),
    b: &[f32],
    (oh, ow, oc): (usize, usize, usize),
    (sh, sw): (usize, usize),
    ayni: bool,
) -> Vec<f32> {
    let mut y = vec![0f32; oh * ow * oc];
    for p in y.chunks_exact_mut(oc) {
        p.copy_from_slice(&b[..oc]);
    }
    // SAME: tam çıktı (ih-1)*s+k; fazlası ikiye bölünüp baştan kırpılır
    let (py, px) = if ayni {
        ((((ih - 1) * sh + kh).saturating_sub(oh)) / 2, (((iw - 1) * sw + kw).saturating_sub(ow)) / 2)
    } else {
        (0, 0)
    };
    for iy in 0..ih {
        for ix in 0..iw {
            let p = &x[(iy * iw + ix) * ic..][..ic];
            for ky in 0..kh {
                let oy = (iy * sh + ky) as isize - py as isize;
                if oy < 0 || oy >= oh as isize {
                    continue;
                }
                for kx in 0..kw {
                    let ox = (ix * sw + kx) as isize - px as isize;
                    if ox < 0 || ox >= ow as isize {
                        continue;
                    }
                    let cik = &mut y[(oy as usize * ow + ox as usize) * oc..][..oc];
                    for (o, c) in cik.iter_mut().enumerate() {
                        let wk = &w[((o * kh + ky) * kw + kx) * ic..][..ic];
                        *c += nokta(p, wk);
                    }
                }
            }
        }
    }
    y
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn yarim_duyarlik() {
        assert_eq!(f16_den_f32(0x3c00), 1.0);
        assert_eq!(f16_den_f32(0xc000), -2.0);
        assert_eq!(f16_den_f32(0x0000), 0.0);
        assert!((f16_den_f32(0x0001) - 5.960_464_5e-8).abs() < 1e-12);
    }

    #[test]
    fn same_dolgu() {
        assert_eq!(bas_dolgu(144, 72, 3, 2, true), 0);
        assert_eq!(bas_dolgu(18, 9, 5, 2, true), 1);
        assert_eq!(bas_dolgu(18, 18, 3, 1, true), 1);
    }
}
