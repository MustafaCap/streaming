//! OBS Virtual Camera sürücüsüne doğrudan görüntü gönderir (Python outputs/obs_kamera.py).
//!
//! OBS Studio'nun kurduğu sürücü görüntüyü "OBSVirtualCamVideo" adlı paylaşılan bellekten okur.
//! Biz o belleği oluşturup kareleri NV12 olarak yazarız. Biçim OBS'nin shared-memory-queue koduyla
//! aynı (OBS: GPLv2 veya sonrası, GPLv3 ile uyumlu).
//!
//!   Başlık (80 bayt, 96'ya yuvarlanır)
//!      0 u32 write_idx | 4 u32 read_idx | 8 u32 state (1 başlıyor, 2 hazır, 3 duruyor)
//!     12 u32 offsets[3] | 24 u32 type (0 video) | 28 u32 cx | 32 u32 cy
//!     40 u64 interval (100 ns) | 48 u32 reserved[8]
//!   Üç kare yuvası (32 bayta hizalı): [u64 zaman + 24 bayt boşluk][NV12]

pub const BELLEK_ADI: &str = "OBSVirtualCamVideo";
pub const SURUCU_CLSID: &str = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}";
pub const BASLIK_BOYUTU: usize = 96;
pub const KARE_BASLIGI: usize = 32;
pub const DURUM_BASLIYOR: u32 = 1;
pub const DURUM_HAZIR: u32 = 2;
pub const DURUM_DURUYOR: u32 = 3;

fn hizala(n: usize) -> usize {
    (n + 31) & !31
}

/// (üç yuvanın ofseti, toplam bellek boyutu, bir NV12 karenin boyutu)
pub fn bellek_duzeni(w: u32, h: u32) -> ([usize; 3], usize, usize) {
    let kare = (w * h * 3 / 2) as usize;
    let mut ofsetler = [0usize; 3];
    let mut boyut = BASLIK_BOYUTU;
    for o in ofsetler.iter_mut() {
        *o = boyut;
        boyut = hizala(boyut + KARE_BASLIGI + kare);
    }
    (ofsetler, boyut, kare)
}

/// Verilen bellekteki OBS kare kuyruğu (bellek en az `bellek_duzeni().1` bayt olmalı).
pub struct KareKuyrugu {
    adres: *mut u8,
    pub w: u32,
    pub h: u32,
    ofsetler: [usize; 3],
    kare_boyutu: usize,
    saat: std::time::Instant,
}

unsafe impl Send for KareKuyrugu {}

impl KareKuyrugu {
    /// # Safety
    /// `adres` en az `bellek_duzeni(w, h).1` bayt yazılabilir bellek göstermeli ve kuyruk yaşadıkça geçerli kalmalı.
    pub unsafe fn yeni(adres: *mut u8, w: u32, h: u32, fps: f64) -> Result<Self, String> {
        if w % 2 != 0 || h % 2 != 0 {
            return Err("Genişlik ve yükseklik çift sayı olmalı".into());
        }
        let (ofsetler, _, kare_boyutu) = bellek_duzeni(w, h);
        std::ptr::write_bytes(adres, 0, BASLIK_BOYUTU);
        let k = KareKuyrugu { adres, w, h, ofsetler, kare_boyutu, saat: std::time::Instant::now() };
        k.yaz32(8, DURUM_BASLIYOR);
        for (i, o) in ofsetler.iter().enumerate() {
            k.yaz32(12 + 4 * i, *o as u32);
        }
        k.yaz32(24, 0);
        k.yaz32(28, w);
        k.yaz32(32, h);
        std::ptr::write_unaligned(adres.add(40) as *mut u64, (10_000_000.0 / fps.max(1.0)) as u64);
        Ok(k)
    }

    fn yaz32(&self, ofset: usize, deger: u32) {
        unsafe { std::ptr::write_volatile(self.adres.add(ofset) as *mut u32, deger) }
    }
    fn oku32(&self, ofset: usize) -> u32 {
        unsafe { std::ptr::read_volatile(self.adres.add(ofset) as *const u32) }
    }

    /// NV12 kareyi sıradaki yuvaya yazar; okuyucu hep en son tamamlanan kareyi alır.
    pub fn yaz(&mut self, nv12: &[u8]) {
        let sayac = self.oku32(0).wrapping_add(1);
        self.yaz32(0, sayac);
        let yuva = (sayac % 3) as usize;
        let o = self.ofsetler[yuva];
        let n = self.kare_boyutu.min(nv12.len());
        unsafe {
            std::ptr::copy_nonoverlapping(nv12.as_ptr(), self.adres.add(o + KARE_BASLIGI), n);
            std::ptr::write_unaligned(self.adres.add(o) as *mut u64, self.saat.elapsed().as_nanos() as u64);
        }
        std::sync::atomic::fence(std::sync::atomic::Ordering::Release);
        self.yaz32(4, sayac); // kare tamamlandı: okuyucu artık bunu alır
        self.yaz32(8, DURUM_HAZIR);
    }

    pub fn durdur(&mut self) {
        self.yaz32(8, DURUM_DURUYOR);
    }
}

/// Sanal kamera çıkışı: paylaşılan belleği açar, `gonder` ile kare yazılır.
pub struct ObsSanalKamera {
    kuyruk: KareKuyrugu,
    #[cfg(windows)]
    bellek: crate::win::PaylasilanBellek,
}

impl ObsSanalKamera {
    #[cfg(windows)]
    pub fn ac(w: u32, h: u32, fps: f64) -> Result<Self, String> {
        if !crate::win::clsid_kayitli(SURUCU_CLSID) {
            return Err("OBS Virtual Camera sürücüsü bulunamadı. OBS Studio'yu kur, bir kez 'Sanal Kamerayı Başlat'a bas ve kapat.".into());
        }
        let (_, boyut, _) = bellek_duzeni(w, h);
        let bellek = crate::win::PaylasilanBellek::olustur(BELLEK_ADI, boyut)?;
        let kuyruk = unsafe { KareKuyrugu::yeni(bellek.adres(), w, h, fps)? };
        Ok(ObsSanalKamera { kuyruk, bellek })
    }

    #[cfg(not(windows))]
    pub fn ac(_w: u32, _h: u32, _fps: f64) -> Result<Self, String> {
        Err("Sanal kamera sadece Windows'ta çalışır".into())
    }

    pub fn gonder(&mut self, kare: &crate::kare::Kare) -> Result<(), String> {
        if kare.boyut() != (self.kuyruk.w, self.kuyruk.h) {
            let k = crate::kare::olcekle(kare, self.kuyruk.w, self.kuyruk.h);
            self.kuyruk.yaz(k.nv12());
        } else {
            self.kuyruk.yaz(kare.nv12());
        }
        Ok(())
    }
}

impl Drop for ObsSanalKamera {
    fn drop(&mut self) {
        self.kuyruk.durdur(); // sürücü OBS'nin bekleme görüntüsüne döner
        #[cfg(windows)]
        let _ = &self.bellek;
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn duzen_python_ile_ayni() {
        // Python: bellek_duzeni(1280, 720) -> ([96, 1382528, 2764960], 4147392, 1382400)
        let (o, b, k) = bellek_duzeni(1280, 720);
        assert_eq!(k, 1382400);
        assert_eq!(o, [96, 1382528, 2764960]);
        assert_eq!(b, 4147392);
    }

    #[test]
    fn kuyruk_yazar() {
        let (_, boyut, kare) = bellek_duzeni(4, 2);
        let mut bellek = vec![0u8; boyut];
        let mut q = unsafe { KareKuyrugu::yeni(bellek.as_mut_ptr(), 4, 2, 30.0).unwrap() };
        q.yaz(&vec![7u8; kare]);
        let oku = |o: usize| u32::from_le_bytes(bellek[o..o + 4].try_into().unwrap());
        assert_eq!(oku(0), 1);
        assert_eq!(oku(4), 1);
        assert_eq!(oku(8), DURUM_HAZIR);
        assert_eq!(oku(28), 4);
        let o1 = oku(16) as usize;
        assert_eq!(bellek[o1 + KARE_BASLIGI], 7);
    }
}
