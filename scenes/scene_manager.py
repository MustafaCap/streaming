"""Sahneler, kaynaklar ve sahne geçişleri.

Bir sahne, sıralı bir kaynak listesidir. Listede üstteki kaynak öndedir (en son çizilir).
Kaynak türleri:
  ekran   : ana yakalama ("Göster" menüsünde seçilen monitör / pencere / bölge) ya da başka bir monitör
  pencere : tek bir uygulama penceresi
  bolge   : bir monitörün seçilen alanı
  kamera  : ana webcam (köşede ya da tam ekran) ya da ikinci bir kamera / telefon
  gorsel  : resim (logo vb.), en-boy oranı korunarak ortalanır
  video   : dosyadan döngüde oynatılan video
  metin   : alt bantta yazı (isim etiketi, başlık)
  bekleme : bekleme ekranı (yazı, resim ya da kısa video; Ayarlar'dan / sahne menüsünden)
  kalem   : kalem çizimleri çıkışa gitsin mi (ana ekranın üstünde)
  imlec   : imleç vurgusu (halka + tıklama dalgası)

Sahneler settings.json'daki "scenes" listesinde durur. 1.7.0'ın sabit sahneleri
({"screen": true, "camera": "corner"} gibi) okunurken kendiliğinden kaynaklara çevrilir.
Sahne değişince 0,3 sn'lik yumuşak geçiş yapılır.

Bu modül Qt'ye bağlı değildir; testlerde doğrudan kullanılır.
"""

import copy
import threading
import time
import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

from core import frames

VARSAYILAN_SAHNELER = [
    {"name": "Ekran + kamera", "screen": True, "camera": "corner"},
    {"name": "Sadece ekran", "screen": True},
    {"name": "Sadece kamera", "camera": "full"},
    {"name": "Bekleme ekranı", "standby": True},
]

KAYNAK_TURLERI = ("ekran", "pencere", "bolge", "kamera", "gorsel", "video", "metin", "bekleme", "kalem", "imlec")
# Kaynak ekleme menüsü: tür, ad, açıklama
EKLENEBILIR = [
    ("ekran", "Ekran", "Tüm monitör"),
    ("pencere", "Uygulama penceresi", "Tek bir pencere"),
    ("bolge", "Ekran bölgesi", "Seçtiğin alan"),
    ("kamera", "Kamera", "İkinci webcam veya telefon"),
    ("gorsel", "Görsel", "Logo, resim"),
    ("video", "Video", "Dosyadan döngüde oynat"),
    ("metin", "Metin", "Başlık, isim etiketi"),
]
TUR_ADLARI = {t: ad for t, ad, _ in EKLENEBILIR} | {"bekleme": "Bekleme ekranı", "kalem": "Kalem katmanı",
                                                    "imlec": "İmleç vurgusu"}
SAHNE_SINIRI = 30
KAYNAK_SINIRI = 20


def _yeni_kimlik() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Kaynak:
    tur: str
    ad: str = ""
    gorunur: bool = True
    ayar: dict = field(default_factory=dict)
    kimlik: str = field(default_factory=_yeni_kimlik)

    def __post_init__(self):
        if not self.ad:
            self.ad = TUR_ADLARI.get(self.tur, self.tur)

    @property
    def ana(self) -> bool:
        """Ana ekran ("Göster" menüsü) ya da ana webcam (Kamera düğmesi)."""
        return bool(self.ayar.get("ana"))

    def sozluk(self) -> dict:
        return {"id": self.kimlik, "type": self.tur, "name": self.ad, "visible": self.gorunur, **copy.deepcopy(self.ayar)}

    @classmethod
    def sozlukten(cls, d: dict) -> "Kaynak | None":
        tur = d.get("type")
        if tur not in KAYNAK_TURLERI:
            return None
        ayar = {k: copy.deepcopy(v) for k, v in d.items() if k not in ("id", "type", "name", "visible")}
        if tur == "kamera" and ayar.get("yer") not in ("kose", "tam"):
            ayar["yer"] = "kose"
        return cls(tur=tur, ad=str(d.get("name") or ""), gorunur=bool(d.get("visible", True)), ayar=ayar,
                   kimlik=str(d.get("id") or _yeni_kimlik()))

    def esit(self, diger: "Kaynak") -> bool:
        return (self.tur, self.ad, self.gorunur, self.ayar) == (diger.tur, diger.ad, diger.gorunur, diger.ayar)


def _bayraklardan(ekran: bool, kamera: str | None, bekleme: bool, imlec: bool = False) -> list[Kaynak]:
    """1.7.0 sahne biçiminden kaynak listesi (üstteki öndedir)."""
    liste: list[Kaynak] = []
    if bekleme:
        liste.append(Kaynak("bekleme"))
        return liste
    if kamera in ("corner", "full"):
        liste.append(Kaynak("kamera", "Webcam", ayar={"ana": True, "yer": "kose" if kamera == "corner" else "tam"}))
    if ekran:
        liste.append(Kaynak("ekran", "Ekran", ayar={"ana": True}))
        liste.append(Kaynak("kalem"))
        liste.append(Kaynak("imlec", gorunur=imlec))
    return liste


class Sahne:
    """Ad + kaynak listesi. Eski kodla uyum için Sahne("x", ekran=True, kamera="corner") da çalışır."""

    def __init__(self, ad: str, ekran: bool = False, kamera: str | None = None, bekleme: bool = False,
                 kaynaklar: list[Kaynak] | None = None):
        self.ad = ad
        self.kaynaklar: list[Kaynak] = kaynaklar if kaynaklar is not None else _bayraklardan(ekran, kamera, bekleme)

    # ---- eski sorular (video hattı ve önizlemedeki kamera sürükleme bunları sorar)

    def _ilk(self, tur: str, ana: bool | None = None, gorunur: bool = True) -> Kaynak | None:
        for k in self.kaynaklar:
            if k.tur == tur and (not gorunur or k.gorunur) and (ana is None or k.ana == ana):
                return k
        return None

    @property
    def ekran(self) -> bool:
        return self._ilk("ekran", ana=True) is not None

    @property
    def kamera(self) -> str | None:
        k = self._ilk("kamera", ana=True)
        if k is None:
            return None
        return "full" if k.ayar.get("yer") == "tam" else "corner"

    @property
    def kamera_var(self) -> bool:
        """Sahnede görünür bir kamera (ana webcam ya da ikinci kamera) var mı? Yoksa Kamera düğmesi kapanır."""
        return self._ilk("kamera") is not None

    @property
    def bekleme(self) -> bool:
        return self._ilk("bekleme") is not None

    @property
    def kalem(self) -> bool:
        """Kalem çizimleri çıkışa gitsin mi. Eski sahnelerde kalem satırı yoksa evet."""
        k = self._ilk("kalem", gorunur=False)
        return k is None or k.gorunur

    @property
    def imlec_vurgusu(self) -> bool:
        return self._ilk("imlec") is not None

    @property
    def kamera_var(self) -> bool:
        """Bu sahnede görünür herhangi bir kamera (ana ya da ek) var mı."""
        return any(k.tur == "kamera" and k.gorunur for k in self.kaynaklar)

    def kaynak(self, kimlik: str) -> Kaynak | None:
        return next((k for k in self.kaynaklar if k.kimlik == kimlik), None)

    # ---- kayıt

    def sozluk(self) -> dict:
        return {"name": self.ad, "sources": [k.sozluk() for k in self.kaynaklar],
                # eski sürüme dönülürse sahne yine açılsın diye özet bayraklar
                "screen": self.ekran, "camera": self.kamera, "standby": self.bekleme}

    @classmethod
    def sozlukten(cls, s: dict, imlec: bool = False) -> "Sahne":
        ad = str(s.get("name", "Sahne"))
        if isinstance(s.get("sources"), list):
            kaynaklar = [k for k in (Kaynak.sozlukten(d) for d in s["sources"] if isinstance(d, dict)) if k]
            return cls(ad, kaynaklar=kaynaklar[:KAYNAK_SINIRI])
        kamera = s.get("camera")
        if kamera not in ("corner", "full"):
            kamera = None
        return cls(ad, kaynaklar=_bayraklardan(bool(s.get("screen", False)), kamera,
                                               bool(s.get("standby", False)), imlec))

    def __eq__(self, diger) -> bool:
        if not isinstance(diger, Sahne):
            return NotImplemented
        return self.ad == diger.ad and len(self.kaynaklar) == len(diger.kaynaklar) and all(
            a.esit(b) for a, b in zip(self.kaynaklar, diger.kaynaklar))

    def __repr__(self) -> str:
        return f"Sahne({self.ad!r}, {[k.tur for k in self.kaynaklar]})"


def sahneleri_oku(liste, imlec: bool = False) -> list[Sahne]:
    """Ayarlardaki listeyi okur; boş/bozuksa varsayılan sahneleri döndürür.

    imlec: 1.7.0'dan gelen eski sahnelerde imleç vurgusu satırı görünür olsun mu (eski genel ayar).
    """
    try:
        sahneler = [Sahne.sozlukten(s, imlec) for s in liste if isinstance(s, dict)]
    except Exception:
        sahneler = []
    return sahneler[:SAHNE_SINIRI] or [Sahne.sozlukten(s, imlec) for s in VARSAYILAN_SAHNELER]


def yeni_sahne_adi(sahneler: list[Sahne]) -> str:
    adlar = {s.ad for s in sahneler}
    n = 1
    while f"Yeni sahne {n}" in adlar:
        n += 1
    return f"Yeni sahne {n}"


def yeni_kaynak_adi(sahne: Sahne, tur: str) -> str:
    temel = TUR_ADLARI.get(tur, tur)
    adlar = {k.ad for k in sahne.kaynaklar}
    if temel not in adlar:
        return temel
    n = 2
    while f"{temel} {n}" in adlar:
        n += 1
    return f"{temel} {n}"


@dataclass
class KameraYerlesimi:
    kose: str = "bottom-right"   # top-left | top-right | bottom-left | bottom-right
    boyut: float = 0.25          # çıkış genişliğine oranı
    bosluk: int = 24             # kenardan uzaklık (piksel)
    konum: tuple[float, float] | None = None   # önizlemede sürüklenince: kutunun merkezi (0..1)

    @classmethod
    def ayarlardan(cls, d: dict) -> "KameraYerlesimi":
        kose = d.get("corner", "bottom-right")
        if kose not in ("top-left", "top-right", "bottom-left", "bottom-right"):
            kose = "bottom-right"
        try:
            boyut = min(0.6, max(0.1, float(d.get("size", 0.25))))
        except (TypeError, ValueError):
            boyut = 0.25
        konum = d.get("position")
        try:
            konum = (min(1.0, max(0.0, float(konum[0]))), min(1.0, max(0.0, float(konum[1])))) if konum else None
        except (TypeError, ValueError, IndexError):
            konum = None
        try:
            bosluk = max(0, int(d.get("margin", 24)))
        except (TypeError, ValueError):
            bosluk = 24
        return cls(kose=kose, boyut=boyut, bosluk=bosluk, konum=konum)

    def dikdortgen(self, genislik: int, yukseklik: int, oran: float = 16 / 9) -> tuple[int, int, int, int]:
        """Kamera kutusunun (x, y, w, h) yeri; her zaman çıkışın içinde kalır."""
        w = max(16, round(genislik * self.boyut))
        h = max(9, round(w / oran))
        if self.konum is not None:
            x = round(self.konum[0] * genislik - w / 2)
            y = round(self.konum[1] * yukseklik - h / 2)
        else:
            x = self.bosluk if "left" in self.kose else genislik - w - self.bosluk
            y = self.bosluk if "top" in self.kose else yukseklik - h - self.bosluk
        x = min(max(0, x), max(0, genislik - w))
        y = min(max(0, y), max(0, yukseklik - h))
        return x, y, w, h


def ek_kamera_yerlesimi(k: Kaynak) -> KameraYerlesimi:
    """İkinci kamera: kendi konumu (sürüklenince kaydedilir), yoksa sol alt köşe."""
    return KameraYerlesimi.ayarlardan({"corner": k.ayar.get("corner", "bottom-left"), "size": k.ayar.get("size", 0.25),
                                       "position": k.ayar.get("position")})


def _kirp_doldur(kare: np.ndarray, w: int, h: int) -> np.ndarray:
    """Kareyi w x h alanı tam dolduracak şekilde ortadan kırpar ve ölçekler."""
    kh, kw = kare.shape[:2]
    olcek = max(w / kw, h / kh)
    kes_w, kes_h = min(kw, round(w / olcek)), min(kh, round(h / olcek))
    x0, y0 = (kw - kes_w) // 2, (kh - kes_h) // 2
    parca = kare[y0:y0 + kes_h, x0:x0 + kes_w]
    yontem = cv2.INTER_AREA if olcek < 1 else cv2.INTER_LINEAR
    return cv2.resize(parca, (w, h), interpolation=yontem)


_KENAR = (38, 38, 43)  # #26262b


def kamera_kutusu_ciz(tuval: np.ndarray, kamera, yer: KameraYerlesimi) -> None:
    """Tuvalin köşesine kamera görüntüsünü (yoksa 'Kamera yok' kutusunu) yerinde çizer."""
    H, W = tuval.shape[:2]
    x, y, w, h = yer.dikdortgen(W, H)
    if kamera is not None:
        tuval[y:y + h, x:x + w] = _kirp_doldur(kamera, w, h)
    else:
        tuval[y:y + h, x:x + w] = frames.bilgi_karesi(w, h, "Kamera yok", boy=max(12, h // 7))
    cv2.rectangle(tuval, (x - 1, y - 1), (x + w, y + h), _KENAR, 2)


def ustune_koy(tuval: np.ndarray, resim: np.ndarray) -> None:
    """Resmi (RGB ya da RGBA) en-boy oranını koruyarak tuvalin ortasına koyar; saydam yerler alttakini gösterir."""
    H, W = tuval.shape[:2]
    h, w = resim.shape[:2]
    if w == 0 or h == 0:
        return
    olcek = min(W / w, H / h)
    yw, yh = max(1, round(w * olcek)), max(1, round(h * olcek))
    kucuk = cv2.resize(resim, (yw, yh), interpolation=cv2.INTER_AREA if olcek < 1 else cv2.INTER_LINEAR)
    x, y = (W - yw) // 2, (H - yh) // 2
    alan = tuval[y:y + yh, x:x + yw]
    if kucuk.ndim == 3 and kucuk.shape[2] == 4:
        a = kucuk[:, :, 3:4].astype(np.float32) / 255.0
        alan[:] = (kucuk[:, :, :3].astype(np.float32) * a + alan.astype(np.float32) * (1 - a)).astype(np.uint8)
    else:
        alan[:] = kucuk[:, :, :3]


def metin_bandi(tuval: np.ndarray, metin: str) -> None:
    """Alt bantta yarı saydam koyu şerit üstünde yazı (isim etiketi)."""
    if not metin.strip():
        return
    H, W = tuval.shape[:2]
    boy = max(14, round(30 * W / 1280))
    bant_h = round(boy * 2.0)
    y0 = H - bant_h - round(H * 0.05)
    alan = tuval[y0:y0 + bant_h]
    alan[:] = (alan.astype(np.float32) * 0.35).astype(np.uint8) + np.array([13, 13, 15], np.uint8)
    yeni = frames.yazi_yaz(tuval, metin, (W // 2, y0 + bant_h // 2), boy, (228, 228, 231))
    if yeni is not tuval:
        tuval[:] = yeni


def sahne_karesi(sahne: Sahne, genislik: int, yukseklik: int, ekran, kamera,
                 kamera_acik: bool, yer: KameraYerlesimi, bekleme_metni: str, bekleme=None,
                 ek: dict | None = None) -> np.ndarray:
    """Sahneye göre yeni (yazılabilir) bir çıkış karesi kurar. Kaynaklar alttan üste çizilir.

    ekran: ana ekranın çıkış boyutuna sığdırılmış karesi ya da None (kaynak yok).
    kamera: ana kameranın son karesi ya da None (kamera yok/kapalı).
    kamera_acik: kullanıcı kamerayı açık mı tuttu (Kamera düğmesi). Kapalıyken hiçbir kamera görünmez.
    bekleme: bekleme ekranını veren fonksiyon (yazı ya da görsel); yoksa düz yazı.
    ek: {kaynak kimliği: kare ya da None} ana ekran / ana kamera dışındaki kaynakların son kareleri.
    """
    ek = ek or {}

    def bekleme_karesi():
        if bekleme is not None:
            return bekleme().copy()
        return frames.bilgi_karesi(genislik, yukseklik, bekleme_metni).copy()

    tuval = frames.siyah_kare(genislik, yukseklik)
    for k in reversed([k for k in sahne.kaynaklar if k.gorunur]):
        if k.tur == "bekleme":
            tuval = bekleme_karesi()
        elif k.tur == "ekran" and k.ana:
            tuval = ekran.copy() if ekran is not None else \
                frames.bilgi_karesi(genislik, yukseklik, "Ekran yakalanamıyor").copy()
        elif k.tur in ("ekran", "pencere", "bolge", "video"):
            kare = ek.get(k.kimlik)
            if kare is None:
                tuval = frames.bilgi_karesi(genislik, yukseklik, f"{k.ad}: görüntü yok").copy()
            else:
                tuval = frames.sigdir(kare, genislik, yukseklik)
                tuval = tuval.copy() if not tuval.flags.writeable or tuval is kare else tuval
        elif k.tur == "kamera" and k.ana:
            if k.ayar.get("yer") == "tam":
                if not kamera_acik:
                    tuval = bekleme_karesi()  # kamera kapalıyken siyah yerine bekleme ekranı
                elif kamera is None:
                    tuval = frames.bilgi_karesi(genislik, yukseklik, "Kamera bağlı değil").copy()
                else:
                    tuval = _kirp_doldur(kamera, genislik, yukseklik)
            elif kamera_acik:
                kamera_kutusu_ciz(tuval, kamera, yer)
        elif k.tur == "kamera":
            if kamera_acik:
                if k.ayar.get("yer") == "tam":
                    kare = ek.get(k.kimlik)
                    tuval = _kirp_doldur(kare, genislik, yukseklik) if kare is not None else \
                        frames.bilgi_karesi(genislik, yukseklik, f"{k.ad} bağlı değil").copy()
                else:
                    kamera_kutusu_ciz(tuval, ek.get(k.kimlik), ek_kamera_yerlesimi(k))
        elif k.tur == "gorsel":
            resim = ek.get(k.kimlik)
            if resim is not None:
                ustune_koy(tuval, resim)
        elif k.tur == "metin":
            metin_bandi(tuval, str(k.ayar.get("text", "")))
    return tuval


class SahneYoneticisi:
    """Sahne listesi, aktif sahne ve süren geçiş (iş parçacığı güvenli).

    Arayüz sahne ekler, siler, yeniden adlandırır, kaynak ekler/kaldırır; her değişiklikte
    degisti() çağrılır (ayarlara kaydetmek için). Video hattı her karede aktif sahneyi okur.
    """

    def __init__(self, sahneler: list[Sahne], gecis_ms: int = 300, saat=time.monotonic):
        if not sahneler:
            raise ValueError("En az bir sahne gerekli")
        self.sahneler = list(sahneler)
        self.gecis_sn = max(0, gecis_ms) / 1000.0
        self._saat = saat
        self._indeks = 0
        self._kilit = threading.RLock()
        self._gecis_baslangic: float | None = None
        self._gecis_istegi = False
        self._onceki_kare: np.ndarray | None = None
        self.degisti = None          # fn(): liste ya da bir sahnenin kaynakları değişti
        self.surum = 0               # her değişiklikte artar (arayüz yeniden çizsin diye)

    @property
    def indeks(self) -> int:
        return self._indeks

    @property
    def aktif(self) -> Sahne:
        with self._kilit:
            return self.sahneler[min(self._indeks, len(self.sahneler) - 1)]

    def sec(self, indeks: int) -> bool:
        """Sahneyi değiştirir (0 tabanlı). Geçersiz numarada False döner."""
        with self._kilit:
            if not 0 <= indeks < len(self.sahneler):
                return False
            if indeks == self._indeks:
                return True
            self._indeks = indeks
            self._gecis_istegi = self.gecis_sn > 0
        return True

    def _haber_ver(self) -> None:
        self.surum += 1
        if self.degisti is not None:
            self.degisti()

    # ---- sahne düzenleme

    def ekle(self, ad: str | None = None, kaynaklar: list[Kaynak] | None = None) -> int:
        """Yeni sahne ekler ve seçer: 'Yeni sahne 1, 2…'. Ekranı içerir (boş sahne siyah olurdu)."""
        with self._kilit:
            if len(self.sahneler) >= SAHNE_SINIRI:
                return -1
            sahne = Sahne(ad or yeni_sahne_adi(self.sahneler),
                          kaynaklar=kaynaklar if kaynaklar is not None else _bayraklardan(True, None, False))
            self.sahneler = self.sahneler + [sahne]
            indeks = len(self.sahneler) - 1
        self.sec(indeks)
        self._haber_ver()
        return indeks

    def sil(self, indeks: int) -> bool:
        with self._kilit:
            if len(self.sahneler) <= 1 or not 0 <= indeks < len(self.sahneler):
                return False
            yeni = self.sahneler[:indeks] + self.sahneler[indeks + 1:]
            if indeks < self._indeks or self._indeks >= len(yeni):
                self._indeks = max(0, self._indeks - 1)
                self._gecis_istegi = self.gecis_sn > 0
            elif indeks == self._indeks:
                self._gecis_istegi = self.gecis_sn > 0
            self.sahneler = yeni
        self._haber_ver()
        return True

    def yeniden_adlandir(self, indeks: int, ad: str) -> bool:
        ad = ad.strip()
        with self._kilit:
            if not ad or not 0 <= indeks < len(self.sahneler):
                return False
            self.sahneler[indeks].ad = ad[:60]
        self._haber_ver()
        return True

    # ---- kaynak düzenleme (aktif sahne ya da verilen sahne)

    def kaynak_ekle(self, kaynak: Kaynak, indeks: int | None = None) -> bool:
        with self._kilit:
            sahne = self.sahneler[self._indeks if indeks is None else indeks]
            if len(sahne.kaynaklar) >= KAYNAK_SINIRI:
                return False
            sahne.kaynaklar = [kaynak] + sahne.kaynaklar   # yeni kaynak en önde
        self._haber_ver()
        return True

    def kaynak_sil(self, kimlik: str) -> bool:
        with self._kilit:
            sahne = self.aktif
            yeni = [k for k in sahne.kaynaklar if k.kimlik != kimlik]
            if len(yeni) == len(sahne.kaynaklar):
                return False
            sahne.kaynaklar = yeni
        self._haber_ver()
        return True

    def kaynak_gorunurluk(self, kimlik: str, gorunur: bool | None = None) -> bool:
        with self._kilit:
            k = self.aktif.kaynak(kimlik)
            if k is None:
                return False
            k.gorunur = (not k.gorunur) if gorunur is None else gorunur
        self._haber_ver()
        return True

    def kaynak_tasi(self, kimlik: str, yon: int) -> bool:
        """yon -1: öne (listede yukarı), +1: arkaya."""
        with self._kilit:
            liste = list(self.aktif.kaynaklar)
            i = next((n for n, k in enumerate(liste) if k.kimlik == kimlik), None)
            j = None if i is None else i + yon
            if i is None or not 0 <= j < len(liste):
                return False
            liste[i], liste[j] = liste[j], liste[i]
            self.aktif.kaynaklar = liste
        self._haber_ver()
        return True

    def kaynak_ayarla(self, kimlik: str, **ayar) -> bool:
        with self._kilit:
            k = self.aktif.kaynak(kimlik)
            if k is None:
                return False
            k.ayar.update(ayar)
        self._haber_ver()
        return True

    def sozluk_listesi(self) -> list[dict]:
        with self._kilit:
            return [s.sozluk() for s in self.sahneler]

    # ---- geçiş

    def gecis_uygula(self, yeni: np.ndarray, son_cikis: np.ndarray | None) -> np.ndarray:
        """Video iş parçacığında her karede çağrılır: geçiş sürüyorsa iki kareyi karıştırır.

        son_cikis: bir önceki karede çıkışa giden kare (geçişin başlangıç fotoğrafı).
        """
        with self._kilit:
            if self._gecis_istegi:
                self._gecis_istegi = False
                if son_cikis is not None and son_cikis.shape == yeni.shape:
                    self._onceki_kare = son_cikis
                    self._gecis_baslangic = self._saat()
            if self._gecis_baslangic is None:
                return yeni
            t = (self._saat() - self._gecis_baslangic) / self.gecis_sn if self.gecis_sn > 0 else 1
            onceki = self._onceki_kare
            if t >= 1 or onceki is None:
                self._gecis_baslangic, self._onceki_kare = None, None
                return yeni
        t = t * t * (3 - 2 * t)  # yumuşak başla, yumuşak bitir
        return frames.karistir(onceki, yeni, t)

    @property
    def geciste(self) -> bool:
        return self._gecis_baslangic is not None or self._gecis_istegi
