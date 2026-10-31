"""Uygulamanın dosya yolları.

Ayarlar ve loglar program klasöründe değil, kullanıcının %APPDATA% klasöründe
tutulur. Böylece uygulama Program Files'a kurulsa bile yazabiliriz.
"""

import json
import logging
import os
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)

UYGULAMA_ADI = "RizeOn"
ESKI_AD = "YayinUygulamasi"   # 1.5.x ve öncesi (uygulamanın adı "Yayın Uygulaması" iken)


def uygulama_klasoru() -> Path:
    """Programın kendi dosyalarının (ör. varsayılan ayarlar) bulunduğu klasör."""
    if getattr(sys, "frozen", False):  # PyInstaller ile paketlenmişse
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def veri_klasoru() -> Path:
    """Kullanıcıya özel yazılabilir klasör: %APPDATA%\\RizeOn"""
    taban = os.environ.get("YAYIN_VERI_KLASORU") or os.environ.get("APPDATA") or str(Path.home() / ".config")
    yol = Path(taban) / UYGULAMA_ADI
    if not yol.exists():
        eski_klasoru_tasi(Path(taban) / ESKI_AD, yol)
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def eski_klasoru_tasi(eski: Path, yeni: Path) -> bool:
    """Ad değişince ayarlar, loglar ve bekleme görüntüleri kaybolmasın: eski klasörü yeni ada taşır.

    Taşınamazsa (ör. eski sürüm hâlâ açık) kopyalar; eski klasör olduğu gibi kalır."""
    if not eski.is_dir() or yeni.exists():
        return False
    try:
        eski.rename(yeni)
    except OSError:
        try:
            shutil.copytree(eski, yeni)
        except OSError:
            log.warning("Eski veri klasörü taşınamadı: %s", eski, exc_info=True)
            shutil.rmtree(yeni, ignore_errors=True)
            return False
    log.info("Eski veri klasörü yeni ada taşındı: %s -> %s", eski, yeni)
    _ayar_yollarini_duzelt(yeni / "settings.json", eski, yeni)
    return True


def _ayar_yollarini_duzelt(dosya: Path, eski: Path, yeni: Path) -> None:
    """settings.json'da eski klasörü gösteren yollar (ör. bekleme görüntüsü) yeni klasöre çevrilir."""
    if not dosya.exists():
        return
    try:
        veri = json.loads(dosya.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return   # bozuk dosyayı Ayarlar zaten varsayılana döndürür
    onek = str(eski)

    def cevir(d):
        if isinstance(d, dict):
            return {k: cevir(v) for k, v in d.items()}
        if isinstance(d, list):
            return [cevir(v) for v in d]
        if isinstance(d, str) and d.lower().startswith(onek.lower()):
            return str(yeni) + d[len(onek):]
        return d

    yeni_veri = cevir(veri)
    if yeni_veri != veri:
        try:
            dosya.write_text(json.dumps(yeni_veri, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            log.warning("settings.json'daki eski yollar düzeltilemedi", exc_info=True)


def ayar_dosyasi() -> Path:
    return veri_klasoru() / "settings.json"


def varsayilan_ayar_dosyasi() -> Path:
    return uygulama_klasoru() / "config" / "settings.default.json"


def log_klasoru() -> Path:
    yol = veri_klasoru() / "logs"
    yol.mkdir(parents=True, exist_ok=True)
    return yol
