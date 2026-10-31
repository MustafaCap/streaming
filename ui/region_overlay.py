"""F6 kare seçme katmanı.

Ekranın üstüne yarı saydam koyu bir pencere açılır; fareyle kare çizilir.
  Enter: yakınlaştır (sadece bu kare yayına gider)
  V    : vurgula (ekranın geri kalanı kararır)
  Esc  : iptal
Kare çizildikten sonra içinden sürükleyerek taşınabilir, köşelerinden boyutlandırılabilir.
Bu pencere ekran yakalamaya girmez; karşı taraf seçim ekranını görmez.
"""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from core.platform_win import yakalamadan_gizle
from ui.theme import RENK

TUTAMAK = 10


def ekrani_bul(dikdortgen):
    """Yakalanan monitörün (fiziksel piksel: sol, üst, gen, yük) Qt'deki QScreen karşılığı."""
    ekranlar = QGuiApplication.screens()
    if dikdortgen is None:
        return QGuiApplication.primaryScreen()
    sol, ust, w, h = dikdortgen
    en_iyi, en_iyi_puan = None, None
    for e in ekranlar:
        g, dpr = e.geometry(), e.devicePixelRatio()
        boyut_farki = abs(round(g.width() * dpr) - w) + abs(round(g.height() * dpr) - h)
        konum_farki = min(abs(g.x() - sol) + abs(g.y() - ust),
                          abs(round(g.x() * dpr) - sol) + abs(round(g.y() * dpr) - ust))
        puan = boyut_farki * 10 + konum_farki
        if en_iyi_puan is None or puan < en_iyi_puan:
            en_iyi, en_iyi_puan = e, puan
    return en_iyi or QGuiApplication.primaryScreen()


class BolgeKatmani(QWidget):
    secildi = Signal(tuple, str)   # (x, y, w, h) monitöre oranla 0..1, mod
    iptal = Signal()

    def __init__(self, ekran, onceki=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.ekran = ekran
        self.setGeometry(ekran.geometry())
        self.secim = QRect()
        if onceki:
            g = ekran.geometry()
            x, y, w, h = onceki
            self.secim = QRect(round(x * g.width()), round(y * g.height()),
                               round(w * g.width()), round(h * g.height()))
        self._surukle = None   # ("yeni"|"tasi"|köşe adı, başlangıç noktası, başlangıç seçimi)
        self._bitti = False

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ---- çizim

    def _koseler(self) -> dict[str, QRect]:
        r = self.secim.normalized()
        t = TUTAMAK
        return {"sol_ust": QRect(r.left() - t // 2, r.top() - t // 2, t, t),
                "sag_ust": QRect(r.right() - t // 2, r.top() - t // 2, t, t),
                "sol_alt": QRect(r.left() - t // 2, r.bottom() - t // 2, t, t),
                "sag_alt": QRect(r.right() - t // 2, r.bottom() - t // 2, t, t)}

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tum = QPainterPath()
        tum.addRect(QRectF(self.rect()))
        r = self.secim.normalized()
        if not r.isEmpty():
            delik = QPainterPath()
            delik.addRect(QRectF(r))
            tum = tum.subtracted(delik)
        p.fillPath(tum, QColor(0, 0, 0, 140))
        if not r.isEmpty():
            # Windows'ta tamamen saydam piksel tıklamayı alttaki pencereye geçirir; neredeyse saydam boya.
            p.fillRect(r, QColor(0, 0, 0, 1))

        vurgu = QColor(RENK["vurgu"])
        if not r.isEmpty():
            p.setPen(QPen(vurgu, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.setBrush(QColor("white"))
            p.setPen(QPen(vurgu, 2))
            for k in self._koseler().values():
                p.drawRect(k)
            dpr = self.ekran.devicePixelRatio()
            self._etiket(p, f"{round(r.width() * dpr)} × {round(r.height() * dpr)}",
                         QPoint(r.left(), max(0, r.top() - 34)))

        ipucu = "Fareyle kare çiz  ·  Enter: yakınlaştır  ·  V: vurgula  ·  Esc: iptal"
        self._etiket(p, ipucu, QPoint(self.width() // 2, 24), ortala=True, buyuk=True)

    def _etiket(self, p: QPainter, metin: str, nokta: QPoint, ortala=False, buyuk=False) -> None:
        f = QFont("Segoe UI", 11 if buyuk else 10)
        f.setBold(True)
        p.setFont(f)
        olc = p.fontMetrics().boundingRect(metin)
        w, h = olc.width() + 20, olc.height() + 10
        x = nokta.x() - w // 2 if ortala else nokta.x()
        kutu = QRectF(x, nokta.y(), w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RENK["panel"]))
        p.drawRoundedRect(kutu, 6, 6)
        p.setPen(QColor(RENK["yazi"]))
        p.drawText(kutu, Qt.AlignCenter, metin)

    # ---- fare

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            if e.button() == Qt.RightButton:
                self._iptal()
            return
        nokta = e.position().toPoint()
        for ad, k in self._koseler().items():
            if not self.secim.isEmpty() and k.adjusted(-4, -4, 4, 4).contains(nokta):
                self._surukle = (ad, nokta, QRect(self.secim.normalized()))
                return
        if not self.secim.isEmpty() and self.secim.normalized().contains(nokta):
            self._surukle = ("tasi", nokta, QRect(self.secim.normalized()))
            return
        self.secim = QRect(nokta, nokta)
        self._surukle = ("yeni", nokta, None)
        self.update()

    def mouseMoveEvent(self, e):
        nokta = e.position().toPoint()
        if self._surukle is None:
            uzerinde = any(k.adjusted(-4, -4, 4, 4).contains(nokta) for k in self._koseler().values()) \
                if not self.secim.isEmpty() else False
            if uzerinde:
                self.setCursor(Qt.SizeAllCursor)
            elif not self.secim.isEmpty() and self.secim.normalized().contains(nokta):
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return
        tur, bas, ilk = self._surukle
        if tur == "yeni":
            self.secim = QRect(bas, nokta)
        elif tur == "tasi":
            r = QRect(ilk)
            r.translate(nokta - bas)
            r.moveLeft(max(0, min(r.left(), self.width() - r.width())))
            r.moveTop(max(0, min(r.top(), self.height() - r.height())))
            self.secim = r
        else:
            r = QRect(ilk)
            if "sol" in tur:
                r.setLeft(nokta.x())
            else:
                r.setRight(nokta.x())
            if "ust" in tur:
                r.setTop(nokta.y())
            else:
                r.setBottom(nokta.y())
            self.secim = r
        self.update()

    def mouseReleaseEvent(self, e):
        self._surukle = None
        self.secim = self.secim.normalized().intersected(self.rect())
        self.update()

    def mouseDoubleClickEvent(self, e):
        if not self.secim.isEmpty() and self.secim.contains(e.position().toPoint()):
            self._onayla("yakinlastir")

    # ---- klavye

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._onayla("yakinlastir")
        elif e.key() == Qt.Key_V:
            self._onayla("vurgula")
        elif e.key() == Qt.Key_Escape:
            self._iptal()

    def _onayla(self, mod: str) -> None:
        r = self.secim.normalized()
        if r.width() < 8 or r.height() < 8:
            return  # henüz kare çizilmedi
        w, h = self.width(), self.height()
        self._bitti = True
        self.secildi.emit((r.x() / w, r.y() / h, r.width() / w, r.height() / h), mod)
        self.close()

    def _iptal(self) -> None:
        if not self._bitti:
            self._bitti = True
            self.iptal.emit()
        self.close()

    def closeEvent(self, e):
        if not self._bitti:
            self._bitti = True
            self.iptal.emit()
        super().closeEvent(e)

