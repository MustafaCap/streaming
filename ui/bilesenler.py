"""Arayüzün ortak parçaları: karo düğme, simge düğmesi, Windows 11 anahtarı, canlı ses çizgisi,
seçim grubu, tutma yeri, kayıt grubu ve iki satırlı menü öğesi.

Hepsi ui/theme.py'deki kurallarla çizilir. Simge-yalnız düğmelerin erişilebilir adı
(setAccessibleName) ve ipucu (kısayol dahil) vardır.
"""

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget, QWidgetAction)

from core.audio_mixer import db
from ui.icons import simge_pixmap
from ui.theme import ALFA, KARO, RENK, beyaz, qrenk, yazi_tipi


def ipucu(ad: str, tus: str = "") -> str:
    return f"{ad} · {tus}" if tus else ad


class _Dugme(QAbstractButton):
    """Ortak: üzerine gelme, basılma ve klavye odağı çizimi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._uzerinde = False
        self._klavye_odagi = False   # odak halkası sadece Tab ile gelinince çizilir

    def focusInEvent(self, e):
        self._klavye_odagi = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        self._klavye_odagi = False
        super().focusOutEvent(e)
        self.update()

    def odak_halkasi(self) -> bool:
        return self.hasFocus() and self._klavye_odagi

    def enterEvent(self, e):
        self._uzerinde = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._uzerinde = False
        self.update()
        super().leaveEvent(e)

    def _zemin(self, p: QPainter, r: QRectF, yaricap: float, secili: bool = False, kapali: bool = False) -> None:
        alfa = 0.0
        if secili:
            alfa = ALFA["seçili"]
        elif kapali:
            alfa = ALFA["kapali"]
        if self._uzerinde and self.isEnabled():
            alfa = max(alfa, ALFA["uzerine"]) + (0.03 if (secili or kapali) else 0)
        if self.isDown():
            alfa += 0.04
        if alfa > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(qrenk("beyaz", alfa))
            p.drawRoundedRect(r, yaricap, yaricap)
        if self.odak_halkasi():
            p.setPen(qrenk("beyaz", 0.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), yaricap, yaricap)


class KaroDugme(_Dugme):
    """Kontrol barı karosu: simge + altında kısa etiket (76×60).

    kapali: sönük gri zemin, gri simge ve üstünde çapraz çizgi (mikrofon/kamera kapalı).
    secili: açık gri zemin + beyaz yazı (bölge/kalem açık, panik açık).
    """

    def __init__(self, simge_adi: str | None, metin: str, parent=None):
        super().__init__(parent)
        self.simge_adi, self.metin = simge_adi, metin
        self.kapali = False
        self.secili = False
        self.setFixedSize(*KARO)
        self.setAccessibleName(metin)

    def durum(self, kapali: bool = False, secili: bool = False, metin: str | None = None) -> None:
        if metin is not None:
            self.metin = metin
        if (kapali, secili) != (self.kapali, self.secili) or metin is not None:
            self.kapali, self.secili = kapali, secili
            self.update()

    def sizeHint(self):
        return QSize(*KARO)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        self._zemin(p, r, 8, self.secili, self.kapali)
        renk = RENK["yazi2"] if self.kapali else (RENK["beyaz"] if self.secili else RENK["yazi"])
        if not self.isEnabled():
            renk = RENK["soluk"]
        p.setFont(yazi_tipi(11))
        p.setPen(qrenk("yazi2" if self.kapali else ("beyaz" if self.secili else "yazi")))
        if not self.isEnabled():
            p.setPen(qrenk("soluk"))
        if self.simge_adi:
            pm = simge_pixmap(self.simge_adi, renk, 18, cizgili=self.kapali, dpr=self.devicePixelRatioF())
            p.drawPixmap(QPoint(round((r.width() - 18) / 2), 12), pm)
            p.drawText(QRectF(0, 34, r.width(), 18), Qt.AlignHCenter | Qt.AlignTop, self.metin)
        else:
            p.drawText(r, Qt.AlignCenter, self.metin)


class SimgeDugme(_Dugme):
    """Yuvarlak simge düğmesi (36 px; mini bar ve kalem barında da). Erişilebilir adı zorunlu."""

    def __init__(self, simge_adi: str, ad: str, tus: str = "", boyut: int = 36, simge_boyu: int = 16,
                 renk: str | None = None, parent=None, yaricap: float | None = None):
        super().__init__(parent)
        self.simge_adi, self.simge_boyu, self.renk = simge_adi, simge_boyu, renk
        self.kapali = False
        self.secili = False
        self._yaricap = yaricap
        self.gizli = False      # True: yeri durur ama çizilmez (kaynak satırındaki ×, üzerine gelince çıkar)
        self.setFixedSize(boyut, boyut)
        self.ad_ayarla(ad, tus)

    def ad_ayarla(self, ad: str, tus: str = "") -> None:
        self.setAccessibleName(ad)
        self.setToolTip(ipucu(ad, tus))

    def durum(self, kapali: bool = False, secili: bool = False, simge_adi: str | None = None) -> None:
        degisti = (kapali, secili) != (self.kapali, self.secili) or (simge_adi and simge_adi != self.simge_adi)
        self.kapali, self.secili = kapali, secili
        if simge_adi:
            self.simge_adi = simge_adi
        if degisti:
            self.update()

    def paintEvent(self, _):
        if self.gizli and not self.odak_halkasi() and not self._uzerinde:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        self._zemin(p, r, self._yaricap if self._yaricap is not None else r.height() / 2, self.secili, self.kapali)
        renk = RENK["soluk"] if self.kapali else (self.renk or (RENK["beyaz"] if self.secili else RENK["yazi"]))
        if not self.isEnabled():
            renk = RENK["soluk"]
        b = self.simge_boyu
        pm = simge_pixmap(self.simge_adi, renk, b, cizgili=self.kapali, dpr=self.devicePixelRatioF())
        p.drawPixmap(QPoint(round((r.width() - b) / 2), round((r.height() - b) / 2)), pm)


class HapDugme(QPushButton):
    """Başlık çubuğundaki yazılı yuvarlak düğme (28 px)."""

    def __init__(self, metin: str, ipucu_metni: str = "", parent=None):
        super().__init__(metin, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        if ipucu_metni:
            self.setToolTip(ipucu_metni)


class Anahtar(_Dugme):
    """Windows 11 tarzı aç/kapa anahtarı (36×20)."""

    def __init__(self, ad: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(40, 24)
        self.setAccessibleName(ad)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(2, 2, 36, 20)
        acik = self.isChecked()
        if acik:
            p.setPen(qrenk("dugme"))
            p.setBrush(qrenk("beyaz" if self._uzerinde else "dugme"))
        else:
            p.setPen(qrenk("yazi2" if self._uzerinde else "nokta"))
            p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(qrenk("zemin") if acik else qrenk("soluk"))
        x = r.x() + (19 if acik else 3)
        p.drawEllipse(QRectF(x + 0.5, r.y() + 4, 12, 12) if acik else QRectF(x, r.y() + 4, 12, 12))
        if self.odak_halkasi():
            p.setPen(qrenk("beyaz", 0.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        if not self.isEnabled():
            p.fillRect(self.rect(), qrenk("panel", 0.5))


class SesCizgisi(QWidget):
    """İnce yeşil canlı ses seviyesi çizgisi (-60 dB .. 0 dB). Yeşil sadece burada."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.deger = 0.0

    def ayarla(self, seviye: float) -> None:
        hedef = max(0.0, (db(seviye) + 60.0) / 60.0) if seviye > 0 else 0.0
        yeni = hedef if hedef > self.deger else self.deger * 0.8 + hedef * 0.2
        if abs(yeni - self.deger) > 0.002:
            self.deger = yeni
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        yol = QPainterPath()
        yol.addRoundedRect(r, 2, 2)
        p.setClipPath(yol)
        p.fillRect(r, qrenk("iz"))
        w = r.width() * min(1.0, self.deger)
        if w > 0.5:
            p.fillRect(QRectF(0, 0, w, r.height()), qrenk("ses"))


class SecimGrubu(QFrame):
    """Yan yana seçenekler (Sesim / Dengeli / Oyun, Yakınlaştır / Vurgula). secili = -1: hiçbiri."""

    secildi = Signal(int)

    def __init__(self, secenekler: list[str], ipuclari: list[str] | None = None, kucuk: bool = False,
                 zemin: str | None = None, ad: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("secimGrubu")
        self._kucuk = kucuk
        yukseklik = 26 if kucuk else 30
        self.setAccessibleName(ad)
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(3, 3, 3, 3)
        kutu.setSpacing(2)
        self.dugmeler: list[QPushButton] = []
        for i, metin in enumerate(secenekler):
            d = QPushButton(metin)
            d.setCheckable(True)
            d.setCursor(Qt.PointingHandCursor)
            d.setFocusPolicy(Qt.TabFocus)
            d.setMinimumHeight(yukseklik)
            if ipuclari and i < len(ipuclari):
                d.setToolTip(ipuclari[i])
            d.clicked.connect(lambda _=False, n=i: self._tikla(n))
            kutu.addWidget(d, 0 if kucuk else 1)
            self.dugmeler.append(d)
        r = (yukseklik + 6) // 2
        arka = zemin or RENK["zemin"]
        kenar = f"border: 1px solid {beyaz(ALFA['kenarlik'])};" if kucuk else "border: none;"
        self.setStyleSheet(
            f"QFrame#secimGrubu {{ background: {arka}; border-radius: {r}px; {kenar} }}"
            f"QFrame#secimGrubu QPushButton {{ border-radius: {yukseklik // 2}px; min-height: {yukseklik}px;"
            f" padding: 0 12px; color: {RENK['yazi2'] if not kucuk else RENK['dugme']}; font-size: 12px; }}"
            f"QFrame#secimGrubu QPushButton:hover {{ background: {beyaz(ALFA['uzerine'])}; color: {RENK['beyaz']}; }}"
            f"QFrame#secimGrubu QPushButton:checked {{ background: {beyaz(ALFA['seçili'])}; color: {RENK['beyaz']}; }}")
        self.secili = -1

    def _tikla(self, n: int) -> None:
        self.sec(n)
        self.secildi.emit(n)

    def sec(self, n: int) -> None:
        self.secili = n
        for i, d in enumerate(self.dugmeler):
            d.setChecked(i == n)


class TutmaYeri(QWidget):
    """6 noktalı tutma yeri: sürükleyince bulunduğu pencereyi taşır."""

    birakildi = Signal()
    cift_tiklandi = Signal()

    def __init__(self, parent=None, dikey_bosluk: int = 10):
        super().__init__(parent)
        self.setFixedSize(20, 20 + dikey_bosluk)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Taşı")
        self.setAccessibleName("Taşı")
        self._bas: QPoint | None = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(qrenk("nokta"))
        x0 = (self.width() - 9) / 2
        y0 = (self.height() - 15) / 2
        for satir in range(3):
            for sutun in range(2):
                p.drawEllipse(QRectF(x0 + sutun * 6, y0 + satir * 6, 3, 3))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._bas = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._bas is not None:
            self.window().move(e.globalPosition().toPoint() - self._bas)

    def mouseReleaseEvent(self, e):
        if self._bas is not None:
            self._bas = None
            self.setCursor(Qt.OpenHandCursor)
            self.birakildi.emit()

    def mouseDoubleClickEvent(self, e):
        self.cift_tiklandi.emit()


class Nokta(QWidget):
    """Küçük yuvarlak nokta: kayıt sürerken kırmızı, duraklatınca gri."""

    def __init__(self, cap: int = 7, parent=None):
        super().__init__(parent)
        self.setFixedSize(cap, cap)
        self.renk = RENK["nokta"]

    def ayarla(self, renk: str) -> None:
        if renk != self.renk:
            self.renk = renk
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        from PySide6.QtGui import QColor
        p.setBrush(QColor(self.renk))
        p.drawEllipse(QRectF(self.rect()))


def sure_metni(sn: int) -> str:
    sn = max(0, int(sn))
    s, kalan = divmod(sn, 3600)
    d, sn = divmod(kalan, 60)
    return f"{s}:{d:02d}:{sn:02d}" if s else f"{d:02d}:{sn:02d}"


class KayitGrubu(QFrame):
    """Kayıt sürerken: kırmızı nokta + süre, duraklat/devam et, bitir (kare).

    Duraklatınca süre durur, nokta griye döner, düğme ▶ olur.
    """

    duraklat_basildi = Signal()
    bitir_basildi = Signal()

    def __init__(self, dugme_boyu: int = 40, bitir: bool = True, zemin: bool = True, tus_duraklat: str = "",
                 tus_bitir: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("kayitGrubu" if zemin else "")
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(8 if zemin else 2, 0, 4 if zemin else 0, 0)
        kutu.setSpacing(2)
        self.nokta = Nokta(7 if dugme_boyu >= 40 else 6)
        self.sure = QLabel("00:00")
        self.sure.setFont(yazi_tipi(13))
        self.sure.setStyleSheet(f"color: {RENK['yazi']}; padding: 0 6px 0 6px;")
        self.sure.setAccessibleName("Kayıt süresi")
        ic = QHBoxLayout()
        ic.setContentsMargins(4, 0, 0, 0)
        ic.setSpacing(6)
        ic.addWidget(self.nokta, 0, Qt.AlignVCenter)
        ic.addWidget(self.sure, 0, Qt.AlignVCenter)
        kutu.addLayout(ic)
        yaricap = 8 if dugme_boyu >= 40 else None
        self.duraklat = SimgeDugme("duraklat", "Kaydı duraklat", tus_duraklat, dugme_boyu, 12, yaricap=yaricap)
        self.duraklat.clicked.connect(self.duraklat_basildi.emit)
        kutu.addWidget(self.duraklat)
        self.bitir = None
        if bitir:
            self.bitir = SimgeDugme("bitir", "Kaydı bitir", tus_bitir, dugme_boyu, 12, yaricap=yaricap)
            self.bitir.clicked.connect(self.bitir_basildi.emit)
            kutu.addWidget(self.bitir)
        self._durum = None

    def guncelle(self, saniye: int, duraklatildi: bool, tus_duraklat: str = "") -> None:
        self.sure.setText(sure_metni(saniye))
        if self._durum == duraklatildi:
            return
        self._durum = duraklatildi
        self.nokta.ayarla(RENK["nokta"] if duraklatildi else RENK["kayit"])
        self.sure.setStyleSheet(f"color: {RENK['soluk'] if duraklatildi else RENK['yazi']}; padding: 0 6px;")
        if duraklatildi:
            self.duraklat.durum(simge_adi="oynat")
            self.duraklat.ad_ayarla("Kayda devam et", tus_duraklat)
        else:
            self.duraklat.durum(simge_adi="duraklat")
            self.duraklat.ad_ayarla("Kaydı duraklat", tus_duraklat)


class _MenuSatiri(QWidget):
    def __init__(self, baslik: str, aciklama: str, secili: bool):
        super().__init__()
        self.setMinimumHeight(44)
        self.setMinimumWidth(220)
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self.secili = secili
        self.eylem = None
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(10, 4, 10, 4)
        kutu.setSpacing(0)
        b = QLabel(baslik)
        b.setStyleSheet(f"color: {RENK['yazi']};")
        kutu.addWidget(b)
        if aciklama:
            a = QLabel(aciklama)
            a.setStyleSheet(f"color: {RENK['soluk']}; font-size: 11px;")
            kutu.addWidget(a)

    def _menu(self):
        w = self.parentWidget()
        while w is not None and not w.inherits("QMenu"):
            w = w.parentWidget()
        return w

    def event(self, e):
        if e.type() in (e.Type.HoverEnter, e.Type.HoverLeave):
            menu = self._menu()
            if menu is not None and e.type() == e.Type.HoverEnter:
                menu.setActiveAction(self.eylem)
            self.update()
        return super().event(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.eylem is not None and self.rect().contains(e.position().toPoint()):
            menu = self._menu()
            if menu is not None:
                menu.close()
            self.eylem.trigger()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alfa = ALFA["seçili"] if self.secili else 0
        menu = self._menu()
        if self.underMouse() or (menu is not None and menu.activeAction() is self.eylem):
            alfa = max(alfa, ALFA["uzerine"])
        if alfa:
            p.setPen(Qt.NoPen)
            p.setBrush(qrenk("beyaz", alfa))
            p.drawRoundedRect(QRectF(self.rect()), 6, 6)


def menu_ogesi(menu, baslik: str, aciklama: str = "", tetik=None, secili: bool = False):
    """İki satırlı menü öğesi: ad + altında soluk açıklama (Göster ve kaynak ekleme menüleri).

    Fareyle tıklanınca da, klavyede ok + Enter ile de çalışır."""
    eylem = QWidgetAction(menu)
    satir = _MenuSatiri(baslik, aciklama, secili)
    satir.eylem = eylem
    eylem.setDefaultWidget(satir)
    eylem.setText(baslik if not aciklama else f"{baslik}, {aciklama}")
    if tetik is not None:
        eylem.triggered.connect(tetik)
    menu.addAction(eylem)
    menu.hovered.connect(lambda _a: satir.update())
    return eylem
