"""settings.json okuma/yazma.

- Varsayılan ayarlar config/settings.default.json'dadır.
- Kullanıcının dosyası %APPDATA%\\YayinUygulamasi\\settings.json'dadır.
- Kullanıcı dosyasında eksik olan alanlar varsayılandan tamamlanır, böylece
  yeni bir sürümde eklenen ayarlar eski dosyaları bozmaz.
- Dosya bozuksa uygulama çökmez: yedeği alınır ve varsayılanlarla devam edilir.
"""

import copy
import json
import logging
from pathlib import Path

from core import paths

log = logging.getLogger(__name__)

SURUM = 2


def _tasi(veri: dict, eski_surum: int) -> None:
    """Eski sürümün ayar dosyasını yeni sürüme uyarlar."""
    if eski_surum < 2:
        # F12'yi Windows hata ayıklayıcıya ayırdığı için global kısayol olarak çalışmıyordu.
        tuslar = veri.get("hotkeys")
        if isinstance(tuslar, dict) and str(tuslar.get("panik", "")).lower() == "f12":
            tuslar["panik"] = "Ctrl+Alt+P"


def _birlestir(varsayilan: dict, kullanici: dict) -> dict:
    """Kullanıcı değerlerini varsayılanın üstüne yazar; iç içe sözlükleri de birleştirir."""
    sonuc = copy.deepcopy(varsayilan)
    for anahtar, deger in kullanici.items():
        if isinstance(deger, dict) and isinstance(sonuc.get(anahtar), dict):
            sonuc[anahtar] = _birlestir(sonuc[anahtar], deger)
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
            _tasi(self.veri, int(eski_surum))
        except (TypeError, ValueError):
            pass
        degisti = bool(kullanici) and eski_surum != SURUM
        self.veri["version"] = SURUM
        if degisti:
            self.kaydet()
        if not self.dosya.exists():
            self.kaydet()

    def kaydet(self) -> None:
        self.dosya.parent.mkdir(parents=True, exist_ok=True)
        gecici = self.dosya.with_suffix(".tmp")
        gecici.write_text(json.dumps(self.veri, indent=2, ensure_ascii=False), encoding="utf-8")
        gecici.replace(self.dosya)  # yarım yazılmış dosya kalmasın

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
