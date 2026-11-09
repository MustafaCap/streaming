//! WASAPI ile ses cihazları: listeleme, yakalama (mikrofon / hoparlör loopback) ve çalma (CABLE Input).
//! Paylaşımlı mod + AUTOCONVERTPCM: Windows sesi bizim istediğimiz 48 kHz stereo biçime kendisi çevirir.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use windows::core::{Interface, HSTRING, PWSTR};
use windows::Win32::Foundation::{CloseHandle, HANDLE, WAIT_OBJECT_0};
use windows::Win32::Media::Audio::*;
use windows::Win32::System::Com::{CoCreateInstance, CLSCTX_ALL, STGM_READ};
use windows::Win32::System::Threading::{CreateEventW, WaitForSingleObject};
use windows::Win32::Foundation::PROPERTYKEY;

use super::{KANAL, ORNEKLEME};

/// PKEY_Device_FriendlyName
const AD_ANAHTARI: PROPERTYKEY = PROPERTYKEY {
    fmtid: windows::core::GUID::from_u128(0xa45c254e_df1c_4efd_8020_67d146a850e0),
    pid: 14,
};

pub const WAVE_FORMAT_PCM: u16 = 1;
pub const WAVE_FORMAT_IEEE_FLOAT: u16 = 3;

#[derive(Clone, Debug)]
pub struct Cihaz {
    pub kimlik: String,
    pub ad: String,
}

pub fn kablo_mu(ad: &str) -> bool {
    ad.to_lowercase().contains("cable")
}

fn numaralayici() -> windows::core::Result<IMMDeviceEnumerator> {
    crate::win::com_baslat();
    unsafe { CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL) }
}

unsafe fn cihaz_bilgisi(c: &IMMDevice) -> Option<Cihaz> {
    let id: PWSTR = c.GetId().ok()?;
    let kimlik = id.to_string().ok()?;
    windows::Win32::System::Com::CoTaskMemFree(Some(id.0 as _));
    let depo = c.OpenPropertyStore(STGM_READ).ok()?;
    let deger = depo.GetValue(&AD_ANAHTARI).ok()?;
    let ad = deger.to_string();
    Some(Cihaz { kimlik, ad })
}

/// Etkin cihazlar. giris: mikrofonlar, değilse hoparlörler/çıkışlar.
pub fn cihazlar(giris: bool) -> Vec<Cihaz> {
    let Ok(n) = numaralayici() else { return vec![] };
    unsafe {
        let Ok(l) = n.EnumAudioEndpoints(if giris { eCapture } else { eRender }, DEVICE_STATE_ACTIVE) else { return vec![] };
        let sayi = l.GetCount().unwrap_or(0);
        (0..sayi).filter_map(|i| l.Item(i).ok()).filter_map(|c| cihaz_bilgisi(&c)).collect()
    }
}

pub fn varsayilan(giris: bool) -> Option<Cihaz> {
    let n = numaralayici().ok()?;
    unsafe {
        let c = n.GetDefaultAudioEndpoint(if giris { eCapture } else { eRender }, eConsole).ok()?;
        cihaz_bilgisi(&c)
    }
}

pub fn bicim(etiket: u16, bit: u16) -> WAVEFORMATEX {
    let blok = KANAL as u16 * bit / 8;
    WAVEFORMATEX {
        wFormatTag: etiket,
        nChannels: KANAL as u16,
        nSamplesPerSec: ORNEKLEME,
        nAvgBytesPerSec: ORNEKLEME * blok as u32,
        nBlockAlign: blok,
        wBitsPerSample: bit,
        cbSize: 0,
    }
}

unsafe fn istemci_ac(kimlik: &str) -> windows::core::Result<IAudioClient> {
    let n = numaralayici()?;
    let c = n.GetDevice(&HSTRING::from(kimlik))?;
    c.Activate::<IAudioClient>(CLSCTX_ALL, None)
}

/// Akışın sağlığı: son veri zamanı (ms, Instant tabanına göre) ve çalışıyor bayrağı.
pub struct Akis {
    calis: Arc<AtomicBool>,
    son_ms: Arc<AtomicU64>,
    taban: Instant,
    is: Option<JoinHandle<()>>,
    pub hata: Arc<std::sync::Mutex<String>>,
}

impl Akis {
    pub fn calisiyor(&self) -> bool {
        self.is.as_ref().is_some_and(|i| !i.is_finished())
    }
    /// Son `zaman_asimi` içinde cihazdan veri/olay geldi mi.
    pub fn saglikli(&self, zaman_asimi: Duration) -> bool {
        self.calisiyor() && (self.taban.elapsed().as_millis() as u64).saturating_sub(self.son_ms.load(Ordering::Relaxed)) < zaman_asimi.as_millis() as u64
    }
}

impl Drop for Akis {
    fn drop(&mut self) {
        self.calis.store(false, Ordering::SeqCst);
        if let Some(i) = self.is.take() {
            let bitis = Instant::now() + Duration::from_secs(2);
            while !i.is_finished() && Instant::now() < bitis {
                std::thread::sleep(Duration::from_millis(5));
            }
        }
    }
}

/// Başlatılmış (Initialize edilmiş) bir yakalama istemcisini olay döngüsüyle okur.
/// `yaz` her pakette stereo f32 örneklerle çağrılır. `hazir`: Start başarılı olunca gönderilir.
pub fn yakalama_dongusu(
    olustur: impl FnOnce() -> Result<(IAudioClient, HANDLE, u16), String> + Send + 'static,
    mut yaz: impl FnMut(&[f32]) + Send + 'static,
    ad: &str,
) -> Result<Akis, String> {
    let calis = Arc::new(AtomicBool::new(true));
    let son_ms = Arc::new(AtomicU64::new(0));
    let taban = Instant::now();
    let hata: Arc<std::sync::Mutex<String>> = Default::default();
    let (c2, s2, h2) = (calis.clone(), son_ms.clone(), hata.clone());
    let (hazir_tx, hazir_rx) = std::sync::mpsc::channel::<Result<(), String>>();
    let is = std::thread::Builder::new()
        .name(ad.into())
        .spawn(move || unsafe {
            crate::win::com_baslat();
            let (istemci, olay, etiket) = match olustur() {
                Ok(x) => x,
                Err(e) => {
                    let _ = hazir_tx.send(Err(e));
                    return;
                }
            };
            let yakalayici: IAudioCaptureClient = match istemci.GetService() {
                Ok(y) => y,
                Err(e) => {
                    let _ = hazir_tx.send(Err(e.to_string()));
                    let _ = CloseHandle(olay);
                    return;
                }
            };
            if let Err(e) = istemci.Start() {
                let _ = hazir_tx.send(Err(e.to_string()));
                let _ = CloseHandle(olay);
                return;
            }
            let _ = hazir_tx.send(Ok(()));
            let mut blok: Vec<f32> = Vec::with_capacity(4096);
            s2.store(taban.elapsed().as_millis() as u64, Ordering::Relaxed);
            'dongu: while c2.load(Ordering::Relaxed) {
                let r = WaitForSingleObject(olay, 100);
                if r == WAIT_OBJECT_0 {
                    s2.store(taban.elapsed().as_millis() as u64, Ordering::Relaxed);
                }
                loop {
                    let paket = match yakalayici.GetNextPacketSize() {
                        Ok(p) => p,
                        Err(e) => {
                            *h2.lock().unwrap() = e.to_string();
                            break 'dongu;
                        }
                    };
                    if paket == 0 {
                        break;
                    }
                    let mut veri = std::ptr::null_mut();
                    let mut n = 0u32;
                    let mut bayrak = 0u32;
                    if yakalayici.GetBuffer(&mut veri, &mut n, &mut bayrak, None, None).is_err() {
                        break 'dongu;
                    }
                    blok.clear();
                    let ornek = n as usize * KANAL;
                    if bayrak & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 || veri.is_null() {
                        blok.resize(ornek, 0.0);
                    } else if etiket == WAVE_FORMAT_IEEE_FLOAT {
                        blok.extend_from_slice(std::slice::from_raw_parts(veri as *const f32, ornek));
                    } else {
                        blok.extend(std::slice::from_raw_parts(veri as *const i16, ornek).iter().map(|&s| s as f32 / 32768.0));
                    }
                    let _ = yakalayici.ReleaseBuffer(n);
                    if n > 0 {
                        yaz(&blok);
                    }
                }
            }
            let _ = istemci.Stop();
            let _ = CloseHandle(olay);
        })
        .map_err(|e| e.to_string())?;
    match hazir_rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(())) => Ok(Akis { calis, son_ms, taban, is: Some(is), hata }),
        Ok(Err(e)) => Err(e),
        Err(_) => {
            calis.store(false, Ordering::SeqCst);
            Err("Windows ses arayüzü zamanında cevap vermedi".into())
        }
    }
}

/// Mikrofon ya da hoparlör (loopback) yakalama.
pub fn cihaz_yakala(kimlik: &str, loopback: bool, yaz: impl FnMut(&[f32]) + Send + 'static) -> Result<Akis, String> {
    let kimlik = kimlik.to_string();
    yakalama_dongusu(
        move || unsafe {
            let istemci = istemci_ac(&kimlik).map_err(|e| e.to_string())?;
            let fmt = bicim(WAVE_FORMAT_IEEE_FLOAT, 32);
            let mut bayrak = AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
            if loopback {
                bayrak |= AUDCLNT_STREAMFLAGS_LOOPBACK;
            }
            istemci.Initialize(AUDCLNT_SHAREMODE_SHARED, bayrak, 200_000, 0, &fmt, None).map_err(|e| e.to_string())?;
            let olay = CreateEventW(None, false, false, None).map_err(|e| e.to_string())?;
            istemci.SetEventHandle(olay).map_err(|e| e.to_string())?;
            Ok((istemci, olay, WAVE_FORMAT_IEEE_FLOAT))
        },
        yaz,
        if loopback { "ses-hoparlor" } else { "ses-mikrofon" },
    )
}

/// Çıkış cihazına (CABLE Input) çalma. `doldur(n)` n örneklik stereo blok üretir (mikser).
/// Tampon ~30 ms dolu tutulur: hem cızırtısız hem gecikmesi düşük (Zoom'da ses görüntünün gerisinde kalmasın).
pub fn cal(kimlik: &str, mut doldur: impl FnMut(usize, &mut Vec<f32>) + Send + 'static) -> Result<Akis, String> {
    let kimlik = kimlik.to_string();
    let calis = Arc::new(AtomicBool::new(true));
    let son_ms = Arc::new(AtomicU64::new(0));
    let taban = Instant::now();
    let hata: Arc<std::sync::Mutex<String>> = Default::default();
    let (c2, s2, h2) = (calis.clone(), son_ms.clone(), hata.clone());
    let (hazir_tx, hazir_rx) = std::sync::mpsc::channel::<Result<(), String>>();
    let is = std::thread::Builder::new()
        .name("ses-kablo".into())
        .spawn(move || unsafe {
            crate::win::com_baslat();
            let kur = || -> Result<(IAudioClient, IAudioRenderClient, HANDLE, u32), String> {
                let istemci = istemci_ac(&kimlik).map_err(|e| e.to_string())?;
                let fmt = bicim(WAVE_FORMAT_IEEE_FLOAT, 32);
                let bayrak = AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
                istemci.Initialize(AUDCLNT_SHAREMODE_SHARED, bayrak, 300_000, 0, &fmt, None).map_err(|e| e.to_string())?;
                let olay = CreateEventW(None, false, false, None).map_err(|e| e.to_string())?;
                istemci.SetEventHandle(olay).map_err(|e| e.to_string())?;
                let boyut = istemci.GetBufferSize().map_err(|e| e.to_string())?;
                let calici: IAudioRenderClient = istemci.GetService().map_err(|e| e.to_string())?;
                Ok((istemci, calici, olay, boyut))
            };
            let (istemci, calici, olay, boyut) = match kur() {
                Ok(x) => x,
                Err(e) => {
                    let _ = hazir_tx.send(Err(e));
                    return;
                }
            };
            if let Err(e) = istemci.Start() {
                let _ = hazir_tx.send(Err(e.to_string()));
                return;
            }
            let _ = hazir_tx.send(Ok(()));
            let hedef_dolu = (ORNEKLEME as usize * 3 / 100).min(boyut as usize); // 30 ms
            let mut blok = Vec::with_capacity(4096);
            while c2.load(Ordering::Relaxed) {
                let _ = WaitForSingleObject(olay, 100);
                s2.store(taban.elapsed().as_millis() as u64, Ordering::Relaxed);
                let dolu = match istemci.GetCurrentPadding() {
                    Ok(p) => p as usize,
                    Err(e) => {
                        *h2.lock().unwrap() = e.to_string();
                        break;
                    }
                };
                let mut bos = hedef_dolu.saturating_sub(dolu);
                while bos >= super::BLOK {
                    let n = super::BLOK;
                    blok.clear();
                    doldur(n, &mut blok);
                    let Ok(p) = calici.GetBuffer(n as u32) else { break };
                    std::ptr::copy_nonoverlapping(blok.as_ptr(), p as *mut f32, (n * KANAL).min(blok.len()));
                    let _ = calici.ReleaseBuffer(n as u32, 0);
                    bos -= n;
                }
            }
            let _ = istemci.Stop();
            let _ = CloseHandle(olay);
        })
        .map_err(|e| e.to_string())?;
    match hazir_rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(())) => Ok(Akis { calis, son_ms, taban, is: Some(is), hata }),
        Ok(Err(e)) => Err(e),
        Err(_) => {
            calis.store(false, Ordering::SeqCst);
            Err("Windows ses arayüzü zamanında cevap vermedi".into())
        }
    }
}

#[allow(dead_code)]
fn _kullanilmayan() -> Option<IAudioClient> {
    let x: Option<IAudioClient> = None;
    x.and_then(|c| c.cast().ok())
}
