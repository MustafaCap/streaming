//! Uygulama bazlı bilgisayar sesi — Windows "Process Loopback" (Win10 2004+ / Win11).
//! Python capture/app_audio.py'nin karşılığı.
//!
//! Hoparlör loopback her şeyi yakalar; Zoom'daki karşı tarafın sesi de geri gider ve yankı olur.
//! "auto" modda ses çıkaran her uygulama ayrı ayrı "dahil" moduyla yakalanır; Zoom/Discord ve kendi
//! sürecimiz (ve onların üst/alt süreçleri) bu listeye hiç girmez (1.0.0 testinde bulunan yankı).

use crate::dil::t;
use crate::trf;
use std::collections::{HashMap, HashSet};
use std::sync::mpsc::{sync_channel, SyncSender};

use windows::core::{implement, Interface};
use windows::Win32::Foundation::CloseHandle;
use windows::Win32::Media::Audio::*;
use windows::Win32::System::Com::StructuredStorage::{PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0};
use windows::Win32::System::Com::{CoCreateInstance, BLOB, CLSCTX_ALL};
use windows::Win32::System::Diagnostics::ToolHelp::{CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS};
use windows::Win32::System::Threading::CreateEventW;
use windows::Win32::System::Variant::VT_BLOB;

use super::wasapi::{self, Akis, WAVE_FORMAT_PCM};

#[implement(IActivateAudioInterfaceCompletionHandler)]
struct Tamamlayici {
    tx: SyncSender<Result<IAudioClient, String>>,
}

impl IActivateAudioInterfaceCompletionHandler_Impl for Tamamlayici_Impl {
    fn ActivateCompleted(&self, islem: windows::core::Ref<'_, IActivateAudioInterfaceAsyncOperation>) -> windows::core::Result<()> {
        let sonuc = (|| unsafe {
            let islem = islem.ok().map_err(|e| e.to_string())?;
            let mut hr = windows::core::HRESULT(0);
            let mut arayuz: Option<windows::core::IUnknown> = None;
            islem.GetActivateResult(&mut hr, &mut arayuz).map_err(|e| e.to_string())?;
            hr.ok().map_err(|e| e.to_string())?;
            arayuz.ok_or("arayüz yok".to_string())?.cast::<IAudioClient>().map_err(|e| e.to_string())
        })();
        let _ = self.tx.try_send(sonuc);
        Ok(())
    }
}

unsafe fn surec_istemcisi(pid: u32, haric: bool) -> Result<IAudioClient, String> {
    let mut param = AUDIOCLIENT_ACTIVATION_PARAMS { ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK, ..Default::default() };
    param.Anonymous.ProcessLoopbackParams = AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
        TargetProcessId: pid,
        ProcessLoopbackMode: if haric { PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE } else { PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE },
    };
    // `windows` crate'i PROPVARIANT için Drop'ta PropVariantClear çağırır; VT_BLOB'da bu, blob
    // işaretçisini CoTaskMemFree ile serbest bırakmak demek. Bizim blob'umuz yığındaki `param`,
    // heap'te değil: serbest bırakılırsa Windows heap bozulmasıyla (0xc0000374) uygulamayı kapatır.
    // O yüzden asla drop edilmez.
    let pv = std::mem::ManuallyDrop::new(PROPVARIANT {
        Anonymous: PROPVARIANT_0 {
            Anonymous: std::mem::ManuallyDrop::new(PROPVARIANT_0_0 {
                vt: VT_BLOB,
                Anonymous: PROPVARIANT_0_0_0 {
                    blob: BLOB { cbSize: std::mem::size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>() as u32, pBlobData: &mut param as *mut _ as *mut u8 },
                },
                ..Default::default()
            }),
        },
    });
    let (tx, rx) = sync_channel(1);
    let isleyici: IActivateAudioInterfaceCompletionHandler = Tamamlayici { tx }.into();
    let _islem = ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, &IAudioClient::IID, Some(&*pv as *const PROPVARIANT), &isleyici)
        .map_err(|e| e.to_string())?;
    rx.recv_timeout(std::time::Duration::from_secs(5)).map_err(|_| t("Windows 5 saniye içinde cevap vermedi").to_string())?
}

/// Bir sürecin (ve alt süreçlerinin) sesini yakalar (`haric` ise o süreç dışındaki her şeyi).
pub fn surec_yakala(pid: u32, haric: bool, yaz: impl FnMut(&[f32]) + Send + 'static) -> Result<Akis, String> {
    let akis = wasapi::yakalama_dongusu(
        move || unsafe {
            let istemci = surec_istemcisi(pid, haric)?;
            let fmt = wasapi::bicim(WAVE_FORMAT_PCM, 16);
            istemci
                .Initialize(
                    AUDCLNT_SHAREMODE_SHARED,
                    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                    200_000,
                    0,
                    &fmt,
                    None,
                )
                .map_err(|e| e.to_string())?;
            let olay = CreateEventW(None, false, false, None).map_err(|e| e.to_string())?;
            istemci.SetEventHandle(olay).map_err(|e| e.to_string())?;
            Ok((istemci, olay, WAVE_FORMAT_PCM))
        },
        yaz,
        "surec-sesi",
    )
    .map_err(|e| trf!("Uygulama sesi yakalanamadı: {}", e))?;
    log::info!("Uygulama sesi yakalanıyor: pid={pid}, {}", if haric { "hariç" } else { "sadece bu" });
    Ok(akis)
}

/// {pid: (ebeveyn pid, küçük harfli ad)} — bütün süreçler.
pub fn surec_tablosu() -> HashMap<u32, (u32, String)> {
    let mut t = HashMap::new();
    unsafe {
        let Ok(anlik) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else { return t };
        let mut g = PROCESSENTRY32W { dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32, ..Default::default() };
        let mut ok = Process32FirstW(anlik, &mut g).is_ok();
        while ok {
            let ad = String::from_utf16_lossy(&g.szExeFile);
            t.insert(g.th32ProcessID, (g.th32ParentProcessID, ad.trim_end_matches('\0').to_lowercase()));
            ok = Process32NextW(anlik, &mut g).is_ok();
        }
        let _ = CloseHandle(anlik);
    }
    t
}

/// Adı verilen uygulamanın ana süreci (Chrome/Edge gibi çok süreçlilerde en üstteki).
pub fn surec_bul(ad: &str, tablo: &HashMap<u32, (u32, String)>) -> Option<u32> {
    let ad = ad.to_lowercase();
    let adaylar: Vec<(u32, u32)> = tablo.iter().filter(|(_, (_, a))| *a == ad).map(|(p, (e, _))| (*p, *e)).collect();
    let pidler: HashSet<u32> = adaylar.iter().map(|(p, _)| *p).collect();
    adaylar.iter().find(|(_, e)| !pidler.contains(e)).or(adaylar.first()).map(|(p, _)| *p)
}

/// Varsayılan hoparlörde ses oturumu açık olan süreçler (Windows ses karıştırıcısındakiler).
pub fn ses_oturumu_pidleri() -> Result<HashSet<u32>, String> {
    unsafe {
        crate::win::com_baslat();
        let n: IMMDeviceEnumerator = CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL).map_err(|e| e.to_string())?;
        let c = n.GetDefaultAudioEndpoint(eRender, eMultimedia).map_err(|e| e.to_string())?;
        let y: IAudioSessionManager2 = c.Activate(CLSCTX_ALL, None).map_err(|e| e.to_string())?;
        let l = y.GetSessionEnumerator().map_err(|e| e.to_string())?;
        let mut p = HashSet::new();
        for i in 0..l.GetCount().unwrap_or(0) {
            let Ok(o) = l.GetSession(i) else { continue };
            let Ok(o2) = o.cast::<IAudioSessionControl2>() else { continue };
            if o2.GetState().map(|s| s == AudioSessionStateExpired).unwrap_or(true) {
                continue;
            }
            if let Ok(pid) = o2.GetProcessId() {
                if pid > 0 {
                    p.insert(pid);
                }
            }
        }
        Ok(p)
    }
}

pub use crate::ses::surec_secimi::{atalar, yakalanacak_surecler};
