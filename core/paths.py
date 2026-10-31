"""Uygulamanın dosya yolları.

Ayarlar ve loglar program klasöründe değil, kullanıcının %APPDATA% klasöründe
tutulur. Böylece uygulama Program Files'a kurulsa bile yazabiliriz.
"""

import os
import sys
from pathlib import Path

UYGULAMA_ADI = "YayinUygulamasi"


def uygulama_klasoru() -> Path:
    """Programın kendi dosyalarının (ör. varsayılan ayarlar) bulunduğu klasör."""
    if getattr(sys, "frozen", False):  # PyInstaller ile paketlenmişse
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def veri_klasoru() -> Path:
    """Kullanıcıya özel yazılabilir klasör: %APPDATA%\\YayinUygulamasi"""
    taban = os.environ.get("YAYIN_VERI_KLASORU") or os.environ.get("APPDATA") or str(Path.home() / ".config")
    yol = Path(taban) / UYGULAMA_ADI
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def ayar_dosyasi() -> Path:
    return veri_klasoru() / "settings.json"


def varsayilan_ayar_dosyasi() -> Path:
    return uygulama_klasoru() / "config" / "settings.default.json"


def log_klasoru() -> Path:
    yol = veri_klasoru() / "logs"
    yol.mkdir(parents=True, exist_ok=True)
    return yol
