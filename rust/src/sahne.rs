//! Sahneler, kaynaklar ve sahne geçişleri (Python scenes/scene_manager.py).
//!
//! Bir sahne sıralı bir kaynak listesidir; listede üstteki kaynak öndedir (en son çizilir).
//! Sahneler settings.json'daki "scenes" listesinde durur; 1.7.0'ın sabit sahneleri
//! ({"screen": true, "camera": "corner"}) okunurken kaynaklara çevrilir. Sahne değişince yumuşak geçiş.

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

use serde_json::{Map, Value};

use crate::kare::{self, Kare, KareRef};
use crate::yazi;

pub const SAHNE_SINIRI: usize = 30;
pub const KAYNAK_SINIRI: usize = 20;
const KENAR: [u8; 3] = [38, 38, 43];

pub fn tur_adi(tur: &str) -> &'static str {
    match tur {
        "ekran" => "Ekran",
        "pencere" => "Uygulama penceresi",
        "bolge" => "Ekran bölgesi",
        "kamera" => "Kamera",
        "gorsel" => "Görsel",
        "video" => "Video",
        "metin" => "Metin",
        "bekleme" => "Bekleme ekranı",
        "kalem" => "Kalem katmanı",
        "imlec" => "İmleç vurgusu",
        _ => "Kaynak",
    }
}

const TURLER: &[&str] = &["ekran", "pencere", "bolge", "kamera", "gorsel", "video", "metin", "bekleme", "kalem", "imlec"];

fn yeni_kimlik() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SAYAC: AtomicU64 = AtomicU64::new(0);
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0) as u64;
    format!("{:08x}", (t ^ SAYAC.fetch_add(0x9E37_79B9, Ordering::Relaxed).rotate_left(17)) as u32)
}

#[derive(Clone, Debug, PartialEq)]
pub struct Kaynak {
    pub tur: String,
    pub ad: String,
    pub gorunur: bool,
    /// Türüne özel ayarlar (ana, yer, text, path, ...) — settings.json'da düz alanlar olarak durur.
    pub ayar: Map<String, Value>,
    pub kimlik: String,
}

impl Kaynak {
    pub fn yeni(tur: &str, ad: &str, ayar: Map<String, Value>) -> Self {
        Kaynak {
            tur: tur.into(),
            ad: if ad.is_empty() { tur_adi(tur).into() } else { ad.into() },
            gorunur: true,
            ayar,
            kimlik: yeni_kimlik(),
        }
    }
    pub fn ana(&self) -> bool {
        self.ayar.get("ana").and_then(Value::as_bool).unwrap_or(false)
    }
    pub fn tam(&self) -> bool {
        self.ayar.get("yer").and_then(Value::as_str) == Some("tam")
    }
    pub fn metin(&self, a: &str) -> String {
        self.ayar.get(a).and_then(Value::as_str).unwrap_or("").to_string()
    }

    pub fn sozluk(&self) -> Value {
        let mut m = Map::new();
        m.insert("id".into(), self.kimlik.clone().into());
        m.insert("type".into(), self.tur.clone().into());
        m.insert("name".into(), self.ad.clone().into());
        m.insert("visible".into(), self.gorunur.into());
        for (k, v) in &self.ayar {
            m.insert(k.clone(), v.clone());
        }
        Value::Object(m)
    }

    pub fn sozlukten(d: &Map<String, Value>) -> Option<Kaynak> {
        let tur = d.get("type")?.as_str()?;
        if !TURLER.contains(&tur) {
            return None;
        }
        let mut ayar: Map<String, Value> =
            d.iter().filter(|(k, _)| !["id", "type", "name", "visible"].contains(&k.as_str())).map(|(k, v)| (k.clone(), v.clone())).collect();
        if tur == "kamera" && !matches!(ayar.get("yer").and_then(Value::as_str), Some("kose" | "tam")) {
            ayar.insert("yer".into(), "kose".into());
        }
        let ad = d.get("name").and_then(Value::as_str).unwrap_or("");
        Some(Kaynak {
            tur: tur.into(),
            ad: if ad.is_empty() { tur_adi(tur).into() } else { ad.into() },
            gorunur: d.get("visible").and_then(Value::as_bool).unwrap_or(true),
            ayar,
            kimlik: d.get("id").and_then(Value::as_str).map(String::from).unwrap_or_else(yeni_kimlik),
        })
    }
}

fn ayar(cifler: &[(&str, Value)]) -> Map<String, Value> {
    cifler.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
}

/// 1.7.0 sahne biçiminden kaynak listesi.
fn bayraklardan(ekran: bool, kamera: Option<&str>, bekleme: bool, imlec: bool) -> Vec<Kaynak> {
    let mut l = vec![];
    if bekleme {
        l.push(Kaynak::yeni("bekleme", "", Map::new()));
        return l;
    }
    if let Some(k @ ("corner" | "full")) = kamera {
        let yer = if k == "corner" { "kose" } else { "tam" };
        l.push(Kaynak::yeni("kamera", "Webcam", ayar(&[("ana", true.into()), ("yer", yer.into())])));
    }
    if ekran {
        l.push(Kaynak::yeni("ekran", "Ekran", ayar(&[("ana", true.into())])));
        l.push(Kaynak::yeni("kalem", "", Map::new()));
        let mut i = Kaynak::yeni("imlec", "", Map::new());
        i.gorunur = imlec;
        l.push(i);
    }
    l
}

#[derive(Clone, Debug, PartialEq)]
pub struct Sahne {
    pub ad: String,
    pub kaynaklar: Vec<Kaynak>,
}

impl Sahne {
    fn ilk(&self, tur: &str, ana: Option<bool>, gorunur: bool) -> Option<&Kaynak> {
        self.kaynaklar.iter().find(|k| k.tur == tur && (!gorunur || k.gorunur) && ana.is_none_or(|a| k.ana() == a))
    }
    pub fn ekran(&self) -> bool {
        self.ilk("ekran", Some(true), true).is_some()
    }
    /// Ana webcam: Some("full") | Some("corner") | None
    pub fn kamera(&self) -> Option<&'static str> {
        self.ilk("kamera", Some(true), true).map(|k| if k.tam() { "full" } else { "corner" })
    }
    pub fn kamera_var(&self) -> bool {
        self.kaynaklar.iter().any(|k| k.tur == "kamera" && k.gorunur)
    }
    pub fn bekleme(&self) -> bool {
        self.ilk("bekleme", None, true).is_some()
    }
    /// Kalem çizimleri çıkışa gitsin mi (eski sahnelerde kalem satırı yoksa evet).
    pub fn kalem(&self) -> bool {
        self.ilk("kalem", None, false).is_none_or(|k| k.gorunur)
    }
    pub fn imlec_vurgusu(&self) -> bool {
        self.ilk("imlec", None, true).is_some()
    }

    pub fn sozluk(&self) -> Value {
        serde_json::json!({
            "name": self.ad,
            "sources": self.kaynaklar.iter().map(Kaynak::sozluk).collect::<Vec<_>>(),
            "screen": self.ekran(), "camera": self.kamera(), "standby": self.bekleme(),
        })
    }

    pub fn sozlukten(s: &Map<String, Value>, imlec: bool) -> Sahne {
        let ad = s.get("name").and_then(Value::as_str).unwrap_or("Sahne").to_string();
        if let Some(l) = s.get("sources").and_then(Value::as_array) {
            let mut k: Vec<Kaynak> = l.iter().filter_map(Value::as_object).filter_map(Kaynak::sozlukten).collect();
            k.truncate(KAYNAK_SINIRI);
            return Sahne { ad, kaynaklar: k };
        }
        let kamera = s.get("camera").and_then(Value::as_str).filter(|k| matches!(*k, "corner" | "full"));
        let b = |a: &str| s.get(a).and_then(Value::as_bool).unwrap_or(false);
        Sahne { ad, kaynaklar: bayraklardan(b("screen"), kamera, b("standby"), imlec) }
    }
}

/// Ayarlardaki listeyi okur; boş/bozuksa varsayılan sahneler.
pub fn sahneleri_oku(liste: Option<&Value>, imlec: bool) -> Vec<Sahne> {
    let mut s: Vec<Sahne> = liste
        .and_then(Value::as_array)
        .map(|l| l.iter().filter_map(Value::as_object).map(|o| Sahne::sozlukten(o, imlec)).collect())
        .unwrap_or_default();
    s.truncate(SAHNE_SINIRI);
    if s.is_empty() {
        let v = crate::ayarlar::varsayilan();
        return sahneleri_oku(v.get("scenes"), imlec);
    }
    s
}

pub fn yeni_sahne_adi(sahneler: &[Sahne]) -> String {
    (1..).map(|n| format!("Yeni sahne {n}")).find(|a| !sahneler.iter().any(|s| &s.ad == a)).unwrap()
}

/// Kaynaklar panelindeki + menüsü: (tür, ad, açıklama).
pub const EKLENEBILIR: [(&str, &str, &str); 7] = [
    ("ekran", "Ekran", "Tüm monitör"),
    ("pencere", "Uygulama penceresi", "Tek bir pencere"),
    ("bolge", "Ekran bölgesi", "Seçtiğin alan"),
    ("kamera", "Kamera", "İkinci webcam veya telefon"),
    ("gorsel", "Görsel", "Logo, resim"),
    ("video", "Video", "Dosyadan döngüde oynat"),
    ("metin", "Metin", "Başlık, isim etiketi"),
];

/// Sahnede olmayan bir ad: "Metin", yoksa "Metin 2", "Metin 3"…
pub fn yeni_kaynak_adi(sahne: &Sahne, tur: &str) -> String {
    let temel = tur_adi(tur);
    let var = |a: &str| sahne.kaynaklar.iter().any(|k| k.ad == a);
    if !var(temel) {
        return temel.to_string();
    }
    (2..).map(|n| format!("{temel} {n}")).find(|a| !var(a)).unwrap()
}

#[derive(Clone, Debug, PartialEq)]
pub struct KameraYerlesimi {
    pub kose: String,
    pub boyut: f64,
    pub bosluk: i64,
    pub konum: Option<(f64, f64)>,
}

impl Default for KameraYerlesimi {
    fn default() -> Self {
        KameraYerlesimi { kose: "bottom-right".into(), boyut: 0.25, bosluk: 24, konum: None }
    }
}

impl KameraYerlesimi {
    pub fn ayarlardan(d: &Value) -> Self {
        let kose = d.get("corner").and_then(Value::as_str).unwrap_or("bottom-right");
        let kose = if ["top-left", "top-right", "bottom-left", "bottom-right"].contains(&kose) { kose } else { "bottom-right" };
        let boyut = d.get("size").and_then(Value::as_f64).unwrap_or(0.25).clamp(0.1, 0.6);
        let konum = d.get("position").and_then(Value::as_array).and_then(|a| {
            Some((a.first()?.as_f64()?.clamp(0.0, 1.0), a.get(1)?.as_f64()?.clamp(0.0, 1.0)))
        });
        let bosluk = d.get("margin").and_then(Value::as_i64).unwrap_or(24).max(0);
        KameraYerlesimi { kose: kose.into(), boyut, bosluk, konum }
    }

    /// Kamera kutusunun (x, y, w, h) yeri; her zaman çıkışın içinde kalır.
    pub fn dikdortgen(&self, gen: u32, yuk: u32) -> (i64, i64, u32, u32) {
        let (g, y) = (gen as f64, yuk as f64);
        let w = ((g * self.boyut).round() as i64).max(16);
        let h = ((w as f64 / (16.0 / 9.0)).round() as i64).max(9);
        let (mut x, mut yy) = match self.konum {
            Some((cx, cy)) => ((cx * g - w as f64 / 2.0).round() as i64, (cy * y - h as f64 / 2.0).round() as i64),
            None => (
                if self.kose.contains("left") { self.bosluk } else { gen as i64 - w - self.bosluk },
                if self.kose.contains("top") { self.bosluk } else { yuk as i64 - h - self.bosluk },
            ),
        };
        x = x.min((gen as i64 - w).max(0)).max(0);
        yy = yy.min((yuk as i64 - h).max(0)).max(0);
        (x, yy, w as u32, h as u32)
    }
}

pub fn kamera_kutusu_ciz(tuval: &mut Kare, kamera: Option<&Kare>, yer: &KameraYerlesimi) {
    let (x, y, w, h) = yer.dikdortgen(tuval.w, tuval.h);
    match kamera {
        Some(k) => kare::yapistir(tuval, &kare::kirp_doldur(k, w, h), x as i32, y as i32),
        None => kare::yapistir(tuval, &yazi::bilgi_karesi(w, h, "Kamera yok", Some((h / 7).max(12))), x as i32, y as i32),
    }
    kare::cerceve(tuval, x as f32 - 1.0, y as f32 - 1.0, w as f32 + 1.0, h as f32 + 1.0, 2.0, KENAR);
}

/// Resmi (alfa olabilir) en-boy oranını koruyarak tuvalin ortasına koyar.
pub fn ustune_koy(tuval: &mut Kare, resim: &Kare) {
    let olcek = (tuval.w as f64 / resim.w as f64).min(tuval.h as f64 / resim.h as f64);
    let yw = ((resim.w as f64 * olcek).round() as u32).max(1);
    let yh = ((resim.h as f64 * olcek).round() as u32).max(1);
    let kucuk = kare::olcekle(resim, yw, yh);
    kare::alfa_yapistir(tuval, &kucuk, ((tuval.w - yw) / 2) as i32, ((tuval.h - yh) / 2) as i32);
}

/// Alt bantta yarı saydam koyu şerit üstünde yazı (isim etiketi).
pub fn metin_bandi(tuval: &mut Kare, metin: &str) {
    if metin.trim().is_empty() {
        return;
    }
    let boy = (30.0 * tuval.w as f32 / 1280.0).round().max(14.0);
    let bant_h = (boy * 2.0).round() as u32;
    let y0 = tuval.h.saturating_sub(bant_h + (tuval.h as f32 * 0.05).round() as u32);
    kare::karart(tuval, 0, y0, tuval.w, bant_h, 0.35, [15, 13, 13]);
    yazi::yazi_yaz(tuval, metin, (tuval.w as i32 / 2, (y0 + bant_h / 2) as i32), boy, [228, 228, 231]);
}

/// Sahne karesini kurmak için gerekenler.
pub struct SahneGirdisi<'a> {
    pub ekran: Option<KareRef>,
    pub kamera: Option<KareRef>,
    pub kamera_acik: bool,
    pub yer: &'a KameraYerlesimi,
    pub bekleme: &'a dyn Fn() -> KareRef,
    /// kaynak kimliği -> son kare (görseller vb.)
    pub ek: &'a HashMap<String, KareRef>,
}

/// Sahneye göre çıkış karesini kurar; kaynaklar alttan üste çizilir. Üstüne çizim yoksa alttaki
/// paylaşılan kare (ör. değişmeyen ekran) aynen döner: sanal kamera ve kayıt onu yeniden çevirmez.
pub fn sahne_karesi(sahne: &Sahne, w: u32, h: u32, g: &SahneGirdisi) -> KareRef {
    enum Tuval {
        Yok,
        Paylasilan(KareRef),
        Ozel(Kare),
    }
    let mut t = Tuval::Yok;
    fn yazilabilir(t: &mut Tuval, w: u32, h: u32) -> &mut Kare {
        let yeni = match std::mem::replace(t, Tuval::Yok) {
            Tuval::Yok => Kare::siyah(w, h),
            Tuval::Paylasilan(k) => k.kopya(),
            Tuval::Ozel(k) => k,
        };
        *t = Tuval::Ozel(yeni);
        match t {
            Tuval::Ozel(k) => k,
            _ => unreachable!(),
        }
    }
    for k in sahne.kaynaklar.iter().rev().filter(|k| k.gorunur) {
        match k.tur.as_str() {
            "bekleme" => t = Tuval::Paylasilan((g.bekleme)()),
            "ekran" if k.ana() => {
                t = Tuval::Paylasilan(g.ekran.clone().unwrap_or_else(|| yazi::bilgi_karesi(w, h, "Ekran yakalanamıyor", None)))
            }
            "ekran" | "pencere" | "bolge" | "video" => {
                t = match g.ek.get(&k.kimlik) {
                    Some(kare) if kare.boyut() == (w, h) => Tuval::Paylasilan(kare.clone()),
                    Some(kare) => Tuval::Ozel(kare::sigdir(kare, w, h)),
                    None => Tuval::Paylasilan(yazi::bilgi_karesi(w, h, &format!("{}: görüntü yok", k.ad), None)),
                }
            }
            "kamera" if k.ana() => {
                if k.tam() {
                    t = if !g.kamera_acik {
                        Tuval::Paylasilan((g.bekleme)())
                    } else if let Some(kam) = &g.kamera {
                        Tuval::Ozel(kare::kirp_doldur(kam, w, h))
                    } else {
                        Tuval::Paylasilan(yazi::bilgi_karesi(w, h, "Kamera bağlı değil", None))
                    };
                } else if g.kamera_acik {
                    kamera_kutusu_ciz(yazilabilir(&mut t, w, h), g.kamera.as_deref(), g.yer);
                }
            }
            "kamera" => {
                if g.kamera_acik {
                    let kare = g.ek.get(&k.kimlik);
                    if k.tam() {
                        t = match kare {
                            Some(kam) => Tuval::Ozel(kare::kirp_doldur(kam, w, h)),
                            None => Tuval::Paylasilan(yazi::bilgi_karesi(w, h, &format!("{} bağlı değil", k.ad), None)),
                        };
                    } else {
                        let yer = KameraYerlesimi::ayarlardan(&serde_json::json!({
                            "corner": k.ayar.get("corner").cloned().unwrap_or("bottom-left".into()),
                            "size": k.ayar.get("size").cloned().unwrap_or(0.25.into()),
                            "position": k.ayar.get("position").cloned().unwrap_or(Value::Null),
                        }));
                        kamera_kutusu_ciz(yazilabilir(&mut t, w, h), kare.map(|k| &**k), &yer);
                    }
                }
            }
            "gorsel" => {
                if let Some(resim) = g.ek.get(&k.kimlik) {
                    ustune_koy(yazilabilir(&mut t, w, h), resim);
                }
            }
            "metin" => {
                let m = k.metin("text");
                if !m.trim().is_empty() {
                    metin_bandi(yazilabilir(&mut t, w, h), &m);
                }
            }
            _ => {}
        }
    }
    match t {
        Tuval::Yok => Kare::siyah(w, h).arc(),
        Tuval::Paylasilan(k) => k,
        Tuval::Ozel(k) => k.arc(),
    }
}

struct Gecis {
    istek: bool,
    baslangic: Option<Instant>,
    onceki: Option<KareRef>,
}

/// Sahne listesi, aktif sahne ve süren geçiş (iş parçacığı güvenli).
pub struct SahneYoneticisi {
    sahneler: Mutex<(Vec<Sahne>, usize)>,
    /// Geçiş süresi (ms); ayarlardan canlı değişir
    gecis_ms: std::sync::atomic::AtomicU32,
    gecis: Mutex<Gecis>,
    surum: std::sync::atomic::AtomicU64,
}

impl SahneYoneticisi {
    pub fn yeni(sahneler: Vec<Sahne>, gecis_ms: i64) -> Self {
        assert!(!sahneler.is_empty(), "En az bir sahne gerekli");
        SahneYoneticisi {
            sahneler: Mutex::new((sahneler, 0)),
            gecis_ms: std::sync::atomic::AtomicU32::new(gecis_ms.clamp(0, 10_000) as u32),
            gecis: Mutex::new(Gecis { istek: false, baslangic: None, onceki: None }),
            surum: Default::default(),
        }
    }

    pub fn gecis_sn(&self) -> f32 {
        self.gecis_ms.load(std::sync::atomic::Ordering::Relaxed) as f32 / 1000.0
    }

    pub fn gecis_ayarla(&self, ms: i64) {
        self.gecis_ms.store(ms.clamp(0, 10_000) as u32, std::sync::atomic::Ordering::Relaxed);
    }

    pub fn surum(&self) -> u64 {
        self.surum.load(std::sync::atomic::Ordering::Relaxed)
    }
    fn haber_ver(&self) {
        self.surum.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    }

    pub fn indeks(&self) -> usize {
        self.sahneler.lock().unwrap().1
    }
    pub fn aktif(&self) -> Sahne {
        let g = self.sahneler.lock().unwrap();
        g.0[g.1.min(g.0.len() - 1)].clone()
    }
    pub fn liste(&self) -> Vec<Sahne> {
        self.sahneler.lock().unwrap().0.clone()
    }

    /// Sahneyi değiştirir (0 tabanlı). Geçersiz numarada false.
    pub fn sec(&self, indeks: usize) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        if indeks >= g.0.len() {
            return false;
        }
        if indeks != g.1 {
            g.1 = indeks;
            self.gecis.lock().unwrap().istek = self.gecis_sn() > 0.0;
            self.haber_ver();
        }
        true
    }

    pub fn ekle(&self) -> Option<usize> {
        let indeks = {
            let mut g = self.sahneler.lock().unwrap();
            if g.0.len() >= SAHNE_SINIRI {
                return None;
            }
            let ad = yeni_sahne_adi(&g.0);
            g.0.push(Sahne { ad, kaynaklar: bayraklardan(true, None, false, false) });
            g.0.len() - 1
        };
        self.sec(indeks);
        self.haber_ver();
        Some(indeks)
    }

    pub fn sil(&self, indeks: usize) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        if g.0.len() <= 1 || indeks >= g.0.len() {
            return false;
        }
        g.0.remove(indeks);
        if indeks < g.1 || g.1 >= g.0.len() {
            g.1 = g.1.saturating_sub(1);
        }
        self.gecis.lock().unwrap().istek = self.gecis_sn() > 0.0;
        self.haber_ver();
        true
    }

    pub fn yeniden_adlandir(&self, indeks: usize, ad: &str) -> bool {
        let ad = ad.trim();
        let mut g = self.sahneler.lock().unwrap();
        if ad.is_empty() || indeks >= g.0.len() {
            return false;
        }
        g.0[indeks].ad = ad.chars().take(60).collect();
        self.haber_ver();
        true
    }

    /// Aktif sahnenin bir kaynağını değiştirir.
    pub fn kaynak_degistir(&self, kimlik: &str, f: impl FnOnce(&mut Kaynak)) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        let i = g.1;
        let Some(k) = g.0[i].kaynaklar.iter_mut().find(|k| k.kimlik == kimlik) else { return false };
        f(k);
        self.haber_ver();
        true
    }

    pub fn kaynak_ekle(&self, k: Kaynak) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        let i = g.1;
        if g.0[i].kaynaklar.len() >= KAYNAK_SINIRI {
            return false;
        }
        g.0[i].kaynaklar.insert(0, k);
        self.haber_ver();
        true
    }

    pub fn kaynak_sil(&self, kimlik: &str) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        let i = g.1;
        let once = g.0[i].kaynaklar.len();
        g.0[i].kaynaklar.retain(|k| k.kimlik != kimlik);
        let degisti = g.0[i].kaynaklar.len() != once;
        if degisti {
            self.haber_ver();
        }
        degisti
    }

    /// yon -1: öne, +1: arkaya
    pub fn kaynak_tasi(&self, kimlik: &str, yon: i32) -> bool {
        let mut g = self.sahneler.lock().unwrap();
        let s = g.1;
        let l = &mut g.0[s].kaynaklar;
        let Some(i) = l.iter().position(|k| k.kimlik == kimlik) else { return false };
        let j = i as i32 + yon;
        if j < 0 || j as usize >= l.len() {
            return false;
        }
        l.swap(i, j as usize);
        self.haber_ver();
        true
    }

    pub fn sozluk_listesi(&self) -> Value {
        Value::Array(self.sahneler.lock().unwrap().0.iter().map(Sahne::sozluk).collect())
    }

    /// Video iş parçacığında her karede: geçiş sürüyorsa iki kareyi karıştırır.
    pub fn gecis_uygula(&self, yeni: KareRef, son_cikis: Option<&KareRef>) -> KareRef {
        let (onceki, t) = {
            let mut g = self.gecis.lock().unwrap();
            if g.istek {
                g.istek = false;
                if let Some(s) = son_cikis.filter(|s| s.boyut() == yeni.boyut()) {
                    g.onceki = Some(s.clone());
                    g.baslangic = Some(Instant::now());
                }
            }
            let Some(bas) = g.baslangic else { return yeni };
            let t = if self.gecis_sn() > 0.0 { bas.elapsed().as_secs_f32() / self.gecis_sn() } else { 1.0 };
            if t >= 1.0 || g.onceki.is_none() {
                g.baslangic = None;
                g.onceki = None;
                return yeni;
            }
            (g.onceki.clone().unwrap(), t)
        };
        let t = t * t * (3.0 - 2.0 * t); // yumuşak başla, yumuşak bitir
        kare::karistir(&onceki, &yeni, t)
    }

    pub fn geciste(&self) -> bool {
        let g = self.gecis.lock().unwrap();
        g.baslangic.is_some() || g.istek
    }
}

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn eski_sahneler_kaynaklara_cevrilir() {
        let s = sahneleri_oku(None, false);
        assert_eq!(s.len(), 4);
        assert!(s[0].ekran());
        assert_eq!(s[0].kamera(), Some("corner"));
        assert_eq!(s[2].kamera(), Some("full"));
        assert!(s[3].bekleme());
        assert!(s[0].kalem());
        assert!(!s[0].imlec_vurgusu());
    }

    #[test]
    fn sozluk_gidis_donus() {
        let s = sahneleri_oku(None, true);
        let v = s[0].sozluk();
        let geri = Sahne::sozlukten(v.as_object().unwrap(), false);
        assert_eq!(geri, s[0]);
        assert!(geri.imlec_vurgusu());
    }

    #[test]
    fn kamera_kutusu_icerde_kalir() {
        let y = KameraYerlesimi { konum: Some((1.0, 1.0)), ..Default::default() };
        let (x, yy, w, h) = y.dikdortgen(1280, 720);
        assert_eq!((x + w as i64, yy + h as i64), (1280, 720));
        let y = KameraYerlesimi::default();
        assert_eq!(y.dikdortgen(1280, 720), (1280 - 320 - 24, 720 - 180 - 24, 320, 180));
    }

    #[test]
    fn sadece_ekran_paylasilan_kareyi_dondurur() {
        let s = sahneleri_oku(None, false);
        let ekran = Kare::dolu(64, 36, [1, 2, 3]).arc();
        let ek = HashMap::new();
        let yer = KameraYerlesimi::default();
        let bek = || yazi::bilgi_karesi(64, 36, "b", None);
        let g = SahneGirdisi { ekran: Some(ekran.clone()), kamera: None, kamera_acik: true, yer: &yer, bekleme: &bek, ek: &ek };
        let k = sahne_karesi(&s[1], 64, 36, &g);
        assert!(std::sync::Arc::ptr_eq(&k, &ekran));
        let k2 = sahne_karesi(&s[0], 64, 36, &g);
        assert!(!std::sync::Arc::ptr_eq(&k2, &ekran));
    }

    #[test]
    fn gecis_karistirir() {
        let y = SahneYoneticisi::yeni(sahneleri_oku(None, false), 300);
        let a = Kare::dolu(4, 4, [0, 0, 0]).arc();
        let b = Kare::dolu(4, 4, [200, 200, 200]).arc();
        assert!(y.sec(1));
        let k = y.gecis_uygula(b.clone(), Some(&a));
        assert!(k.piksel(0, 0)[0] < 200);
        assert!(!y.sec(9));
    }
}
