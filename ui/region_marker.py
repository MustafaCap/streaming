"""Yakınlaştırma izi: F6 + Enter ile bir kare yayına verilince, o karenin ekrandaki
yerini gösteren ince, yarı saydam bir çerçeve.

  - Sadece sen görürsün: pencere ekran yakalamaya girmez, yayına çıkmaz.
  - Tıklamaları engellemez (fare alttaki pencereye geçer).
  - Tam ekrana dönünce (tekrar F6) kaybolur.
"""

from PySide6.QtCore import QLineF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.platform_win import yakalamadan_gizle
from ui.theme import RENK

PAY = 6  # çerçeve, seçilen alanın biraz dışına çizilir; içerik kapanmasın


class YakinlastirmaIzi(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def goster(self, ekran, bolge) -> None:
        """bolge: (x, y, w, h) monitöre oranla 0..1."""
        g = ekran.geometry()
        x, y, w, h = bolge
        r = QRect(g.x() + round(x * g.width()), g.y() + round(y * g.height()),
                  round(w * g.width()), round(h * g.height()))
        self.setGeometry(r.adjusted(-PAY, -PAY, PAY, PAY).intersected(g.adjusted(-PAY, -PAY, PAY, PAY)))
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        renk = QColor(RENK["vurgu"])
        renk.setAlpha(110)
        kalem = QPen(renk, 2, Qt.DashLine)
        p.setPen(kalem)
        p.setBrush(Qt.NoBrush)
        r = QRectF(self.rect()).adjusted(PAY / 2, PAY / 2, -PAY / 2, -PAY / 2)
        p.drawRoundedRect(r, 4, 4)
        # köşelerde daha belirgin kısa çizgiler
        renk.setAlpha(200)
        p.setPen(QPen(renk, 3))
        u = min(18.0, r.width() / 4, r.height() / 4)
        for (x, y, dx, dy) in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                               (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(QLineF(x, y, x + dx * u, y))
            p.drawLine(QLineF(x, y, x, y + dy * u))
        # küçük etiket
        f = QFont("Segoe UI", 8)
        f.setBold(True)
        p.setFont(f)
        metin = "● Yayında"
        olc = p.fontMetrics().boundingRect(metin)
        kutu = QRectF(r.left() + 8, r.top() + 8, olc.width() + 12, olc.height() + 4)
        if kutu.right() < r.right() and kutu.bottom() < r.bottom():
            zemin = QColor(RENK["panel"])
            zemin.setAlpha(150)
            p.setPen(Qt.NoPen)
            p.setBrush(zemin)
            p.drawRoundedRect(kutu, 4, 4)
            yazi = QColor(RENK["yazi"])
            yazi.setAlpha(200)
            p.setPen(yazi)
            p.drawText(kutu, Qt.AlignCenter, metin)
