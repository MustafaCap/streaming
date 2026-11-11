//! Birleşik bölge + kalem katmanı (Python ui/drawing_overlay.py, ui/region_overlay.py,
//! ui/region_marker.py).
//!
//! Yakalanan monitörün üstüne saydam bir katman açılır. Ekran yakalamaya girmez; karşı taraf
//! çizimleri video hattının çıkış karesinde görür (tam ekran oyunda katman görünmese de).
//! Toplantı modunda ise yakalamaya girer: Zoom'da "Tüm ekran" paylaşımında kalem ve vurgu görünür.
//!
//!   bölge (Bölge düğmesi, Ctrl+Shift+S): ekran kararır, fareyle kutu çizilir. İnce beyaz çerçeve,
//!       4 yuvarlak tutamak; altında Yakınlaştır / Vurgula ve boyut (ör. 580 × 190). Kutu çizilince
//!       hemen yayına uygulanır. Enter ya da çift tık: tamam. Esc: vazgeç (önceki hâle döner).
//!       Bölge açıkken tekrar Ctrl+Shift+S: tam ekrana dön.
//!
//!   kalem (Kalem düğmesi, Ctrl+Shift+D): üst ortada sürüklenebilir kalem barı: Kalem, Fosforlu,
//!       Ok, Kare, Yazı, Lazer, Silgi · beyaz/kırmızı/sarı/mavi · ince/orta/kalın · temizle · Bitti.
//!       Yazı aracında: tıkla yaz (Enter kaydeder; boşken dışarı tık ya da Esc vazgeçer), var olan
//!       yazıyı tutup sürükleyerek yerini değiştir (Ctrl+Z eski yerine döndürür).
//!       Altta ipucu satırı. Bölge seçiliyse çerçevesi görünür, tutamaklarından düzenlenebilir.
//!       Kalem açıkken 1-7 araç, Ctrl+Z geri al, Del hepsini sil, Esc çık ("kalem" kısayol grubu
//!       sadece kalem açıkken alınır).
//!
//!   kaynak bölgesi (Kaynaklar > + > Ekran bölgesi): basit seçici; kutu çiz, Enter ya da çift tık
//!       onaylar, Esc vazgeçer.
//!
//! Yakınlaştırma açık ve katman kapalıyken bölgenin ekrandaki yeri ince bir çerçeveyle gösterilir
//! (yakınlaştırma izi; tıklamaları engellemez, yayına çıkmaz).

use std::sync::Arc;

use eframe::egui::{self, Align2, Color32, CursorIcon, Pos2, Rect, Stroke, Vec2};

use rizeon::bolge::{VURGULA, YAKINLASTIR};
use rizeon::cizim::{self, CizimDeposu};
use rizeon::uygulama::Uygulama;
use rizeon::yakalama::Monitor;

use super::bilesen::{self, ipucu, SimgeDugme};
use super::tema::{self, beyaz};

const BASLIK: &str = "RizeOn katman";
const IZ_BASLIK: &str = "RizeOn bölge izi";
const PAYLASIM_BASLIK: &str = "RizeOn paylaşım katmanı";
/// yuvarlak tutamak çapı
const TUTAMAK: f32 = 7.0;
/// fareyle yakalama alanı
const TUTAMAK_ALANI: f32 = 22.0;
/// rgba(9,9,11,.55)
const KARARTMA: Color32 = Color32::from_rgba_premultiplied(5, 5, 6, 140);
const HAFIF_KARARTMA: Color32 = Color32::from_rgba_premultiplied(2, 2, 3, 70);
const MODLAR: [&str; 2] = [YAKINLASTIR, VURGULA];
const TAM_EKRAN_UYARISI: &str = "Tam ekran oyunda katman görünmez · oyunu kenarlıksız pencere moduna al (çizimler yine yayına gider)";
/// yakınlaştırma izi çerçevesi, seçilen alanın biraz dışına çizilir; içerik kapanmasın
const IZ_PAY: f32 = 6.0;
const SIMGE: [&str; 7] = ["kalem", "fosforlu", "ok", "kare", "yazi", "lazer", "silgi"];
const KALINLIK_CAPI: [f32; 3] = [4.0, 8.0, 12.0];

fn renk32([r, g, b]: [u8; 3], a: u8) -> Color32 {
    Color32::from_rgba_unmultiplied(r, g, b, a)
}

fn tus(uyg: &Uygulama, komut: &str) -> String {
    let a = uyg.ayarlar.lock().unwrap();
    ["hotkeys", "pen_hotkeys"]
        .iter()
        .find_map(|g| a.veri.get(*g).and_then(|h| h.get(komut)).and_then(|v| v.as_str()).filter(|t| !t.is_empty()).map(rizeon::kisayol::tus_metni))
        .unwrap_or_default()
}

fn ozel_tam_ekran() -> bool {
    #[cfg(windows)]
    {
        rizeon::win::ozel_tam_ekran_mi()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

// ---------------------------------------------------------------- seçim düzenleyici

#[derive(Clone, Copy, PartialEq, Debug)]
enum Kose {
    SolUst,
    SagUst,
    SolAlt,
    SagAlt,
}

#[derive(Clone, Copy, Debug)]
enum Surukleme {
    Yeni(Pos2),
    Tasi(Pos2, Rect),
    Kose(Kose, Rect),
}

/// Katman üstündeki seçim kutusu (katman noktası cinsinden; `alan` katmanın kendisi).
#[derive(Default)]
struct Duzenleyici {
    secim: Option<Rect>,
    surukle: Option<Surukleme>,
}

impl Duzenleyici {
    fn oranlardan(alan: Rect, [x, y, w, h]: [f64; 4]) -> Self {
        let (aw, ah) = (alan.width() as f64, alan.height() as f64);
        let min = alan.min + Vec2::new((x * aw).round() as f32, (y * ah).round() as f32);
        Duzenleyici { secim: Some(Rect::from_min_size(min, Vec2::new((w * aw).round() as f32, (h * ah).round() as f32))), surukle: None }
    }

    fn oranlar(&self, alan: Rect) -> [f64; 4] {
        let r = self.secim.unwrap_or(Rect::NOTHING);
        let (aw, ah) = (alan.width().max(1.0) as f64, alan.height().max(1.0) as f64);
        [(r.min.x - alan.min.x) as f64 / aw, (r.min.y - alan.min.y) as f64 / ah, r.width() as f64 / aw, r.height() as f64 / ah]
    }

    fn var(&self) -> bool {
        self.secim.is_some_and(|r| r.width() >= 8.0 && r.height() >= 8.0)
    }

    fn kose_noktalari(&self) -> [(Kose, Pos2); 4] {
        let r = self.secim.unwrap_or(Rect::NOTHING);
        [(Kose::SolUst, r.left_top()), (Kose::SagUst, r.right_top()), (Kose::SolAlt, r.left_bottom()), (Kose::SagAlt, r.right_bottom())]
    }

    fn kose_altinda(&self, p: Pos2) -> Option<Kose> {
        if !self.var() {
            return None;
        }
        self.kose_noktalari().into_iter().find(|(_, k)| (k.x - p.x).abs() <= TUTAMAK_ALANI / 2.0 && (k.y - p.y).abs() <= TUTAMAK_ALANI / 2.0).map(|(a, _)| a)
    }

    fn imlec(&self, p: Pos2, icinden_tasi: bool) -> Option<CursorIcon> {
        match self.kose_altinda(p) {
            Some(Kose::SolUst | Kose::SagAlt) => Some(CursorIcon::ResizeNwSe),
            Some(_) => Some(CursorIcon::ResizeNeSw),
            None if icinden_tasi && self.var() && self.secim.is_some_and(|r| r.contains(p)) => Some(CursorIcon::Move),
            None => None,
        }
    }

    /// true: olay seçim düzenlemesine gitti.
    fn bas(&mut self, p: Pos2, yeni_kutu: bool, icinden_tasi: bool) -> bool {
        let r = self.secim.unwrap_or(Rect::NOTHING);
        if let Some(k) = self.kose_altinda(p) {
            self.surukle = Some(Surukleme::Kose(k, r));
            return true;
        }
        if icinden_tasi && self.var() && r.contains(p) {
            self.surukle = Some(Surukleme::Tasi(p, r));
            return true;
        }
        if yeni_kutu {
            self.secim = Some(Rect::from_min_max(p, p));
            self.surukle = Some(Surukleme::Yeni(p));
            return true;
        }
        false
    }

    fn surukleniyor(&self) -> bool {
        self.surukle.is_some()
    }

    fn tasi(&mut self, p: Pos2, alan: Rect) {
        match self.surukle {
            Some(Surukleme::Yeni(bas)) => self.secim = Some(Rect::from_two_pos(bas, p)),
            Some(Surukleme::Tasi(bas, ilk)) => {
                let mut r = ilk.translate(p - bas);
                let dx = (alan.min.x - r.min.x).max(0.0) + (alan.max.x - r.max.x).min(0.0);
                let dy = (alan.min.y - r.min.y).max(0.0) + (alan.max.y - r.max.y).min(0.0);
                r = r.translate(Vec2::new(dx, dy));
                self.secim = Some(r);
            }
            Some(Surukleme::Kose(k, ilk)) => {
                let (mut a, mut b) = (ilk.min, ilk.max);
                match k {
                    Kose::SolUst => a = p,
                    Kose::SagAlt => b = p,
                    Kose::SagUst => {
                        b.x = p.x;
                        a.y = p.y;
                    }
                    Kose::SolAlt => {
                        a.x = p.x;
                        b.y = p.y;
                    }
                }
                self.secim = Some(Rect::from_two_pos(a, b));
            }
            None => {}
        }
    }

    /// true: bir düzenleme bitti.
    fn birak(&mut self, alan: Rect) -> bool {
        if self.surukle.take().is_none() {
            return false;
        }
        self.secim = self.secim.map(|r| r.intersect(alan));
        true
    }

    fn ciz(&self, p: &egui::Painter, alan: Rect, karartma: Option<Color32>) {
        let var = self.var();
        let r = self.secim.unwrap_or(Rect::NOTHING);
        if let Some(c) = karartma {
            if var {
                for d in [
                    Rect::from_min_max(alan.min, Pos2::new(alan.max.x, r.min.y)),
                    Rect::from_min_max(Pos2::new(alan.min.x, r.max.y), alan.max),
                    Rect::from_min_max(Pos2::new(alan.min.x, r.min.y), Pos2::new(r.min.x, r.max.y)),
                    Rect::from_min_max(Pos2::new(r.max.x, r.min.y), Pos2::new(alan.max.x, r.max.y)),
                ] {
                    if d.is_positive() {
                        p.rect_filled(d, 0.0, c);
                    }
                }
            } else {
                p.rect_filled(alan, 0.0, c);
            }
        }
        if !var {
            return;
        }
        p.rect_stroke(r.shrink(0.5), 0.0, Stroke::new(1.0, Color32::from_white_alpha(230)), egui::StrokeKind::Middle);
        for (_, k) in self.kose_noktalari() {
            p.circle_filled(k, TUTAMAK / 2.0, Color32::WHITE);
        }
    }
}

// ---------------------------------------------------------------- katman

#[derive(Clone, Copy, PartialEq, Debug)]
enum Mod {
    Bolge,
    Kalem,
    /// "Ekran bölgesi" kaynağı için alan seçme
    Kaynak,
}

struct YaziKutusu {
    konum: Pos2,
    oran: (f32, f32),
    metin: String,
    /// açıldığı an: kutuyu açan tıkın bırakılması odağı almasın diye
    acilis: std::time::Instant,
}

pub struct Katman {
    mod_: Option<Mod>,
    /// kalem barı açık mı (kalem açık; bölge seçimi kalemin içinden de açılabilir)
    kalem: bool,
    monitor: Option<Monitor>,
    duz: Duzenleyici,
    /// katman boyutu bilinince bölgeden kurulacak seçim
    duz_bekleyen: Option<Option<[f64; 4]>>,
    alan: Rect,
    tur: usize,
    renk: usize,
    kalinlik: usize,
    yazi: Option<YaziKutusu>,
    /// sürüklenen yazı: (kimlik, eski yer, tutma farkı)
    tasinan: Option<(u64, (f32, f32), (f32, f32))>,
    ciziyor: bool,
    /// basılı tuş bu katmanda başladı mı (yazı kutusunu kapatan tık sayılmaz)
    basili: bool,
    fare: Option<Pos2>,
    /// bölge düzenlemesi başlarken (bölge, mod); Esc ile geri dönülür
    onceki_bolge: Option<(Option<[f64; 4]>, Option<&'static str>)>,
    bolgeden_kaleme: bool,
    cubuk_konumu: Option<Pos2>,
    /// Katmana en son uygulanan "yakalamadan gizli" değeri (None: henüz uygulanmadı)
    gizlendi: Option<bool>,
    iz_gizlendi: bool,
    /// Toplantı modunda, katman kapalıyken çizimleri ve vurguyu ekranda tutan pencere açık mı
    pub paylasim_acik: bool,
    /// katman açılınca klavye odağı istensin (Enter, Esc, V, Z)
    odakla: bool,
    /// kaynak için seçilen bölge: (monitör, oran x,y,w,h, piksel w,h)
    pub secilen_kaynak: Option<(usize, [f64; 4], [i64; 2])>,
    /// arayüzün göstereceği bildirimler
    pub bildirimler: Vec<String>,
}

impl Default for Katman {
    fn default() -> Self {
        Katman {
            mod_: None,
            kalem: false,
            monitor: None,
            duz: Duzenleyici::default(),
            duz_bekleyen: None,
            alan: Rect::NOTHING,
            tur: 0,
            renk: cizim::VARSAYILAN_RENK,
            kalinlik: 1,
            yazi: None,
            tasinan: None,
            ciziyor: false,
            basili: false,
            fare: None,
            onceki_bolge: None,
            bolgeden_kaleme: false,
            cubuk_konumu: None,
            gizlendi: None,
            iz_gizlendi: false,
            paylasim_acik: false,
            odakla: false,
            secilen_kaynak: None,
            bildirimler: Vec::new(),
        }
    }
}

impl Katman {
    /// Katman ekranda mı (bölge seçimi, kalem ya da kaynak bölgesi)
    pub fn etkin(&self) -> bool {
        self.mod_.is_some() || self.kalem
    }

    pub fn kalem_acik(&self) -> bool {
        self.kalem && self.mod_.is_some()
    }

    /// "kalem" kısayol grubu (1-7, renk, kalınlık, Ctrl+Z, Del, Esc) alınmalı mı: kalem açık ve
    /// yazı yazılmıyorken.
    #[cfg_attr(not(windows), allow(dead_code))]
    pub fn kalem_tuslari_istenen(&self) -> bool {
        self.kalem_acik() && self.yazi.is_none()
    }

    fn carpan(&self) -> f32 {
        cizim::KALINLIK_CARPANI[self.kalinlik]
    }

    fn son_bolge_modu(uyg: &Uygulama) -> &'static str {
        let m = uyg.ayarlar.lock().unwrap().metin("region.mode");
        if m == VURGULA {
            VURGULA
        } else {
            YAKINLASTIR
        }
    }

    fn monitoru_al(uyg: &Uygulama) -> Option<Monitor> {
        let n = uyg.k.ayar.lock().unwrap().monitor;
        let l = rizeon::yakalama::monitorler();
        let m = l.get(n).or(l.first()).cloned();
        // Linux'ta (sadece geliştirme / ekran görüntüsü denemesi) monitör listesi yok
        #[cfg(not(windows))]
        let m = m.or(Some(Monitor { ad: "test".into(), sol: 0, ust: 0, w: 1920, h: 1080 }));
        m
    }

    fn penceredeyiz(uyg: &Uygulama) -> bool {
        uyg.depo.al().kaynak_turu == "pencere"
    }

    fn katmani_ac(&mut self, uyg: &Uygulama, mod_: Mod) {
        if self.mod_.is_none() {
            self.monitor = Self::monitoru_al(uyg);
            self.gizlendi = None;
        }
        self.mod_ = Some(mod_);
        self.odakla = true;
    }

    // ---- kalem

    pub fn kalem_ac_kapat(&mut self, uyg: &Uygulama) -> String {
        if self.kalem_acik() {
            self.kapat(uyg);
            return "Kalem kapandı".into();
        }
        if Self::penceredeyiz(uyg) {
            return "Kalem tüm ekranda çalışır · Göster menüsünden bir ekran seç".into();
        }
        self.ac(uyg);
        if ozel_tam_ekran() {
            TAM_EKRAN_UYARISI.into()
        } else {
            "Kalem açıldı".into()
        }
    }

    fn ac(&mut self, uyg: &Uygulama) {
        if self.mod_ != Some(Mod::Bolge) {
            if self.mod_.is_none() {
                self.duz_bekleyen = Some(uyg.k.bolge.aktif().then(|| uyg.k.bolge.bolge()).flatten());
            }
            self.katmani_ac(uyg, Mod::Kalem);
        }
        self.kalem = true;
        uyg.depo.guncelle(|d| d.kalem_acik = true);
    }

    /// Kalemi (ve açıksa bölge seçimini) kapatır.
    pub fn kapat(&mut self, uyg: &Uygulama) {
        let kalem_acikti = self.kalem;
        if self.mod_ == Some(Mod::Bolge) {
            self.onceki_bolge = None; // bölge seçimi de kapanır, seçilen bölge kalır
        }
        self.mod_ = None;
        self.kalem = false;
        self.yazi = None;
        self.tasinan = None;
        self.ciziyor = false;
        self.bolgeden_kaleme = false;
        self.duz = Duzenleyici::default();
        if kalem_acikti && uyg.ayarlar.lock().unwrap().mantik("pen.clear_on_close", true) {
            uyg.k.cizim.temizle();
        }
        uyg.depo.guncelle(|d| d.kalem_acik = false);
    }

    /// Esc (kalem.kapat): bölge seçimindeyse vazgeçer, kalemdeyse kapatır.
    pub fn kapat_komutu(&mut self, uyg: &Uygulama) -> String {
        match self.mod_ {
            None => String::new(),
            Some(Mod::Bolge) => {
                self.bolge_vazgec(uyg);
                String::new()
            }
            Some(Mod::Kaynak) => {
                self.mod_ = None;
                String::new()
            }
            Some(Mod::Kalem) => {
                if let Some((k, eski, _)) = self.tasinan.take() {
                    // sürüklemeyi iptal et, yazı eski yerine dönsün
                    uyg.k.cizim.yazi_tasi(k, eski.0, eski.1);
                    return String::new();
                }
                self.kapat(uyg);
                "Kalem kapandı".into()
            }
        }
    }

    pub fn tur_sec(&mut self, n: usize) {
        if self.kalem_acik() && n < cizim::TURLER.len() {
            self.tur = n;
        }
    }

    pub fn renk_sec(&mut self, n: usize) {
        if n < cizim::RENKLER.len() {
            self.renk = n;
        }
    }

    pub fn kalinlik_sec(&mut self, n: usize) {
        if n < cizim::KALINLIK_CARPANI.len() {
            self.kalinlik = n;
        }
    }

    pub fn temizle(uyg: &Uygulama) -> String {
        if uyg.k.cizim.bos() {
            return String::new();
        }
        uyg.k.cizim.temizle();
        "Çizimler silindi".into()
    }

    // ---- bölge

    /// Bölge düğmesi / Ctrl+Shift+S.
    pub fn bolge_ac_kapat(&mut self, uyg: &Uygulama) -> String {
        if self.mod_ == Some(Mod::Bolge) {
            self.bolge_vazgec(uyg);
            return "Bölge seçimi iptal edildi".into();
        }
        if uyg.k.bolge.aktif() {
            self.bolge_temizle(uyg);
            return "Tam ekrana dönüldü".into();
        }
        if Self::penceredeyiz(uyg) {
            return "Bölge tüm ekranda çalışır · Göster menüsünden bir ekran seç".into();
        }
        self.onceki_bolge = None;
        self.bolgeden_kaleme = self.mod_.is_some();
        self.duz = Duzenleyici::default();
        self.duz_bekleyen = None;
        self.katmani_ac(uyg, Mod::Bolge);
        if ozel_tam_ekran() {
            TAM_EKRAN_UYARISI.into()
        } else {
            String::new()
        }
    }

    /// Kaynaklar > + > Ekran bölgesi: çizilen kutu sahneye kaynak olarak eklenir.
    pub fn kaynak_bolgesi_sec(&mut self, uyg: &Uygulama) {
        if self.mod_.is_some() {
            self.kapat(uyg);
        }
        self.duz = Duzenleyici::default();
        self.duz_bekleyen = None;
        self.katmani_ac(uyg, Mod::Kaynak);
    }

    /// Kutu çizildi ya da düzenlendi: hemen yayına uygulanır.
    fn bolge_uygula(&mut self, uyg: &Uygulama, oranlar: [f64; 4]) {
        if self.onceki_bolge.is_none() {
            self.onceki_bolge = Some((uyg.k.bolge.bolge(), uyg.k.bolge.mod_()));
        }
        let mod_ = uyg.k.bolge.mod_().unwrap_or_else(|| Self::son_bolge_modu(uyg));
        uyg.bolge_sec(oranlar, mod_);
    }

    fn bolge_modu(&mut self, uyg: &Uygulama, mod_: &'static str) {
        if self.mod_.is_none() || !self.duz.var() {
            return;
        }
        {
            let mut a = uyg.ayarlar.lock().unwrap();
            a.ayarla("region.mode", mod_.into());
            let _ = a.kaydet();
        }
        if self.onceki_bolge.is_none() {
            self.onceki_bolge = Some((uyg.k.bolge.bolge(), uyg.k.bolge.mod_()));
        }
        uyg.bolge_sec(self.duz.oranlar(self.alan), mod_);
    }

    fn bolge_tamam(&mut self, uyg: &Uygulama) {
        self.onceki_bolge = None;
        self.bolge_duzenlemesini_bitir(uyg);
        if let Some(m) = uyg.k.bolge.mod_() {
            let metin = if m == YAKINLASTIR { "Bölge yakınlaştırıldı" } else { "Bölge vurgulanıyor" };
            let t = tus(uyg, "bolge.sec");
            self.bildirimler.push(if t.is_empty() { metin.into() } else { format!("{metin} · tam ekran için {t}") });
        }
    }

    fn bolge_vazgec(&mut self, uyg: &Uygulama) {
        if let Some((bolge, mod_)) = self.onceki_bolge.take() {
            match (bolge, mod_) {
                (Some(b), Some(m)) => uyg.bolge_sec(b, m),
                _ => uyg.bolge_temizle(),
            }
        }
        self.bolge_duzenlemesini_bitir(uyg);
    }

    fn bolge_duzenlemesini_bitir(&mut self, uyg: &Uygulama) {
        if self.mod_.is_none() {
            return;
        }
        if self.bolgeden_kaleme || self.kalem {
            self.bolgeden_kaleme = false;
            self.duz = Duzenleyici::default();
            self.duz_bekleyen = Some(uyg.k.bolge.aktif().then(|| uyg.k.bolge.bolge()).flatten());
            self.mod_ = Some(Mod::Kalem);
        } else {
            self.mod_ = None;
            self.duz = Duzenleyici::default();
        }
    }

    fn bolge_temizle(&mut self, uyg: &Uygulama) {
        uyg.bolge_temizle();
        self.duz = Duzenleyici::default();
    }

    /// Pencere yakalamaya geçerken: kalem, bölge seçimi ve bölge kapanır.
    pub fn hepsini_kapat(&mut self, uyg: &Uygulama) {
        if self.mod_.is_some() {
            self.kapat(uyg);
        }
        if uyg.k.bolge.aktif() {
            self.bolge_temizle(uyg);
        }
    }

    fn ipucu_satiri(&self, uyg: &Uygulama) -> String {
        match self.mod_ {
            Some(Mod::Kaynak) => "Kutu çiz · Enter ya da çift tık tamam · Esc vazgeç".into(),
            Some(Mod::Bolge) => {
                let mut p = vec!["Kutu çiz".to_string(), "Enter tamam".into(), "Esc vazgeç".into()];
                let t = tus(uyg, "bolge.sec");
                if uyg.k.bolge.aktif() && !t.is_empty() {
                    p.push(format!("{t} tam ekran"));
                }
                p.join(" · ")
            }
            _ => {
                let mut p = vec![];
                for (k, ad) in [("kalem.ac_kapat", "kalem"), ("kalem.temizle", "temizle")] {
                    let t = tus(uyg, k);
                    if !t.is_empty() {
                        p.push(format!("{t} {ad}"));
                    }
                }
                p.push("Esc çık".into());
                p.join(" · ")
            }
        }
    }

    // ---------------------------------------------------------------- çizim

    pub fn goster(&mut self, ctx: &egui::Context, uyg: &Arc<Uygulama>) {
        self.iz_goster(ctx, uyg);
        self.paylasim_goster(ctx, uyg);
        let Some(mod_) = self.mod_ else { return };
        let Some(m) = self.monitor.clone() else {
            self.bildirimler.push("Monitör bulunamadı".into());
            self.mod_ = None;
            return;
        };
        let ppp = ctx.native_pixels_per_point().unwrap_or(ctx.pixels_per_point()).max(0.5);
        let vb = egui::ViewportBuilder::default()
            .with_title(BASLIK)
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_position([m.sol as f32 / ppp, m.ust as f32 / ppp])
            .with_inner_size([m.w as f32 / ppp, m.h as f32 / ppp]);
        let mut kapat = false;
        crate::arayuz::pencereler::anlik(ctx, egui::ViewportId::from_hash_of("katman"), vb, |ui, _| {
            let vctx = ui.ctx().clone();
            self.yakalamadan_gizle(uyg);
            if std::mem::take(&mut self.odakla) {
                vctx.send_viewport_cmd(egui::ViewportCommand::Focus);
            }
            // Katman monitörü tam kaplamalı: Windows sürüklemeyle (ya da Win+ok, ekran değişimi)
            // kaydırırsa yerine geri konur. Mustafa testte karartmayı aşağı kaydırabildi.
            let hedef = Rect::from_min_size(Pos2::new(m.sol as f32 / ppp, m.ust as f32 / ppp), Vec2::new(m.w as f32 / ppp, m.h as f32 / ppp));
            if let Some(dis) = vctx.input(|i| i.viewport().outer_rect) {
                if (dis.min - hedef.min).length() > 1.0 || (dis.size() - hedef.size()).length() > 1.0 {
                    vctx.send_viewport_cmd(egui::ViewportCommand::OuterPosition(hedef.min));
                    vctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(hedef.size()));
                }
            }
            egui::CentralPanel::default().frame(egui::Frame::NONE).show(ui, |ui| {
                let alan = ui.max_rect();
                self.alan = alan;
                if let Some(b) = self.duz_bekleyen.take() {
                    self.duz = b.map(|b| Duzenleyici::oranlardan(alan, b)).unwrap_or_default();
                }
                let cevap = ui.allocate_rect(alan, egui::Sense::click_and_drag());
                // Neredeyse saydam zemin: Windows'ta tamamen saydam piksel tıklamayı alttaki pencereye geçirir.
                ui.painter().rect_filled(alan, 0.0, Color32::from_black_alpha(1));
                match mod_ {
                    Mod::Kaynak => kapat |= self.kaynak_katmani(ui, &cevap, alan, &m, ppp),
                    _ => self.katman_ciz(ui, &vctx, &cevap, alan, uyg, ppp),
                }
            });
            if vctx.input(|i| i.viewport().close_requested()) {
                kapat = true;
            }
            let canli = self.mod_ == Some(Mod::Kalem) && (uyg.k.cizim.lazer_var() || matches!(cizim::TURLER[self.tur], "lazer" | "silgi"));
            if canli || self.duz.surukleniyor() || self.ciziyor {
                vctx.request_repaint_after(std::time::Duration::from_millis(33));
            }
        });
        if kapat {
            if self.mod_ == Some(Mod::Kaynak) {
                self.mod_ = None;
            } else {
                self.kapat(uyg);
            }
        }
    }

    /// Katman normalde ekran yakalamaya girmez (çizimler zaten çıkış karesinde). Toplantı modunda
    /// girer: Zoom'da "Tüm ekran" paylaşılınca kalem ve vurgu karşı tarafa da görünür.
    #[cfg(windows)]
    fn yakalamadan_gizle(&mut self, uyg: &Uygulama) {
        let gizle = !uyg.toplanti_acik();
        if self.gizlendi != Some(gizle) {
            if let Some(h) = rizeon::win::pencere_bul(BASLIK) {
                rizeon::win::yakalamadan_gizle(h, gizle);
                self.gizlendi = Some(gizle);
            }
        }
    }

    #[cfg(not(windows))]
    fn yakalamadan_gizle(&mut self, _uyg: &Uygulama) {}

    /// Alttaki ipucu satırı (12 px, açık gri).
    fn alt_ipucu(p: &egui::Painter, alan: Rect, alt_bosluk: f32, metin: &str) {
        p.text(Pos2::new(alan.center().x, alan.bottom() - alt_bosluk - 9.0), Align2::CENTER_CENTER, metin, tema::yazi(tema::KUCUK_PX), tema::DUGME);
    }

    /// Basit bölge seçici (kaynak eklerken). true: katman kapansın.
    fn kaynak_katmani(&mut self, ui: &mut egui::Ui, cevap: &egui::Response, alan: Rect, m: &Monitor, ppp: f32) -> bool {
        let (basildi, sag, birakti, cift, konum) = ui.input(|i| {
            (i.pointer.primary_pressed(), i.pointer.secondary_pressed(), i.pointer.primary_released(), i.pointer.button_double_clicked(egui::PointerButton::Primary), i.pointer.interact_pos())
        });
        let mut onayla = false;
        if sag && cevap.hovered() {
            return true;
        }
        if let Some(p) = konum {
            if basildi && cevap.hovered() {
                self.duz.bas(p, true, true);
            } else if self.duz.surukleniyor() {
                self.duz.tasi(p, alan);
            }
            if !self.duz.surukleniyor() {
                ui.ctx().set_cursor_icon(self.duz.imlec(p, true).unwrap_or(CursorIcon::Crosshair));
            }
            if cift && self.duz.var() && self.duz.secim.is_some_and(|r| r.contains(p)) {
                onayla = true;
            }
        }
        if birakti {
            self.duz.birak(alan);
        }
        // Python BolgeKatmani: Enter ve V onaylar (kaynakta mod kullanılmaz), Esc vazgeçer
        let (enter, esc) = ui.input(|i| (i.key_pressed(egui::Key::Enter) || i.key_pressed(egui::Key::V), i.key_pressed(egui::Key::Escape)));
        if esc {
            return true;
        }
        onayla |= enter;
        let p = ui.painter();
        self.duz.ciz(p, alan, Some(KARARTMA));
        if self.duz.var() {
            let r = self.duz.secim.unwrap();
            let (w, h) = ((r.width() * ppp).round(), (r.height() * ppp).round());
            let y = if r.bottom() + 30.0 < alan.bottom() { r.bottom() + 10.0 } else { r.top() - 24.0 };
            p.text(Pos2::new(r.left(), y + 9.0), Align2::LEFT_CENTER, format!("{w:.0} × {h:.0}"), tema::yazi(tema::KUCUK_PX), tema::DUGME);
        }
        Self::alt_ipucu(p, alan, 24.0, "Kutu çiz · Enter ya da çift tık tamam · Esc vazgeç");
        if onayla && self.duz.var() {
            let oran = self.duz.oranlar(alan).map(|v| (v * 10000.0).round() / 10000.0);
            let n = rizeon::yakalama::monitorler().iter().position(|x| x.sol == m.sol && x.ust == m.ust).unwrap_or(0);
            let r = self.duz.secim.unwrap();
            self.secilen_kaynak = Some((n, oran, [(r.width() * ppp).round() as i64, (r.height() * ppp).round() as i64]));
            return true;
        }
        false
    }

    fn arac_imleci(&self) -> CursorIcon {
        if self.mod_ == Some(Mod::Bolge) {
            return CursorIcon::Crosshair;
        }
        match cizim::TURLER[self.tur] {
            "yazi" => CursorIcon::Text,
            "lazer" | "silgi" => CursorIcon::None,
            _ => CursorIcon::Crosshair,
        }
    }

    fn oran(alan: Rect, p: Pos2) -> (f32, f32) {
        ((p.x - alan.min.x) / alan.width().max(1.0), (p.y - alan.min.y) / alan.height().max(1.0))
    }

    /// Ekrandaki yazının kapladığı dikdörtgen (çizimdeki yazı tipiyle ölçülür).
    fn yazi_alani(p: &egui::Painter, alan: Rect, s: &cizim::Sekil) -> Rect {
        let kalin = (s.kalinlik() * alan.height()).max(1.0);
        let g = p.layout_no_wrap(s.metin.clone(), tema::yazi(kalin.round().max(8.0)), Color32::WHITE);
        let min = alan.min + Vec2::new(s.noktalar[0].0 * alan.width(), s.noktalar[0].1 * alan.height());
        Rect::from_min_size(min, Vec2::new(g.size().x, g.size().y.max(kalin * 1.3)))
    }

    /// Tıklanan yerdeki en öndeki yazı (yoksa None).
    fn yazi_bul(p: &egui::Painter, alan: Rect, depo: &CizimDeposu, konum: Pos2) -> Option<cizim::Sekil> {
        let (sekiller, _, _) = depo.anlik();
        sekiller.into_iter().rev().find(|s| s.tur == "yazi" && Self::yazi_alani(p, alan, s).expand2(Vec2::new(6.0, 4.0)).contains(konum))
    }

    fn yazi_bitir(&mut self, uyg: &Uygulama, kaydet: bool) {
        if let Some(y) = self.yazi.take() {
            if kaydet && !y.metin.trim().is_empty() {
                uyg.k.cizim.yazi_ekle(cizim::RENKLER[self.renk], y.oran.0, y.oran.1, &y.metin, self.carpan());
            }
        }
    }

    fn katman_ciz(&mut self, ui: &mut egui::Ui, vctx: &egui::Context, cevap: &egui::Response, alan: Rect, uyg: &Arc<Uygulama>, ppp: f32) {
        let depo: &CizimDeposu = &uyg.k.cizim;
        if let Some(m) = &self.monitor {
            depo.oran_ayarla(m.w as f32 / m.h.max(1) as f32);
        }
        let bolge_mod = self.mod_ == Some(Mod::Bolge);
        let bolge_aktif = uyg.k.bolge.aktif();
        let tur = cizim::TURLER[self.tur];
        let renk = cizim::RENKLER[self.renk];
        let (basildi, sag, birakti, cift, konum) = ui.input(|i| {
            (i.pointer.primary_pressed(), i.pointer.secondary_pressed(), i.pointer.primary_released(), i.pointer.button_double_clicked(egui::PointerButton::Primary), i.pointer.interact_pos())
        });
        let uzerinde = cevap.hovered() || self.basili;
        self.fare = konum.filter(|_| cevap.hovered());
        let mut imlec = None;

        // ---- fare
        if let Some(p) = konum {
            if bolge_mod {
                if sag && cevap.hovered() {
                    self.bolge_vazgec(uyg);
                    return;
                }
                if basildi && cevap.hovered() {
                    self.duz.bas(p, true, true);
                    self.basili = true;
                } else if self.duz.surukleniyor() {
                    self.duz.tasi(p, alan);
                } else if uzerinde {
                    imlec = Some(self.duz.imlec(p, true).unwrap_or(CursorIcon::Crosshair));
                }
                if cift && self.duz.var() && self.duz.secim.is_some_and(|r| r.contains(p)) {
                    self.bolge_tamam(uyg);
                    return;
                }
            } else if (basildi || sag) && cevap.hovered() {
                if self.yazi.is_some() {
                    // Açık yazı kutusunun dışına tıklandı: yazılan varsa kaydedilir, boşsa vazgeçilir.
                    // Bu tık yeni kutu açmaz.
                    self.yazi_bitir(uyg, true);
                } else if sag {
                    depo.geri_al();
                } else {
                    self.basili = true;
                    // kalemde: bölge varsa tutamaklarından düzenlenir, gerisi çizim
                    if bolge_aktif && self.duz.bas(p, false, false) {
                    } else if tur == "yazi" {
                        let (x, y) = Self::oran(alan, p);
                        if let Some(s) = Self::yazi_bul(ui.painter(), alan, depo, p) {
                            let eski = s.noktalar[0];
                            self.tasinan = Some((s.kimlik, eski, (x - eski.0, y - eski.1)));
                        } else {
                            self.yazi = Some(YaziKutusu { konum: p, oran: (x, y), metin: String::new(), acilis: std::time::Instant::now() });
                        }
                    } else {
                        let (x, y) = Self::oran(alan, p);
                        self.ciziyor = true;
                        depo.basla(tur, renk, x, y, self.carpan());
                    }
                }
            } else {
                let (x, y) = Self::oran(alan, p);
                if self.duz.surukleniyor() {
                    self.duz.tasi(p, alan);
                } else if let Some((k, _, (fx, fy))) = self.tasinan {
                    depo.yazi_tasi(k, x - fx, y - fy);
                    imlec = Some(CursorIcon::Grabbing);
                } else if self.ciziyor {
                    depo.surukle(x, y);
                } else if uzerinde {
                    let tutamak = if bolge_aktif { self.duz.imlec(p, false) } else { None };
                    imlec = tutamak.or_else(|| {
                        (tur == "yazi" && self.yazi.is_none()).then(|| if Self::yazi_bul(ui.painter(), alan, depo, p).is_some() { CursorIcon::Grab } else { CursorIcon::Text })
                    });
                    if tur == "lazer" && cevap.hovered() && ui.input(|i| i.pointer.delta() != Vec2::ZERO) {
                        depo.lazer_noktasi(x, y, renk);
                    }
                }
            }
        }
        if birakti {
            self.basili = false;
            if self.duz.birak(alan) {
                if self.duz.var() {
                    let o = self.duz.oranlar(alan);
                    self.bolge_uygula(uyg, o);
                }
            } else if let Some((k, eski, _)) = self.tasinan.take() {
                depo.tasima_bitti(k, eski);
            } else if self.ciziyor {
                self.ciziyor = false;
                depo.bitir();
            }
        }

        // ---- tuşlar (Windows'ta kalem tuşları genel kısayol olarak alınır; burada sadece bölge tuşları)
        if self.yazi.is_none() {
            let (esc, enter, v, z) = ui.input(|i| (i.key_pressed(egui::Key::Escape), i.key_pressed(egui::Key::Enter), i.key_pressed(egui::Key::V), i.key_pressed(egui::Key::Z) && !i.modifiers.command));
            if bolge_mod {
                if esc {
                    self.bolge_vazgec(uyg);
                    return;
                } else if enter {
                    self.bolge_tamam(uyg);
                    return;
                } else if v && self.duz.var() {
                    self.bolge_modu(uyg, VURGULA);
                } else if z && self.duz.var() {
                    self.bolge_modu(uyg, YAKINLASTIR);
                }
            } else {
                #[cfg(not(windows))]
                {
                    let (num, geri_al, sil) = ui.input(|i| {
                        let num = [egui::Key::Num1, egui::Key::Num2, egui::Key::Num3, egui::Key::Num4, egui::Key::Num5, egui::Key::Num6, egui::Key::Num7]
                            .iter()
                            .position(|k| i.key_pressed(*k));
                        (num, i.modifiers.command && i.key_pressed(egui::Key::Z), i.key_pressed(egui::Key::Delete))
                    });
                    if let Some(n) = num {
                        self.tur_sec(n);
                    }
                    if geri_al {
                        depo.geri_al();
                    }
                    if sil {
                        depo.temizle();
                    }
                    if esc {
                        let _ = self.kapat_komutu(uyg);
                        return;
                    }
                }
            }
        }
        if self.mod_.is_none() {
            return;
        }
        let bolge_mod = self.mod_ == Some(Mod::Bolge);
        vctx.set_cursor_icon(imlec.unwrap_or_else(|| self.arac_imleci()));

        // ---- çizim
        let p = ui.painter().clone();
        if bolge_mod {
            self.duz.ciz(&p, alan, Some(KARARTMA));
        } else if uyg.k.bolge.aktif() || self.duz.surukleniyor() {
            self.duz.ciz(&p, alan, Some(HAFIF_KARARTMA));
        }
        Self::cizimler(&p, alan, depo);
        if !bolge_mod && cizim::TURLER[self.tur] == "silgi" {
            if let Some(f) = self.fare {
                let r = cizim::SILGI_YARICAPI * alan.height();
                p.circle(f, r, Color32::from_white_alpha(30), Stroke::new(1.2, Color32::from_white_alpha(200)));
            }
        }
        Self::alt_ipucu(&p, alan, 24.0, &self.ipucu_satiri(uyg));

        // ---- yazı kutusu
        if !bolge_mod {
            self.yazi_kutusu(vctx, alan, uyg);
        }
        // ---- bölge bilgisi (Yakınlaştır / Vurgula + boyut)
        let bilgi_goster = self.duz.var() && !self.duz.surukleniyor() && (bolge_mod || uyg.k.bolge.aktif());
        if bilgi_goster {
            self.bolge_bilgisi(vctx, alan, uyg, ppp);
        }
        // ---- kalem barı
        if self.kalem {
            self.kalem_cubugu(vctx, alan, uyg);
        }
    }

    fn yazi_kutusu(&mut self, vctx: &egui::Context, alan: Rect, uyg: &Uygulama) {
        let Some(y) = self.yazi.as_mut() else { return };
        let boy = (cizim::kalinlik("yazi") * cizim::KALINLIK_CARPANI[self.kalinlik] * alan.height()).round().max(10.0);
        let renk = renk32(cizim::RENKLER[self.renk], 255);
        let gen = (alan.width() / 4.0).max(260.0);
        let mut bitti = None;
        egui::Area::new(egui::Id::unique("kalem-yazi")).fixed_pos(y.konum).order(egui::Order::Foreground).show(vctx, |ui| {
            let r = Rect::from_min_size(y.konum, Vec2::new(gen, boy + 10.0));
            ui.painter().rect_filled(r, 0.0, Color32::from_black_alpha(90));
            ui.painter().add(egui::Shape::dashed_line(
                &[r.left_top(), r.right_top(), r.right_bottom(), r.left_bottom(), r.left_top()],
                Stroke::new(1.0, beyaz(0.6)),
                4.0,
                3.0,
            ));
            let cevap = ui.add_sized(
                r.size(),
                egui::TextEdit::singleline(&mut y.metin)
                    .font(tema::yazi(boy))
                    .text_color(renk)
                    .frame(egui::Frame::NONE)
                    .margin(egui::Margin::symmetric(2, 0))
                    .hint_text(egui::RichText::new("Yaz, Enter").color(tema::SOLUK)),
            );
            let yeni = y.acilis.elapsed() < std::time::Duration::from_millis(400);
            if yeni && !cevap.has_focus() {
                cevap.request_focus();
            } else if cevap.lost_focus() {
                bitti = Some(!ui.input(|i| i.key_pressed(egui::Key::Escape)));
            }
        });
        if let Some(kaydet) = bitti {
            self.yazi_bitir(uyg, kaydet);
        }
    }

    fn bolge_bilgisi(&mut self, vctx: &egui::Context, alan: Rect, uyg: &Uygulama, ppp: f32) {
        let r = self.duz.secim.unwrap_or(Rect::NOTHING);
        let mod_ = uyg.k.bolge.mod_().unwrap_or_else(|| Self::son_bolge_modu(uyg));
        let secili = MODLAR.iter().position(|m| *m == mod_).map(|i| i as i32).unwrap_or(-1);
        let boyut = format!("{:.0} × {:.0}", (r.width() * ppp).round(), (r.height() * ppp).round());
        // genişliği ölç: iki seçenek + boşluk + boyut yazısı
        let olc = egui::Painter::new(vctx.clone(), egui::LayerId::background(), Rect::EVERYTHING);
        let f = tema::yazi(tema::KUCUK_PX);
        let sec_gen: f32 = ["Yakınlaştır", "Vurgula"].iter().map(|m| olc.layout_no_wrap(m.to_string(), f.clone(), Color32::WHITE).size().x + 24.0).sum::<f32>() + 2.0 + 6.0;
        let gen = sec_gen + 10.0 + olc.layout_no_wrap(boyut.clone(), f.clone(), Color32::WHITE).size().x;
        let yuk = 32.0;
        let mut y = r.bottom() + 10.0;
        if y + yuk > alan.bottom() - 60.0 {
            y = r.top() - yuk - 10.0;
        }
        let x = r.left().clamp(alan.left(), (alan.right() - gen).max(alan.left()));
        let mut yeni = None;
        egui::Area::new(egui::Id::unique("bolge-bilgisi")).fixed_pos(Pos2::new(x, y.max(alan.top()))).order(egui::Order::Foreground).show(vctx, |ui| {
            ui.horizontal(|ui| {
                ui.spacing_mut().item_spacing.x = 10.0;
                yeni = bilesen::secim_grubu(
                    ui,
                    &["Yakınlaştır", "Vurgula"],
                    &["Seçili bölgeyi büyütüp tüm çıkışı ona ayırır", "Bölge aynı kalır, geri kalanı kararır"],
                    secili,
                    true,
                    Some(tema::YUZEN),
                );
                ui.label(egui::RichText::new(&boyut).font(f.clone()).color(tema::DUGME));
            });
        });
        if let Some(n) = yeni {
            self.bolge_modu(uyg, MODLAR[n]);
        }
    }

    fn kalem_cubugu(&mut self, vctx: &egui::Context, alan: Rect, uyg: &Arc<Uygulama>) {
        let depo = &uyg.k.cizim;
        // genişlik: tutma 20 + 7 araç + 4 renk + 3 kalınlık + temizle + Bitti + 4 ayraç
        let olc = egui::Painter::new(vctx.clone(), egui::LayerId::background(), Rect::EVERYTHING);
        let bitti_gen = olc.layout_no_wrap("Bitti".into(), tema::yazi(tema::GOVDE_PX), Color32::WHITE).size().x + 28.0;
        let gen = 4.0 + 20.0 + 8.0 * 36.0 + 7.0 * 28.0 + 4.0 * 13.0 + bitti_gen + 4.0 + 2.0 * 21.0;
        let konum = self.cubuk_konumu.filter(|k| alan.contains(*k)).unwrap_or(Pos2::new(alan.center().x - gen / 2.0, alan.top() + 24.0));
        let mut tasima = Vec2::ZERO;
        let mut kapat = false;
        egui::Area::new(egui::Id::unique("kalem-bari")).fixed_pos(konum).order(egui::Order::Foreground).show(vctx, |ui| {
            egui::Frame::new()
                .fill(tema::YUZEN)
                .stroke(Stroke::new(1.0, beyaz(tema::A_KENARLIK)))
                .corner_radius(22)
                .inner_margin(egui::Margin::symmetric(4, 0))
                .show(ui, |ui| {
                    ui.set_height(44.0);
                    ui.horizontal_centered(|ui| {
                        ui.spacing_mut().item_spacing.x = 2.0;
                        let t = bilesen::tutma_yeri(ui, 4.0);
                        if t.dragged() {
                            tasima += t.drag_delta();
                        }
                        for (i, ad) in cizim::TUR_ADLARI.iter().enumerate() {
                            let komut = format!("kalem.tur:{}", i + 1);
                            let ip = match i {
                                5 => ipucu(&format!("{ad}: İz bırakmaz, birkaç saniyede kaybolur"), &tus(uyg, &komut)),
                                6 => ipucu(&format!("{ad}: Değdiği çizimi siler"), &tus(uyg, &komut)),
                                _ => ipucu(ad, &tus(uyg, &komut)),
                            };
                            if SimgeDugme::new(SIMGE[i]).secili(self.tur == i).goster(ui).on_hover_text(ip).clicked() {
                                self.tur = i;
                            }
                        }
                        cubuk_ayraci(ui);
                        for (i, r) in cizim::RENKLER.iter().enumerate() {
                            let (a, c) = ui.allocate_exact_size(Vec2::new(28.0, 36.0), egui::Sense::click());
                            let c = c.on_hover_cursor(CursorIcon::PointingHand);
                            bilesen::zemin(ui, a, 14.0, false, false, &c, true);
                            if self.renk == i {
                                // seçili: koyu boşluk + açık gri halka
                                ui.painter().circle_stroke(a.center(), 9.5, Stroke::new(1.5, tema::YAZI));
                            }
                            ui.painter().circle_filled(a.center(), 7.0, renk32(*r, 255));
                            if c.on_hover_text(cizim::RENK_ADLARI[i]).clicked() {
                                self.renk = i;
                            }
                        }
                        cubuk_ayraci(ui);
                        for (i, ad) in cizim::KALINLIK_ADLARI.iter().enumerate() {
                            let (a, c) = ui.allocate_exact_size(Vec2::new(28.0, 36.0), egui::Sense::click());
                            let c = c.on_hover_cursor(CursorIcon::PointingHand);
                            let secili = self.kalinlik == i;
                            bilesen::zemin(ui, a, 14.0, secili, false, &c, true);
                            ui.painter().circle_filled(a.center(), KALINLIK_CAPI[i] / 2.0, if secili { Color32::from_rgb(0xf4, 0xf4, 0xf5) } else { tema::SOLUK });
                            if c.on_hover_text(*ad).clicked() {
                                self.kalinlik = i;
                            }
                        }
                        cubuk_ayraci(ui);
                        if SimgeDugme::new("temizle").goster(ui).on_hover_text(ipucu("Tüm çizimleri temizle", &tus(uyg, "kalem.temizle"))).clicked() {
                            let m = Self::temizle(uyg);
                            if !m.is_empty() {
                                self.bildirimler.push(m);
                            }
                        }
                        cubuk_ayraci(ui);
                        if bitti_dugmesi(ui).on_hover_text(ipucu("Kalemi kapat", "Esc")).clicked() {
                            kapat = true;
                        }
                    });
                });
        });
        if tasima != Vec2::ZERO {
            self.cubuk_konumu = Some(konum + tasima);
        }
        let _ = depo;
        if kapat {
            self.kapat(uyg);
            self.bildirimler.push("Kalem kapandı".into());
        }
    }

    fn cizimler(p: &egui::Painter, alan: Rect, depo: &CizimDeposu) {
        let (w, h) = (alan.width(), alan.height());
        let (sekiller, lazer, lazer_rengi) = depo.anlik();
        let nokta = |(x, y): (f32, f32)| alan.min + Vec2::new(x * w, y * h);
        for s in &sekiller {
            let kalin = (s.kalinlik() * h).max(1.0);
            let alfa = if s.tur == "fosforlu" { (cizim::FOSFOR_SAYDAMLIK * 255.0) as u8 } else { 255 };
            let c = renk32(s.renk, alfa);
            let pts: Vec<Pos2> = s.noktalar.iter().map(|n| nokta(*n)).collect();
            match s.tur {
                "kalem" | "fosforlu" => {
                    if pts.len() == 1 {
                        if s.tur == "kalem" {
                            p.circle_filled(pts[0], kalin / 2.0, c);
                        } else {
                            p.rect_filled(Rect::from_center_size(pts[0], Vec2::splat(kalin)), 0.0, c);
                        }
                    } else {
                        p.add(egui::Shape::line(pts.clone(), Stroke::new(kalin, c)));
                        if s.tur == "kalem" {
                            // yuvarlak uçlar
                            p.circle_filled(pts[0], kalin / 2.0, c);
                            p.circle_filled(*pts.last().unwrap(), kalin / 2.0, c);
                        }
                    }
                }
                "ok" => {
                    let (a, b) = (pts[0], pts[1]);
                    p.line_segment([a, b], Stroke::new(kalin, c));
                    p.circle_filled(a, kalin / 2.0, c);
                    let d = b - a;
                    let uz = d.length().max(1.0);
                    let (ux, uy) = (d.x / uz, d.y / uz);
                    let boy = (uz * 0.4).min(kalin * 5.0);
                    let sol = Pos2::new(b.x - ux * boy - uy * boy * 0.5, b.y - uy * boy + ux * boy * 0.5);
                    let sag = Pos2::new(b.x - ux * boy + uy * boy * 0.5, b.y - uy * boy - ux * boy * 0.5);
                    p.add(egui::Shape::convex_polygon(vec![b, sol, sag], c, Stroke::new(kalin, c)));
                }
                "kare" => {
                    p.rect_stroke(Rect::from_two_pos(pts[0], pts[1]), 0.0, Stroke::new(kalin, c), egui::StrokeKind::Middle);
                }
                "yazi" => {
                    p.text(pts[0], Align2::LEFT_TOP, &s.metin, tema::yazi(kalin.round().max(8.0)), c);
                }
                _ => {}
            }
        }
        if !lazer.is_empty() {
            let kalin = (cizim::kalinlik("lazer") * h).max(2.0);
            for i in 1..lazer.len() {
                let canlilik = 1.0 - lazer[i].2 / cizim::LAZER_OMRU;
                if canlilik <= 0.0 {
                    continue;
                }
                let c = renk32(lazer_rengi, (canlilik.clamp(0.0, 1.0) * 255.0) as u8);
                p.line_segment([nokta((lazer[i - 1].0, lazer[i - 1].1)), nokta((lazer[i].0, lazer[i].1))], Stroke::new(kalin * canlilik, c));
            }
            let son = lazer[lazer.len() - 1];
            if son.2 / cizim::LAZER_OMRU < 0.3 {
                let m = nokta((son.0, son.1));
                p.circle_filled(m, kalin + 3.0, Color32::WHITE);
                p.circle_filled(m, kalin + 1.0, renk32(lazer_rengi, 255));
            }
        }
    }

    // ---------------------------------------------------------------- toplantı modu

    /// Toplantı modunda katman kapalıyken ("Bitti"den sonra) çizimler ve bölge vurgusu ekranda
    /// kalır: tıklamaları geçiren, saydam, ekran yakalamaya giren bir pencere. Böylece Zoom'da
    /// "Tüm ekran" paylaşılınca karşı taraf da görür.
    fn paylasim_goster(&mut self, ctx: &egui::Context, uyg: &Uygulama) {
        let depo: &CizimDeposu = &uyg.k.cizim;
        let vurgu = uyg.k.bolge.mod_() == Some(VURGULA) && uyg.k.bolge.bolge().is_some();
        let goster = uyg.toplanti_acik() && self.mod_.is_none() && !Self::penceredeyiz(uyg) && (!depo.bos() || depo.lazer_var() || vurgu);
        self.paylasim_acik = goster;
        if !goster {
            return;
        }
        let Some(m) = Self::monitoru_al(uyg) else { return };
        depo.oran_ayarla(m.w as f32 / m.h.max(1) as f32);
        let ppp = ctx.native_pixels_per_point().unwrap_or(ctx.pixels_per_point()).max(0.5);
        let vb = egui::ViewportBuilder::default()
            .with_title(PAYLASIM_BASLIK)
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_mouse_passthrough(true)
            .with_active(false)
            .with_position([m.sol as f32 / ppp, m.ust as f32 / ppp])
            .with_inner_size([m.w as f32 / ppp, m.h as f32 / ppp]);
        crate::arayuz::pencereler::anlik(ctx, egui::ViewportId::from_hash_of("paylasim-katmani"), vb, |ui, _| {
            let alan = ui.max_rect();
            let p = ui.painter().clone();
            if vurgu {
                if let Some([x, y, w, h]) = uyg.k.bolge.bolge() {
                    let duz = Duzenleyici::oranlardan(alan, [x, y, w, h]);
                    // kenar çizgisi ve tutamaklar olmadan, sadece dışarısı kararır
                    let r = duz.secim.unwrap_or(alan);
                    for d in [
                        Rect::from_min_max(alan.min, Pos2::new(alan.max.x, r.min.y)),
                        Rect::from_min_max(Pos2::new(alan.min.x, r.max.y), alan.max),
                        Rect::from_min_max(Pos2::new(alan.min.x, r.min.y), Pos2::new(r.min.x, r.max.y)),
                        Rect::from_min_max(Pos2::new(r.max.x, r.min.y), Pos2::new(alan.max.x, r.max.y)),
                    ] {
                        if d.is_positive() {
                            p.rect_filled(d, 0.0, KARARTMA);
                        }
                    }
                }
            }
            Self::cizimler(&p, alan, depo);
            if depo.lazer_var() {
                ui.ctx().request_repaint_after(std::time::Duration::from_millis(33));
            }
        });
    }

    // ---------------------------------------------------------------- yakınlaştırma izi

    /// Yakınlaştırma açık ve katman kapalıyken bölgenin ekrandaki yerini ince çerçeveyle gösterir.
    fn iz_goster(&mut self, ctx: &egui::Context, uyg: &Uygulama) {
        let goster = self.mod_.is_none() && uyg.k.bolge.mod_() == Some(YAKINLASTIR);
        let (Some([x, y, w, h]), true) = (uyg.k.bolge.bolge(), goster) else {
            self.iz_gizlendi = false;
            return;
        };
        let Some(m) = Self::monitoru_al(uyg) else { return };
        let ppp = ctx.native_pixels_per_point().unwrap_or(ctx.pixels_per_point()).max(0.5);
        let (mw, mh) = (m.w as f32 / ppp, m.h as f32 / ppp);
        let (ox, oy) = (m.sol as f32 / ppp, m.ust as f32 / ppp);
        let r = Rect::from_min_size(Pos2::new(ox + x as f32 * mw, oy + y as f32 * mh), Vec2::new(w as f32 * mw, h as f32 * mh));
        let dis = r.expand(IZ_PAY).intersect(Rect::from_min_size(Pos2::new(ox, oy), Vec2::new(mw, mh)).expand(IZ_PAY));
        let vb = egui::ViewportBuilder::default()
            .with_title(IZ_BASLIK)
            .with_decorations(false)
            .with_transparent(true)
            .with_resizable(false)
            .with_taskbar(false)
            .with_always_on_top()
            .with_mouse_passthrough(true)
            .with_active(false)
            .with_position(dis.min)
            .with_inner_size(dis.size());
        crate::arayuz::pencereler::anlik(ctx, egui::ViewportId::from_hash_of("bolge-izi"), vb, |ui, _| {
            #[cfg(windows)]
            if !self.iz_gizlendi {
                if let Some(h) = rizeon::win::pencere_bul(IZ_BASLIK) {
                    rizeon::win::yakalamadan_gizle(h, true);
                    self.iz_gizlendi = true;
                }
            }
            let ic = ui.max_rect();
            let cerceve = Rect::from_min_size(ic.min + (r.min - dis.min), r.size());
            let p = ui.painter();
            p.rect_stroke(cerceve.expand(0.5), 0.0, Stroke::new(1.0, Color32::from_white_alpha(150)), egui::StrokeKind::Middle);
            for k in [cerceve.left_top(), cerceve.right_top(), cerceve.left_bottom(), cerceve.right_bottom()] {
                p.circle_filled(k, 3.0, Color32::from_white_alpha(200));
            }
        });
    }
}

/// Kalem barındaki ince dikey ayraç (13×20, solda 1 px çizgi).
fn cubuk_ayraci(ui: &mut egui::Ui) {
    let (a, _) = ui.allocate_exact_size(Vec2::new(13.0, 20.0), egui::Sense::hover());
    let x = a.left() + 6.5;
    ui.painter().line_segment([Pos2::new(x, a.top()), Pos2::new(x, a.bottom())], Stroke::new(1.0, beyaz(tema::A_KENARLIK)));
}

/// Kalem barındaki "Bitti" (36 px yüksek, yuvarlak, 13 px yazı).
fn bitti_dugmesi(ui: &mut egui::Ui) -> egui::Response {
    let g = ui.painter().layout_no_wrap("Bitti".into(), tema::yazi(tema::GOVDE_PX), Color32::WHITE);
    let (r, c) = ui.allocate_exact_size(Vec2::new(g.size().x + 28.0, 36.0), egui::Sense::click());
    let c = c.on_hover_cursor(CursorIcon::PointingHand);
    bilesen::zemin(ui, r, 18.0, false, false, &c, true);
    let renk = if c.hovered() { tema::BEYAZ } else { tema::DUGME };
    ui.painter().galley(r.center() - g.size() / 2.0, g, renk);
    c
}

#[cfg(test)]
mod testler {
    use super::*;

    fn alan() -> Rect {
        Rect::from_min_size(Pos2::ZERO, Vec2::new(1000.0, 500.0))
    }

    #[test]
    fn yeni_kutu_tasi_boyutlandir() {
        let a = alan();
        let mut d = Duzenleyici::default();
        assert!(d.bas(Pos2::new(100.0, 100.0), true, true));
        d.tasi(Pos2::new(300.0, 200.0), a);
        assert!(d.birak(a));
        assert!(d.var());
        assert_eq!(d.oranlar(a), [0.1, 0.2, 0.2, 0.2]);
        // içinden taşı: alanın dışına çıkamaz
        assert!(d.bas(Pos2::new(150.0, 150.0), true, true));
        d.tasi(Pos2::new(-500.0, 150.0), a);
        d.birak(a);
        assert_eq!(d.secim.unwrap().min.x, 0.0);
        // sağ alt köşeden büyüt
        let k = d.secim.unwrap().right_bottom();
        assert!(d.bas(k, true, true));
        d.tasi(k + Vec2::new(50.0, 50.0), a);
        d.birak(a);
        assert_eq!(d.secim.unwrap().size(), Vec2::new(250.0, 150.0));
        // kalemde: kutu dışına basmak yeni kutu açmaz
        assert!(!d.bas(Pos2::new(900.0, 450.0), false, false));
    }

    #[test]
    fn oranlardan_geri_donus() {
        let a = alan();
        let d = Duzenleyici::oranlardan(a, [0.25, 0.5, 0.5, 0.25]);
        assert_eq!(d.oranlar(a), [0.25, 0.5, 0.5, 0.25]);
        assert_eq!(d.imlec(Pos2::new(250.0, 250.0), true), Some(CursorIcon::ResizeNwSe));
        assert_eq!(d.imlec(Pos2::new(500.0, 300.0), true), Some(CursorIcon::Move));
        assert_eq!(d.imlec(Pos2::new(500.0, 300.0), false), None);
    }
}
