"""settings.json okuma/yazma.

- Varsayılan ayarlar config/settings.default.json'dadır.
- Kullanıcının dosyası %APPDATA%\\RizeOn\\settings.json'dadır.
- Kullanıcı dosyasında eksik olan alanlar varsayılandan tamamlanır, böylece
  yeni bir sürümde eklenen ayarlar eski dosyaları bozmaz.
- Dosya bozuksa uygulama çökmez: yedeği alınır ve varsayılanlarla devam edilir.
- Elle yanlış türde değer yazılırsa (ör. genişliğe metin) o alan varsayılana döner.
- Dosya yazılamazsa (OneDrive/antivirüs kilitlediyse) uygulama çökmez, log'a yazılır.
"""

import copy
import json
import logging
from pathlib import Path

from core import paths

log = logging.getLogger(__name__)

SURUM = 3

# 2.0.0: F tuşları oyunlarla ve dizüstü Fn tuşlarıyla çakıştığı için kısayollar Ctrl+Shift'e taşındı.
# Sadece kullanıcının hiç değiştirmediği (eski varsayılanında duran) tuşlar taşınır.
KISAYOL_TASIMA_3 = {   # komut: (eski varsayılan, yeni varsayılan)
    "bolge.sec": ("F6", "Ctrl+Shift+S"),
    "kalem.ac_kapat": ("F7", "Ctrl+Shift+D"),
    "ses.mikrofon": ("F8", "Ctrl+Shift+M"),
    "ses.sistem": ("F9", "Ctrl+Shift+A"),
    "kamera.ac_kapat": ("F10", "Ctrl+Shift+C"),
    "anlik_kayit.kaydet": ("F11", "Ctrl+Shift+B"),
    "panik": ("Ctrl+Alt+P", "Ctrl+Shift+P"),
    "sahne.sec:1": ("Ctrl+1", "Ctrl+Shift+1"),
    "sahne.sec:2": ("Ctrl+2", "Ctrl+Shift+2"),
    "sahne.sec:3": ("Ctrl+3", "Ctrl+Shift+3"),
    "sahne.sec:4": ("Ctrl+4", "Ctrl+Shift+4"),
    "kayit.duraklat": ("Ctrl+Alt+D", "Ctrl+Shift+K"),
}
# 2.0.0'da eklenen kısayollar (eski dosyada yoksa eklenir; tuş başka işte kullanılıyorsa boş kalır)
YENI_KISAYOLLAR_3 = {
    **{f"sahne.sec:{n}": f"Ctrl+Shift+{n}" for n in range(5, 10)},
    "ekran.goruntusu": "Ctrl+Shift+G",
    "kalem.temizle": "Ctrl+Shift+X",
}
YENI_KALEM_TUSLARI_3 = {"kalem.tur:7": "7", "kalem.kapat": "Esc"}


def _tus_anahtari(tus) -> str:
    """Karşılaştırma için tuşun tek biçimi ("ctrl + shift+m" == "Ctrl+Shift+M")."""
    from core.hotkeys import GecersizTus, tus_metni
    metin = str(tus or "").strip()
    if not metin:
        return ""
    try:
        return tus_metni(metin).lower()
    except (GecersizTus, ValueError, KeyError):
        return metin.replace(" ", "").lower()


def kisayollari_tasi(tuslar: dict, eski_tuslar: dict, tasima: dict, yeniler: dict) -> list[str]:
    """tuslar: birleştirilmiş (varsayılanla tamamlanmış) sözlük, yerinde değişir.
    eski_tuslar: kullanıcının dosyasındaki ham sözlük. Döndürür: çakıştığı için boş bırakılan komutlar."""
    adaylar: dict[str, str] = {}
    for komut, (eski, yeni) in tasima.items():
        deger = eski_tuslar.get(komut)
        if deger is None or _tus_anahtari(deger) == _tus_anahtari(eski):
            adaylar[komut] = yeni
    for komut, yeni in yeniler.items():
        if komut not in eski_tuslar:
            adaylar[komut] = yeni
    kullanilan = {_tus_anahtari(t) for k, t in tuslar.items() if k not in adaylar and _tus_anahtari(t)}
    bos_kalan = []
    for komut, yeni in adaylar.items():
        anahtar = _tus_anahtari(yeni)
        if anahtar in kullanilan:
            tuslar[komut] = ""
            bos_kalan.append(komut)
            log.info("Kısayol %s taşınmadı: %s başka bir işte kullanılıyor", komut, yeni)
        else:
            tuslar[komut] = yeni
            kullanilan.add(anahtar)
    return bos_kalan


def _tasi(veri: dict, eski_surum: int, kullanici: dict | None = None) -> None:
    """Eski sürümün ayar dosyasını yeni sürüme uyarlar. kullanici: dosyadaki ham (birleştirilmemiş) veri."""
    kullanici = kullanici or {}
    if eski_surum < 2:
        # F12'yi Windows hata ayıklayıcıya ayırdığı için global kısayol olarak çalışmıyordu.
        tuslar = veri.get("hotkeys")
        if isinstance(tuslar, dict) and str(tuslar.get("panik", "")).lower() == "f12":
            tuslar["panik"] = "Ctrl+Alt+P"
    if eski_surum < 3:
        tuslar = veri.get("hotkeys")
        eski = kullanici.get("hotkeys") if isinstance(kullanici.get("hotkeys"), dict) else {}
        if eski_surum < 2 and str(eski.get("panik", "")).lower() == "f12":
            eski = {**eski, "panik": "Ctrl+Alt+P"}
        if isinstance(tuslar, dict):
            kisayollari_tasi(tuslar, eski, KISAYOL_TASIMA_3, YENI_KISAYOLLAR_3)
            if tuslar.get("bas_konus"):
                veri.setdefault("audio", {})["ptt"] = True   # 2.0.0: bas-konuş ayrı bir anahtarla açılır
        kalem = veri.get("pen_hotkeys")
        eski_kalem = kullanici.get("pen_hotkeys") if isinstance(kullanici.get("pen_hotkeys"), dict) else {}
        if isinstance(kalem, dict):
            kisayollari_tasi(kalem, eski_kalem, {}, YENI_KALEM_TUSLARI_3)


def _uygun_deger(varsayilan, deger, yol: str):
    """Değer varsayılanla aynı türdeyse (gerekirse dönüştürülmüş) onu, değilse varsayılanı döndürür."""
    if varsayilan is None:   # türü serbest alan (ör. camera.position)
        return deger
    sayi = isinstance(deger, (int, float)) and not isinstance(deger, bool)
    if isinstance(varsayilan, bool):
        uygun = isinstance(deger, bool)
    elif isinstance(varsayilan, int):
        uygun = sayi and float(deger).is_integer()
        deger = int(deger) if uygun else deger
    elif isinstance(varsayilan, float):
        uygun = sayi
        deger = float(deger) if uygun else deger
    else:
        uygun = isinstance(deger, type(varsayilan))
    if uygun:
        return deger
    log.warning("Ayar %s geçersiz (%r); varsayılan değer kullanılıyor: %r", yol, deger, varsayilan)
    return copy.deepcopy(varsayilan)


def _birlestir(varsayilan: dict, kullanici: dict, onek: str = "") -> dict:
    """Kullanıcı değerlerini varsayılanın üstüne yazar; iç içe sözlükleri de birleştirir, türleri denetler."""
    sonuc = copy.deepcopy(varsayilan)
    for anahtar, deger in kullanici.items():
        yol = f"{onek}{anahtar}"
        if isinstance(deger, dict) and isinstance(sonuc.get(anahtar), dict):
            sonuc[anahtar] = _birlestir(sonuc[anahtar], deger, yol + ".")
        elif anahtar in sonuc:
            sonuc[anahtar] = _uygun_deger(sonuc[anahtar], deger, yol)
        else:
            sonuc[anahtar] = deger
    return sonuc


class Ayarlar:
    def __init__(self, dosya: Path | None = None, varsayilan_dosya: Path | None = None):
        self.dosya = dosya or paths.ayar_dosyasi()
        self.varsayilan_dosya = varsayilan_dosya or paths.varsayilan_ayar_dosyasi()
        self.veri: dict = {}
        self.yukle()

    def yukle(self) -> None:
        varsayilan = json.loads(self.varsayilan_dosya.read_text(encoding="utf-8"))
        kullanici: dict = {}
        if self.dosya.exists():
            try:
                kullanici = json.loads(self.dosya.read_text(encoding="utf-8"))
                if not isinstance(kullanici, dict):
                    raise ValueError("ayar dosyası bir JSON nesnesi değil")
            except (ValueError, OSError) as e:
                yedek = self.dosya.with_suffix(".bozuk.json")
                log.warning("Ayar dosyası okunamadı (%s); %s olarak yedeklendi, varsayılanlar kullanılıyor", e, yedek.name)
                try:
                    self.dosya.replace(yedek)
                except OSError:
                    pass
                kullanici = {}
        eski_surum = kullanici.get("version", 1) if kullanici else SURUM
        self.veri = _birlestir(varsayilan, kullanici)
        try:
            _tasi(self.veri, int(eski_surum), kullanici)
        except (TypeError, ValueError):
            pass
        degisti = bool(kullanici) and eski_surum != SURUM
        self.veri["version"] = SURUM
        if degisti:
            self.kaydet()
        if not self.dosya.exists():
            self.kaydet()

    def kaydet(self) -> bool:
        try:
            self.dosya.parent.mkdir(parents=True, exist_ok=True)
            gecici = self.dosya.with_suffix(".tmp")
            gecici.write_text(json.dumps(self.veri, indent=2, ensure_ascii=False), encoding="utf-8")
            gecici.replace(self.dosya)  # yarım yazılmış dosya kalmasın
            return True
        except OSError as e:
            # OneDrive/antivirüs dosyayı kilitlemiş olabilir; ayar bellekte geçerli, bir sonraki kayıtta yazılır.
            log.warning("Ayarlar kaydedilemedi: %s", e)
            return False

    def al(self, yol: str, varsayilan=None):
        """ayarlar.al("video.fps") gibi noktalı yol ile okur."""
        dugum = self.veri
        for parca in yol.split("."):
            if not isinstance(dugum, dict) or parca not in dugum:
                return varsayilan
            dugum = dugum[parca]
        return dugum

    def ayarla(self, yol: str, deger) -> None:
        parcalar = yol.split(".")
        dugum = self.veri
        for parca in parcalar[:-1]:
            dugum = dugum.setdefault(parca, {})
        dugum[parcalar[-1]] = deger
        self.kaydet()
