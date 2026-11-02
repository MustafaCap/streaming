"""Bölge seçimi: ekranın üstüne kararan katman, ince beyaz çerçeve ve 4 yuvarlak tutamak.

SecimDuzenleyici çerçeveyi çizer ve fareyle düzenler (yeni kutu çiz, içinden taşı, köşeden
boyutlandır). İki yerde kullanılır:
  - ui/drawing_overlay.py'deki birleşik bölge + kalem katmanı (Bölge düğmesi, Ctrl+Shift+S)
  - BolgeKatmani: "Ekran bölgesi" kaynağı eklerken alan seçmek için basit seçici

Bu pencereler ekran yakalamaya girmez; karşı taraf seçim ekranını görmez.
"""

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from core.platform_win import yakalamadan_gizle
from ui.theme import RENK, qrenk, yazi_tipi

TUTAMAK = 7          # yuvarlak tutamak çapı
TUTAMAK_ALANI = 22   # fareyle yakalama alanı
KARARTMA = QColor(9, 9, 11, 140)   # rgba(9,9,11,.55)


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


class SecimDuzenleyici:
    """Bir widget üstündeki seçim kutusu (widget koordinatında)."""

    KOSELER = ("sol_ust", "sag_ust", "sol_alt", "sag_alt")

    def __init__(self, widget: QWidget, oranlar=None):
        self.w = widget
        self.secim = QRect()
        self._surukle = None   # (tür, başlangıç noktası, başlangıç kutusu)
        if oranlar:
            self.oranlardan(oranlar)

    # ---- dönüşüm

    def oranlardan(self, oranlar) -> None:
        W, H = self.w.width(), self.w.height()
        x, y, w, h = oranlar
        self.secim = QRect(round(x * W), round(y * H), round(w * W), round(h * H))

    def oranlar(self):
        r = self.secim.normalized()
        W, H = max(1, self.w.width()), max(1, self.w.height())
        return r.x() / W, r.y() / H, r.width() / W, r.height() / H

    @property
    def var(self) -> bool:
        r = self.secim.normalized()
        return r.width() >= 8 and r.height() >= 8

    def piksel_boyutu(self, dpr: float) -> tuple[int, int]:
        r = self.secim.normalized()
        return round(r.width() * dpr), round(r.height() * dpr)

    # ---- tutamaklar

    def kose_noktalari(self) -> dict[str, QPoint]:
        r = self.secim.normalized()
        return {"sol_ust": r.topLeft(), "sag_ust": QPoint(r.right() + 1, r.top()),
                "sol_alt": QPoint(r.left(), r.bottom() + 1), "sag_alt": QPoint(r.right() + 1, r.bottom() + 1)}

    def kose_altinda(self, nokta: QPoint) -> str | None:
        if not self.var:
            return None
        for ad, k in self.kose_noktalari().items():
            if abs(k.x() - nokta.x()) <= TUTAMAK_ALANI // 2 and abs(k.y() - nokta.y()) <= TUTAMAK_ALANI // 2:
                return ad
        return None

    def imlec(self, nokta: QPoint, icinden_tasi: bool = True):
        kose = self.kose_altinda(nokta)
        if kose in ("sol_ust", "sag_alt"):
            return Qt.SizeFDiagCursor
        if kose:
            return Qt.SizeBDiagCursor
        if icinden_tasi and self.var and self.secim.normalized().contains(nokta):
            return Qt.SizeAllCursor
        return None

    # ---- fare

    def bas(self, nokta: QPoint, yeni_kutu: bool = True, icinden_tasi: bool = True) -> bool:
        """True: olay seçim düzenlemesine gitti."""
        kose = self.kose_altinda(nokta)
        if kose:
            self._surukle = (kose, nokta, QRect(self.secim.normalized()))
            return True
        if icinden_tasi and self.var and self.secim.normalized().contains(nokta):
            self._surukle = ("tasi", nokta, QRect(self.secim.normalized()))
            return True
        if yeni_kutu:
            self.secim = QRect(nokta, nokta)
            self._surukle = ("yeni", nokta, None)
            return True
        return False

    @property
    def surukleniyor(self) -> bool:
        return self._surukle is not None

    def tasi(self, nokta: QPoint) -> None:
        if self._surukle is None:
            return
        tur, bas, ilk = self._surukle
        if tur == "yeni":
            self.secim = QRect(bas, nokta)
        elif tur == "tasi":
            r = QRect(ilk)
            r.translate(nokta - bas)
            r.moveLeft(max(0, min(r.left(), self.w.width() - r.width())))
            r.moveTop(max(0, min(r.top(), self.w.height() - r.height())))
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

    def birak(self) -> bool:
        """True: bir düzenleme bitti."""
        if self._surukle is None:
            return False
        self._surukle = None
        self.secim = self.secim.normalized().intersected(self.w.rect())
        return True

    # ---- çizim

    def ciz(self, p: QPainter, karartma: QColor | None = KARARTMA) -> None:
        r = self.secim.normalized()
        if karartma is not None and karartma.alpha() > 0:
            tum = QPainterPath()
            tum.addRect(QRectF(self.w.rect()))
            if self.var:
                delik = QPainterPath()
                delik.addRect(QRectF(r))
                tum = tum.subtracted(delik)
            p.fillPath(tum, karartma)
        if not self.var:
            return
        p.setRenderHint(QPainter.Antialiasing)
        beyaz = QColor(255, 255, 255, 230)
        p.setPen(QPen(beyaz, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        for k in self.kose_noktalari().values():
            p.drawEllipse(QPointF(k), TUTAMAK / 2, TUTAMAK / 2)


class BolgeKatmani(QWidget):
    """Basit bölge seçici (kaynak eklerken): kutu çiz, Enter ya da çift tık onaylar, Esc vazgeçer."""

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
        self.duzenleyici = SecimDuzenleyici(self, onceki)
        self._bitti = False

    @property
    def secim(self) -> QRect:
        return self.duzenleyici.secim

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def paintEvent(self, _):
        p = QPainter(self)
        self.duzenleyici.ciz(p)
        if self.duzenleyici.var:
            # Windows'ta tamamen saydam piksel tıklamayı alttaki pencereye geçirir; neredeyse saydam boya.
            p.fillRect(self.duzenleyici.secim.normalized(), QColor(0, 0, 0, 1))
            r = self.duzenleyici.secim.normalized()
            w, h = self.duzenleyici.piksel_boyutu(self.ekran.devicePixelRatio())
            p.setFont(yazi_tipi(12))
            p.setPen(qrenk("dugme"))
            y = r.bottom() + 10 if r.bottom() + 30 < self.height() else r.top() - 24
            p.drawText(QRectF(r.left(), y, 200, 18), Qt.AlignLeft | Qt.AlignVCenter, f"{w} × {h}")
        p.setFont(yazi_tipi(12))
        p.setPen(QColor(RENK["dugme"]))
        p.drawText(QRectF(0, self.height() - 48, self.width(), 24), Qt.AlignCenter,
                   "Kutu çiz · Enter ya da çift tık tamam · Esc vazgeç")

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._iptal()
        elif e.button() == Qt.LeftButton:
            self.duzenleyici.bas(e.position().toPoint())
            self.update()

    def mouseMoveEvent(self, e):
        nokta = e.position().toPoint()
        if self.duzenleyici.surukleniyor:
            self.duzenleyici.tasi(nokta)
            self.update()
        else:
            self.setCursor(self.duzenleyici.imlec(nokta) or Qt.CrossCursor)

    def mouseReleaseEvent(self, e):
        self.duzenleyici.birak()
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.duzenleyici.var and self.duzenleyici.secim.normalized().contains(e.position().toPoint()):
            self._onayla("yakinlastir")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._onayla("yakinlastir")
        elif e.key() == Qt.Key_V:
            self._onayla("vurgula")
        elif e.key() == Qt.Key_Escape:
            self._iptal()

    def _onayla(self, mod: str) -> None:
        if not self.duzenleyici.var:
            return  # henüz kutu çizilmedi
        self._bitti = True
        self.secildi.emit(self.duzenleyici.oranlar(), mod)
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
