"""Yakınlaştırma izi: bölge yakınlaştırılınca o alanın ekrandaki yerini gösteren ince çerçeve.

  - Sadece sen görürsün: pencere ekran yakalamaya girmez, yayına çıkmaz.
  - Tıklamaları engellemez (fare alttaki pencereye geçer).
  - Tam ekrana dönünce kaybolur.
"""

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core.platform_win import yakalamadan_gizle

PAY = 6  # çerçeve, seçilen alanın biraz dışına çizilir; içerik kapanmasın


class YakinlastirmaIzi(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def goster(self, ekran, bolge) -> None:
        """bolge: (x, y, w, h) monitöre oranla 0..1."""
        if not bolge:
            self.hide()
            return
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
        r = QRectF(self.rect()).adjusted(PAY, PAY, -PAY, -PAY)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(-0.5, -0.5, 0.5, 0.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        for nokta in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            p.drawEllipse(QPointF(nokta), 3, 3)
