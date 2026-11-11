//! Ayarlar penceresi (Python ui/settings_dialog.py): Genel, Kamera, Ses ve Kısayollar.
//!
//! Ayarların bir kopyası (taslak) üzerinde çalışılır; "Kaydet" ile settings.json'a yazılır ve
//! çalışan parçalara uygulanır. Monitör ve kamera cihazı değişikliği yeniden açılınca geçerli olur.

use std::collections::HashSet;
use std::sync::Arc;

use eframe::egui::{self, Align2, Pos2, Rect, Sense, Stroke, Ui, Vec2};
use serde_json::{json, Value};

use rizeon::uygulama::Uygulama;

use super::bilesen;
use super::simge;
use super::tema::{self, beyaz};

const KOSELER: [(&str, &str); 4] = [("bottom-right", "Sağ alt"), ("bottom-left", "Sol alt"), ("top-right", "Sağ üst"), ("top-left", "Sol üst")];
const SES_MODLARI: [(&str, &str); 3] = [
    ("auto", "Tüm ses (Zoom/Discord hariç, yankı yapmaz)"),
    ("all", "Hoparlörden çıkan her şey"),
    ("app", "Sadece bir uygulama"),
];
const VARSAYILAN_KISAYOLLAR: [(&str, &str); 20] = [
    ("bolge.sec", "Ctrl+Shift+S"),
    ("kalem.ac_kapat", "Ctrl+Shift+D"),
    ("ses.mikrofon", "Ctrl+Shift+M"),
    ("ses.sistem", "Ctrl+Shift+A"),
    ("kamera.ac_kapat", "Ctrl+Shift+C"),
    ("anlik_kayit.kaydet", "Ctrl+Shift+B"),
    ("ekran.goruntusu", "Ctrl+Shift+G"),
    ("kalem.temizle", "Ctrl+Shift+X"),
    ("panik", "Ctrl+Shift+P"),
    ("sahne.sec:1", "Ctrl+Shift+1"),
    ("sahne.sec:2", "Ctrl+Shift+2"),
    ("sahne.sec:3", "Ctrl+Shift+3"),
    ("sahne.sec:4", "Ctrl+Shift+4"),
    ("sahne.sec:5", "Ctrl+Shift+5"),
    ("sahne.sec:6", "Ctrl+Shift+6"),
    ("sahne.sec:7", "Ctrl+Shift+7"),
    ("sahne.sec:8", "Ctrl+Shift+8"),
    ("sahne.sec:9", "Ctrl+Shift+9"),
    ("kayit.ac_kapat", "Ctrl+Shift+R"),
    ("kayit.duraklat", "Ctrl+Shift+K"),
];
const VARSAYILAN_KALEM_TUSLARI: [(&str, &str); 10] = [
    ("kalem.tur:1", "1"),
    ("kalem.tur:2", "2"),
    ("kalem.tur:3", "3"),
    ("kalem.tur:4", "4"),
    ("kalem.tur:5", "5"),
    ("kalem.tur:6", "6"),
    ("kalem.tur:7", "7"),
    ("kalem.geri_al", "Ctrl+Z"),
    ("kalem.temizle", "Del"),
    ("kalem.kapat", "Esc"),
];

fn komut_adi(grup: &str, komut: &str) -> String {
    if grup == "pen_hotkeys" && komut == "kalem.temizle" {
        return "Kalem: hepsini sil".into();
    }
    if let Some(n) = komut.strip_prefix("sahne.sec:") {
        return format!("Sahne {n}");
    }
    match komut {
        "bolge.sec" => "Bölge seç / tam ekran",
        "kalem.ac_kapat" => "Kalemi aç/kapat",
        "ses.mikrofon" => "Mikrofon aç/kapat",
        "ses.sistem" => "Bilgisayar sesi aç/kapat",
        "kamera.ac_kapat" => "Kamera aç/kapat",
        "anlik_kayit.kaydet" => "Son dakikaları kaydet (anlık tekrar)",
        "ekran.goruntusu" => "Ekran görüntüsü al",
        "kalem.temizle" => "Çizimleri sil",
        "panik" => "Panik (bekleme ekranı)",
        "kayit.ac_kapat" => "Yerel kaydı başlat/durdur",
        "kayit.duraklat" => "Kaydı duraklat/devam et",
        "kaynak.sec" => "Ne gösterilsin (tüm ekran / pencere)",
        "toplanti.pencere" => "Toplantıda paylaş (pencereyi aç/kapat)",
        "bas_konus" => "Bas-konuş tuşu",
        "kalem.tur:1" => "Kalem: kalem",
        "kalem.tur:2" => "Kalem: fosforlu",
        "kalem.tur:3" => "Kalem: ok",
        "kalem.tur:4" => "Kalem: kare",
        "kalem.tur:5" => "Kalem: yazı",
        "kalem.tur:6" => "Kalem: lazer",
        "kalem.tur:7" => "Kalem: silgi",
        "kalem.geri_al" => "Kalem: geri al",
        "kalem.kapat" => "Kalem: kapat",
        k => k,
    }
    .to_string()
}

#[derive(Clone, Copy, PartialEq, Default)]
enum Sekme {
    #[default]
    Genel,
    Kamera,
    Ses,
    Kisayollar,
}

struct KisayolSatiri {
    grup: &'static str,
    komut: String,
    tus: String,
}

#[derive(Default)]
pub struct AyarPenceresi {
    acik: bool,
    sekme: Sekme,
    taslak: Value,
    eski: Value,
    monitorler: Vec<String>,
    mikrofonlar: Vec<String>,
    haric: String,
    tablo: Vec<KisayolSatiri>,
    duzenlenen: Option<(usize, bool)>,
    hata: String,
    mod_bilgisi: String,
    /// alınamayan kısayolların komutları (⚠ ile gösterilir)
    pub basarisiz: HashSet<String>,
    /// kaydedince gösterilecek bilgi (monitör ve kamera değişikliği)
    pub bilgi: Option<String>,
    /// bir sonraki karede pencere öne getirilsin
    odakla: bool,
    gizlendi: bool,
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

// ------------------------------------------------------------------ alanlar (Qt QSS ile aynı)

const ALAN_YUK: f32 = 36.0;

fn alan_cercevesi(ui: &Ui, r: Rect, resp: &egui::Response, odak: bool) {
    let kenar = if odak {
        beyaz(0.3)
    } else if resp.hovered() {
        beyaz(0.16)
    } else {
        beyaz(tema::A_KENARLIK)
    };
    ui.painter().rect(r.shrink(0.5), 6.0, tema::PANEL, Stroke::new(1.0, kenar), egui::StrokeKind::Middle);
}

/// QLineEdit: 36 px, 6 px köşe, ince kenarlık.
fn alan(ui: &mut Ui, metin: &mut String, ipucu: &str, gen: f32) -> egui::Response {
    ui.scope(|ui| {
        let v = &mut ui.visuals_mut().widgets;
        for w in [&mut v.inactive, &mut v.hovered, &mut v.active] {
            w.corner_radius = egui::CornerRadius::same(6);
        }
        v.inactive.bg_stroke = Stroke::new(1.0, beyaz(tema::A_KENARLIK));
        v.hovered.bg_stroke = Stroke::new(1.0, beyaz(0.16));
        ui.visuals_mut().selection.stroke = Stroke::new(1.0, beyaz(0.3));
        ui.add(
            egui::TextEdit::singleline(metin)
                .hint_text(egui::RichText::new(ipucu).color(tema::SOLUK))
                .font(tema::yazi(tema::GOVDE_PX))
                .text_color(tema::YAZI)
                .desired_width(gen - 18.0)
                .min_size(Vec2::new(gen, ALAN_YUK))
                .margin(egui::vec2(9.0, 4.0))
                .align(Align2::LEFT_CENTER),
        )
    })
    .inner
}

/// QComboBox: seçili metin + aşağı ok; menüden seçilir. Değişince true.
fn secim(ui: &mut Ui, secili: &mut usize, secenekler: &[String], gen: f32) -> bool {
    let (r, resp) = ui.allocate_exact_size(Vec2::new(gen, ALAN_YUK), Sense::click());
    let resp = resp.on_hover_cursor(egui::CursorIcon::PointingHand);
    alan_cercevesi(ui, r, &resp, false);
    let metin = secenekler.get(*secili).cloned().unwrap_or_default();
    let metin = bilesen::kisalt(&metin, ((gen - 40.0) / 6.8) as usize);
    ui.painter().text(Pos2::new(r.left() + 9.0, r.center().y), Align2::LEFT_CENTER, metin, tema::yazi(tema::GOVDE_PX), tema::YAZI);
    simge::simge(ui, "asagi", tema::YAZI2, 12.0, Pos2::new(r.right() - 18.0, r.center().y - 6.0), false);
    let mut degisti = false;
    egui::Popup::menu(&resp).frame(bilesen::menu_cercevesi()).align(egui::RectAlign::BOTTOM_START).show(|ui| {
        ui.set_min_width(gen - 8.0);
        for (i, s) in secenekler.iter().enumerate() {
            let (sr, sresp) = ui.allocate_exact_size(Vec2::new(gen - 8.0, 32.0), Sense::click());
            if sresp.hovered() || i == *secili {
                ui.painter().rect_filled(sr, 6.0, beyaz(if sresp.hovered() { tema::A_UZERINE } else { tema::A_SECILI }));
            }
            ui.painter().text(Pos2::new(sr.left() + 8.0, sr.center().y), Align2::LEFT_CENTER, s, tema::yazi(tema::GOVDE_PX), if sresp.hovered() { tema::BEYAZ } else { tema::YAZI });
            if sresp.clicked() {
                degisti = *secili != i;
                *secili = i;
                ui.close();
            }
        }
    });
    degisti
}

/// QCheckBox: 16 px kutu, 4 px köşe; işaretliyken açık gri dolu.
fn onay(ui: &mut Ui, deger: &mut bool, metin: &str) -> bool {
    let g = ui.painter().layout_no_wrap(metin.to_string(), tema::yazi(tema::GOVDE_PX), tema::YAZI);
    let (r, resp) = ui.allocate_exact_size(Vec2::new(16.0 + 8.0 + g.size().x, 20.0f32.max(g.size().y)), Sense::click());
    let resp = resp.on_hover_cursor(egui::CursorIcon::PointingHand);
    let kutu = Rect::from_min_size(Pos2::new(r.left(), r.center().y - 8.0), Vec2::splat(16.0));
    if *deger {
        ui.painter().rect_filled(kutu, 4.0, tema::DUGME);
    } else {
        ui.painter().rect_stroke(kutu.shrink(0.5), 4.0, Stroke::new(1.0, beyaz(if resp.hovered() { 0.5 } else { 0.3 })), egui::StrokeKind::Middle);
    }
    ui.painter().galley(Pos2::new(kutu.right() + 8.0, r.center().y - g.size().y / 2.0), g, tema::YAZI);
    if resp.clicked() {
        *deger = !*deger;
        return true;
    }
    false
}

/// QSpinBox: değer + birim; sağdaki oklarla, tekerlekle ya da ↑↓ ile değişir.
fn sayi_kutusu(ui: &mut Ui, deger: &mut i64, aralik: (i64, i64), adim: i64, birim: &str, gen: f32, etkin: bool) -> bool {
    let (r, resp) = ui.allocate_exact_size(Vec2::new(gen, ALAN_YUK), if etkin { Sense::click() } else { Sense::hover() });
    alan_cercevesi(ui, r, &resp, resp.has_focus());
    let renk = if etkin { tema::YAZI } else { tema::SOLUK };
    ui.painter().text(Pos2::new(r.left() + 9.0, r.center().y), Align2::LEFT_CENTER, format!("{deger}{birim}"), tema::yazi(tema::GOVDE_PX), renk);
    let ok = Rect::from_min_max(Pos2::new(r.right() - 16.0, r.top() + 1.0), Pos2::new(r.right() - 1.0, r.bottom() - 1.0));
    ui.painter().line_segment([Pos2::new(ok.left(), ok.top()), Pos2::new(ok.left(), ok.bottom())], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
    ui.painter().line_segment([Pos2::new(ok.left(), ok.center().y), Pos2::new(ok.right(), ok.center().y)], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
    let ucgen = |y: f32, yukari: bool| {
        let c = Pos2::new(ok.center().x, y);
        let (a, b) = if yukari { (-2.0, 2.0) } else { (2.0, -2.0) };
        vec![Pos2::new(c.x - 3.5, c.y - a), Pos2::new(c.x + 3.5, c.y - a), Pos2::new(c.x, c.y - b)]
    };
    ui.painter().add(egui::Shape::convex_polygon(ucgen(ok.top() + ok.height() * 0.25 + 1.0, true), tema::YAZI2, Stroke::NONE));
    ui.painter().add(egui::Shape::convex_polygon(ucgen(ok.top() + ok.height() * 0.75, false), tema::YAZI2, Stroke::NONE));
    if !etkin {
        return false;
    }
    let mut yeni = *deger;
    if resp.clicked() {
        if let Some(p) = resp.interact_pointer_pos().filter(|p| ok.contains(*p)) {
            yeni += if p.y < ok.center().y { adim } else { -adim };
        }
        resp.request_focus();
    }
    if resp.hovered() {
        let t = ui.input(|i| i.smooth_scroll_delta.y);
        if t.abs() > 0.5 {
            yeni += if t > 0.0 { adim } else { -adim };
        }
    }
    if resp.has_focus() {
        ui.input(|i| {
            if i.key_pressed(egui::Key::ArrowUp) {
                yeni += adim;
            }
            if i.key_pressed(egui::Key::ArrowDown) {
                yeni -= adim;
            }
        });
    }
    let yeni = yeni.clamp(aralik.0, aralik.1);
    if yeni != *deger {
        *deger = yeni;
        return true;
    }
    false
}

/// QFormLayout satırı: solda etiket (ilk alanın ortasına hizalı), sağda içerik.
fn satir(ui: &mut Ui, etiket: &str, lw: f32, ic: impl FnOnce(&mut Ui)) {
    satir_yuk(ui, etiket, lw, ALAN_YUK, ic);
}

/// Etiketsiz onay kutusu satırları gibi alçak satırlar için `yuk` yüksekliğinde satır.
fn satir_yuk(ui: &mut Ui, etiket: &str, lw: f32, satir_yuk: f32, ic: impl FnOnce(&mut Ui)) {
    let ust = ui.cursor().min;
    let gen = ui.available_width();
    let mut alt = ui.new_child(egui::UiBuilder::new().max_rect(Rect::from_min_size(Pos2::new(ust.x + lw, ust.y), Vec2::new(gen - lw, satir_yuk))).layout(egui::Layout::left_to_right(egui::Align::Center)));
    alt.spacing_mut().item_spacing.x = 6.0;
    ic(&mut alt);
    let yuk = alt.min_rect().height().max(satir_yuk);
    if !etiket.is_empty() {
        ui.painter().text(Pos2::new(ust.x, ust.y + yuk.min(ALAN_YUK) / 2.0), Align2::LEFT_CENTER, etiket, tema::yazi(tema::GOVDE_PX), tema::YAZI);
    }
    ui.allocate_rect(Rect::from_min_size(ust, Vec2::new(gen, yuk)), Sense::hover());
}

fn etiket_genisligi(ui: &Ui, etiketler: &[&str]) -> f32 {
    etiketler.iter().map(|e| ui.painter().layout_no_wrap(e.to_string(), tema::yazi(tema::GOVDE_PX), tema::YAZI).size().x).fold(0.0, f32::max) + 13.0
}

impl AyarPenceresi {
    pub fn acik_mi(&self) -> bool {
        self.acik
    }

    pub fn ac_sekme(&mut self, uyg: &Arc<Uygulama>, sekme: Option<&str>) {
        if self.acik {
            // zaten açık (belki başka pencerenin arkasında): değişiklikleri silmeden öne getir
            self.odakla = true;
            return;
        }
        self.odakla = true;
        self.taslak = uyg.ayarlar.lock().unwrap().veri.clone();
        self.eski = self.taslak.clone();
        self.monitorler = rizeon::yakalama::monitorler().iter().enumerate().map(|(i, m)| format!("Monitör {}  ({}×{})", i + 1, m.w, m.h)).collect();
        if self.monitorler.is_empty() {
            self.monitorler.push("Monitör 1".into());
        }
        #[cfg(windows)]
        {
            self.mikrofonlar = uyg.ses.mikrofonlar();
        }
        let secili = al(&self.taslak, "audio.mic_device").as_str().unwrap_or("").to_string();
        if !secili.is_empty() && !self.mikrofonlar.contains(&secili) {
            self.mikrofonlar.push(secili); // şu an takılı değilse de seçili kalsın
        }
        self.haric = al(&self.taslak, "audio.exclude_apps")
            .as_array()
            .map(|l| l.iter().filter_map(Value::as_str).collect::<Vec<_>>().join(", "))
            .unwrap_or_default();
        let genel = al(&self.taslak, "hotkeys").as_object().cloned().unwrap_or_default();
        let kalem = al(&self.taslak, "pen_hotkeys").as_object().cloned().unwrap_or_default();
        self.tabloyu_doldur(
            genel.iter().map(|(k, v)| (k.clone(), v.as_str().unwrap_or("").to_string())).collect(),
            kalem.iter().map(|(k, v)| (k.clone(), v.as_str().unwrap_or("").to_string())).collect(),
        );
        self.sekme = match sekme {
            Some("kamera") => Sekme::Kamera,
            Some("ses") => Sekme::Ses,
            Some("kisayollar") => Sekme::Kisayollar,
            _ => Sekme::Genel,
        };
        self.hata.clear();
        self.mod_bilgisi.clear();
        self.duzenlenen = None;
        self.acik = true;
    }

    fn tabloyu_doldur(&mut self, genel: Vec<(String, String)>, kalem: Vec<(String, String)>) {
        self.tablo = genel
            .into_iter()
            .map(|(komut, tus)| KisayolSatiri { grup: "hotkeys", tus: if tus.is_empty() { tus } else { rizeon::kisayol::tus_metni(&tus) }, komut })
            .chain(kalem.into_iter().map(|(komut, tus)| KisayolSatiri { grup: "pen_hotkeys", tus: if tus.is_empty() { tus } else { rizeon::kisayol::tus_metni(&tus) }, komut }))
            .collect();
    }

    fn mantik(&self, yol: &str, v: bool) -> bool {
        al(&self.taslak, yol).as_bool().unwrap_or(v)
    }

    fn metin(&self, yol: &str, v: &str) -> String {
        al(&self.taslak, yol).as_str().unwrap_or(v).to_string()
    }

    fn sayi(&self, yol: &str, v: i64) -> i64 {
        al(&self.taslak, yol).as_f64().map(|f| f.round() as i64).unwrap_or(v)
    }

    fn onay_satiri(&mut self, ui: &mut Ui, lw: f32, yol: &str, v: bool, metin: &str) {
        let mut d = self.mantik(yol, v);
        satir_yuk(ui, "", lw, 18.0, |ui| {
            if onay(ui, &mut d, metin) {
                koy(&mut self.taslak, yol, d.into());
            }
        });
    }

    fn alan_satiri(&mut self, ui: &mut Ui, lw: f32, etiket: &str, yol: &str, v: &str, ipucu: &str, dugmeler: &[&str]) -> Option<usize> {
        let mut m = self.metin(yol, v);
        let mut basilan = None;
        satir(ui, etiket, lw, |ui| {
            let d_gen: f32 = dugmeler.iter().map(|d| ui.painter().layout_no_wrap(d.to_string(), tema::yazi(tema::KUCUK_PX), tema::YAZI).size().x + 24.0 + 6.0).sum();
            let gen = ui.available_width() - d_gen;
            if alan(ui, &mut m, ipucu, gen).changed() {
                koy(&mut self.taslak, yol, m.clone().into());
            }
            for (i, d) in dugmeler.iter().enumerate() {
                if bilesen::hap(ui, d, false, true).clicked() {
                    basilan = Some(i);
                }
            }
        });
        basilan
    }

    fn genel(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>) {
        let lw = etiket_genisligi(ui, &["Yakalanan ekran", "Bekleme ekranı yazısı", "Bekleme ekranı resmi/videosu", "Sahne geçiş süresi", "Kayıt klasörü", "Kayıt kodlayıcısı", "Anlık tekrar", "Ekran görüntüsü klasörü"]);
        let mut mon = (self.sayi("video.monitor", 0).max(0) as usize).min(self.monitorler.len() - 1);
        let monitorler = self.monitorler.clone();
        satir(ui, "Yakalanan ekran", lw, |ui| {
            if secim(ui, &mut mon, &monitorler, ui.available_width()) {
                koy(&mut self.taslak, "video.monitor", json!(mon));
            }
        });
        self.onay_satiri(ui, lw, "video.show_cursor", true, "Fare imlecini yayında göster");
        self.onay_satiri(ui, lw, "video.cursor_highlight", false, "İmlecin etrafında halka, tıklayınca dalga efekti");
        self.alan_satiri(ui, lw, "Bekleme ekranı yazısı", "standby_text", "Birazdan döneceğim", "", &[]);
        if self.alan_satiri(ui, lw, "Bekleme ekranı resmi/videosu", "standby_image", "", "İsteğe bağlı: resim (PNG/JPG) ya da kısa video (MP4/GIF)", &["Seç…"]).is_some() {
            #[cfg(windows)]
            if let Some(y) = rizeon::win::dosya_sec("Bekleme ekranı: resim ya da kısa video", &[("Resim ya da video", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.mp4;*.webm;*.avi;*.mov;*.mkv;*.gif;*.wmv;*.m4v")]) {
                koy(&mut self.taslak, "standby_image", y.to_string_lossy().into_owned().into());
            }
        }
        let mut gecis = self.sayi("transition_ms", 300);
        satir(ui, "Sahne geçiş süresi", lw, |ui| {
            if sayi_kutusu(ui, &mut gecis, (0, 2000), 50, " ms", ui.available_width(), true) {
                koy(&mut self.taslak, "transition_ms", gecis.into());
            }
        });
        let varsayilan = rizeon::yollar::varsayilan_kayit_klasoru().to_string_lossy().into_owned();
        match self.alan_satiri(ui, lw, "Kayıt klasörü", "record.folder", "", &varsayilan, &["Seç…", "Aç"]) {
            Some(0) => {
                #[cfg(windows)]
                if let Some(y) = rizeon::win::klasor_sec("Kayıt klasörü", Some(std::path::Path::new(&self.metin("record.folder", "")))) {
                    koy(&mut self.taslak, "record.folder", y.to_string_lossy().into_owned().into());
                }
            }
            Some(_) => {
                let m = self.metin("record.folder", "");
                let k = if m.trim().is_empty() { rizeon::yollar::varsayilan_kayit_klasoru() } else { std::path::PathBuf::from(m.trim()) };
                if std::fs::create_dir_all(&k).is_ok() {
                    #[cfg(windows)]
                    rizeon::win::ac(&k);
                }
            }
            None => {}
        }
        let mut kodlar: Vec<String> = vec!["Otomatik (ekran kartına göre)".into()];
        kodlar.extend(rizeon::ffmpeg::KODLAYICILAR.iter().map(|k| k.to_string()));
        let su_an = self.metin("record.encoder", "auto");
        let mut kod = rizeon::ffmpeg::KODLAYICILAR.iter().position(|k| *k == su_an).map(|i| i + 1).unwrap_or(0);
        satir(ui, "Kayıt kodlayıcısı", lw, |ui| {
            if secim(ui, &mut kod, &kodlar, ui.available_width()) {
                let v = if kod == 0 { "auto" } else { rizeon::ffmpeg::KODLAYICILAR[kod - 1] };
                koy(&mut self.taslak, "record.encoder", v.into());
            }
        });
        let mut tekrar = self.mantik("record.replay", true);
        let mut sure = self.sayi("record.replay_seconds", 15);
        satir(ui, "Anlık tekrar", lw, |ui| {
            if onay(ui, &mut tekrar, "Son dakikaları bellekte tut (diske yazmaz)") {
                koy(&mut self.taslak, "record.replay", tekrar.into());
            }
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if sayi_kutusu(ui, &mut sure, (15, 300), 15, " sn", 90.0, tekrar) {
                    koy(&mut self.taslak, "record.replay_seconds", sure.into());
                }
            });
        });
        if self.alan_satiri(ui, lw, "Ekran görüntüsü klasörü", "screenshot.folder", "", "Kayıt klasörüyle aynı", &["Seç…"]).is_some() {
            #[cfg(windows)]
            if let Some(y) = rizeon::win::klasor_sec("Ekran görüntüsü klasörü", Some(std::path::Path::new(&self.metin("screenshot.folder", "")))) {
                koy(&mut self.taslak, "screenshot.folder", y.to_string_lossy().into_owned().into());
            }
        }
        self.onay_satiri(ui, lw, "ui.toasts", true, "Kısayola basınca köşede bildirim göster");
        self.onay_satiri(ui, lw, "ui.minimize_to_tray", true, "Pencereyi kapatınca sistem tepsisinde çalışmaya devam et");
        let _ = uyg;
    }

    fn kamera(&mut self, ui: &mut Ui) {
        let lw = etiket_genisligi(ui, &["Kamera numarası (0 = ilk kamera)", "Köşe", "Köşedeki boyutu"]);
        let mut no = self.sayi("camera.device", 0);
        satir(ui, "Kamera numarası (0 = ilk kamera)", lw, |ui| {
            if sayi_kutusu(ui, &mut no, (0, 9), 1, "", ui.available_width(), true) {
                koy(&mut self.taslak, "camera.device", no.into());
            }
        });
        self.onay_satiri(ui, lw, "camera.mirror", false, "Ayna görüntüsü (sağ-sol çevir)");
        let adlar: Vec<String> = KOSELER.iter().map(|(_, a)| a.to_string()).collect();
        let su_an = self.metin("camera.corner", "bottom-right");
        let mut k = KOSELER.iter().position(|(c, _)| *c == su_an).unwrap_or(0);
        satir(ui, "Köşe", lw, |ui| {
            if secim(ui, &mut k, &adlar, ui.available_width()) {
                koy(&mut self.taslak, "camera.corner", KOSELER[k].0.into());
            }
        });
        let mut boy = (al(&self.taslak, "camera.size").as_f64().unwrap_or(0.25) * 100.0).round() as i32;
        satir_yuk(ui, "Köşedeki boyutu", lw, 22.0, |ui| {
            let et = format!("%{boy}");
            let ew = ui.painter().layout_no_wrap(et.clone(), tema::yazi(tema::GOVDE_PX), tema::YAZI).size().x;
            let mut su = ui.new_child(egui::UiBuilder::new().max_rect(Rect::from_min_size(ui.cursor().min, Vec2::new(ui.available_width() - ew - 8.0, 20.0))));
            let r = bilesen::surgu_aralik(&mut su, &mut boy, 10, 60);
            ui.allocate_exact_size(Vec2::new(ui.available_width() - ew - 8.0, 20.0), Sense::hover());
            bilesen::etiket(ui, &et, tema::GOVDE_PX, tema::YAZI);
            if r.changed() {
                koy(&mut self.taslak, "camera.size", json!(boy as f64 / 100.0));
            }
        });
        self.onay_satiri(ui, lw, "camera.blur", false, "Arka planı bulanıklaştır");
    }

    fn ses(&mut self, ui: &mut Ui, uyg: &Arc<Uygulama>) {
        let lw = etiket_genisligi(ui, &["Mikrofon", "Bilgisayar sesi", "Sadece bu uygulama", "Hariç tutulanlar", "Kısınca kalan ses"]);
        let mut mikler = vec!["Windows varsayılanı".to_string()];
        mikler.extend(self.mikrofonlar.iter().cloned());
        let su_an = self.metin("audio.mic_device", "");
        let mut m = self.mikrofonlar.iter().position(|x| *x == su_an).map(|i| i + 1).unwrap_or(0);
        satir(ui, "Mikrofon", lw, |ui| {
            if secim(ui, &mut m, &mikler, ui.available_width()) {
                let v = if m == 0 { String::new() } else { mikler[m].clone() };
                koy(&mut self.taslak, "audio.mic_device", v.into());
            }
        });
        let modlar: Vec<String> = SES_MODLARI.iter().map(|(_, a)| a.to_string()).collect();
        let su_an = self.metin("audio.system_mode", "auto");
        let mut sm = SES_MODLARI.iter().position(|(k, _)| *k == su_an).unwrap_or(0);
        satir(ui, "Bilgisayar sesi", lw, |ui| {
            if secim(ui, &mut sm, &modlar, ui.available_width()) {
                koy(&mut self.taslak, "audio.system_mode", SES_MODLARI[sm].0.into());
            }
        });
        self.alan_satiri(ui, lw, "Sadece bu uygulama", "audio.include_app", "", "ör. valorant.exe (Görev Yöneticisi > Ayrıntılar)", &[]);
        let mut haric = self.haric.clone();
        satir(ui, "Hariç tutulanlar", lw, |ui| {
            if alan(ui, &mut haric, "", ui.available_width()).changed() {
                let l: Vec<Value> = haric.split(',').map(str::trim).filter(|s| !s.is_empty()).map(|s| json!(s)).collect();
                koy(&mut self.taslak, "audio.exclude_apps", Value::Array(l));
            }
        });
        self.haric = haric;
        self.onay_satiri(ui, lw, "audio.ducking", false, "Konuşunca bilgisayar sesini otomatik kıs");
        let mut sev = (al(&self.taslak, "audio.ducking_level").as_f64().unwrap_or(0.3) * 100.0).round() as i32;
        satir_yuk(ui, "Kısınca kalan ses", lw, 22.0, |ui| {
            let et = format!("%{sev}");
            let ew = ui.painter().layout_no_wrap(et.clone(), tema::yazi(tema::GOVDE_PX), tema::YAZI).size().x;
            let mut su = ui.new_child(egui::UiBuilder::new().max_rect(Rect::from_min_size(ui.cursor().min, Vec2::new(ui.available_width() - ew - 8.0, 20.0))));
            let r = bilesen::surgu_aralik(&mut su, &mut sev, 5, 80);
            ui.allocate_exact_size(Vec2::new(ui.available_width() - ew - 8.0, 20.0), Sense::hover());
            bilesen::etiket(ui, &et, tema::GOVDE_PX, tema::YAZI);
            if r.changed() {
                koy(&mut self.taslak, "audio.ducking_level", json!(sev as f64 / 100.0));
            }
        });
        ui.add(
            egui::Label::new(
                egui::RichText::new(
                    "Hariç tutulanlar listesinden çalışan ilk uygulamanın sesi gönderilmez; böylece toplantıdaki kişiler kendi seslerini yankı olarak duymaz. Meet tarayıcıda çalıştığı için yankı olursa kulaklık kullan ya da msedge.exe'yi ekle.",
                )
                .font(tema::yazi(tema::KUCUK_PX))
                .color(tema::YAZI2),
            )
            .wrap(),
        );
        satir(ui, "", lw, |ui| {
            if bilesen::hap(ui, "Ses modlarını sıfırla", false, true).on_hover_text("Sesim, Dengeli ve Oyun modları ilk ayarlarına döner").clicked() {
                let mut a = uyg.ayarlar.lock().unwrap();
                rizeon::ses_modlari::varsayilana_don(&mut a);
                a.kaydet();
                if let Some(m) = a.al("audio.modes").cloned() {
                    koy(&mut self.taslak, "audio.modes", m);
                }
                self.mod_bilgisi = "Modlar ilk ayarlarına döndü".into();
            }
            bilesen::etiket(ui, &self.mod_bilgisi, tema::KUCUK_PX, tema::YAZI2);
        });
    }

    fn kisayollar(&mut self, ui: &mut Ui) {
        // altta: açıklama (≈4 satır) + Varsayılanlara dön
        let alt_yuk = 124.0;
        let gen = ui.available_width();
        let tablo_yuk = (ui.available_height() - alt_yuk).max(120.0);
        let (tr, _) = ui.allocate_exact_size(Vec2::new(gen, tablo_yuk), Sense::hover());
        ui.painter().rect(tr, 6.0, tema::PANEL, Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)), egui::StrokeKind::Inside);
        let tus_gen = self
            .tablo
            .iter()
            .map(|s| ui.painter().layout_no_wrap(s.tus.clone(), tema::yazi(tema::GOVDE_PX), tema::YAZI).size().x)
            .fold(ui.painter().layout_no_wrap("Tuş".into(), tema::yazi(tema::GOVDE_PX), tema::YAZI).size().x, f32::max)
            + 12.0
            + 8.0;
        let ic = tr.shrink(1.0);
        // başlık
        let bas = Rect::from_min_size(ic.min, Vec2::new(ic.width(), 30.0));
        ui.painter().rect_filled(bas, egui::CornerRadius { nw: 5, ne: 5, sw: 0, se: 0 }, tema::ZEMIN);
        let ayir = ic.right() - 8.0 - tus_gen;
        ui.painter().text(Pos2::new((ic.left() + ayir) / 2.0, bas.center().y), Align2::CENTER_CENTER, "İşlem", tema::yazi(tema::GOVDE_PX), tema::YAZI2);
        ui.painter().text(Pos2::new(ayir + tus_gen / 2.0, bas.center().y), Align2::CENTER_CENTER, "Tuş", tema::yazi(tema::GOVDE_PX), tema::YAZI2);
        let govde = Rect::from_min_max(Pos2::new(ic.left(), bas.bottom()), ic.max);
        let mut gu = ui.new_child(egui::UiBuilder::new().max_rect(govde));
        let basarisiz = self.basarisiz.clone();
        egui::ScrollArea::vertical().auto_shrink(false).show(&mut gu, |ui| {
            ui.spacing_mut().item_spacing.y = 0.0;
            let w = ui.available_width();
            let sutun = ayir - govde.left();
            let duzenlenen = self.duzenlenen;
            for (i, s) in self.tablo.iter_mut().enumerate() {
                let (r, _) = ui.allocate_exact_size(Vec2::new(w, 30.0), Sense::hover());
                let p = ui.painter();
                p.line_segment([Pos2::new(r.left(), r.bottom() - 0.5), Pos2::new(r.right(), r.bottom() - 0.5)], Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)));
                p.line_segment([Pos2::new(r.left() + sutun - 0.5, r.top()), Pos2::new(r.left() + sutun - 0.5, r.bottom())], Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)));
                let uyari = s.grup == "hotkeys" && !s.tus.is_empty() && basarisiz.contains(&s.komut);
                let ad = komut_adi(s.grup, &s.komut);
                let ad = if uyari { format!("⚠ {ad}") } else { ad };
                p.text(Pos2::new(r.left() + 4.0, r.center().y), Align2::LEFT_CENTER, ad, tema::yazi(tema::GOVDE_PX), tema::YAZI);
                let hucre = Rect::from_min_max(Pos2::new(r.left() + sutun, r.top()), Pos2::new(r.right(), r.bottom() - 1.0));
                if duzenlenen.map(|d| d.0) == Some(i) {
                    let mut hu = ui.new_child(egui::UiBuilder::new().max_rect(hucre));
                    let te = hu.add(
                        egui::TextEdit::singleline(&mut s.tus)
                            .hint_text("Tuş yaz ya da fare yan tuşuna bas")
                            .font(tema::yazi(tema::GOVDE_PX))
                            .desired_width(hucre.width() - 8.0)
                            .min_size(hucre.size())
                            .align(Align2::LEFT_CENTER),
                    );
                    if duzenlenen.map(|d| d.1) == Some(true) {
                        te.request_focus();
                    }
                    // orta / yan fare tuşu: o tuş yazılır (Ctrl/Alt/Shift ile)
                    let fare = hu.input(|x| {
                        let ad = if x.pointer.button_pressed(egui::PointerButton::Middle) {
                            Some("Fare3")
                        } else if x.pointer.button_pressed(egui::PointerButton::Extra1) {
                            Some("Fare4")
                        } else if x.pointer.button_pressed(egui::PointerButton::Extra2) {
                            Some("Fare5")
                        } else {
                            None
                        };
                        ad.map(|a| {
                            let mut on: Vec<&str> = Vec::new();
                            if x.modifiers.ctrl {
                                on.push("Ctrl");
                            }
                            if x.modifiers.alt {
                                on.push("Alt");
                            }
                            if x.modifiers.shift {
                                on.push("Shift");
                            }
                            on.push(a);
                            on.join("+")
                        })
                    });
                    let fare_basildi = fare.is_some();
                    if let Some(f) = fare {
                        s.tus = f;
                    }
                    self.duzenlenen = Some((i, false));
                    if te.lost_focus() && !fare_basildi {
                        self.duzenlenen = None;
                    }
                } else {
                    let resp = ui.interact(hucre, ui.scope_id().with(("tus", i)), Sense::click());
                    if resp.hovered() {
                        ui.painter().rect_filled(hucre, 0.0, beyaz(tema::A_UZERINE));
                    }
                    ui.painter().text(Pos2::new(hucre.left() + 4.0, hucre.center().y), Align2::LEFT_CENTER, &s.tus, tema::yazi(tema::GOVDE_PX), tema::YAZI);
                    let resp = if uyari { resp.on_hover_text("Bu tuş alınamadı: başka bir program kullanıyor") } else { resp };
                    if resp.double_clicked() {
                        self.duzenlenen = Some((i, true));
                    }
                }
            }
        });
        ui.add_space(6.0);
        ui.add(
            egui::Label::new(
                egui::RichText::new(
                    "Örnek: Ctrl+Shift+M, Ctrl+1, F8, Alt+M, Del. Fare tuşu da olur: hücreye çift tıkla, farenin orta ya da yan tuşuna bas (Fare3, Fare4, Fare5; Ctrl/Alt/Shift ile de). Fare tıkı açık uygulamaya da gider. Boş bırakırsan o kısayol kapanır. Kalem tuşları sadece kalem açıkken çalışır. ⚠ işaretli tuşları başka bir program kullanıyor; başka bir tuş seç.",
                )
                .font(tema::yazi(tema::KUCUK_PX))
                .color(tema::YAZI2),
            )
            .wrap(),
        );
        ui.add_space(6.0);
        if bilesen::hap(ui, "Varsayılanlara dön", false, true).clicked() {
            let mut genel: Vec<(String, String)> = VARSAYILAN_KISAYOLLAR.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
            genel.push(("bas_konus".into(), String::new()));
            self.tabloyu_doldur(genel, VARSAYILAN_KALEM_TUSLARI.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect());
            self.duzenlenen = None;
        }
    }

    /// Tablodaki kısayolları okur: (hotkeys, pen_hotkeys) ya da hatalar.
    fn kisayollari_oku(&self) -> Result<(serde_json::Map<String, Value>, serde_json::Map<String, Value>), Vec<String>> {
        let mut gruplar = (serde_json::Map::new(), serde_json::Map::new());
        let mut hatalar = Vec::new();
        let mut kullanilan: std::collections::HashMap<(&str, String), String> = Default::default();
        for s in &self.tablo {
            let mut tus = s.tus.trim().to_string();
            if !tus.is_empty() {
                if let Err(e) = rizeon::kisayol::tus_coz(&tus) {
                    hatalar.push(format!("{}: {}", komut_adi(s.grup, &s.komut), e.0));
                    continue;
                }
                tus = rizeon::kisayol::tus_metni(&tus);
                if let Some(onceki) = kullanilan.insert((s.grup, tus.clone()), s.komut.clone()) {
                    hatalar.push(format!("{tus} iki kez kullanılmış ({})", komut_adi(s.grup, &onceki)));
                }
            }
            let g = if s.grup == "hotkeys" { &mut gruplar.0 } else { &mut gruplar.1 };
            g.insert(s.komut.clone(), tus.into());
        }
        if hatalar.is_empty() {
            Ok(gruplar)
        } else {
            Err(hatalar)
        }
    }

    fn kaydet(&mut self, uyg: &Arc<Uygulama>) -> bool {
        let (genel, kalem) = match self.kisayollari_oku() {
            Ok(g) => g,
            Err(h) => {
                self.hata = format!("Kısayollarda sorun var:\n{}", h.join("\n"));
                return false;
            }
        };
        koy(&mut self.taslak, "hotkeys", Value::Object(genel));
        koy(&mut self.taslak, "pen_hotkeys", Value::Object(kalem));
        let t = &mut self.taslak;
        if al(t, "standby_text").as_str().unwrap_or("").trim().is_empty() {
            koy(t, "standby_text", "Birazdan döneceğim".into());
        }
        // elle yazılan video yolu da veri klasörüne kopyalansın
        let gorsel = al(t, "standby_image").as_str().unwrap_or("").trim().to_string();
        if gorsel != al(&self.eski, "standby_image").as_str().unwrap_or("") && rizeon::yollar::video_mu(&gorsel) {
            match rizeon::yollar::video_kopyala(std::path::Path::new(&gorsel)) {
                Ok(y) => koy(t, "standby_image", y.to_string_lossy().into_owned().into()),
                Err(e) => log::warn!("Bekleme videosu kopyalanamadı: {e}"),
            }
        }
        // köşe seçilince sürükleyerek verilen yer unutulur
        if al(t, "camera.corner") != al(&self.eski, "camera.corner") {
            koy(t, "camera.position", Value::Null);
        }
        let yeniden = al(t, "video.monitor").as_i64().unwrap_or(0) != al(&self.eski, "video.monitor").as_i64().unwrap_or(0)
            || al(t, "camera.device").as_i64().unwrap_or(0) != al(&self.eski, "camera.device").as_i64().unwrap_or(0);
        {
            let mut a = uyg.ayarlar.lock().unwrap();
            a.veri = std::mem::take(&mut self.taslak);
            a.kaydet();
        }
        uyg.ayarlari_uygula();
        if yeniden {
            self.bilgi = Some("Monitör ve kamera değişikliği uygulamayı yeniden açınca geçerli olur.".into());
        }
        true
    }

    fn sekme_cubugu(&mut self, ui: &mut Ui) {
        ui.horizontal(|ui| {
            ui.spacing_mut().item_spacing.x = 0.0;
            for (s, ad) in [(Sekme::Genel, "Genel"), (Sekme::Kamera, "Kamera"), (Sekme::Ses, "Ses"), (Sekme::Kisayollar, "Kısayollar")] {
                let g = ui.painter().layout_no_wrap(ad.to_string(), tema::yazi(tema::GOVDE_PX), tema::YAZI);
                let (r, resp) = ui.allocate_exact_size(Vec2::new(g.size().x + 28.0, 32.0), Sense::click());
                let secili = self.sekme == s;
                if secili {
                    ui.painter().rect_filled(r, 6.0, beyaz(tema::A_SECILI));
                } else if resp.hovered() {
                    ui.painter().rect_filled(r, 6.0, beyaz(tema::A_UZERINE));
                }
                let renk = if secili || resp.hovered() { tema::BEYAZ } else { tema::YAZI2 };
                ui.painter().galley(Pos2::new(r.left() + 14.0, r.center().y - g.size().y / 2.0), g, renk);
                if resp.clicked() {
                    self.sekme = s;
                    self.duzenlenen = None;
                }
            }
        });
    }

    /// Ayarlar kaydedildiyse true (arayüz kısayolları ve ipuçlarını yeniler). Hakkında istenirse
    /// `hakkinda` true olur.
    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>, hakkinda: &mut bool) -> bool {
        if !self.acik {
            self.gizlendi = false;
            return false;
        }
        let vp = egui::ViewportBuilder::default().with_title("Ayarlar").with_inner_size([640.0, 560.0]).with_min_inner_size([520.0, 420.0]);
        let mut kaydet = false;
        let mut kapat = false;
        crate::arayuz::pencereler::anlik(ctx, egui::ViewportId::from_hash_of("ayarlar"), vp, |ui, _| {
            // ayarlar karşı tarafa görünmesin, ana pencerenin arkasında kalmasın
            crate::arayuz::pencereler::diyalog_hazirla("Ayarlar", &mut self.gizlendi);
            if std::mem::take(&mut self.odakla) {
                ui.ctx().send_viewport_cmd(egui::ViewportCommand::Focus);
            }
            if ui.input(|i| i.viewport().close_requested()) || (self.duzenlenen.is_none() && ui.input(|i| i.key_pressed(egui::Key::Escape))) {
                kapat = true;
            }
            egui::CentralPanel::default().frame(egui::Frame::new().fill(tema::ZEMIN).inner_margin(11)).show(ui, |ui| {
                self.sekme_cubugu(ui);
                let hata_yuk = if self.hata.is_empty() { 0.0 } else { 16.0 * (self.hata.lines().count() as f32) + 6.0 };
                let alt = 28.0 + 12.0 + hata_yuk;
                let pr = Rect::from_min_max(Pos2::new(ui.max_rect().left(), ui.cursor().min.y - ui.spacing().item_spacing.y - 1.0), Pos2::new(ui.max_rect().right(), ui.max_rect().bottom() - alt));
                ui.painter().rect(pr, 8.0, tema::PANEL, Stroke::new(1.0, beyaz(tema::A_KENARLIK_INCE)), egui::StrokeKind::Inside);
                let mut pu = ui.new_child(egui::UiBuilder::new().max_rect(pr.shrink(10.0)));
                pu.spacing_mut().item_spacing.y = 6.0;
                match self.sekme {
                    Sekme::Kisayollar => self.kisayollar(&mut pu),
                    s => {
                        egui::ScrollArea::vertical().auto_shrink(false).show(&mut pu, |ui| {
                            ui.spacing_mut().item_spacing.y = 6.0;
                            match s {
                                Sekme::Genel => self.genel(ui, uyg),
                                Sekme::Kamera => self.kamera(ui),
                                _ => self.ses(ui, uyg),
                            }
                        });
                    }
                }
                ui.allocate_rect(pr, Sense::hover());
                if !self.hata.is_empty() {
                    ui.add_space(6.0);
                    bilesen::etiket(ui, &self.hata, tema::KUCUK_PX, tema::YAZI);
                }
                ui.with_layout(egui::Layout::bottom_up(egui::Align::Max), |ui| {
                    ui.horizontal(|ui| {
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.spacing_mut().item_spacing.x = 6.0;
                            if bilesen::hap(ui, "Hakkında", false, true).clicked() {
                                *hakkinda = true;
                            }
                            if bilesen::hap(ui, "Vazgeç", false, true).clicked() {
                                kapat = true;
                            }
                            if bilesen::hap(ui, "Kaydet", false, true).clicked() {
                                kaydet = true;
                            }
                        });
                    });
                });
            });
        });
        if kaydet && self.kaydet(uyg) {
            self.acik = false;
            return true;
        }
        if kapat {
            self.acik = false;
            self.taslak = Value::Null;
        }
        false
    }
}
