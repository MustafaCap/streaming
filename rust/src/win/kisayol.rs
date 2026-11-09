//! RegisterHotKey ile global kısayollar. Kendi mesaj döngüsü olan bir iş parçacığında çalışır;
//! tuşlar değişince o iş parçacığına mesajla bildirilir.

use std::collections::HashMap;
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};

use windows::Win32::Foundation::{LPARAM, WPARAM};
use windows::Win32::System::Threading::GetCurrentThreadId;
use windows::Win32::UI::Input::KeyboardAndMouse::{RegisterHotKey, UnregisterHotKey, HOT_KEY_MODIFIERS};
use windows::Win32::UI::WindowsAndMessaging::{GetMessageW, PeekMessageW, PostThreadMessageW, MSG, PM_NOREMOVE, WM_APP, WM_HOTKEY, WM_QUIT};

use crate::kisayol::{birlesim_basili, fare_tusu, tus_coz, MOD_NOREPEAT};

fn tus_basili(vk: u32) -> bool {
    unsafe { windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(vk as i32) as u16 & 0x8000 != 0 }
}

/// Fare tuşlu kısayollar saniyede 50 kez yoklanır (fare kancası kurulmaz).
const YOKLAMA: std::time::Duration = std::time::Duration::from_millis(20);

enum Islem {
    Ayarla(String, HashMap<String, String>), // grup, komut -> tuş
    Kaldir(String),
}

pub struct KisayolYoneticisi {
    is_kimligi: u32,
    /// grup -> [(değiştiriciler, fare tuşu, komut)]
    fare: Arc<Mutex<HashMap<String, Vec<(u32, u32, String)>>>>,
    fare_calis: Arc<std::sync::atomic::AtomicBool>,
    tx: Sender<Islem>,
    /// tuşu kaydedilemeyen komutlar (başka program kullanıyor) -> açıklama
    pub hatalar: Arc<Mutex<HashMap<String, String>>>,
}

impl KisayolYoneticisi {
    /// `basildi(komut)` kısayol iş parçacığında çağrılır.
    pub fn baslat(basildi: impl Fn(&str) + Send + Sync + 'static) -> Self {
        let basildi = Arc::new(basildi);
        let fare: Arc<Mutex<HashMap<String, Vec<(u32, u32, String)>>>> = Default::default();
        let fare_calis = Arc::new(std::sync::atomic::AtomicBool::new(true));
        {
            let (fare, calis, basildi) = (fare.clone(), fare_calis.clone(), basildi.clone());
            std::thread::Builder::new()
                .name("fare-kisayollari".into())
                .spawn(move || {
                    let mut onceki: std::collections::HashSet<String> = Default::default();
                    while calis.load(std::sync::atomic::Ordering::Relaxed) {
                        let liste: Vec<(u32, u32, String)> = fare.lock().unwrap().values().flatten().cloned().collect();
                        let mut simdi = std::collections::HashSet::new();
                        for (m, vk, komut) in liste {
                            if birlesim_basili(m, vk, tus_basili) {
                                if !onceki.contains(&komut) {
                                    basildi(&komut); // basıldığı an bir kez
                                }
                                simdi.insert(komut);
                            }
                        }
                        onceki = simdi;
                        std::thread::sleep(YOKLAMA);
                    }
                })
                .ok();
        }
        let (fare2, basildi2) = (fare.clone(), basildi);
        let (tx, rx) = channel::<Islem>();
        let (kimlik_tx, kimlik_rx) = channel();
        let hatalar: Arc<Mutex<HashMap<String, String>>> = Default::default();
        let h2 = hatalar.clone();
        std::thread::Builder::new()
            .name("kisayollar".into())
            .spawn(move || unsafe {
                let mut msg = MSG::default();
                let _ = PeekMessageW(&mut msg, None, 0, 0, PM_NOREMOVE); // mesaj kuyruğu oluşsun
                let _ = kimlik_tx.send(GetCurrentThreadId());
                let mut gruplar: HashMap<String, Vec<(i32, String)>> = HashMap::new();
                let mut sonraki = 1i32;
                loop {
                    let r = GetMessageW(&mut msg, None, 0, 0);
                    if r.0 <= 0 || msg.message == WM_QUIT {
                        break;
                    }
                    if msg.message == WM_HOTKEY {
                        let id = msg.wParam.0 as i32;
                        if let Some(k) = gruplar.values().flatten().find(|(i, _)| *i == id).map(|(_, k)| k.clone()) {
                            basildi2(&k);
                        }
                    } else if msg.message == WM_APP {
                        while let Ok(is) = rx.try_recv() {
                            let grup = match &is {
                                Islem::Ayarla(g, _) | Islem::Kaldir(g) => g.clone(),
                            };
                            fare2.lock().unwrap().remove(&grup);
                            for (id, k) in gruplar.remove(&grup).unwrap_or_default() {
                                let _ = UnregisterHotKey(None, id);
                                h2.lock().unwrap().remove(&k);
                            }
                            if let Islem::Ayarla(g, tuslar) = is {
                                let mut liste = vec![];
                                for (komut, tus) in tuslar {
                                    if tus.trim().is_empty() {
                                        continue;
                                    }
                                    match tus_coz(&tus) {
                                        Ok((m, vk)) if fare_tusu(vk) => {
                                            fare2.lock().unwrap().entry(g.clone()).or_default().push((m, vk, komut));
                                        }
                                        Ok((m, vk)) => {
                                            let id = sonraki;
                                            sonraki += 1;
                                            if RegisterHotKey(None, id, HOT_KEY_MODIFIERS(m | MOD_NOREPEAT), vk).is_ok() {
                                                liste.push((id, komut));
                                            } else {
                                                log::warn!("Kısayol kaydedilemedi: {tus} ({komut}) başka bir program kullanıyor olabilir");
                                                h2.lock().unwrap().insert(komut, format!("{tus} başka bir program tarafından kullanılıyor"));
                                            }
                                        }
                                        Err(e) => {
                                            h2.lock().unwrap().insert(komut, e.0);
                                        }
                                    }
                                }
                                gruplar.insert(g, liste);
                            }
                        }
                    }
                }
                for (id, _) in gruplar.values().flatten() {
                    let _ = UnregisterHotKey(None, *id);
                }
            })
            .expect("kısayol iş parçacığı");
        let is_kimligi = kimlik_rx.recv().unwrap_or(0);
        KisayolYoneticisi { is_kimligi, fare, fare_calis, tx, hatalar }
    }

    fn uyandir(&self) {
        unsafe {
            let _ = PostThreadMessageW(self.is_kimligi, WM_APP, WPARAM(0), LPARAM(0));
        }
    }

    pub fn grup_ayarla(&self, grup: &str, tuslar: HashMap<String, String>) {
        let _ = self.tx.send(Islem::Ayarla(grup.into(), tuslar));
        self.uyandir();
    }

    pub fn grubu_kaldir(&self, grup: &str) {
        let _ = self.tx.send(Islem::Kaldir(grup.into()));
        self.uyandir();
    }
}

impl Drop for KisayolYoneticisi {
    fn drop(&mut self) {
        self.fare_calis.store(false, std::sync::atomic::Ordering::Relaxed);
        let _ = &self.fare;
        unsafe {
            let _ = PostThreadMessageW(self.is_kimligi, WM_QUIT, WPARAM(0), LPARAM(0));
        }
    }
}

/// Bas-konuş: ayarlanan tuş basılıyken mikrofon açık, bırakınca kapalı. RegisterHotKey "bırakıldı"
/// haberi vermediği için tuş durumu saniyede 50 kez GetAsyncKeyState ile okunur (tuş oyuna da gider).
pub struct BasKonus {
    calis: Arc<std::sync::atomic::AtomicBool>,
}

impl BasKonus {
    /// `degisti(basili)` durum değişince yoklama iş parçacığında çağrılır (başta bir kez false).
    pub fn baslat(tus: &str, degisti: impl Fn(bool) + Send + 'static) -> Result<BasKonus, String> {
        let (m, vk) = tus_coz(tus).map_err(|e| e.0)?;
        let calis = Arc::new(std::sync::atomic::AtomicBool::new(true));
        let c = calis.clone();
        std::thread::Builder::new()
            .name("bas-konus".into())
            .spawn(move || {
                let mut basili = false;
                degisti(false);
                while c.load(std::sync::atomic::Ordering::Relaxed) {
                    // değiştiriciler gevşek: Ctrl+Fare4'te Ctrl basılıyken Shift'e de basılabilir
                    let simdi = tus_basili(vk) && [(crate::kisayol::MOD_CONTROL, 0x11), (crate::kisayol::MOD_ALT, 0x12), (crate::kisayol::MOD_SHIFT, 0x10)]
                        .iter()
                        .all(|(mm, v)| m & mm == 0 || tus_basili(*v));
                    // durdurulduysa bir daha çağırma (sahibi mikrofonu kendisi açar)
                    if simdi != basili && c.load(std::sync::atomic::Ordering::Relaxed) {
                        basili = simdi;
                        degisti(basili);
                    }
                    std::thread::sleep(YOKLAMA);
                }
            })
            .map_err(|e| e.to_string())?;
        Ok(BasKonus { calis })
    }
}

impl Drop for BasKonus {
    fn drop(&mut self) {
        self.calis.store(false, std::sync::atomic::Ordering::Relaxed);
    }
}
