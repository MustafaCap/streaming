"""Uygulama simgesi (dosya gerektirmez, kodla çizilir)."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF

from ui.theme import RENK


def uygulama_ikonu(canli: bool = False, boyut: int = 64) -> QIcon:
    """Koyu kare içinde kamera simgesi; yayın açıkken yeşil nokta."""
    pm = QPixmap(boyut, boyut)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = boyut / 64
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(RENK["panel"]))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 14 * s, 14 * s)
    p.setBrush(QColor(RENK["vurgu"]))
    p.drawRoundedRect(QRectF(12 * s, 20 * s, 28 * s, 24 * s), 5 * s, 5 * s)
    p.drawPolygon(QPolygonF([QPointF(40 * s, 26 * s), QPointF(52 * s, 20 * s),
                             QPointF(52 * s, 44 * s), QPointF(40 * s, 38 * s)]))
    if canli:
        p.setBrush(QColor(RENK["acik"]))
        p.setPen(QColor(RENK["panel"]))
        p.drawEllipse(QRectF(40 * s, 40 * s, 20 * s, 20 * s))
    p.end()
    return QIcon(pm)
