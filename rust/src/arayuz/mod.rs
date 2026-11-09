//! Arayüz (egui): ana pencere, mini bar, ayarlar, tepsi. Python ui/ klasörünün karşılığı.
//!
//! Ana pencere (Python ui/main_window.py) çerçevesizdir, kendi başlık çubuğuyla:
//!   logo RizeOn · ☰ Gelişmiş · Kayıt klasörü · Son 15 sn'yi kaydet · Mini bar · Ayarlar · _ □ ×
//!
//! Sade görünüm: önizleme, kontrol barı ve ses mikseri.
//! Gelişmiş (☰, ilk açılışta açık, sonra hatırlanır): solda Sahneler ve Kaynaklar, sağda mikserin altında anahtarlar.
//!
//!   orta : "Göster  Ekran 1 ⌄" (her monitör, Pencere seç…, Bölge seç…) · sahne adı, çözünürlük, FPS
//!          16:9 önizleme (kamera fareyle sürüklenir)
//!          kontrol barı: Mikrofon · Sistem sesi · Kamera | Bölge · Kalem | Kayıt | Panik
//!   alt  : CPU · GPU · FPS · Çıkış
//!
//! Pencere daralınca sütunlar alt alta dizilir. Arayüz video hattını ve ses motorunu asla beklemez:
//! önizleme için hattın son karesini alır, durumu DurumDeposu'ndan okur. Komutlar Uygulama::komut'a
//! gider (kısayollarla aynı yol).

mod ayar_penceresi;
mod bilesen;
mod diyalog;
mod katman;
mod mini;
mod paneller;
mod pencereler;
mod simge;
mod tema;
#[cfg(windows)]
mod tepsi;

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui::{self, CursorIcon, Pos2, Rect, ResizeDirection, Sense, Stroke, Ui, Vec2, ViewportCommand};
use serde_json::json;

use rizeon::durum::Durum;
use rizeon::islemci::{GpuSayaci, IslemciOlcer};
use rizeon::kare::KareRef;
use rizeon::tek_kopya::TekKopya;
use rizeon::tekrar;
use rizeon::uygulama::{Komut, Uygulama};

use bilesen::{ipucu, kisalt};
use diyalog::{Amac, Diyalog};
use paneller::Istek;
use tema::beyaz;

const SOL_GENISLIK: f32 = 230.0;
const SAG_GENISLIK: f32 = 264.0;
const BOSLUK: f32 = 16.0;
/// pencere kenarından boyutlandırma payı (px)
const KENAR: f32 = 6.0;
const MIN_SADE: [f32; 2] = [760.0, 560.0];
const MIN_GELISMIS: [f32; 2] = [900.0, 600.0];
const BASLIK_YUK: f32 = 40.0;
/// kontrol barı yüksekliği: 60 px karo + 6 px iç boşluk + 1 px kenarlık (üst ve alt)
const KONTROL_YUK: f32 = 74.0;

#[derive(Clone, Copy, PartialEq, Debug)]
enum Duzen {
    Genis,
    Dar,
    CokDar,
}

pub fn calistir(uyg: Arc<Uygulama>, tek: TekKopya) -> eframe::Result {
    let gelismis = uyg.ayarlar.lock().unwrap().mantik("ui.advanced", true);
    let mut vp = egui::ViewportBuilder::default()
        .with_title("RizeOn")
        .with_decorations(false)
        .with_inner_size([1320.0, 820.0])
        .with_min_inner_size(if gelismis { MIN_GELISMIS } else { MIN_SADE });
    if let Some(s) = simge::logo_ikonu() {
        vp = vp.with_icon(Arc::new(s));
    }
    let secenek = eframe::NativeOptions { viewport: vp, ..Default::default() };
    eframe::run_native("RizeOn", secenek, Box::new(move |cc| Ok(Box::new(Pencere::new(cc, uyg, tek)))))
}

fn tus_metni(uyg: &Uygulama, komut: &str) -> String {
    let a = uyg.ayarlar.lock().unwrap();
    a.veri.get("hotkeys").and_then(|h| h.get(komut)).and_then(|v| v.as_str()).map(rizeon::kisayol::tus_metni).unwrap_or_default()
}

/// Önizlemede sürüklenen kamera: imleçle kutu merkezi arasındaki fark ve kutu boyutu.
struct Surukleme {
    dx: f32,
    dy: f32,
    w: f32,
    h: f32,
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
    katman: katman::Katman,
    secici: pencereler::PencereSecici,
    hakkinda: pencereler::Hakkinda,
    yardim: pencereler::Yardim,
    bildirim: pencereler::BildirimPenceresi,
    /// sanal çıkış sorunu ("" = yok); değişince bildirilir
    cikis_sorunu: String,
    pencere_koptu: bool,
    #[cfg_attr(not(windows), allow(dead_code))]
    tepsi_surumu: u64,
    son_hata: String,
    ayarlar: ayar_penceresi::AyarPenceresi,
    sahneler: paneller::SahnelerPaneli,
    kaynaklar: paneller::KaynaklarPaneli,
    mikser: paneller::MikserPaneli,
    anahtarlar: paneller::AnahtarPaneli,
    diyalog: Option<Diyalog>,
    istek: Option<Istek>,
    gelismis: bool,
    surukleme: Option<Surukleme>,
    logo: Option<egui::TextureHandle>,
    olcer: IslemciOlcer,
    gpu: Option<GpuSayaci>,
    alt_bilgi: String,
    son_olcum: Instant,
    gizli: bool,
    /// ana pencere görev çubuğuna küçültülmüş
    kucuk: bool,
    tepsiye: bool,
    ilk_kuculme: bool,
    onceki_kayit: bool,
    cikiyor: bool,
    #[cfg_attr(not(windows), allow(dead_code))]
    hazirlandi: bool,
    #[cfg(windows)]
    tepsi: Option<tepsi::Tepsi>,
    #[cfg(windows)]
    kisayollar: Option<rizeon::kisayol::KisayolYoneticisi>,
    /// "kalem" kısayol grubu (1-7, Ctrl+Z, Del, Esc) şu an alınmış mı
    #[cfg(windows)]
    kalem_tuslari: bool,
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
        let (onizleme_fps, tepsiye, gelismis) = {
            let a = uyg.ayarlar.lock().unwrap();
            (a.sayi("ui.preview_fps", 15).clamp(5, 30) as f32, a.mantik("ui.minimize_to_tray", true), a.mantik("ui.advanced", true))
        };
        let mut olcer = IslemciOlcer::new();
        let mut gpu = GpuSayaci::new();
        let alt_bilgi = rizeon::islemci::alt_bilgi_metni(Some(olcer.olc().uygulama), gpu.as_mut().and_then(|g| g.oku()), 0.0);
        let mut p = Pencere {
            mini: mini::MiniBar::default(),
            katman: katman::Katman::default(),
            secici: Default::default(),
            hakkinda: Default::default(),
            yardim: Default::default(),
            bildirim: Default::default(),
            cikis_sorunu: String::new(),
            pencere_koptu: false,
            tepsi_surumu: u64::MAX,
            son_hata: String::new(),
            ayarlar: ayar_penceresi::AyarPenceresi::default(),
            sahneler: Default::default(),
            kaynaklar: Default::default(),
            mikser: Default::default(),
            anahtarlar: Default::default(),
            diyalog: None,
            istek: None,
            gelismis,
            surukleme: None,
            logo: simge::logo(&cc.egui_ctx),
            olcer,
            gpu,
            alt_bilgi,
            son_olcum: Instant::now(),
            durum: uyg.depo.al(),
            uyg,
            _tek: tek,
            onizleme: None,
            son_kare: None,
            son_onizleme: Instant::now(),
            onizleme_fps,
            gizli: false,
            kucuk: false,
            tepsiye,
            ilk_kuculme: true,
            onceki_kayit: false,
            cikiyor: false,
            hazirlandi: false,
            #[cfg(windows)]
            tepsi: None,
            #[cfg(windows)]
            kisayollar: None,
            #[cfg(windows)]
            kalem_tuslari: false,
        };
        #[cfg(windows)]
        {
            p.tepsi = tepsi::Tepsi::kur(cc.egui_ctx.clone(), p.uyg.clone());
        }
        p.kisayollari_kur();
        // Geliştirme: ekran görüntüsü karşılaştırması için bir pencereyi açık başlat (RIZEON_AC=hakkinda|yardim|secici|ayarlar|bildirim)
        if std::env::var("RIZEON_AC").is_ok() {
            // ana pencere kenara çekilsin, açılan pencere görünsün
            cc.egui_ctx.send_viewport_cmd(ViewportCommand::OuterPosition(egui::pos2(1600.0, 0.0)));
        }
        match std::env::var("RIZEON_AC").as_deref() {
            Ok("hakkinda") => p.hakkinda.acik = true,
            Ok("yardim") => p.yardim.ac(""),
            Ok("secici") => p.secici.ac(),
            Ok("kaynakbolge") => p.katman.kaynak_bolgesi_sec(&p.uyg),
            Ok("bolgesec") => {
                let _ = p.katman.bolge_ac_kapat(&p.uyg);
            }
            Ok("kalem") => {
                let _ = p.katman.kalem_ac_kapat(&p.uyg);
            }
            Ok("bolge") => {
                p.uyg.bolge_sec([0.2, 0.25, 0.4, 0.35], "vurgula");
                let _ = p.katman.kalem_ac_kapat(&p.uyg);
                p.uyg.k.cizim.basla("kare", rizeon::cizim::RENKLER[1], 0.3, 0.35, 1.0);
                p.uyg.k.cizim.surukle(0.45, 0.5);
                p.uyg.k.cizim.bitir();
                p.uyg.k.cizim.yazi_ekle(rizeon::cizim::RENKLER[2], 0.3, 0.52, "Deneme yazısı", 1.0);
            }
            Ok(a) if a.starts_with("ayarlar") => p.ayarlari_ac(a.strip_prefix("ayarlar:")),
            Ok("bildirim") => p.uyg.bildirim_ekle(rizeon::uygulama::Bildirim {
                metin: "Mikrofon kapandı".into(),
                tus: "Ctrl+Shift+M".into(),
                eylem: None,
                kisayol: false,
                zaman: Instant::now(),
            }),
            _ => {}
        }
        p
    }

    /// Ayarlar penceresini açar; kaydedilemeyen kısayollar tabloda ⚠ ile görünür.
    fn ayarlari_ac(&mut self, sekme: Option<&str>) {
        #[cfg(windows)]
        {
            self.ayarlar.basarisiz = self.kisayollar.as_ref().map(|k| k.hatalar.lock().unwrap().keys().cloned().collect()).unwrap_or_default();
        }
        self.ayarlar.ac_sekme(&self.uyg, sekme);
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
                            let tus = tus_metni(&uyg, ad);
                            uyg.bildirim_ekle(rizeon::uygulama::Bildirim { metin: m, tus, eylem: None, kisayol: true, zaman: Instant::now() });
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
    }

    /// Kalem açıkken (yazı yazılmıyorken) kalem tuşları genel kısayol olarak alınır; kapanınca bırakılır.
    #[cfg(windows)]
    fn kalem_tuslarini_esle(&mut self) {
        let istenen = self.katman.kalem_tuslari_istenen();
        if istenen == self.kalem_tuslari {
            return;
        }
        let Some(y) = self.kisayollar.as_ref() else { return };
        if istenen {
            let mut tuslar: std::collections::HashMap<String, String> = {
                let a = self.uyg.ayarlar.lock().unwrap();
                a.veri
                    .get("pen_hotkeys")
                    .and_then(|v| v.as_object())
                    .map(|m| m.iter().filter(|(k, _)| Komut::coz(k).is_some()).filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string()))).collect())
                    .unwrap_or_default()
            };
            tuslar.entry("kalem.kapat".into()).or_insert_with(|| "Esc".into());
            y.grup_ayarla("kalem", tuslar);
        } else {
            y.grubu_kaldir("kalem");
        }
        self.kalem_tuslari = istenen;
    }

    fn tus(&self, komut: &str) -> String {
        tus_metni(&self.uyg, komut)
    }

    /// Kısayol ya da tepsiden gelen arayüz istekleri (pencereyi göster, mini bar, çıkış).
    fn istekleri_isle(&mut self, ctx: &egui::Context) {
        let istekler: Vec<Komut> = self.uyg.arayuz_istekleri.lock().unwrap().drain(..).collect();
        for k in istekler {
            match k {
                Komut::AnaPencere => {
                    self.gizli = false;
                    self.mini.acik = false;
                    ctx.send_viewport_cmd(ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(ViewportCommand::Minimized(false));
                    ctx.send_viewport_cmd(ViewportCommand::Focus);
                }
                Komut::MiniBar => self.mini_moda_gec(ctx),
                Komut::Bolge => {
                    let m = self.katman.bolge_ac_kapat(&self.uyg);
                    self.katman.bildirimler.push(m);
                }
                Komut::Kalem => {
                    let m = self.katman.kalem_ac_kapat(&self.uyg);
                    self.katman.bildirimler.push(m);
                }
                Komut::KalemTemizle => {
                    let m = katman::Katman::temizle(&self.uyg);
                    self.katman.bildirimler.push(m);
                }
                Komut::KalemTur(n) => self.katman.tur_sec(n),
                Komut::KalemRenk(n) => self.katman.renk_sec(n),
                Komut::KalemKalinlik(n) => self.katman.kalinlik_sec(n),
                Komut::KalemGeriAl => {
                    self.uyg.k.cizim.geri_al();
                }
                Komut::KalemKapat => {
                    let m = self.katman.kapat_komutu(&self.uyg);
                    self.katman.bildirimler.push(m);
                }
                Komut::KaynakSec => self.secici.ac(),
                Komut::Cikis => self.cikmayi_onayla(),
                Komut::Hakkinda => self.hakkinda.acik = true,
                Komut::Yardim => self.yardim.ac(&self.cikis_sorunu.clone()),
                Komut::KayitKlasoru => self.kayit_klasorunu_ac(),
                _ => {}
            }
        }
    }

    /// Tepsi menüsü / alt satırdaki Çıkış: kayıt sürüyorsa önce sorar.
    fn cikmayi_onayla(&mut self) {
        if self.durum.kayit == "açık" {
            self.diyalog = Some(Diyalog::soru("Çıkış", "Kayıt sürüyor. Uygulama tamamen kapatılsın mı?\nKayıt durdurulup kaydedilir.", Amac::Cikis));
        } else {
            self.cikiyor = true;
        }
    }

    fn mini_moda_gec(&mut self, ctx: &egui::Context) {
        self.mini.acik = true;
        self.gizli = true;
        ctx.send_viewport_cmd(ViewportCommand::Visible(false));
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

    fn gelismis_ayarla(&mut self, ctx: &egui::Context, acik: bool) {
        self.gelismis = acik;
        ctx.send_viewport_cmd(ViewportCommand::MinInnerSize(Vec2::from(if acik { MIN_GELISMIS } else { MIN_SADE })));
        self.uyg.ayarla("ui.advanced", acik.into());
    }

    // ------------------------------------------------------------ başlık çubuğu

    /// Windows başlık düğmesi (46×40): üzerine gelince açık gri, kapat düğmesi kırmızı.
    fn pencere_dugmesi(ui: &mut Ui, simge_adi: &'static str, ad: &str, kapat: bool) -> egui::Response {
        let (r, resp) = ui.allocate_exact_size(Vec2::new(46.0, BASLIK_YUK), Sense::click());
        let uzerinde = resp.hovered() || resp.is_pointer_button_down_on();
        if uzerinde {
            ui.painter().rect_filled(r, 0.0, if kapat { tema::KAPAT } else { beyaz(0.07) });
        }
        simge::ortaya(ui, simge_adi, if uzerinde { tema::BEYAZ } else { tema::YAZI2 }, 14.0, r, false);
        resp.on_hover_text(ad)
    }

    fn baslik_cubugu(&mut self, ui: &mut Ui) {
        let ctx = ui.ctx().clone();
        let r = ui.max_rect();
        let buyuk = ctx.input(|i| i.viewport().maximized.unwrap_or(false));
        // boş yerden sürükleyince pencere taşınır, çift tıklayınca ekranı kaplar
        let arka = ui.interact(r, ui.scope_id().with("baslik-arka"), Sense::click_and_drag());
        if arka.double_clicked() {
            ctx.send_viewport_cmd(ViewportCommand::Maximized(!buyuk));
        } else if arka.drag_started_by(egui::PointerButton::Primary) {
            ctx.send_viewport_cmd(ViewportCommand::StartDrag);
        }
        let y = r.bottom() - 0.5;
        ui.painter().line_segment([Pos2::new(r.left(), y), Pos2::new(r.right(), y)], Stroke::new(1.0, egui::Color32::from_white_alpha(15)));

        ui.horizontal_centered(|ui| {
            ui.spacing_mut().item_spacing.x = 4.0;
            ui.add_space(12.0 - 4.0);
            if let Some(l) = &self.logo {
                ui.add(egui::Image::new((l.id(), Vec2::splat(18.0))));
            }
            ui.add_space(4.0);
            bilesen::etiket(ui, "RizeOn", tema::KUCUK_PX, tema::YAZI2);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.spacing_mut().item_spacing.x = 0.0;
                if Self::pencere_dugmesi(ui, "kapat", "Kapat", true).clicked() {
                    ctx.send_viewport_cmd(ViewportCommand::Close);
                }
                let (s, a) = if buyuk { ("geri_yukle", "Önceki boyuta getir") } else { ("buyut", "Ekranı kapla") };
                if Self::pencere_dugmesi(ui, s, a, false).clicked() {
                    ctx.send_viewport_cmd(ViewportCommand::Maximized(!buyuk));
                }
                if Self::pencere_dugmesi(ui, "kucult", "Simge durumuna küçült", false).clicked() {
                    ctx.send_viewport_cmd(ViewportCommand::Minimized(true));
                }
                ui.add_space(8.0);
                if bilesen::SimgeDugme::new("ayarlar").boyut(28.0, 16.0).goster(ui).on_hover_text("Ayarlar").clicked() {
                    self.ayarlari_ac(None);
                }
                ui.add_space(2.0);
                ui.spacing_mut().item_spacing.x = 4.0;
                if bilesen::hap(ui, "Mini bar", false, true).on_hover_text("Ana pencereyi gizle, her zaman üstte duran küçük bara geç").clicked() {
                    self.mini_moda_gec(&ctx);
                }
                let (tekrar_acik, sure) = {
                    let a = self.uyg.ayarlar.lock().unwrap();
                    (a.mantik("record.replay", true), a.sayi("record.replay_seconds", 15))
                };
                if tekrar_acik {
                    let etiket = tekrar::sure_etiketi(sure);
                    let metin = if etiket.ends_with("dk") { format!("{etiket}'yı kaydet") } else { format!("{etiket}'yi kaydet") };
                    let etkin = self.uyg.tekrar.acik() && !self.uyg.tekrar.kaydediliyor();
                    let r = bilesen::hap(ui, &metin, false, etkin)
                        .on_hover_text(ipucu(&format!("{etiket} MP4 olarak kaydedilir (bellekte tutulur, diske sürekli yazılmaz)"), &self.tus("anlik_kayit.kaydet")));
                    if r.clicked() {
                        let m = self.uyg.komut(Komut::TekrarKaydet);
                        if !m.is_empty() {
                            self.uyg.bildir(&m, None, false);
                        }
                    }
                }
                if bilesen::hap(ui, "Kayıt klasörü", false, true)
                    .on_hover_text("Kayıtların, son 2 dk kayıtlarının ve ekran görüntülerinin olduğu klasörü açar")
                    .clicked()
                {
                    self.kayit_klasorunu_ac();
                }
                if bilesen::hap(ui, "☰ Gelişmiş", self.gelismis, true).on_hover_text("Sahneler, kaynaklar ve ses anahtarları").clicked() {
                    let acik = !self.gelismis;
                    self.gelismis_ayarla(&ctx, acik);
                }
            });
        });
    }

    /// Çerçevesiz pencereyi kenarlarından boyutlandırma (Windows'un kendi boyutlandırmasıyla).
    fn kenar_boyutlandir(&self, ctx: &egui::Context) {
        let (buyuk, tam) = ctx.input(|i| (i.viewport().maximized.unwrap_or(false), i.viewport().fullscreen.unwrap_or(false)));
        if buyuk || tam || ctx.dragged_id().is_some() {
            return;
        }
        let Some(p) = ctx.input(|i| i.pointer.hover_pos()) else { return };
        let r = ctx.content_rect();
        let (sol, sag) = (p.x <= r.left() + KENAR, p.x >= r.right() - KENAR);
        let (ust, alt) = (p.y <= r.top() + KENAR, p.y >= r.bottom() - KENAR);
        let yon = match (sol, sag, ust, alt) {
            (true, _, true, _) => ResizeDirection::NorthWest,
            (_, true, true, _) => ResizeDirection::NorthEast,
            (true, _, _, true) => ResizeDirection::SouthWest,
            (_, true, _, true) => ResizeDirection::SouthEast,
            (true, ..) => ResizeDirection::West,
            (_, true, ..) => ResizeDirection::East,
            (_, _, true, _) => ResizeDirection::North,
            (_, _, _, true) => ResizeDirection::South,
            _ => return,
        };
        ctx.set_cursor_icon(match yon {
            ResizeDirection::NorthWest | ResizeDirection::SouthEast => CursorIcon::ResizeNwSe,
            ResizeDirection::NorthEast | ResizeDirection::SouthWest => CursorIcon::ResizeNeSw,
            ResizeDirection::West | ResizeDirection::East => CursorIcon::ResizeHorizontal,
            _ => CursorIcon::ResizeVertical,
        });
        if ctx.input(|i| i.pointer.primary_pressed()) {
            ctx.send_viewport_cmd(ViewportCommand::BeginResize(yon));
        }
    }

    // ------------------------------------------------------------ gövde

    /// Kontrol barının en geniş hâli (kayıt sürerken): sütunlar kayıt başlayınca yer değiştirmesin.
    fn kontrol_genisligi(ui: &Ui) -> f32 {
        let kg = bilesen::kayit_grubu_genisligi(ui.painter(), 0, 40.0, true, true);
        6.0 * tema::KARO.0 + kg + 3.0 * 9.0 + 9.0 * 4.0 + 12.0 + 2.0
    }

    fn govde(&mut self, ui: &mut Ui) {
        let gorunen = ui.available_size();
        egui::ScrollArea::vertical().auto_shrink(false).show(ui, |ui| {
            egui::Frame::new().inner_margin(BOSLUK as i8).show(ui, |ui| {
                ui.spacing_mut().item_spacing = Vec2::splat(BOSLUK);
                let ic = (gorunen.x - 2.0 * BOSLUK).max(100.0);
                let orta_min = Self::kontrol_genisligi(ui);
                let gerekli = orta_min + if self.gelismis { SOL_GENISLIK + BOSLUK } else { 0.0 } + SAG_GENISLIK + BOSLUK;
                let duzen = if ic >= gerekli {
                    Duzen::Genis
                } else if ic >= SOL_GENISLIK + BOSLUK + SAG_GENISLIK {
                    Duzen::Dar
                } else {
                    Duzen::CokDar
                };
                let orta_min_yuk = 32.0 + 12.0 + 180.0 + 12.0 + KONTROL_YUK;
                let yuk_icin = |w: f32| 32.0 + 12.0 + (w * 9.0 / 16.0).round() + 12.0 + KONTROL_YUK;
                let ust_alta = egui::Layout::top_down(egui::Align::Min);
                match duzen {
                    Duzen::Genis => {
                        let h = (gorunen.y - 2.0 * BOSLUK).max(orta_min_yuk);
                        ui.horizontal_top(|ui| {
                            let mut orta_w = ic - SAG_GENISLIK - BOSLUK;
                            if self.gelismis {
                                orta_w -= SOL_GENISLIK + BOSLUK;
                                ui.allocate_ui_with_layout(Vec2::new(SOL_GENISLIK, h), ust_alta, |ui| {
                                    ui.set_width(SOL_GENISLIK);
                                    self.sol_sutun(ui);
                                });
                            }
                            ui.allocate_ui_with_layout(Vec2::new(orta_w, h), ust_alta, |ui| self.orta_sutun(ui, orta_w, h));
                            ui.allocate_ui_with_layout(Vec2::new(SAG_GENISLIK, h), ust_alta, |ui| {
                                ui.set_width(SAG_GENISLIK);
                                self.sag_sutun(ui);
                            });
                        });
                    }
                    Duzen::Dar => {
                        self.orta_sutun(ui, ic, yuk_icin(ic));
                        ui.horizontal_top(|ui| {
                            let w = if self.gelismis { (ic - BOSLUK) / 2.0 } else { ic };
                            if self.gelismis {
                                ui.allocate_ui_with_layout(Vec2::new(w, 0.0), ust_alta, |ui| {
                                    ui.set_width(w);
                                    self.sol_sutun(ui);
                                });
                            }
                            ui.allocate_ui_with_layout(Vec2::new(w, 0.0), ust_alta, |ui| {
                                ui.set_width(w);
                                self.sag_sutun(ui);
                            });
                        });
                    }
                    Duzen::CokDar => {
                        self.orta_sutun(ui, ic, yuk_icin(ic));
                        if self.gelismis {
                            ui.allocate_ui_with_layout(Vec2::new(ic, 0.0), ust_alta, |ui| {
                                ui.set_width(ic);
                                self.sol_sutun(ui);
                            });
                        }
                        ui.allocate_ui_with_layout(Vec2::new(ic, 0.0), ust_alta, |ui| {
                            ui.set_width(ic);
                            self.sag_sutun(ui);
                        });
                    }
                }
            });
        });
    }

    fn sol_sutun(&mut self, ui: &mut Ui) {
        ui.spacing_mut().item_spacing.y = 12.0;
        let uyg = self.uyg.clone();
        let tus = |k: &str| tus_metni(&uyg, k);
        self.sahneler.goster(ui, &self.uyg, &tus);
        if let Some(i) = self.kaynaklar.goster(ui, &self.uyg) {
            self.istek = Some(i);
        }
    }

    fn sag_sutun(&mut self, ui: &mut Ui) {
        ui.spacing_mut().item_spacing.y = 12.0;
        let d = self.durum.clone();
        if let Some(i) = self.mikser.goster(ui, &self.uyg, &d) {
            self.istek = Some(i);
        }
        if self.gelismis {
            if let Some(i) = self.anahtarlar.goster(ui, &self.uyg) {
                self.istek = Some(i);
            }
        }
    }

    /// Göster satırı, önizleme ve kontrol barı. Önizleme 16:9 kalır, bar hemen altında durur.
    fn orta_sutun(&mut self, ui: &mut Ui, w: f32, h: f32) {
        let (alan, _) = ui.allocate_exact_size(Vec2::new(w, h), Sense::hover());
        let o = alan.min;
        let mut satir = ui.new_child(egui::UiBuilder::new().max_rect(Rect::from_min_size(o, Vec2::new(w, 32.0))).layout(egui::Layout::left_to_right(egui::Align::Center)));
        self.goster_satiri(&mut satir);

        let bos = (h - 32.0 - 12.0 - 12.0 - KONTROL_YUK).max(180.0);
        let ph = (w * 9.0 / 16.0).round().min(bos);
        let kutu = Rect::from_min_size(o + Vec2::new(0.0, 44.0), Vec2::new(w, ph));
        let cerceve = self.onizleme_ciz(ui, kutu);

        let ky = o.y + 44.0 + cerceve.height().round() + 12.0;
        self.kontrol_bari(ui, Rect::from_min_size(Pos2::new(o.x, ky), Vec2::new(w, KONTROL_YUK)));
    }

    fn goster_metni(&self, d: &Durum) -> String {
        if !d.bolge.is_empty() {
            return "Seçili bölge".into();
        }
        if d.kaynak_turu == "pencere" {
            return kisalt(if d.kaynak_adi.is_empty() { "Pencere" } else { &d.kaynak_adi }, 22);
        }
        format!("Ekran {}", self.uyg.k.ayar.lock().unwrap().monitor + 1)
    }

    fn goster_satiri(&mut self, ui: &mut Ui) {
        let d = self.durum.clone();
        let metin = self.goster_metni(&d);
        let font = tema::yazi(tema::GOVDE_PX);
        let g1 = ui.painter().layout_no_wrap("Göster".into(), font.clone(), tema::YAZI2);
        let g2 = ui.painter().layout_no_wrap(metin.clone(), font, tema::YAZI);
        let gen = 12.0 + g1.size().x + 8.0 + g2.size().x + 8.0 + 14.0 + 12.0;
        let (r, resp) = ui.allocate_exact_size(Vec2::new(gen.round(), 32.0), Sense::click());
        let resp = resp.on_hover_cursor(CursorIcon::PointingHand).on_hover_text("Göster: neyin paylaşılacağını seç");
        let p = ui.painter();
        p.rect(r.shrink(0.5), 16.0, tema::PANEL, Stroke::new(1.0, beyaz(tema::A_KENARLIK)), egui::StrokeKind::Middle);
        bilesen::zemin(ui, r, 16.0, false, false, &resp, true);
        let p = ui.painter();
        p.galley(Pos2::new(r.left() + 12.0, r.center().y - g1.size().y / 2.0), g1.clone(), tema::YAZI2);
        p.galley(Pos2::new(r.left() + 12.0 + g1.size().x + 8.0, r.center().y - g2.size().y / 2.0), g2, tema::YAZI);
        simge::simge(ui, "asagi", tema::YAZI2, 14.0, Pos2::new(r.right() - 26.0, r.center().y - 7.0), false);

        egui::Popup::menu(&resp).frame(bilesen::menu_cercevesi()).align(egui::RectAlign::BOTTOM_START).show(|ui| {
            ui.set_min_width(240.0);
            let monitor = self.uyg.k.ayar.lock().unwrap().monitor;
            let tum_ekran = d.kaynak_turu == "ekran" && d.bolge.is_empty();
            let monitorler = rizeon::yakalama::monitorler();
            let n = monitorler.len().max(1);
            for i in 0..n {
                let aciklama = monitorler.get(i).map(|m| format!("Tüm ekran · {}×{}", m.w, m.h)).unwrap_or_else(|| "Tüm ekran".into());
                if bilesen::menu_ogesi(ui, &format!("Ekran {}", i + 1), &aciklama, tum_ekran && i == monitor).clicked() {
                    self.uyg.monitor_sec(i);
                }
            }
            if bilesen::menu_ogesi(ui, "Pencere seç…", "Sadece bir uygulama", d.kaynak_turu == "pencere").clicked() {
                self.secici.ac();
            }
            let tus = self.tus("bolge.sec");
            let aciklama = if tus.is_empty() { "Kutu çiz".to_string() } else { format!("Kutu çiz · {tus}") };
            if bilesen::menu_ogesi(ui, "Bölge seç…", &aciklama, !d.bolge.is_empty()).clicked() {
                let m = self.katman.bolge_ac_kapat(&self.uyg);
                self.katman.bildirimler.push(m);
            }
        });

        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            let ad = if d.sahne_adi.is_empty() { self.uyg.k.sahneler.aktif().ad.clone() } else { d.sahne_adi.clone() };
            bilesen::etiket(ui, &format!("{ad} · {}p · {} FPS", self.uyg.k.yukseklik, self.uyg.k.fps), tema::KUCUK_PX, tema::SOLUK);
        });
    }

    /// Görünen köşe kamerası (çıkış pikselinde x, y, w, h). Sürüklenip taşınabilir.
    fn kamera_kutusu(&self) -> Option<(f32, f32, f32, f32)> {
        let k = &self.uyg.k;
        if k.panik.load(Ordering::Relaxed) || !k.kamera_istegi.load(Ordering::Relaxed) {
            return None;
        }
        let sahne = k.sahneler.aktif();
        sahne.kaynaklar.iter().find(|x| x.tur == "kamera" && x.ana() && x.gorunur && !x.tam())?;
        let (x, y, w, h) = k.ayar.lock().unwrap().yer.dikdortgen(k.genislik, k.yukseklik);
        Some((x as f32, y as f32, w as f32, h as f32))
    }

    /// Karşı tarafın gördüğü 16:9 görüntü; köşedeki kamera fareyle sürüklenip taşınır.
    fn onizleme_ciz(&mut self, ui: &mut Ui, kutu: Rect) -> Rect {
        let (gw, gh) = (self.uyg.k.genislik as f32, self.uyg.k.yukseklik.max(1) as f32);
        let oran = gw / gh;
        let w = kutu.width().min(kutu.height() * oran);
        let r = Rect::from_center_size(kutu.center(), Vec2::new(w, w / oran));
        let resp = ui.interact(r, ui.scope_id().with("onizleme"), Sense::drag());
        ui.painter().rect_filled(r, 8.0, tema::ONIZLEME);
        if let Some(t) = &self.onizleme {
            egui::Image::new((t.id(), r.size())).corner_radius(8).paint_at(ui, r);
        }
        let cikis = |p: Pos2| -> Option<(f32, f32)> {
            let (x, y) = ((p.x - r.left()) / r.width(), (p.y - r.top()) / r.height());
            ((0.0..=1.0).contains(&x) && (0.0..=1.0).contains(&y)).then_some((x * gw, y * gh))
        };
        let kamera = self.kamera_kutusu();
        let ustunde = |p: Option<Pos2>| -> Option<(f32, f32, (f32, f32, f32, f32))> {
            let (cx, cy) = cikis(p?)?;
            let k = kamera?;
            (cx >= k.0 && cx <= k.0 + k.2 && cy >= k.1 && cy <= k.1 + k.3).then_some((cx, cy, k))
        };
        if resp.drag_started_by(egui::PointerButton::Primary) {
            if let Some((cx, cy, (x, y, w, h))) = ustunde(resp.interact_pointer_pos()) {
                self.surukleme = Some(Surukleme { dx: cx - (x + w / 2.0), dy: cy - (y + h / 2.0), w, h });
            }
        }
        if let Some(s) = &self.surukleme {
            ui.ctx().set_cursor_icon(CursorIcon::Grabbing);
            if let Some((px, py)) = resp.interact_pointer_pos().and_then(cikis) {
                let cx = (px - s.dx).clamp(s.w / 2.0, gw - s.w / 2.0) / gw;
                let cy = (py - s.dy).clamp(s.h / 2.0, gh - s.h / 2.0) / gh;
                self.uyg.k.ayar.lock().unwrap().yer.konum = Some((cx as f64, cy as f64));
            }
            if resp.drag_stopped() || !resp.dragged() {
                self.surukleme = None;
                if let Some((x, y)) = self.uyg.k.ayar.lock().unwrap().yer.konum {
                    let yuvarla = |v: f64| (v * 10000.0).round() / 10000.0;
                    self.uyg.ayarla("camera.position", json!([yuvarla(x), yuvarla(y)]));
                }
            }
        } else if ustunde(resp.hover_pos()).is_some() {
            ui.ctx().set_cursor_icon(CursorIcon::Grab);
            resp.on_hover_text("Kamerayı fareyle sürükleyip taşı");
        }
        r
    }

    fn kontrol_bari(&mut self, ui: &mut Ui, r: Rect) {
        let d = self.durum.clone();
        ui.painter().rect(r.shrink(0.5), 12.0, tema::PANEL, Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)), egui::StrokeKind::Middle);
        let kayitta = d.kayit == "açık";
        let kayit_gen = if kayitta { bilesen::kayit_grubu_genisligi(ui.painter(), d.kayit_suresi, 40.0, true, true) } else { tema::KARO.0 };
        let icerik = 6.0 * tema::KARO.0 + kayit_gen + 3.0 * 9.0 + 9.0 * 4.0;
        let x0 = (r.center().x - icerik / 2.0).max(r.left() + 7.0).round();
        let ic = Rect::from_min_size(Pos2::new(x0, r.top() + 7.0), Vec2::new(icerik, 60.0));
        let mut ui = ui.new_child(egui::UiBuilder::new().max_rect(ic).layout(egui::Layout::left_to_right(egui::Align::Center)));
        let ui = &mut ui;
        ui.spacing_mut().item_spacing.x = 4.0;

        let mik = d.mikrofon_sessiz;
        if bilesen::karo(ui, Some("mikrofon"), if mik { "Sessizde" } else { "Mikrofon" }, mik, false, true)
            .on_hover_text(ipucu(if mik { "Mikrofonu aç" } else { "Mikrofonu kapat" }, &self.tus("ses.mikrofon")))
            .clicked()
        {
            self.uyg.komut(Komut::Mikrofon);
        }
        let sis = d.sistem_sessiz;
        if bilesen::karo(ui, Some("ses"), "Sistem sesi", sis, false, true)
            .on_hover_text(ipucu(if sis { "Sistem sesini aç" } else { "Sistem sesini kapat" }, &self.tus("ses.sistem")))
            .clicked()
        {
            self.uyg.komut(Komut::Sistem);
        }
        let kamera_sahnede = self.uyg.k.kamera_sahnede();
        let kamera = self.uyg.kamera_gorunur_acik();
        let r = bilesen::karo(ui, Some("kamera"), "Kamera", !kamera, false, kamera_sahnede);
        let r = if kamera_sahnede {
            r.on_hover_text(ipucu(if kamera { "Kamerayı kapat" } else { "Kamerayı aç" }, &self.tus("kamera.ac_kapat")))
        } else {
            r.on_hover_text("Bu sahnede kamera yok. Kaynaklar'dan Kamera ekleyebilirsin.")
        };
        if r.clicked() {
            self.uyg.komut(Komut::Kamera);
        }
        bilesen::dikey_ayrac(ui, 60.0);
        if bilesen::karo(ui, Some("bolge"), "Bölge", false, !d.bolge.is_empty(), true)
            .on_hover_text(ipucu("Bölge: ekranın bir kısmını yakınlaştır ya da vurgula", &self.tus("bolge.sec")))
            .clicked()
        {
            let m = self.uyg.komut(Komut::Bolge);
            if !m.is_empty() {
                self.uyg.bildir(&m, None, false);
            }
        }
        if bilesen::karo(ui, Some("kalem"), "Kalem", false, self.katman.kalem_acik(), true)
            .on_hover_text(ipucu("Kalem: ekranın üstüne çiz", &self.tus("kalem.ac_kapat")))
            .clicked()
        {
            self.uyg.komut(Komut::Kalem);
        }
        bilesen::dikey_ayrac(ui, 60.0);
        if kayitta {
            let s = bilesen::kayit_grubu(ui, d.kayit_suresi, d.kayit_duraklatildi, 40.0, true, true, &self.tus("kayit.duraklat"), &self.tus("kayit.ac_kapat"));
            if s.duraklat {
                self.uyg.komut(Komut::KayitDuraklat);
            }
            if s.bitir {
                self.uyg.komut(Komut::Kayit);
            }
        } else {
            let hazirlaniyor = self.uyg.kayitci.bitiyor();
            let r = bilesen::karo(ui, Some("kayit"), "Kayıt", false, false, !hazirlaniyor);
            let r = if hazirlaniyor { r.on_hover_text("Önceki kayıt kaydediliyor…") } else { r.on_hover_text(ipucu("Kaydı başlat", &self.tus("kayit.ac_kapat"))) };
            if r.clicked() {
                let m = self.uyg.komut(Komut::Kayit);
                if m.starts_with("Kayıt başlamadı") {
                    self.uyg.bildir(&m, None, false);
                }
            }
        }
        bilesen::dikey_ayrac(ui, 60.0);
        if bilesen::karo(ui, None, "Panik", false, d.panik, true)
            .on_hover_text(ipucu("Panik: tüm çıkışı anında durdurur, bekleme ekranına geçer", &self.tus("panik")))
            .clicked()
        {
            self.uyg.komut(Komut::Panik);
        }
    }

    fn alt_satir(&mut self, ui: &mut Ui) {
        if self.son_olcum.elapsed() >= Duration::from_secs(1) {
            self.son_olcum = Instant::now();
            let cpu = self.olcer.olc().uygulama;
            let gpu = self.gpu.as_mut().and_then(|g| g.oku());
            self.alt_bilgi = rizeon::islemci::alt_bilgi_metni(Some(cpu), gpu, self.durum.fps);
        }
        ui.ctx().request_repaint_after(Duration::from_secs(1));
        let r = ui.max_rect().expand2(Vec2::new(12.0, 0.0));
        let y = r.top() + 0.5;
        ui.painter().line_segment([Pos2::new(r.left(), y), Pos2::new(r.right(), y)], Stroke::new(1.0, egui::Color32::from_white_alpha(15)));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            ui.spacing_mut().item_spacing.x = 8.0;
            if bilesen::hap(ui, "Çıkış", false, true).on_hover_text("RizeOn'u tamamen kapat (tepside de kalmaz)").clicked() {
                self.cikmayi_onayla();
            }
            bilesen::etiket(ui, &self.alt_bilgi, tema::EN_KUCUK_PX, tema::SOLUK);
        });
    }

    // ------------------------------------------------------------ istekler

    fn istek_isle(&mut self) {
        if let Some(i) = self.istek.take() {
            match i {
                Istek::Diyalog(d) => self.diyalog = Some(d),
                Istek::PencereSecKaynak => self.secici.kaynak_ac(true),
                Istek::BolgeSecKaynak => self.katman.kaynak_bolgesi_sec(&self.uyg),
                Istek::AyarlarAc(sekme) => self.ayarlari_ac(Some(sekme)),
            }
        }
        if let Some(baslik) = self.secici.secilen_kaynak.take() {
            let a = json!({ "title": baslik });
            self.istek = paneller::KaynaklarPaneli::ekle(&self.uyg, "pencere", a.as_object().cloned().unwrap_or_default());
        }
        if let Some((monitor, rect, piksel)) = self.katman.secilen_kaynak.take() {
            let a = json!({ "monitor": monitor, "rect": rect, "pixels": piksel });
            self.istek = paneller::KaynaklarPaneli::ekle(&self.uyg, "bolge", a.as_object().cloned().unwrap_or_default());
        }
    }

    #[cfg(windows)]
    fn pencereyi_hazirla(&mut self, frame: &eframe::Frame) {
        use raw_window_handle::{HasWindowHandle, RawWindowHandle};
        if self.hazirlandi {
            return;
        }
        if let Ok(h) = frame.window_handle() {
            if let RawWindowHandle::Win32(w) = h.as_raw() {
                // önizleme kendini yakalamasın (sonsuz ayna), karşı tarafa gitmesin
                rizeon::win::yakalamadan_gizle(w.hwnd.get(), true);
                // Windows 11: çerçevesiz pencerenin köşeleri 8 px yuvarlak
                rizeon::win::koseleri_yuvarla(w.hwnd.get());
                self.hazirlandi = true;
            }
        }
    }

    fn kayit_klasorunu_ac(&self) {
        let k = rizeon::uygulama::kayit_klasoru(&self.uyg.ayarlar.lock().unwrap());
        let _ = std::fs::create_dir_all(&k);
        #[cfg(windows)]
        rizeon::win::ac(&k);
    }

    /// Durum değişikliklerinden doğan bildirimler (Python shell._durumu_goster).
    fn durum_bildirimleri(&mut self) {
        let d = &self.durum;
        let koptu = d.kaynak_turu == "pencere" && d.ekran_kaynagi == "koptu";
        if koptu && !self.pencere_koptu {
            // Tüm ekrana kendiliğinden dönülmez: yayında başka bir şey görünmesin
            self.uyg.bildir("Seçilen pencere kapandı · Göster menüsünden yenisini seç", None, false);
        }
        self.pencere_koptu = koptu;
        let sorun = pencereler::cikis_sorunu(&d.sanal_kamera, &d.sanal_mikrofon);
        if sorun != self.cikis_sorunu {
            if !sorun.is_empty() {
                self.uyg.bildirim_ekle(rizeon::uygulama::Bildirim {
                    metin: sorun.clone(),
                    tus: String::new(),
                    eylem: Some(rizeon::uygulama::BildirimEylemi::Yardim),
                    kisayol: false,
                    zaman: Instant::now(),
                });
            }
            #[cfg(windows)]
            if let Some(t) = &mut self.tepsi {
                t.sorun_ayarla(&sorun);
            }
            self.cikis_sorunu = sorun.clone();
        }
        // Sanal çıkış hataları yukarıdaki uyarıyla gösterildi; aynısı ikinci kez çıkmasın
        let h = d.son_hata.clone();
        if !h.is_empty() && h != self.son_hata && !(!sorun.is_empty() && (h.starts_with("Sanal") || h.starts_with("OBS"))) {
            self.uyg.bildir(&h, None, false);
        }
        self.son_hata = h;
    }
}

impl eframe::App for Pencere {
    /// Saydam pencereler (mini bar, katman) için arka plan tamamen saydam temizlenir.
    fn clear_color(&self, _v: &egui::Visuals) -> [f32; 4] {
        [0.0; 4]
    }

    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.istekleri_isle(ctx);
        if self.cikiyor {
            ctx.send_viewport_cmd(ViewportCommand::Close);
        }
        let kapat_istendi = ctx.input(|i| i.viewport().close_requested());
        if kapat_istendi && !self.cikiyor && self.tepsiye {
            // Kapat düğmesi uygulamayı kapatmaz; saatin yanına (sistem tepsisine) küçülür.
            ctx.send_viewport_cmd(ViewportCommand::CancelClose);
            if self.durum.kayit == "açık" {
                // Kayıt sürüyor: görünür kalsın, mini bardan durdurulsun.
                self.mini_moda_gec(ctx);
                self.uyg.bildir("Kayıt sürüyor · mini bardan durdurabilirsin", None, false);
            } else {
                ctx.send_viewport_cmd(ViewportCommand::Visible(false));
                self.gizli = true;
                if self.ilk_kuculme {
                    self.ilk_kuculme = false;
                    self.uyg.bildir("RizeOn tepside çalışıyor · kısayollar açık, kamera kapalı", None, false);
                }
            }
        }
        // Kayıt kısayolla (başka bir uygulamadayken) başladıysa mini bar açılsın: kayıt sürdüğü görünsün
        let kayitta = self.uyg.depo.al().kayit == "açık";
        if kayitta && !self.onceki_kayit && !self.mini.acik {
            let odakta = ctx.input(|i| i.viewport().focused.unwrap_or(false));
            if self.gizli || !odakta {
                self.mini_moda_gec(ctx);
            }
        }
        self.onceki_kayit = kayitta;
        let kucuk = ctx.input(|i| i.viewport().minimized.unwrap_or(false));
        // (küçültülmüşken kamera açık kalır: önizleme_görünür kameranın kullanımını da belirler)
        self.uyg.k.onizleme_gorunur.store(!self.gizli, Ordering::Relaxed);
        self.kucuk = kucuk;
        let gorunur = !self.gizli && !kucuk;
        // Ana pencere küçültülmüş ya da tepsideyken eframe arayüzü hiç çalıştırmaz; katman, kalem barı,
        // bildirim ve Ayarlar gibi pencereler ana pencerenin arayüzü içinde çizildiği için onlar da
        // açılamaz. Bunlardan biri gerekiyorsa ana pencere görünmese de arayüz çalıştırılır.
        if !gorunur {
            let gerekli = self.katman.etkin()
                || self.istek.is_some()
                || self.diyalog.is_some()
                || self.bildirim.gosteriyor()
                || !self.uyg.bildirimler.lock().unwrap().is_empty()
                || self.ayarlar.acik_mi()
                || self.secici.acik_mi()
                || self.hakkinda.acik
                || self.yardim.acik;
            if gerekli {
                ctx.send_viewport_cmd(ViewportCommand::RequestPaintWhileHidden);
                ctx.request_repaint();
            }
        }
        self.uyg.k.mini_gorunur.store(self.mini.acik, Ordering::Relaxed);
        if self.gizli {
            ctx.request_repaint_after(Duration::from_millis(500));
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        #[cfg(windows)]
        self.pencereyi_hazirla(frame);
        let _ = frame;
        self.durum = self.uyg.depo.al();
        if !self.gizli && !self.kucuk {
            self.onizlemeyi_guncelle(&ctx);
        }
        egui::Panel::top("baslik")
            .exact_size(BASLIK_YUK)
            .resizable(false)
            .show_separator_line(false)
            .frame(egui::Frame::new().fill(tema::ZEMIN))
            .show(ui, |ui| self.baslik_cubugu(ui));
        egui::Panel::bottom("alt")
            .exact_size(31.0)
            .resizable(false)
            .show_separator_line(false)
            .frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(egui::Margin { left: 12, right: 12, top: 0, bottom: 0 }))
            .show(ui, |ui| self.alt_satir(ui));
        egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN)).show(ui, |ui| self.govde(ui));
        self.kenar_boyutlandir(&ctx);
        self.istek_isle();
        if let Some((amac, metin)) = diyalog::goster(&ctx, &mut self.diyalog) {
            match amac {
                Amac::Cikis => self.cikiyor = true,
                Amac::Bilgi => {}
                a => paneller::diyalog_sonucu(&self.uyg, a, metin),
            }
        }
        self.durum_bildirimleri();
        #[cfg(windows)]
        {
            let surum = self.uyg.depo.surum();
            if surum != self.tepsi_surumu || self.son_olcum.elapsed() < Duration::from_millis(20) {
                self.tepsi_surumu = surum;
                if let Some(t) = &mut self.tepsi {
                    t.durumu_goster(&self.durum, &self.uyg);
                }
            }
        }
        self.bildirim.goster(&ctx, &self.uyg);
        match self.bildirim.istenen.take() {
            Some(rizeon::uygulama::BildirimEylemi::Yardim) => self.yardim.ac(&self.cikis_sorunu.clone()),
            Some(rizeon::uygulama::BildirimEylemi::Ayarlar(s)) => self.ayarlari_ac(Some(s)),
            _ => {}
        }
        self.hakkinda.goster(&ctx);
        self.yardim.goster(&ctx);
        self.mini.goster(&ctx, &self.uyg, &self.durum);
        if self.durum.kaynak_turu == "pencere" && (self.katman.kalem_acik() || !self.durum.bolge.is_empty()) {
            // pencere yakalamaya geçildi: kalem, bölge seçimi ve bölge kapanır
            self.katman.hepsini_kapat(&self.uyg);
        }
        self.katman.goster(&ctx, &self.uyg);
        for m in std::mem::take(&mut self.katman.bildirimler) {
            if !m.is_empty() {
                self.uyg.bildir(&m, None, false);
            }
        }
        #[cfg(windows)]
        self.kalem_tuslarini_esle();
        self.secici.goster(&ctx, &self.uyg);
        let mut hakkinda_istendi = false;
        if self.ayarlar.goster(&ctx, &self.uyg, &mut hakkinda_istendi) {
            // kısayollar değişmiş olabilir
            self.kisayollari_kur();
            {
                let a = self.uyg.ayarlar.lock().unwrap();
                self.tepsiye = a.mantik("ui.minimize_to_tray", true);
                self.onizleme_fps = a.sayi("ui.preview_fps", 15).clamp(5, 30) as f32;
            }
            if let Some(m) = self.ayarlar.bilgi.take() {
                self.diyalog = Some(Diyalog::bilgi("Ayarlar", &m));
            }
        }
        if hakkinda_istendi {
            self.hakkinda.acik = true;
        }
    }
}
