"""Köşe bildirimleri: "Mikrofon kapandı · F8" gibi 1,5 saniyelik küçük kart.

Bildirim penceresi odak almaz, tıklamaları alttaki pencereye geçirir ve
ekran yakalamaya girmez (karşı taraf görmez, sadece sen görürsün).
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.platform_win import yakalamadan_gizle
from ui.theme import RENK


class Bildirim(QWidget):
    SURE_MS = 1600

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.kart = QWidget(self)
        self.kart.setObjectName("kart")
        self.metin = QLabel()
        self.tus = QLabel()
        self.metin.setStyleSheet(f"color: {RENK['yazi']}; font-size: 14px; font-weight: 600; background: transparent;")
        self.tus.setStyleSheet(f"color: {RENK['yazi2']}; font-size: 12px; background: {RENK['kenarlik']};"
                               " border-radius: 4px; padding: 2px 6px;")
        satir = QHBoxLayout(self.kart)
        satir.setContentsMargins(14, 10, 14, 10)
        satir.setSpacing(10)
        satir.addWidget(self.metin)
        satir.addWidget(self.tus)
        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(self.kart)
        self._renk(RENK["vurgu"])

        self._zamanlayici = QTimer(self)
        self._zamanlayici.setSingleShot(True)
        self._zamanlayici.timeout.connect(self._sondur)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._anim_bitti)
        self._gizlenecek = False
        self._gizli_ayarlandi = False

    def _renk(self, renk: str) -> None:
        self.kart.setStyleSheet(f"QWidget#kart {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']};"
                                f" border-left: 4px solid {renk}; border-radius: 10px; }}")

    def goster(self, metin: str, tus: str = "", renk: str | None = None) -> None:
        self.metin.setText(metin)
        self.tus.setText(tus)
        self.tus.setVisible(bool(tus))
        self._renk(renk or RENK["vurgu"])
        self.adjustSize()
        ekran = QGuiApplication.primaryScreen().availableGeometry()
        self.move(ekran.right() - self.width() - 20, ekran.bottom() - self.height() - 20)
        self._anim.stop()
        self._gizlenecek = False
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        if not self._gizli_ayarlandi:
            self._gizli_ayarlandi = yakalamadan_gizle(int(self.winId())) or True
        self._zamanlayici.start(self.SURE_MS)

    def _sondur(self) -> None:
        self._gizlenecek = True
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _anim_bitti(self) -> None:
        if self._gizlenecek:
            self.hide()


def bildirim_rengi(mesaj: str) -> str:
    """Kapandı/durduruldu gibi mesajlar kırmızı, açıldı/başladı yeşil, diğerleri mavi."""
    m = mesaj.lower()
    if any(k in m for k in ("kapandı", "kapatıldı", "durduruldu", "kapalı")):
        return RENK["kapali"]
    if any(k in m for k in ("açıldı", "başlatılıyor", "başladı", "açık")):
        return RENK["acik"]
    if "panik" in m:
        return RENK["panik"]
    return RENK["vurgu"]
