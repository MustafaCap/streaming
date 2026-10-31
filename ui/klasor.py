"""Kayıt klasörünü Windows Gezgini'nde açar (ana pencere, tepsi menüsü, ayarlar)."""

import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

log = logging.getLogger(__name__)


def kayit_klasoru(ayarlar) -> Path:
    from core.recorder import varsayilan_klasor
    yol = ayarlar.al("record.folder", "") if ayarlar is not None else ""
    return Path(yol) if yol else varsayilan_klasor()


def kayit_klasorunu_ac(ayarlar) -> bool:
    klasor = kayit_klasoru(ayarlar)
    try:
        klasor.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Kayıt klasörü oluşturulamadı: %s", e)
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(klasor)))
