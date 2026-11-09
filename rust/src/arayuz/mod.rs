//! Arayüz (egui): ana pencere, mini bar, ayarlar, tepsi. Python ui/ klasörünün karşılığı.
//!
//! Arayüz video hattını ve ses motorunu asla beklemez: önizleme için hattın son karesini alır,
//! durumu DurumDeposu'ndan okur. Komutlar Uygulama::komut'a gider (kısayollarla aynı yol).

mod ayar_penceresi;
mod mini;
mod tema;
#[cfg(windows)]
mod tepsi;

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui::{self, Color32, RichText};

use rizeon::durum::Durum;
use rizeon::kare::KareRef;
use rizeon::sahne::Kaynak;
use rizeon::tek_kopya::TekKopya;
use rizeon::uygulama::{Komut, Uygulama};
use rizeon::{tekrar, surum};

pub fn calistir(uyg: Arc<Uygulama>, tek: TekKopya) -> eframe::Result {
    let simge = image::load_from_memory(include_bytes!("../../../kurulum/uygulama.ico"))
        .ok()
        .map(|r| {
            let r = r.into_rgba8();
            let (w, h) = r.dimensions();
            egui::IconData { rgba: r.into_raw(), width: w, height: h }
        });
    let mut vp = egui::ViewportBuilder::default().with_title("RizeOn").with_inner_size([1180.0, 760.0]).with_min_inner_size([760.0, 520.0]);
    if let Some(s) = simge {
        vp = vp.with_icon(Arc::new(s));
    }
    let secenek = eframe::NativeOptions { viewport: vp, ..Default::default() };
    eframe::run_native("RizeOn", secenek, Box::new(move |cc| Ok(Box::new(Pencere::new(cc, uyg, tek)))))
}

struct Pencere {
    uyg: Arc<Uygulama>,
    /// tek kopya kilidi pencere yaşadıkça tutulur
    _tek: Arc<TekKopya>,
    onizleme: Option<egui::TextureHandle>,
    son_kare: Option<KareRef>,
    son_onizleme: Instant,
    onizleme_fps: f32,
    mini: mini::MiniBar,
    ayarlar: ayar_penceresi::AyarPenceresi,
    yeniden_adlandir: Option<(usize, String)>,
    gizli: bool,
    tepsiye: bool,
    cikiyor: bool,
    #[cfg_attr(not(windows), allow(dead_code))]
    yakalamadan_gizlendi: bool,
    #[cfg(windows)]
    tepsi: Option<tepsi::Tepsi>,
    #[cfg(windows)]
    kisayollar: Option<rizeon::kisayol::KisayolYoneticisi>,
    kisayol_surumu: u64,
    durum: Durum,
}

impl Pencere {
    fn new(cc: &eframe::CreationContext, uyg: Arc<Uygulama>, tek: TekKopya) -> Self {
        tema::kur(&cc.egui_ctx);
        let ctx = cc.egui_ctx.clone();
        *uyg.uyandir.lock().unwrap() = Some(Box::new(move || ctx.request_repaint()));
        let tek = Arc::new(tek);
        // İkinci kopya açılmak istenirse pencereyi öne getir
        {
            let (tek, uyg, ctx) = (tek.clone(), uyg.clone(), cc.egui_ctx.clone());
            std::thread::Builder::new()
                .name("tek-kopya".into())
                .spawn(move || loop {
                    if tek.goster_istendi() {
                        uyg.arayuz_istekleri.lock().unwrap().push_back(Komut::AnaPencere);
                        ctx.request_repaint();
                    }
                    std::thread::sleep(Duration::from_millis(250));
                })
                .ok();
        }
        let (onizleme_fps, tepsiye) = {
            let a = uyg.ayarlar.lock().unwrap();
            (a.sayi("ui.preview_fps", 15).clamp(5, 30) as f32, a.mantik("ui.minimize_to_tray", true))
        };
        let mut p = Pencere {
            mini: mini::MiniBar::default(),
            ayarlar: ayar_penceresi::AyarPenceresi::default(),
            durum: uyg.depo.al(),
            uyg,
            _tek: tek,
            onizleme: None,
            son_kare: None,
            son_onizleme: Instant::now(),
            onizleme_fps,
            yeniden_adlandir: None,
            gizli: false,
            tepsiye,
            cikiyor: false,
            yakalamadan_gizlendi: false,
            #[cfg(windows)]
            tepsi: None,
            #[cfg(windows)]
            kisayollar: None,
            kisayol_surumu: 0,
        };
        #[cfg(windows)]
        {
            p.tepsi = tepsi::Tepsi::kur(cc.egui_ctx.clone(), p.uyg.clone());
        }
        p.kisayollari_kur();
        p
    }

    fn kisayollari_kur(&mut self) {
        #[cfg(windows)]
        {
            let uyg = self.uyg.clone();
            let y = self.kisayollar.get_or_insert_with(|| {
                rizeon::kisayol::KisayolYoneticisi::baslat(move |ad| {
                    if let Some(k) = Komut::coz(ad) {
                        let m = uyg.komut(k);
                        if !m.is_empty() {
                            uyg.bildir(&m, None, false);
                        }
                    }
                })
            });
            let tuslar: std::collections::HashMap<String, String> = {
                let a = self.uyg.ayarlar.lock().unwrap();
                a.veri
                    .get("hotkeys")
                    .and_then(|v| v.as_object())
                    .map(|m| {
                        m.iter()
                            .filter(|(k, _)| Komut::coz(k).is_some())
                            .filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string())))
                            .collect()
                    })
                    .unwrap_or_default()
            };
            y.grup_ayarla("genel", tuslar);
        }
        self.kisayol_surumu += 1;
    }

    fn tus(&self, komut: &str) -> String {
        let a = self.uyg.ayarlar.lock().unwrap();
        a.veri.get("hotkeys").and_then(|h| h.get(komut)).and_then(|v| v.as_str()).map(rizeon::kisayol::tus_metni).unwrap_or_default()
    }

    /// Kısayol ya da tepsiden gelen arayüz istekleri (pencereyi göster, mini bar, çıkış).
    fn istekleri_isle(&mut self, ctx: &egui::Context) {
        let istekler: Vec<Komut> = self.uyg.arayuz_istekleri.lock().unwrap().drain(..).collect();
        for k in istekler {
            match k {
                Komut::AnaPencere => {
                    self.gizli = false;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(false));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                Komut::MiniBar => self.mini.acik = !self.mini.acik,
                Komut::Cikis => {
                    self.cikiyor = true;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
                _ => {}
            }
        }
    }

    fn onizlemeyi_guncelle(&mut self, ctx: &egui::Context) {
        let aralik = Duration::from_secs_f32(1.0 / self.onizleme_fps);
        if self.son_onizleme.elapsed() >= aralik {
            self.son_onizleme = Instant::now();
            let kare = self.uyg.k.son_kare();
            if self.son_kare.as_ref().is_none_or(|s| !Arc::ptr_eq(s, &kare)) {
                let mut rgba = Vec::with_capacity(kare.veri.len());
                for p in kare.veri.chunks_exact(4) {
                    rgba.extend_from_slice(&[p[2], p[1], p[0], 255]);
                }
                let resim = egui::ColorImage::from_rgba_unmultiplied([kare.w as usize, kare.h as usize], &rgba);
                match &mut self.onizleme {
                    Some(t) => t.set(resim, egui::TextureOptions::LINEAR),
                    None => self.onizleme = Some(ctx.load_texture("onizleme", resim, egui::TextureOptions::LINEAR)),
                }
                self.son_kare = Some(kare);
            }
        }
        ctx.request_repaint_after(aralik);
    }

    fn ust_cubuk(&mut self, ui: &mut egui::Ui) {
        let d = self.durum.clone();
        ui.horizontal(|ui| {
            ui.label(RichText::new("RizeOn").strong().size(16.0));
            ui.label(RichText::new(format!("· {}", d.sahne_adi)).color(tema::YAZI2));
            if d.panik {
                ui.label(RichText::new("PANİK").strong().color(tema::YAZI));
            }
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button("Ayarlar").clicked() {
                    self.ayarlar.ac(&self.uyg);
                }
                if ui.button("Kayıtlar").on_hover_text("Kayıt klasörünü aç").clicked() {
                    let k = rizeon::uygulama::kayit_klasoru(&self.uyg.ayarlar.lock().unwrap());
                    let _ = std::fs::create_dir_all(&k);
                    #[cfg(windows)]
                    rizeon::win::ac(&k);
                }
                if ui.button("Mini bar").clicked() {
                    self.mini.acik = !self.mini.acik;
                }
                ui.label(RichText::new(format!("{:.0} fps", d.fps)).color(tema::SOLUK).small());
                let vc = match d.sanal_kamera.as_str() {
                    "açık" => "Sanal kamera açık",
                    "yok" => "OBS sanal kamera yok",
                    "kapalı" => "Sanal kamera duraklatıldı",
                    _ => "Sanal kamera hatası",
                };
                ui.label(RichText::new(vc).color(tema::YAZI2).small()).on_hover_text(&d.son_hata);
                let vb = match d.sanal_mikrofon.as_str() {
                    "açık" => "VB-Cable açık",
                    "yok" => "VB-Cable yok",
                    "kapalı" => "Ses duraklatıldı",
                    _ => "VB-Cable hatası",
                };
                ui.label(RichText::new(vb).color(tema::YAZI2).small()).on_hover_text(&d.ses_hatasi);
            });
        });
    }

    fn sahne_paneli(&mut self, ui: &mut egui::Ui) {
        let sahneler = self.uyg.k.sahneler.liste();
        let aktif = self.uyg.k.sahneler.indeks();
        ui.horizontal(|ui| {
            ui.label(RichText::new("Sahneler").color(tema::YAZI2));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.small_button("+").on_hover_text("Yeni sahne").clicked() && self.uyg.k.sahneler.ekle().is_some() {
                    self.uyg.sahneleri_kaydet();
                }
            });
        });
        let mut sil = None;
        for (i, s) in sahneler.iter().enumerate() {
            if let Some((j, ad)) = &mut self.yeniden_adlandir {
                if *j == i {
                    let r = ui.text_edit_singleline(ad);
                    if r.lost_focus() {
                        let ad = ad.clone();
                        self.uyg.k.sahneler.yeniden_adlandir(i, &ad);
                        self.uyg.sahneleri_kaydet();
                        self.yeniden_adlandir = None;
                    } else {
                        r.request_focus();
                    }
                    continue;
                }
            }
            let ipucu = if i < 9 { self.tus(&format!("sahne.sec:{}", i + 1)) } else { String::new() };
            let r = ui.selectable_label(i == aktif, format!("{}  {}", i + 1, s.ad));
            let r = if ipucu.is_empty() { r } else { r.on_hover_text(ipucu) };
            if r.clicked() {
                self.uyg.komut(Komut::Sahne(i));
            }
            r.context_menu(|ui| {
                if ui.button("Yeniden adlandır").clicked() {
                    self.yeniden_adlandir = Some((i, s.ad.clone()));
                    ui.close();
                }
                if ui.add_enabled(sahneler.len() > 1, egui::Button::new("Sil")).clicked() {
                    sil = Some(i);
                    ui.close();
                }
            });
        }
        if let Some(i) = sil {
            if self.uyg.k.sahneler.sil(i) {
                self.uyg.sahneleri_kaydet();
            }
        }
        ui.add_space(12.0);
        self.kaynak_paneli(ui);
    }

    fn kaynak_paneli(&mut self, ui: &mut egui::Ui) {
        let sahne = self.uyg.k.sahneler.aktif();
        let mut degisti = false;
        ui.horizontal(|ui| {
            ui.label(RichText::new("Kaynaklar").color(tema::YAZI2));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.menu_button("+", |ui| {
                    if ui.button("Metin (alt bant)").clicked() {
                        let mut a = serde_json::Map::new();
                        a.insert("text".into(), "Adın Soyadın".into());
                        degisti |= self.uyg.k.sahneler.kaynak_ekle(Kaynak::yeni("metin", "", a));
                        ui.close();
                    }
                    if ui.button("Görsel (logo)…").clicked() {
                        let mut a = serde_json::Map::new();
                        a.insert("path".into(), "".into());
                        degisti |= self.uyg.k.sahneler.kaynak_ekle(Kaynak::yeni("gorsel", "", a));
                        ui.close();
                    }
                    if ui.button("Bekleme ekranı").clicked() {
                        degisti |= self.uyg.k.sahneler.kaynak_ekle(Kaynak::yeni("bekleme", "", Default::default()));
                        ui.close();
                    }
                    if !sahne.kamera_var() && ui.button("Kamera").clicked() {
                        let mut a = serde_json::Map::new();
                        a.insert("ana".into(), true.into());
                        a.insert("yer".into(), "kose".into());
                        degisti |= self.uyg.k.sahneler.kaynak_ekle(Kaynak::yeni("kamera", "Webcam", a));
                        ui.close();
                    }
                });
            });
        });
        let n = sahne.kaynaklar.len();
        for (i, k) in sahne.kaynaklar.iter().enumerate() {
            ui.horizontal(|ui| {
                let mut g = k.gorunur;
                if ui.checkbox(&mut g, "").on_hover_text("Göster / gizle").changed() {
                    degisti |= self.uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| x.gorunur = g);
                }
                let ad = if k.tur == "metin" { format!("{} · {}", k.ad, k.metin("text")) } else { k.ad.clone() };
                ui.label(RichText::new(ad).color(if k.gorunur { tema::YAZI } else { tema::SOLUK }));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.menu_button("…", |ui| {
                        if i > 0 && ui.button("Öne al").clicked() {
                            degisti |= self.uyg.k.sahneler.kaynak_tasi(&k.kimlik, -1);
                            ui.close();
                        }
                        if i + 1 < n && ui.button("Arkaya al").clicked() {
                            degisti |= self.uyg.k.sahneler.kaynak_tasi(&k.kimlik, 1);
                            ui.close();
                        }
                        if k.tur == "metin" {
                            let mut m = k.metin("text");
                            ui.label("Yazı:");
                            if ui.text_edit_singleline(&mut m).changed() {
                                degisti |= self.uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| {
                                    x.ayar.insert("text".into(), m.clone().into());
                                });
                            }
                        }
                        if k.tur == "gorsel" {
                            let mut m = k.metin("path");
                            ui.label("Dosya yolu (PNG/JPG):");
                            if ui.text_edit_singleline(&mut m).changed() {
                                degisti |= self.uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| {
                                    x.ayar.insert("path".into(), m.clone().into());
                                });
                            }
                        }
                        if k.tur == "kamera" {
                            let mut tam = k.tam();
                            if ui.checkbox(&mut tam, "Tam ekran").changed() {
                                degisti |= self.uyg.k.sahneler.kaynak_degistir(&k.kimlik, |x| {
                                    x.ayar.insert("yer".into(), if tam { "tam" } else { "kose" }.into());
                                });
                            }
                        }
                        if !k.ana() && ui.button("Kaldır").clicked() {
                            degisti |= self.uyg.k.sahneler.kaynak_sil(&k.kimlik);
                            ui.close();
                        }
                    });
                });
            });
        }
        if degisti {
            self.uyg.sahneleri_kaydet();
        }
    }

    fn seviye(ui: &mut egui::Ui, seviye: f32, genislik: f32) {
        let (r, _) = ui.allocate_exact_size(egui::vec2(genislik, 4.0), egui::Sense::hover());
        let p = ui.painter();
        p.rect_filled(r, 2.0, tema::IZ);
        let db = rizeon::ses::db(seviye);
        let oran = ((db + 60.0) / 60.0).clamp(0.0, 1.0);
        let mut dolu = r;
        dolu.set_width(r.width() * oran);
        p.rect_filled(dolu, 2.0, tema::SES);
    }

    /// Gürültü azaltma ve bas-konuş anahtarları (mikrofon sütununun altında).
    fn mikrofon_secenekleri(&mut self, ui: &mut egui::Ui, d: &Durum) {
        ui.horizontal(|ui| {
            #[cfg(windows)]
            {
                let mut g = self.uyg.ses.gurultu_acik();
                if ui.checkbox(&mut g, RichText::new("Gürültü azalt").small()).on_hover_text("Klavye, fan ve uğultu sesini bastırır (RNNoise)").changed() {
                    self.uyg.ses.gurultu_ayarla(g);
                    self.uyg.ayarla("audio.noise_suppression", g.into());
                }
            }
            let mut ptt = self.uyg.ayarlar.lock().unwrap().mantik("audio.ptt", false);
            let tus = self.tus("bas_konus");
            let ipucu = if tus.is_empty() { "Önce Ayarlar > Kısayollar'da bas-konuş tuşu seç".to_string() } else { format!("{tus} basılıyken mikrofon açık") };
            if ui.checkbox(&mut ptt, RichText::new("Bas-konuş").small()).on_hover_text(ipucu).changed() {
                self.uyg.ayarla("audio.ptt", ptt.into());
                if let Err(e) = self.uyg.bas_konusu_uygula() {
                    self.uyg.ayarla("audio.ptt", false.into());
                    self.uyg.bildir(&format!("Bas-konuş açılamadı: {e}"), None, false);
                }
            }
            if d.bas_konus {
                let (m, r) = if d.konusuyor { ("konuşuyor", tema::SES) } else { ("susuyor", tema::SOLUK) };
                ui.label(RichText::new(m).small().color(r));
            }
        });
    }

    fn kontrol_cubugu(&mut self, ui: &mut egui::Ui) {
        let d = self.durum.clone();
        let seviyeler = self.uyg.mikser.lock().unwrap().seviyeler();
        let sev = |a: &str| seviyeler.iter().find(|(k, _)| k == a).map(|(_, v)| *v).unwrap_or(0.0);
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 14.0;
            // Ses kanalları
            for (anahtar, ad, sessiz, komut, ayar, yol) in [
                ("mikrofon", "Mikrofon", d.mikrofon_sessiz, Komut::Mikrofon, "ses.mikrofon", "audio.mic_gain"),
                ("sistem", "Bilgisayar sesi", d.sistem_sessiz, Komut::Sistem, "ses.sistem", "audio.system_gain"),
            ] {
                ui.vertical(|ui| {
                    ui.set_width(170.0);
                    ui.horizontal(|ui| {
                        let metin = if sessiz { format!("{ad} kapalı") } else { ad.to_string() };
                        if ui
                            .add(egui::Button::new(metin).selected(!sessiz))
                            .on_hover_text(format!("Aç/kapat {}", self.tus(ayar)))
                            .clicked()
                        {
                            self.uyg.komut(komut.clone());
                        }
                    });
                    Self::seviye(ui, if sessiz { 0.0 } else { sev(anahtar) }, 160.0);
                    let mut kazanc = self.uyg.mikser.lock().unwrap().kanal_oku(anahtar).map(|k| k.kazanc()).unwrap_or(1.0);
                    let r = ui.add(egui::Slider::new(&mut kazanc, 0.0..=2.0).show_value(false));
                    if r.changed() {
                        if let Some(k) = self.uyg.mikser.lock().unwrap().kanal(anahtar) {
                            k.kazanc_ayarla(kazanc);
                        }
                    }
                    if r.drag_stopped() || (r.changed() && !r.dragged()) {
                        self.uyg.ayarla(yol, (kazanc as f64).into());
                    }
                    let alt = if anahtar == "mikrofon" { &d.mikrofon_adi } else { &d.sistem_kaynagi };
                    ui.label(RichText::new(alt).small().color(tema::SOLUK));
                    if anahtar == "mikrofon" {
                        self.mikrofon_secenekleri(ui, &d);
                    }
                });
            }
            ui.separator();
            // Kamera
            let kamera_sahnede = self.uyg.k.kamera_sahnede();
            let kamera = self.uyg.kamera_gorunur_acik();
            let r = ui.add_enabled(kamera_sahnede, egui::Button::new(if kamera { "Kamera açık" } else { "Kamera kapalı" }).selected(kamera));
            let r = if kamera_sahnede { r.on_hover_text(self.tus("kamera.ac_kapat")) } else { r.on_disabled_hover_text("Bu sahnede kamera yok") };
            if r.clicked() {
                self.uyg.komut(Komut::Kamera);
            }
            ui.separator();
            // Kayıt
            if d.kayit == "açık" {
                let sn = d.kayit_suresi;
                let renk = if d.kayit_duraklatildi { tema::SOLUK } else { tema::KAYIT };
                ui.label(RichText::new("●").color(renk));
                ui.label(RichText::new(format!("{:02}:{:02}:{:02}", sn / 3600, sn / 60 % 60, sn % 60)).monospace());
                if ui.button(if d.kayit_duraklatildi { "Devam" } else { "Duraklat" }).on_hover_text(self.tus("kayit.duraklat")).clicked() {
                    self.uyg.komut(Komut::KayitDuraklat);
                }
                if ui.button("Bitir").on_hover_text(self.tus("kayit.ac_kapat")).clicked() {
                    self.uyg.komut(Komut::Kayit);
                }
            } else {
                let hazirlaniyor = self.uyg.kayitci.bitiyor();
                let r = ui.add_enabled(!hazirlaniyor, egui::Button::new(if hazirlaniyor { "Kayıt hazırlanıyor…" } else { "Kaydı başlat" }));
                if r.on_hover_text(self.tus("kayit.ac_kapat")).clicked() {
                    let m = self.uyg.komut(Komut::Kayit);
                    if m.starts_with("Kayıt başlamadı") {
                        self.uyg.bildir(&m, None, false);
                    }
                }
            }
            let etiket = tekrar::sure_etiketi(self.uyg.tekrar.sure_sn() as i64);
            let r = ui.add_enabled(self.uyg.tekrar.acik() && !self.uyg.tekrar.kaydediliyor(), egui::Button::new(etiket));
            if r.on_hover_text(format!("Anlık tekrarı kaydet {}", self.tus("anlik_kayit.kaydet"))).clicked() {
                let m = self.uyg.komut(Komut::TekrarKaydet);
                if !m.is_empty() {
                    self.uyg.bildir(&m, None, false);
                }
            }
            if ui.button("Ekran görüntüsü").on_hover_text(self.tus("ekran.goruntusu")).clicked() {
                self.uyg.komut(Komut::EkranGoruntusu);
            }
            if ui.add(egui::Button::new("Panik").selected(d.panik)).on_hover_text(format!("Bekleme ekranı + ses kapalı {}", self.tus("panik"))).clicked() {
                self.uyg.komut(Komut::Panik);
            }
        });
    }

    fn bildirimler(&mut self, ctx: &egui::Context) {
        let mut b = self.uyg.bildirimler.lock().unwrap();
        b.retain(|x| x.zaman.elapsed() < Duration::from_secs(6));
        if b.is_empty() {
            return;
        }
        let liste: Vec<_> = b.iter().cloned().collect();
        drop(b);
        egui::Area::new(egui::Id::unique("bildirimler"))
            .anchor(egui::Align2::CENTER_BOTTOM, egui::vec2(0.0, -150.0))
            .show(ctx, |ui| {
                for x in liste {
                    egui::Frame::popup(ui.style()).fill(tema::YUZEN).show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.label(&x.metin);
                            if let Some(d) = &x.dosya {
                                let etiket = if x.klasorde { "Klasörde göster" } else { "Aç" };
                                if ui.link(etiket).clicked() {
                                    #[cfg(windows)]
                                    if x.klasorde {
                                        rizeon::win::klasorde_goster(d);
                                    } else {
                                        rizeon::win::ac(d);
                                    }
                                    let _ = d;
                                }
                            }
                        });
                    });
                }
            });
        ctx.request_repaint_after(Duration::from_millis(500));
    }

    #[cfg(windows)]
    fn pencereyi_gizle_yakalamadan(&mut self, frame: &eframe::Frame) {
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};
        if self.yakalamadan_gizlendi {
            return;
        }
        if let Ok(h) = frame.window_handle() {
            if let RawWindowHandle::Win32(w) = h.as_raw() {
                // önizleme kendini yakalamasın (sonsuz ayna), karşı tarafa gitmesin
                rizeon::win::yakalamadan_gizle(w.hwnd.get(), true);
                self.yakalamadan_gizlendi = true;
            }
        }
    }
}

impl eframe::App for Pencere {
    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.istekleri_isle(ctx);
        let kapat_istendi = ctx.input(|i| i.viewport().close_requested());
        if kapat_istendi && !self.cikiyor && self.tepsiye {
            // Pencere kapanınca tepside çalışmaya devam (kamera/mikrofon arka planda)
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            ctx.send_viewport_cmd(egui::ViewportCommand::Visible(false));
            self.gizli = true;
        }
        let gorunur = !self.gizli;
        self.uyg.k.onizleme_gorunur.store(gorunur, Ordering::Relaxed);
        self.uyg.k.mini_gorunur.store(self.mini.acik, Ordering::Relaxed);
        if self.gizli {
            ctx.request_repaint_after(Duration::from_millis(500));
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        #[cfg(windows)]
        self.pencereyi_gizle_yakalamadan(frame);
        let _ = frame;
        self.durum = self.uyg.depo.al();
        self.onizlemeyi_guncelle(&ctx);
        egui::Panel::top("ust").frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(10)).show(ui, |ui| self.ust_cubuk(ui));
        egui::Panel::bottom("kontrol").frame(egui::Frame::new().fill(tema::PANEL).inner_margin(12)).show(ui, |ui| self.kontrol_cubugu(ui));
        egui::Panel::left("sahneler")
            .default_size(230.0)
            .frame(egui::Frame::new().fill(tema::PANEL).inner_margin(12))
            .show(ui, |ui| egui::ScrollArea::vertical().show(ui, |ui| self.sahne_paneli(ui)));
        egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(12)).show(ui, |ui| {
            let alan = ui.available_rect_before_wrap();
            let (w, h) = (self.uyg.k.genislik as f32, self.uyg.k.yukseklik as f32);
            let olcek = (alan.width() / w).min(alan.height() / h);
            let boyut = egui::vec2(w * olcek, h * olcek);
            let r = egui::Rect::from_center_size(alan.center(), boyut);
            ui.painter().rect_filled(r, 8.0, tema::ONIZLEME);
            if let Some(t) = &self.onizleme {
                egui::Image::new((t.id(), boyut)).corner_radius(8).paint_at(ui, r);
            }
            let d = &self.durum;
            let alt = format!(
                "{} · {} · kare {:.1} ms{}",
                d.sahne_adi,
                if d.yakalama_yontemi.is_empty() { "ekran yok".to_string() } else { d.yakalama_yontemi.clone() },
                d.kare_suresi_ms,
                if self.uyg.tekrar.acik() { format!(" · tekrar {:.0} MB", self.uyg.tekrar.bellek() as f64 / 1e6) } else { String::new() }
            );
            ui.painter().text(r.left_bottom() + egui::vec2(10.0, -10.0), egui::Align2::LEFT_BOTTOM, alt, egui::FontId::proportional(11.5), Color32::from_white_alpha(140));
        });
        self.bildirimler(&ctx);
        self.mini.goster(&ctx, &self.uyg, &self.durum);
        if self.ayarlar.goster(&ctx, &self.uyg) {
            // kısayollar değişmiş olabilir
            self.kisayollari_kur();
            let a = self.uyg.ayarlar.lock().unwrap();
            self.tepsiye = a.mantik("ui.minimize_to_tray", true);
            self.onizleme_fps = a.sayi("ui.preview_fps", 15).clamp(5, 30) as f32;
        }
        ctx.send_viewport_cmd(egui::ViewportCommand::Title(format!("RizeOn {}", surum::SURUM)));
    }
}
