//! RegisterHotKey ile global kısayollar. Kendi mesaj döngüsü olan bir iş parçacığında çalışır;
//! tuşlar değişince o iş parçacığına mesajla bildirilir.

use std::collections::HashMap;
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};

use windows::Win32::Foundation::{LPARAM, WPARAM};
use windows::Win32::System::Threading::GetCurrentThreadId;
use windows::Win32::UI::Input::KeyboardAndMouse::{RegisterHotKey, UnregisterHotKey, HOT_KEY_MODIFIERS};
use windows::Win32::UI::WindowsAndMessaging::{GetMessageW, PeekMessageW, PostThreadMessageW, MSG, PM_NOREMOVE, WM_APP, WM_HOTKEY, WM_QUIT};

use crate::kisayol::{tus_coz, MOD_NOREPEAT};

enum Islem {
    Ayarla(String, HashMap<String, String>), // grup, komut -> tuş
    Kaldir(String),
}

pub struct KisayolYoneticisi {
    is_kimligi: u32,
    tx: Sender<Islem>,
    /// tuşu kaydedilemeyen komutlar (başka program kullanıyor) -> açıklama
    pub hatalar: Arc<Mutex<HashMap<String, String>>>,
}

impl KisayolYoneticisi {
    /// `basildi(komut)` kısayol iş parçacığında çağrılır.
    pub fn baslat(basildi: impl Fn(&str) + Send + 'static) -> Self {
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
                            basildi(&k);
                        }
                    } else if msg.message == WM_APP {
                        while let Ok(is) = rx.try_recv() {
                            let grup = match &is {
                                Islem::Ayarla(g, _) | Islem::Kaldir(g) => g.clone(),
                            };
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
        KisayolYoneticisi { is_kimligi, tx, hatalar }
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
        unsafe {
            let _ = PostThreadMessageW(self.is_kimligi, WM_QUIT, WPARAM(0), LPARAM(0));
        }
    }
}
