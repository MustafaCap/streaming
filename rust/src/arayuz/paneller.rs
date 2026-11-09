//! Gelişmiş görünümün panelleri (Python ui/sahne_panelleri.py ve ui/mixer_panel.py):
//! Sahneler, Kaynaklar (sol sütun), Ses mikseri ve Anahtarlar (sağ sütun).

use std::sync::Arc;

use eframe::egui::{self, Align2, Pos2, Rect, Sense, Ui, Vec2};
use serde_json::{json, Map, Value};

use rizeon::durum::Durum;
use rizeon::sahne::{self, Kaynak, EKLENEBILIR};
use rizeon::ses_modlari;
use rizeon::uygulama::{Komut, Uygulama};

use super::bilesen::{self, SimgeDugme};
use super::diyalog::{Amac, Diyalog};
use super::tema::{self, beyaz};

/// Panellerin ana pencereden istedikleri (pencere açan işler orada yapılır).
pub enum Istek {
    Diyalog(Diyalog),
    PencereSecKaynak,
    BolgeSecKaynak,
    AyarlarAc(&'static str),
}

fn panel_basligi(ui: &mut Ui, metin: &str, ipucu: &str) -> bool {
    let mut basildi = false;
    ui.horizontal(|ui| {
        ui.set_height(28.0);
        bilesen::etiket(ui, metin, tema::KUCUK_PX, tema::YAZI2);
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            basildi = SimgeDugme::new("arti").boyut(28.0, 14.0).goster(ui).on_hover_text(ipucu).clicked();
        });
    });
    ui.add_space(4.0);
    basildi
}

/// Satır zemini: üzerine gelince açık gri, seçiliyken biraz daha açık (Python _Satir).
fn satir_zemini(ui: &Ui, r: Rect, secili: bool, uzerinde: bool) {
    let mut alfa = if secili { tema::A_SECILI } else { 0.0 };
    if uzerinde {
        alfa = alfa.max(tema::A_UZERINE) + if secili { 0.02 } else { 0.0 };
    }
    if alfa > 0.0 {
        ui.painter().rect_filled(r, 8.0, beyaz(alfa));
    }
}

// ------------------------------------------------------------------ Sahneler

#[derive(Default)]
pub struct SahnelerPaneli {
    duzenlenen: Option<(usize, String, bool)>,
}

impl SahnelerPaneli {
    pub fn goster(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>, tus: &dyn Fn(&str) -> String) {
        bilesen::panel(12.0).show(ui, |ui| {
            ui.spacing_mut().item_spacing.y = 2.0;
            if panel_basligi(ui, "Sahneler", "Sahne ekle") {
                if let Some(n) = uyg.k.sahneler.ekle() {
                    uyg.komut(Komut::Sahne(n));
                    uyg.sahneleri_kaydet();
                }
            }
            let sahneler = uyg.k.sahneler.liste();
            let aktif = uyg.k.sahneler.indeks();
            let mut sil = None;
            for (i, s) in sahneler.iter().enumerate() {
                let (r, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 40.0), Sense::click());
                if let Some((j, ad, ilk)) = &mut self.duzenlenen {
                    if *j == i {
                        let mut alt = ui.new_child(egui::UiBuilder::new().max_rect(r.shrink2(Vec2::new(2.0, 4.0))));
                        let te = alt.add(egui::TextEdit::singleline(ad).char_limit(60).desired_width(f32::INFINITY).margin(egui::vec2(8.0, 6.0)));
                        if *ilk {
                            te.request_focus();
                            *ilk = false;
                        }
                        let vazgec = alt.input(|x| x.key_pressed(egui::Key::Escape));
                        if vazgec {
                            self.duzenlenen = None;
                        } else if te.lost_focus() {
                            let yeni = ad.trim().to_string();
                            if !yeni.is_empty() && yeni != s.ad {
                                uyg.k.sahneler.yeniden_adlandir(i, &yeni);
                                uyg.sahneleri_kaydet();
                            }
                            self.duzenlenen = None;
                        }
                        continue;
                    }
                }
                let resp = resp.on_hover_cursor(egui::CursorIcon::PointingHand);
                satir_zemini(ui, r, i == aktif, resp.hovered());
                ui.painter().text(
                    Pos2::new(r.left() + 10.0, r.center().y),
                    Align2::LEFT_CENTER,
                    &s.ad,
                    tema::yazi(tema::GOVDE_PX),
                    if i == aktif { tema::BEYAZ } else { tema::DUGME },
                );
                let t = if i < 9 { tus(&format!("sahne.sec:{}", i + 1)) } else { String::new() };
                if !t.is_empty() {
                    ui.painter().text(Pos2::new(r.right() - 10.0, r.center().y), Align2::RIGHT_CENTER, &t, tema::yazi(tema::EN_KUCUK_PX), tema::SOLUK);
                }
                let resp = if t.is_empty() { resp } else { resp.on_hover_text(&t) };
                if resp.double_clicked() {
                    self.duzenlenen = Some((i, s.ad.clone(), true));
                } else if resp.clicked() {
                    uyg.komut(Komut::Sahne(i));
                }
                let n = sahneler.len();
                egui::Popup::context_menu(&resp).frame(bilesen::menu_cercevesi()).show(|ui| {
                    ui.set_min_width(180.0);
                    if bilesen::menu_satiri(ui, "Yeniden adlandır", true).clicked() {
                        self.duzenlenen = Some((i, s.ad.clone(), true));
                    }
                    if bilesen::menu_satiri(ui, "Sil", n > 1).clicked() {
                        sil = Some(i);
                    }
                });
            }
            if let Some(i) = sil {
                if uyg.k.sahneler.sil(i) {
                    uyg.komut(Komut::Sahne(uyg.k.sahneler.indeks()));
                    uyg.sahneleri_kaydet();
                }
            }
        });
    }
}

// ------------------------------------------------------------------ Kaynaklar

#[derive(Default)]
pub struct KaynaklarPaneli {
    /// "+ > Ekran" ya da "+ > Kamera" alt menüsü
    alt_menu: Option<&'static str>,
}

pub fn kaynak_bilgisi(k: &Kaynak, bekleme_gorseli: &str) -> String {
    let a = &k.ayar;
    let sayi = |ad: &str, v: i64| a.get(ad).and_then(Value::as_i64).unwrap_or(v);
    match k.tur.as_str() {
        "ekran" if k.ana() => "Göster'deki görüntü".into(),
        "ekran" => format!("Monitör {}", sayi("monitor", 0) + 1),
        "pencere" => k.metin("title").chars().take(40).collect(),
        "bolge" => {
            if let Some(p) = a.get("pixels").and_then(Value::as_array).filter(|p| p.len() == 2) {
                format!("{} × {}", p[0].as_i64().unwrap_or(0), p[1].as_i64().unwrap_or(0))
            } else {
                let r: Vec<f64> = a.get("rect").and_then(Value::as_array).map(|v| v.iter().filter_map(Value::as_f64).collect()).unwrap_or_default();
                let (w, h) = (r.get(2).copied().unwrap_or(1.0), r.get(3).copied().unwrap_or(1.0));
                format!("%{} × %{}", (w * 100.0).round(), (h * 100.0).round())
            }
        }
        "kamera" if k.ana() => format!("Webcam · {}", if k.tam() { "tam ekran" } else { "köşede" }),
        "kamera" => format!("Cihaz {}", sayi("device", 1) + 1),
        "gorsel" | "video" => std::path::Path::new(&k.metin("path")).file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
        "metin" => k.metin("text").chars().take(40).collect(),
        "kalem" => "Saydam".into(),
        "imlec" => "Halka".into(),
        "bekleme" => {
            if bekleme_gorseli.is_empty() {
                "Yazı".into()
            } else if rizeon::yollar::video_mu(bekleme_gorseli) {
                "Video".into()
            } else {
                std::path::Path::new(bekleme_gorseli).file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default()
            }
        }
        _ => String::new(),
    }
}

impl KaynaklarPaneli {
    pub fn ekle(uyg: &Arc<Uygulama>, tur: &str, ayar: Map<String, Value>) -> Option<Istek> {
        let sahne = uyg.k.sahneler.aktif();
        let k = Kaynak::yeni(tur, &sahne::yeni_kaynak_adi(&sahne, tur), ayar);
        if !uyg.k.sahneler.kaynak_ekle(k) {
            return Some(Istek::Diyalog(Diyalog::bilgi("Kaynaklar", "Bir sahnede en çok 20 kaynak olabilir.")));
        }
        uyg.sahneleri_kaydet();
        None
    }

    fn kaynak_ekle(&mut self, uyg: &Arc<Uygulama>, tur: &'static str) -> Option<Istek> {
        let ayar = |v: Value| v.as_object().cloned().unwrap_or_default();
        match tur {
            "ekran" => {
                let n = rizeon::yakalama::monitorler().len().max(1);
                if n == 1 {
                    return Self::ekle(uyg, "ekran", ayar(json!({"monitor": 0})));
                }
                self.alt_menu = Some("ekran");
                None
            }
            "pencere" => Some(Istek::PencereSecKaynak),
            "bolge" => Some(Istek::BolgeSecKaynak),
            "kamera" => {
                self.alt_menu = Some("kamera");
                None
            }
            "gorsel" => {
                #[cfg(windows)]
                if let Some(y) = rizeon::win::dosya_sec("Görsel seç", &[("Görseller", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")]) {
                    return Self::ekle(uyg, "gorsel", ayar(json!({"path": y.to_string_lossy()})));
                }
                None
            }
            "video" => {
                #[cfg(windows)]
                if let Some(y) = rizeon::win::dosya_sec("Video seç", &[("Videolar", "*.mp4;*.webm;*.avi;*.mov;*.mkv;*.gif;*.wmv;*.m4v")]) {
                    match rizeon::yollar::video_kopyala(&y) {
                        Ok(y) => return Self::ekle(uyg, "video", ayar(json!({"path": y.to_string_lossy()}))),
                        Err(e) => log::warn!("Video kopyalanamadı: {e}"),
                    }
                }
                None
            }
            "metin" => Some(Istek::Diyalog(Diyalog::girdi("Metin", "Görünecek yazı (ör. adın):", "", Amac::YeniMetin))),
            _ => None,
        }
    }

    pub fn goster(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>) -> Option<Istek> {
        let mut istek = None;
        bilesen::panel(12.0).show(ui, |ui| {
            ui.spacing_mut().item_spacing.y = 2.0;
            let mut ekle_r = None;
            ui.horizontal(|ui| {
                ui.set_height(28.0);
                bilesen::etiket(ui, "Kaynaklar", tema::KUCUK_PX, tema::YAZI2);
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ekle_r = Some(SimgeDugme::new("arti").boyut(28.0, 14.0).goster(ui).on_hover_text("Kaynak ekle"));
                });
            });
            ui.add_space(4.0);
            let ekle_r = ekle_r.unwrap();
            egui::Popup::menu(&ekle_r).frame(bilesen::menu_cercevesi()).align(egui::RectAlign::BOTTOM_START).show(|ui| {
                ui.set_min_width(240.0);
                for (tur, ad, aciklama) in EKLENEBILIR {
                    if bilesen::menu_ogesi(ui, ad, aciklama, false).clicked() {
                        istek = self.kaynak_ekle(uyg, tur);
                    }
                }
            });
            if let Some(alt) = self.alt_menu {
                let id = ui.scope_id().with("kaynak-alt-menu");
                egui::Popup::new(id, ui.ctx().clone(), egui::PopupAnchor::from(&ekle_r), ui.layer_id())
                    .open(true)
                    .kind(egui::PopupKind::Menu)
                    .frame(bilesen::menu_cercevesi())
                    .align(egui::RectAlign::BOTTOM_START)
                    .show(|ui| {
                        ui.set_min_width(240.0);
                        if alt == "ekran" {
                            for (i, m) in rizeon::yakalama::monitorler().iter().enumerate() {
                                if bilesen::menu_ogesi(ui, &format!("Ekran {}", i + 1), &format!("Tüm ekran · {}×{}", m.w, m.h), false).clicked() {
                                    istek = Self::ekle(uyg, "ekran", json!({"monitor": i}).as_object().cloned().unwrap());
                                    self.alt_menu = None;
                                }
                            }
                        } else {
                            let ana = uyg.ayarlar.lock().unwrap().sayi("camera.device", 0);
                            for n in 0..4i64 {
                                if n == ana {
                                    continue;
                                }
                                if bilesen::menu_ogesi(ui, &format!("Cihaz {}", n + 1), "İkinci webcam, telefon ya da yakalama kartı", false).clicked() {
                                    istek = Self::ekle(uyg, "kamera", json!({"device": n, "yer": "kose"}).as_object().cloned().unwrap());
                                    self.alt_menu = None;
                                }
                            }
                        }
                    });
                if ui.input(|i| i.pointer.any_click() || i.key_pressed(egui::Key::Escape)) && !ui.ctx().is_pointer_over_egui() {
                    self.alt_menu = None;
                }
            }

            let sahne = uyg.k.sahneler.aktif();
            let bekleme = uyg.k.ayar.lock().unwrap().bekleme_gorseli.clone();
            let n = sahne.kaynaklar.len();
            for (i, k) in sahne.kaynaklar.iter().enumerate() {
                let bilgi = kaynak_bilgisi(k, &bekleme);
                let (r, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 44.0), Sense::click());
                let uzerinde = ui.rect_contains_pointer(r);
                satir_zemini(ui, r, false, uzerinde);
                let ad_renk = if k.gorunur { tema::YAZI } else { tema::SOLUK };
                if bilgi.is_empty() {
                    ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y), Align2::LEFT_CENTER, &k.ad, tema::yazi(tema::GOVDE_PX), ad_renk);
                } else {
                    ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y - 9.0), Align2::LEFT_CENTER, &k.ad, tema::yazi(tema::GOVDE_PX), ad_renk);
                    ui.painter().text(Pos2::new(r.left() + 10.0, r.center().y + 10.0), Align2::LEFT_CENTER, &bilgi, tema::yazi(tema::EN_KUCUK_PX), tema::SOLUK);
                }
                // göz ve × (× sadece üzerine gelince)
                let kaldir_r = Rect::from_min_size(Pos2::new(r.right() - 2.0 - 28.0, r.center().y - 14.0), Vec2::splat(28.0));
                let goz_r = kaldir_r.translate(Vec2::new(-30.0, 0.0));
                let mut goz_ui = ui.new_child(egui::UiBuilder::new().max_rect(goz_r).id_salt(("goz", &k.kimlik)));
                let goz = SimgeDugme::new(if k.gorunur { "goz" } else { "goz_kapali" }).boyut(28.0, 14.0).renk(tema::YAZI2).goster(&mut goz_ui).on_hover_text(if k.gorunur {
                    format!("{}: görünür, gizle", k.ad)
                } else {
                    format!("{}: gizli, göster", k.ad)
                });
                if goz.clicked() && uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| x.gorunur = !x.gorunur) {
                    uyg.sahneleri_kaydet();
                }
                let mut kaldir_ui = ui.new_child(egui::UiBuilder::new().max_rect(kaldir_r).id_salt(("kaldir", &k.kimlik)));
                let kaldir = SimgeDugme::new("kapat").boyut(28.0, 14.0).renk(tema::YAZI2).gizli(!uzerinde).goster(&mut kaldir_ui).on_hover_text(format!("{} kaynağını kaldır", k.ad));
                if kaldir.clicked() && uyg.k.sahneler.kaynak_sil(&k.kimlik) {
                    uyg.sahneleri_kaydet();
                }
                if resp.double_clicked() {
                    istek = self.duzenle(uyg, k);
                }
                egui::Popup::context_menu(&resp).frame(bilesen::menu_cercevesi()).show(|ui| {
                    ui.set_min_width(200.0);
                    let mut degisti = false;
                    if bilesen::menu_satiri(ui, "Öne al", i > 0).clicked() {
                        degisti |= uyg.k.sahneler.kaynak_tasi(&k.kimlik, -1);
                    }
                    if bilesen::menu_satiri(ui, "Arkaya al", i + 1 < n).clicked() {
                        degisti |= uyg.k.sahneler.kaynak_tasi(&k.kimlik, 1);
                    }
                    bilesen::menu_ayraci(ui);
                    if bilesen::menu_satiri(ui, "Yeniden adlandır", true).clicked() {
                        istek = Some(Istek::Diyalog(Diyalog::girdi("Yeniden adlandır", "Kaynak adı:", &k.ad, Amac::KaynakAdi(k.kimlik.clone()))));
                    }
                    if k.tur == "metin" && bilesen::menu_satiri(ui, "Yazıyı düzenle…", true).clicked() {
                        istek = self.duzenle(uyg, k);
                    }
                    if k.tur == "bekleme" {
                        if bilesen::menu_satiri(ui, "Resim ya da kısa video seç…", true).clicked() {
                            bekleme_sec(uyg);
                        }
                        if bilesen::menu_satiri(ui, "Sadece yazı kullan", !bekleme.is_empty()).clicked() {
                            bekleme_uygula(uyg, "");
                        }
                        if bilesen::menu_satiri(ui, "Bekleme yazısını değiştir…", true).clicked() {
                            let m = uyg.k.ayar.lock().unwrap().bekleme_metni.clone();
                            istek = Some(Istek::Diyalog(Diyalog::girdi("Bekleme ekranı", "Yazı:", &m, Amac::BeklemeYazisi)));
                        }
                    }
                    if k.tur == "kamera" && !k.ana() && bilesen::menu_satiri(ui, if k.tam() { "Köşede" } else { "Tam ekran" }, true).clicked() {
                        let tam = k.tam();
                        degisti |= uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| {
                            x.ayar.insert("yer".into(), if tam { "kose" } else { "tam" }.into());
                        });
                    }
                    bilesen::menu_ayraci(ui);
                    if bilesen::menu_satiri(ui, "Kaldır", true).clicked() {
                        degisti |= uyg.k.sahneler.kaynak_sil(&k.kimlik);
                    }
                    if degisti {
                        uyg.sahneleri_kaydet();
                    }
                });
            }
            if n == 0 {
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    ui.add_space(10.0);
                    bilesen::etiket(ui, "Bu sahnede kaynak yok", tema::EN_KUCUK_PX, tema::SOLUK);
                });
                ui.add_space(8.0);
            }
        });
        istek
    }

    fn duzenle(&mut self, uyg: &Arc<Uygulama>, k: &Kaynak) -> Option<Istek> {
        match k.tur.as_str() {
            "metin" => Some(Istek::Diyalog(Diyalog::girdi("Metin", "Görünecek yazı:", &k.metin("text"), Amac::KaynakMetni(k.kimlik.clone())))),
            "bekleme" => {
                bekleme_sec(uyg);
                None
            }
            _ => None,
        }
    }
}

fn bekleme_sec(uyg: &Arc<Uygulama>) {
    #[cfg(windows)]
    if let Some(y) = rizeon::win::dosya_sec(
        "Bekleme ekranı: resim ya da kısa video",
        &[("Resim ya da video", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.mp4;*.webm;*.avi;*.mov;*.mkv;*.gif;*.wmv;*.m4v")],
    ) {
        bekleme_uygula(uyg, &y.to_string_lossy());
    }
    let _ = uyg;
}

pub fn bekleme_uygula(uyg: &Arc<Uygulama>, yol: &str) {
    uyg.ayarla("standby_image", yol.into());
    uyg.k.ayar.lock().unwrap().bekleme_gorseli = yol.to_string();
}

/// Diyalogdan dönen metni uygular.
pub fn diyalog_sonucu(uyg: &Arc<Uygulama>, amac: Amac, metin: String) {
    let m = metin.trim().to_string();
    match amac {
        Amac::KaynakAdi(kim) if !m.is_empty() => {
            uyg.k.sahneler.kaynak_degistir(&kim, |k| k.ad = m.chars().take(60).collect());
        }
        Amac::KaynakMetni(kim) => {
            uyg.k.sahneler.kaynak_degistir(&kim, |k| {
                k.ayar.insert("text".into(), metin.chars().take(120).collect::<String>().into());
            });
        }
        Amac::YeniMetin if !m.is_empty() => {
            let _ = KaynaklarPaneli::ekle(uyg, "metin", json!({"text": m.chars().take(120).collect::<String>()}).as_object().cloned().unwrap());
        }
        Amac::BeklemeYazisi if !m.is_empty() => {
            let m: String = m.chars().take(120).collect();
            uyg.k.ayar.lock().unwrap().bekleme_metni = m.clone();
            uyg.ayarla("standby_text", m.into());
        }
        _ => return,
    }
    uyg.sahneleri_kaydet();
}

// ------------------------------------------------------------------ Ses mikseri

pub const SURGU_UST: i32 = 200;

#[derive(Default)]
pub struct MikserPaneli {
    cizgi: [f32; 2],
}

impl MikserPaneli {
    fn kanal(ui: &mut Ui, baslik: &str, yuzde: &mut i32, bilgi: &str, duzenle: bool, cizgi: f32) -> (bool, bool, bool) {
        let mut duzenle_basildi = false;
        ui.spacing_mut().item_spacing.y = 8.0;
        ui.spacing_mut().interact_size.y = 0.0;
        ui.horizontal(|ui| {
            bilesen::etiket(ui, baslik, tema::GOVDE_PX, tema::YAZI);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                bilesen::etiket(ui, &format!("{yuzde}%"), tema::KUCUK_PX, tema::YAZI2);
            });
        });
        if !bilgi.is_empty() || duzenle {
            ui.add_space(-4.0);
            ui.horizontal(|ui| {
                if duzenle {
                    ui.set_min_height(26.0);
                }
                ui.add(egui::Label::new(egui::RichText::new(bilgi).font(tema::yazi(tema::EN_KUCUK_PX)).color(tema::SOLUK)).wrap());
                if duzenle {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        duzenle_basildi = bilesen::baglanti(ui, "Düzenle", tema::EN_KUCUK_PX, tema::YAZI2, true).on_hover_text("Hangi uygulamaların sesi alınmasın").clicked();
                    });
                }
            });
        }
        bilesen::ses_cizgisi(ui, cizgi);
        let r = bilesen::surgu(ui, yuzde, SURGU_UST);
        (r.changed(), r.drag_stopped() || (r.changed() && !r.dragged()), duzenle_basildi)
    }

    pub fn goster(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>, d: &Durum) -> Option<Istek> {
        let mut istek = None;
        let seviyeler = uyg.mikser.lock().unwrap().seviyeler();
        let sev = |a: &str| seviyeler.iter().find(|(k, _)| k == a).map(|(_, v)| *v).unwrap_or(0.0);
        self.cizgi[0] = bilesen::seviye_yumusat(self.cizgi[0], if d.mikrofon_sessiz { 0.0 } else { sev("mikrofon") });
        self.cizgi[1] = bilesen::seviye_yumusat(self.cizgi[1], if d.sistem_sessiz { 0.0 } else { sev("sistem") });
        let kazanc = |a: &str| (uyg.mikser.lock().unwrap().kanal_oku(a).map(|k| k.kazanc()).unwrap_or(1.0) * 100.0).round() as i32;
        let (mut mik, mut sis) = (kazanc("mikrofon"), kazanc("sistem"));
        let (haric, tum, son) = {
            let a = uyg.ayarlar.lock().unwrap();
            (ses_modlari::haric_metni(&a), ses_modlari::modlar(&a), ses_modlari::son_mod(&a))
        };
        let mik_bilgi = if d.mikrofon == "yok" {
            if d.ses_hatasi.is_empty() { "Mikrofon bulunamadı".to_string() } else { d.ses_hatasi.clone() }
        } else if d.bas_konus {
            if d.konusuyor { "Konuşuyor".into() } else { "Bas-konuş: konuşmak için tuşu basılı tut".into() }
        } else {
            String::new()
        };
        let sis_bilgi = if d.sistem_sesi == "yok" {
            if d.ses_hatasi.is_empty() { "Sistem sesi alınamıyor".to_string() } else { d.ses_hatasi.clone() }
        } else {
            haric
        };
        let mut kaydet = false;
        bilesen::panel(14.0).show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.spacing_mut().item_spacing.y = 18.0;
            bilesen::etiket(ui, "Ses mikseri", tema::KUCUK_PX, tema::YAZI2);
            ui.vertical(|ui| {
                let (degisti, birakti, _) = Self::kanal(ui, "Mikrofon", &mut mik, &mik_bilgi, false, self.cizgi[0]);
                if degisti {
                    if let Some(k) = uyg.mikser.lock().unwrap().kanal("mikrofon") {
                        k.kazanc_ayarla(mik as f32 / 100.0);
                    }
                }
                kaydet |= birakti;
            });
            ui.vertical(|ui| {
                let (degisti, birakti, duzenle) = Self::kanal(ui, "Sistem / oyun", &mut sis, &sis_bilgi, true, self.cizgi[1]);
                if degisti {
                    if let Some(k) = uyg.mikser.lock().unwrap().kanal("sistem") {
                        k.kazanc_ayarla(sis as f32 / 100.0);
                    }
                }
                kaydet |= birakti;
                if duzenle {
                    istek = Some(Istek::AyarlarAc("ses"));
                }
            });
            ui.vertical(|ui| {
                ui.spacing_mut().item_spacing.y = 8.0;
                let eslesen = ses_modlari::eslesen(mik, sis, &tum);
                ui.spacing_mut().interact_size.y = 0.0;
                ui.horizontal(|ui| {
                    bilesen::etiket(ui, "Önde olan", tema::KUCUK_PX, tema::YAZI2);
                    if eslesen.is_none() {
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            let r = bilesen::baglanti(ui, ses_modlari::kaydet_etiketi(son), tema::KUCUK_PX, tema::YAZI, true)
                                .on_hover_text(format!("Şimdiki seviyeler {} modunun yeni değeri olsun", ses_modlari::etiket(son)));
                            if r.clicked() {
                                ses_modlari::kaydet(&mut uyg.ayarlar.lock().unwrap(), son, mik, sis);
                                kaydet = true;
                            }
                        });
                    }
                });
                let adlar: Vec<&str> = ses_modlari::MODLAR.iter().map(|m| ses_modlari::etiket(m)).collect();
                let ipuclari: Vec<&str> = ses_modlari::MODLAR.iter().map(|m| ses_modlari::ipucu(m)).collect();
                if let Some(n) = bilesen::secim_grubu(ui, &adlar, &ipuclari, eslesen.map(|e| e as i32).unwrap_or(-1), false, None) {
                    let (m, s) = ses_modlari::uygula(&mut uyg.ayarlar.lock().unwrap(), ses_modlari::MODLAR[n]);
                    let mut mk = uyg.mikser.lock().unwrap();
                    if let Some(k) = mk.kanal("mikrofon") {
                        k.kazanc_ayarla(m as f32 / 100.0);
                    }
                    if let Some(k) = mk.kanal("sistem") {
                        k.kazanc_ayarla(s as f32 / 100.0);
                    }
                }
            });
        });
        if kaydet {
            let mut a = uyg.ayarlar.lock().unwrap();
            if let Some(ses) = a.veri.get_mut("audio").and_then(Value::as_object_mut) {
                ses.insert("mic_gain".into(), json!(mik as f64 / 100.0));
            }
            a.ayarla("audio.system_gain", json!(sis as f64 / 100.0));
        }
        istek
    }
}

// ------------------------------------------------------------------ Anahtarlar

#[derive(Default)]
pub struct AnahtarPaneli;

impl AnahtarPaneli {
    pub fn goster(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>) -> Option<Istek> {
        let mut istek = None;
        let (mut gurultu, mut kisma, mut ptt, mut bulanik) = {
            let a = uyg.ayarlar.lock().unwrap();
            (
                a.mantik("audio.noise_suppression", false),
                uyg.mikser.lock().unwrap().kisma_acik,
                a.mantik("audio.ptt", false),
                a.mantik("camera.blur", false),
            )
        };
        let gurultu_var = cfg!(windows);
        bilesen::panel_kenarli(14.0, 6.0, 14.0, 6.0).show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.spacing_mut().item_spacing.y = 0.0;
            // Python _AnahtarSatiri: 52 px satır; başlık ve açıklama satırın üst ve alt yarısında ortalı
            let satir = |ui: &mut Ui, baslik: &str, aciklama: &str, deger: &mut bool, etkin: bool| -> bool {
                let (r, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 52.0), Sense::hover());
                let p = ui.painter();
                p.text(Pos2::new(r.left(), r.top() + 13.0), Align2::LEFT_CENTER, baslik, tema::yazi(tema::GOVDE_PX), tema::YAZI);
                p.text(Pos2::new(r.left(), r.top() + 39.0), Align2::LEFT_CENTER, aciklama, tema::yazi(tema::EN_KUCUK_PX), tema::SOLUK);
                let ar = Rect::from_min_size(Pos2::new(r.right() - 40.0, r.center().y - 12.0), Vec2::new(40.0, 24.0));
                let mut alt = ui.new_child(egui::UiBuilder::new().max_rect(ar).id_salt(("anahtar", baslik)));
                bilesen::anahtar(&mut alt, deger, etkin).on_hover_text(aciklama).changed()
            };
            if satir(ui, "Gürültü azaltma", if gurultu_var { "Klavye ve fan sesini bastırır" } else { "Bu kurulumda yok (rnnoise)" }, &mut gurultu, gurultu_var) {
                #[cfg(windows)]
                uyg.ses.gurultu_ayarla(gurultu);
                uyg.ayarla("audio.noise_suppression", gurultu.into());
            }
            if satir(ui, "Otomatik kısma", "Konuşunca oyun sesi kısılır", &mut kisma, true) {
                uyg.mikser.lock().unwrap().kisma_acik = kisma;
                uyg.ayarla("audio.ducking", kisma.into());
            }
            if satir(ui, "Bas-konuş", "Tuşa basılıyken mikrofon açık", &mut ptt, true) {
                let tus = uyg.ayarlar.lock().unwrap().metin("hotkeys.bas_konus");
                if ptt && tus.is_empty() {
                    uyg.bildir("Önce bas-konuş tuşunu seç", None, false);
                    istek = Some(Istek::AyarlarAc("kisayollar"));
                } else {
                    uyg.ayarla("audio.ptt", ptt.into());
                    if let Err(e) = uyg.bas_konusu_uygula() {
                        uyg.bildir(&format!("Bas-konuş tuşu geçersiz: {e}"), None, false);
                    }
                }
            }
            if satir(ui, "Kamera arka planı", "Arkadaki odayı bulanıklaştırır", &mut bulanik, true) {
                uyg.ayarla("camera.blur", bulanik.into());
                uyg.k.ayar.lock().unwrap().kamera_bulanik = bulanik;
            }
        });
        istek
    }
}
