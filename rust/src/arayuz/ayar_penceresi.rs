//! Ayarlar penceresi (Python ui/settings_dialog.py karşılığı, sade hali).
//!
//! Ayarların bir kopyası (taslak) üzerinde çalışılır; "Kaydet" ile settings.json'a yazılır ve
//! çalışan parçalara (hat, ses, kayıt, anlık tekrar) yeniden başlatmadan uygulanır.

use std::sync::Arc;

use eframe::egui::{self, RichText};
use serde_json::{json, Value};

use rizeon::uygulama::{Komut, Uygulama};

use super::tema;

const KOMUT_ADLARI: &[(&str, &str)] = &[
    ("ses.mikrofon", "Mikrofon aç/kapat"),
    ("ses.sistem", "Bilgisayar sesi aç/kapat"),
    ("kamera.ac_kapat", "Kamera aç/kapat"),
    ("kayit.ac_kapat", "Yerel kaydı başlat/durdur"),
    ("kayit.duraklat", "Kaydı duraklat/devam et"),
    ("anlik_kayit.kaydet", "Son saniyeleri kaydet (anlık tekrar)"),
    ("ekran.goruntusu", "Ekran görüntüsü al"),
    ("panik", "Panik (bekleme ekranı)"),
];

#[derive(Clone, Copy, PartialEq, Default)]
enum Sekme {
    #[default]
    Genel,
    Ses,
    Kamera,
    Kayit,
    Kisayollar,
}

#[derive(Default)]
pub struct AyarPenceresi {
    acik: bool,
    sekme: Sekme,
    taslak: Value,
    monitorler: Vec<String>,
    kameralar: Vec<String>,
    mikrofonlar: Vec<String>,
    haric: String,
    hata: String,
}

fn al<'a>(v: &'a Value, yol: &str) -> &'a Value {
    let mut d = v;
    for p in yol.split('.') {
        d = d.get(p).unwrap_or(&Value::Null);
    }
    d
}

fn koy(v: &mut Value, yol: &str, deger: Value) {
    let parcalar: Vec<&str> = yol.split('.').collect();
    let mut d = v;
    for p in &parcalar[..parcalar.len() - 1] {
        if !d.get(*p).is_some_and(Value::is_object) {
            d[*p] = json!({});
        }
        d = d.get_mut(*p).unwrap();
    }
    d[parcalar[parcalar.len() - 1]] = deger;
}

impl AyarPenceresi {
    pub fn ac(&mut self, uyg: &Arc<Uygulama>) {
        self.taslak = uyg.ayarlar.lock().unwrap().veri.clone();
        self.monitorler = rizeon::yakalama::monitorler().iter().map(|m| format!("{} ({}×{})", m.ad, m.w, m.h)).collect();
        #[cfg(windows)]
        {
            self.kameralar = rizeon::yakalama::kamera::kameralar();
            self.mikrofonlar = uyg.ses.mikrofonlar();
        }
        self.haric = al(&self.taslak, "audio.exclude_apps")
            .as_array()
            .map(|l| l.iter().filter_map(Value::as_str).collect::<Vec<_>>().join(", "))
            .unwrap_or_default();
        self.hata.clear();
        self.acik = true;
    }

    fn onay(&mut self, ui: &mut egui::Ui, yol: &str, varsayilan: bool, etiket: &str) {
        let mut v = al(&self.taslak, yol).as_bool().unwrap_or(varsayilan);
        if ui.checkbox(&mut v, etiket).changed() {
            koy(&mut self.taslak, yol, v.into());
        }
    }

    fn metin(&mut self, ui: &mut egui::Ui, yol: &str, ipucu: &str) {
        let mut v = al(&self.taslak, yol).as_str().unwrap_or("").to_string();
        if ui.add(egui::TextEdit::singleline(&mut v).hint_text(ipucu).desired_width(320.0)).changed() {
            koy(&mut self.taslak, yol, v.into());
        }
    }

    fn secim(&mut self, ui: &mut egui::Ui, id: &str, yol: &str, secenekler: &[(Value, String)]) {
        let su_an = al(&self.taslak, yol).clone();
        let etiket = secenekler.iter().find(|(v, _)| *v == su_an).map(|(_, e)| e.clone()).unwrap_or_else(|| {
            secenekler.first().map(|(_, e)| e.clone()).unwrap_or_default()
        });
        egui::ComboBox::from_id_salt(id).selected_text(etiket).width(320.0).show_ui(ui, |ui| {
            for (v, e) in secenekler {
                if ui.selectable_label(*v == su_an, e).clicked() {
                    koy(&mut self.taslak, yol, v.clone());
                }
            }
        });
    }

    fn genel(&mut self, ui: &mut egui::Ui) {
        ui.label("Ekran");
        let mon: Vec<(Value, String)> = if self.monitorler.is_empty() {
            vec![(json!(0), "Ana ekran".into())]
        } else {
            self.monitorler.iter().enumerate().map(|(i, m)| (json!(i), m.clone())).collect()
        };
        self.secim(ui, "monitor", "video.monitor", &mon);
        self.secim(
            ui,
            "yakalama",
            "video.capture_backend",
            &[(json!("dxcam"), "Otomatik (DXGI, hızlı)".into()), (json!("mss"), "Uyumlu (GDI, yavaş)".into())],
        );
        self.onay(ui, "video.show_cursor", true, "Fare imlecini göster");
        ui.add_space(8.0);
        ui.label("Bekleme ekranı");
        self.metin(ui, "standby_text", "Birazdan döneceğim");
        self.metin(ui, "standby_image", "Görsel dosyası (PNG/JPG), boşsa yazı");
        ui.add_space(8.0);
        ui.label("Pencere");
        self.onay(ui, "ui.minimize_to_tray", true, "Kapatınca tepside çalışmaya devam et");
        let mut fps = al(&self.taslak, "ui.preview_fps").as_i64().unwrap_or(15);
        if ui.add(egui::Slider::new(&mut fps, 5..=30).text("önizleme fps")).changed() {
            koy(&mut self.taslak, "ui.preview_fps", fps.into());
        }
        ui.add_space(8.0);
        ui.label(RichText::new("Çözünürlük ve fps (video.width/height/fps) bir sonraki açılışta geçerli olur.").small().color(tema::SOLUK));
    }

    fn ses(&mut self, ui: &mut egui::Ui) {
        ui.label("Mikrofon");
        let mut mik: Vec<(Value, String)> = vec![(json!(""), "Windows varsayılanı".into())];
        mik.extend(self.mikrofonlar.iter().map(|m| (json!(m), m.clone())));
        self.secim(ui, "mikrofon", "audio.mic_device", &mik);
        self.onay(ui, "audio.ducking", false, "Konuşunca bilgisayar sesini kıs");
        let mut sev = al(&self.taslak, "audio.ducking_level").as_f64().unwrap_or(0.3);
        if ui.add(egui::Slider::new(&mut sev, 0.0..=1.0).text("kısma seviyesi")).changed() {
            koy(&mut self.taslak, "audio.ducking_level", sev.into());
        }
        ui.add_space(8.0);
        ui.label("Bilgisayar sesi");
        self.secim(
            ui,
            "sistem",
            "audio.system_mode",
            &[
                (json!("auto"), "Toplantı uygulamaları hariç (önerilen)".into()),
                (json!("all"), "Tüm bilgisayar sesi".into()),
                (json!("app"), "Sadece bir uygulama".into()),
            ],
        );
        if al(&self.taslak, "audio.system_mode").as_str() == Some("app") {
            self.metin(ui, "audio.include_app", "Uygulama (ör. chrome.exe)");
        } else {
            ui.label(RichText::new("Hariç tutulacak uygulamalar (virgülle)").small().color(tema::YAZI2));
            if ui.add(egui::TextEdit::singleline(&mut self.haric).desired_width(320.0)).changed() {
                let l: Vec<Value> = self.haric.split(',').map(str::trim).filter(|s| !s.is_empty()).map(|s| json!(s)).collect();
                koy(&mut self.taslak, "audio.exclude_apps", Value::Array(l));
            }
        }
    }

    fn kamera(&mut self, ui: &mut egui::Ui) {
        ui.label("Kamera");
        let kam: Vec<(Value, String)> = if self.kameralar.is_empty() {
            vec![(json!(0), "Varsayılan kamera".into())]
        } else {
            self.kameralar.iter().enumerate().map(|(i, k)| (json!(i), k.clone())).collect()
        };
        self.secim(ui, "kamera", "camera.device", &kam);
        self.onay(ui, "camera.mirror", false, "Aynala");
        ui.add_space(8.0);
        ui.label("Köşe");
        self.secim(
            ui,
            "kose",
            "camera.corner",
            &[
                (json!("bottom-right"), "Sağ alt".into()),
                (json!("bottom-left"), "Sol alt".into()),
                (json!("top-right"), "Sağ üst".into()),
                (json!("top-left"), "Sol üst".into()),
            ],
        );
        let mut boy = al(&self.taslak, "camera.size").as_f64().unwrap_or(0.25);
        if ui.add(egui::Slider::new(&mut boy, 0.1..=0.6).text("boyut")).changed() {
            koy(&mut self.taslak, "camera.size", boy.into());
            koy(&mut self.taslak, "camera.position", Value::Null);
        }
    }

    fn kayit(&mut self, ui: &mut egui::Ui) {
        ui.label("Kayıt klasörü");
        self.metin(ui, "record.folder", "Boşsa Videolar\\RizeOn");
        ui.label("Ekran görüntüsü klasörü");
        self.metin(ui, "screenshot.folder", "Boşsa kayıt klasörü");
        ui.add_space(8.0);
        ui.label("Kodlayıcı");
        let mut kod: Vec<(Value, String)> = vec![(json!("auto"), "Otomatik (ekran kartına göre)".into())];
        kod.extend(rizeon::ffmpeg::KODLAYICILAR.iter().map(|k| (json!(k), k.to_string())));
        self.secim(ui, "kodlayici", "record.encoder", &kod);
        ui.add_space(8.0);
        self.onay(ui, "record.replay", true, "Anlık tekrar (son saniyeler RAM'de tutulur)");
        let mut sn = al(&self.taslak, "record.replay_seconds").as_i64().unwrap_or(15);
        if ui.add(egui::Slider::new(&mut sn, 15..=300).text("saniye")).changed() {
            koy(&mut self.taslak, "record.replay_seconds", sn.into());
        }
    }

    fn kisayollar(&mut self, ui: &mut egui::Ui) {
        ui.label(RichText::new("Örnek: Ctrl+Shift+R. Boş bırakırsan kısayol olmaz.").small().color(tema::YAZI2));
        let mut adlar: Vec<(String, String)> = KOMUT_ADLARI.iter().map(|(k, a)| (k.to_string(), a.to_string())).collect();
        for i in 1..=9 {
            adlar.push((format!("sahne.sec:{i}"), format!("Sahne {i}")));
        }
        egui::Grid::new("kisayollar").num_columns(2).spacing([16.0, 6.0]).show(ui, |ui| {
            for (komut, ad) in adlar {
                ui.label(ad);
                let mut v = self.taslak.get("hotkeys").and_then(|h| h.get(&komut)).and_then(Value::as_str).unwrap_or("").to_string();
                let gecerli = v.trim().is_empty() || rizeon::kisayol::tus_coz(&v).is_ok();
                let mut te = egui::TextEdit::singleline(&mut v).desired_width(180.0);
                if !gecerli {
                    te = te.text_color(tema::KAYIT);
                }
                if ui.add(te).changed() {
                    if !self.taslak.get("hotkeys").is_some_and(Value::is_object) {
                        self.taslak["hotkeys"] = json!({});
                    }
                    self.taslak["hotkeys"][&komut] = v.into();
                }
                ui.end_row();
            }
        });
    }

    fn dogrula(&self) -> Result<(), String> {
        let mut kullanilan = std::collections::HashMap::new();
        if let Some(h) = self.taslak.get("hotkeys").and_then(Value::as_object) {
            for (komut, v) in h {
                let Some(t) = v.as_str().filter(|t| !t.trim().is_empty()) else { continue };
                if Komut::coz(komut).is_none() {
                    continue;
                }
                let tus = rizeon::kisayol::tus_coz(t).map_err(|_| format!("Geçersiz kısayol: {t}"))?;
                if let Some(onceki) = kullanilan.insert(tus, komut.clone()) {
                    return Err(format!("{t} iki kez kullanılmış ({onceki}, {komut})"));
                }
            }
        }
        Ok(())
    }

    /// Ayarlar kaydedildiyse true (arayüz kısayolları ve önizleme hızını yeniler).
    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) -> bool {
        if !self.acik {
            return false;
        }
        let mut acik = true;
        let mut kaydet = false;
        let mut vazgec = false;
        egui::Window::new("Ayarlar")
            .open(&mut acik)
            .collapsible(false)
            .resizable(true)
            .default_size([560.0, 480.0])
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    for (s, ad) in [
                        (Sekme::Genel, "Genel"),
                        (Sekme::Ses, "Ses"),
                        (Sekme::Kamera, "Kamera"),
                        (Sekme::Kayit, "Kayıt"),
                        (Sekme::Kisayollar, "Kısayollar"),
                    ] {
                        ui.selectable_value(&mut self.sekme, s, ad);
                    }
                });
                ui.separator();
                egui::ScrollArea::vertical().max_height(380.0).show(ui, |ui| match self.sekme {
                    Sekme::Genel => self.genel(ui),
                    Sekme::Ses => self.ses(ui),
                    Sekme::Kamera => self.kamera(ui),
                    Sekme::Kayit => self.kayit(ui),
                    Sekme::Kisayollar => self.kisayollar(ui),
                });
                ui.separator();
                if !self.hata.is_empty() {
                    ui.label(RichText::new(&self.hata).color(tema::KAYIT));
                }
                ui.horizontal(|ui| {
                    if ui.button("Kaydet").clicked() {
                        kaydet = true;
                    }
                    if ui.button("Vazgeç").clicked() {
                        vazgec = true;
                    }
                });
            });
        if kaydet {
            if let Err(e) = self.dogrula() {
                self.hata = e;
                return false;
            }
            {
                let mut a = uyg.ayarlar.lock().unwrap();
                a.veri = std::mem::take(&mut self.taslak);
                a.kaydet();
            }
            uyg.ayarlari_uygula();
            self.acik = false;
            return true;
        }
        if vazgec || !acik {
            self.acik = false;
            self.taslak = Value::Null;
        }
        false
    }
}
