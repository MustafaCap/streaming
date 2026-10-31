"""Hakkında penceresi: sürüm, lisans (GPLv3), kaynak kod adresi ve lisans dosyaları.

GPLv3 madde 5(d): etkileşimli programlar lisansı ve garantinin olmadığını göstermeli.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from core.surum import SURUM
from ui.theme import QSS

KAYNAK = "https://github.com/MustafaCap/streaming"


def lisans_yolu() -> Path:
    """Kurulu pakette 'lisanslar' klasörü, kaynaktan çalışırken depodaki LICENSE dosyası."""
    if getattr(sys, "frozen", False):
        kok = Path(sys.executable).resolve().parent
        return kok / "lisanslar" if (kok / "lisanslar").is_dir() else kok / "LICENSE.txt"
    return Path(__file__).resolve().parent.parent / "LICENSE"


def metin() -> str:
    return (
        f"<h3>Yayın Uygulaması {SURUM}</h3>"
        "<p>Telif hakkı © 2026 Mustafa</p>"
        "<p>Bu program özgür yazılımdır. <b>GNU Genel Kamu Lisansı sürüm 3 (GPLv3)</b> koşullarıyla "
        "kullanabilir, değiştirebilir ve dağıtabilirsiniz. Program <b>hiçbir garanti olmadan</b>, "
        "\"olduğu gibi\" sunulur.</p>"
        f"<p>Kaynak kod ve yeni sürümler:<br>{KAYNAK}</p>"
        "<p>Uygulama internete bağlanmaz. Kullandığı açık kaynak kütüphanelerin (PySide6/Qt, OpenCV, "
        "FFmpeg ve diğerleri) lisansları <i>lisanslar</i> klasöründedir.</p>"
    )


class HakkindaPenceresi(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hakkında")
        self.setStyleSheet(QSS)
        yazi = QLabel(metin())
        yazi.setWordWrap(True)
        yazi.setTextFormat(Qt.RichText)
        yazi.setTextInteractionFlags(Qt.TextSelectableByMouse)  # adres kopyalanabilsin
        dugmeler = QDialogButtonBox(QDialogButtonBox.Close)
        dugmeler.button(QDialogButtonBox.Close).setText("Kapat")
        lisanslar = dugmeler.addButton("Lisansları göster", QDialogButtonBox.ActionRole)
        lisanslar.clicked.connect(self.lisanslari_ac)
        dugmeler.rejected.connect(self.reject)
        kok = QVBoxLayout(self)
        kok.addWidget(yazi)
        kok.addWidget(dugmeler)
        self.resize(460, 0)

    def showEvent(self, olay):
        super().showEvent(olay)
        from core.platform_win import yakalamadan_gizle
        yakalamadan_gizle(int(self.winId()))

    @staticmethod
    def lisanslari_ac() -> bool:
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(lisans_yolu())))


def hakkinda_goster(parent=None) -> None:
    HakkindaPenceresi(parent).exec()
