"""Ana pencere.

Çerçevesiz pencere, kendi başlık çubuğuyla:
  RizeOn · ☰ Gelişmiş · Kayıt klasörü · Son 2 dk'yı kaydet · Mini bar · Ayarlar · _ □ ×

Sade görünüm: önizleme, kontrol barı ve ses mikseri.
Gelişmiş (☰, ilk açılışta açık, sonra hatırlanır): solda Sahneler ve Kaynaklar, sağda mikserin altında anahtarlar.

  orta : "Göster: Ekran 1 ▾" (her monitör, Pencere seç…, Bölge seç…) · sahne adı, çözünürlük, FPS
         16:9 önizleme (kamera fareyle sürüklenir)
         kontrol barı: Mikrofon · Sistem sesi · Kamera | Bölge · Kalem | Kayıt | Panik
  alt  : CPU · GPU · FPS · Çıkış

Pencere daralınca sütunlar alt alta dizilir. Pencere hiçbir durumu kendi tutmaz; her şey
DurumDeposu'ndan okunur, her işlem komut adıyla çalıştırılır (kısayol, mini bar ve tepsi ile aynı yol).
"""

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from core.commands import KomutYoneticisi
from core.hotkeys import tus_metni
from core.state import Durum, DurumDeposu
from ui.bilesenler import HapDugme, KaroDugme, KayitGrubu, SimgeDugme, _Dugme, ipucu, menu_ogesi
from ui.icons import simge_pixmap
from ui.theme import RENK, qrenk, yazi_tipi

log = logging.getLogger(__name__)

SOL_GENISLIK = 230
SAG_GENISLIK = 264
BOSLUK = 16
KENAR = 6            # pencere kenarından boyutlandırma payı (px)
MIN_SADE = (760, 560)
MIN_GELISMIS = (900, 600)


class _DurumKoprusu(QObject):
    """Video/ses iş parçacıklarından gelen durum değişikliklerini Qt ana iş parçacığına taşır."""
    degisti = Signal(object)


def kisalt(metin: str, n: int = 22) -> str:
    return metin if len(metin) <= n else metin[: n - 1] + "…"


# ---------------------------------------------------------------- başlık çubuğu

class PencereDugmesi(_Dugme):
    """Windows başlık düğmesi (46×40): küçült, ekranı kapla / geri yükle, kapat (üzerine gelince kırmızı)."""

    def __init__(self, simge_adi: str, ad: str, kapat: bool = False, parent=None):
        super().__init__(parent)
        self.simge_adi, self.kapat = simge_adi, kapat
        self.setFixedSize(46, 40)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.ArrowCursor)
        self.ad_ayarla(ad)

    def ad_ayarla(self, ad: str) -> None:
        self.setAccessibleName(ad)
        self.setToolTip(ad)

    def paintEvent(self, _):
        p = QPainter(self)
        uzerinde = self._uzerinde or self.isDown()
        if uzerinde:
            p.fillRect(self.rect(), qrenk("kapat") if self.kapat else qrenk("beyaz", 0.07))
        renk = RENK["beyaz"] if uzerinde else RENK["yazi2"]
        pm = simge_pixmap(self.simge_adi, renk, 14, dpr=self.devicePixelRatioF())
        p.drawPixmap(QPoint((self.width() - 14) // 2, (self.height() - 14) // 2), pm)


class BaslikCubugu(QWidget):
    def __init__(self, pencere, parent=None):
        super().__init__(parent)
        self.pencere = pencere
        self.setFixedHeight(40)
        self.setObjectName("baslikCubugu")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet("QWidget#baslikCubugu { border-bottom: 1px solid rgba(255, 255, 255, 15); }")
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(12, 0, 0, 0)
        kutu.setSpacing(4)
        from ui.icons import logo_pixmap
        logo = QLabel()
        dpr = self.devicePixelRatioF() or 1.0
        lp = logo_pixmap(round(18 * dpr))
        lp.setDevicePixelRatio(dpr)
        logo.setPixmap(lp)
        logo.setFixedSize(18, 18)
        kutu.addWidget(logo)
        kutu.addSpacing(4)
        ad = QLabel("RizeOn")
        ad.setStyleSheet(f"color: {RENK['yazi2']}; font-size: 12px;")
        kutu.addWidget(ad)
        kutu.addStretch(1)
        self.gelismis = HapDugme("☰ Gelişmiş", "Sahneler, kaynaklar ve ses anahtarları")
        self.gelismis.setCheckable(True)
        self.gelismis.setAccessibleName("Gelişmiş görünüm")
        self.klasor = HapDugme("Kayıt klasörü",
                               "Kayıtların, son 2 dk kayıtlarının ve ekran görüntülerinin olduğu klasörü açar")
        self.tekrar = HapDugme("Son 2 dk'yı kaydet")
        self.mini = HapDugme("Mini bar", "Ana pencereyi gizle, her zaman üstte duran küçük bara geç")
        self.ayarlar = SimgeDugme("ayarlar", "Ayarlar", boyut=28, simge_boyu=16)
        for d in (self.gelismis, self.klasor, self.tekrar, self.mini):
            kutu.addWidget(d)
        kutu.addSpacing(2)
        kutu.addWidget(self.ayarlar)
        kutu.addSpacing(8)
        self.kucult = PencereDugmesi("kucult", "Simge durumuna küçült")
        self.buyut = PencereDugmesi("buyut", "Ekranı kapla")
        self.kapat = PencereDugmesi("kapat", "Kapat", kapat=True)
        self.kucult.clicked.connect(pencere.showMinimized)
        self.buyut.clicked.connect(self.buyut_kucult)
        self.kapat.clicked.connect(pencere.close)
        for d in (self.kucult, self.buyut, self.kapat):
            kutu.addWidget(d)

    def buyut_kucult(self) -> None:
        if self.pencere.isMaximized():
            self.pencere.showNormal()
        else:
            self.pencere.showMaximized()

    def durum_degisti(self) -> None:
        buyuk = self.pencere.isMaximized()
        self.buyut.simge_adi = "geri_yukle" if buyuk else "buyut"
        self.buyut.ad_ayarla("Önceki boyuta getir" if buyuk else "Ekranı kapla")
        self.buyut.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            pencere = self.pencere.windowHandle()
            if pencere is not None and pencere.startSystemMove():
                return
            self._bas = e.globalPosition().toPoint() - self.pencere.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        # startSystemMove desteklenmezse (bazı platformlar) elle taşı
        bas = getattr(self, "_bas", None)
        if bas is not None and e.buttons() & Qt.LeftButton:
            self.pencere.move(e.globalPosition().toPoint() - bas)

    def mouseReleaseEvent(self, e):
        self._bas = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.buyut_kucult()


class KenarBoyutlandirici(QObject):
    """Çerçevesiz pencereyi kenarlarından boyutlandırma (Windows'un kendi boyutlandırmasıyla)."""

    def __init__(self, pencere):
        super().__init__(pencere)
        self.pencere = pencere
        self._imlec = None

    def _kenarlar(self, nokta: QPoint):
        p = self.pencere
        if p.isMaximized() or p.isFullScreen():
            return Qt.Edges()
        r = p.rect()
        kenar = Qt.Edges()
        if nokta.x() <= KENAR:
            kenar |= Qt.LeftEdge
        elif nokta.x() >= r.width() - KENAR:
            kenar |= Qt.RightEdge
        if nokta.y() <= KENAR:
            kenar |= Qt.TopEdge
        elif nokta.y() >= r.height() - KENAR:
            kenar |= Qt.BottomEdge
        return kenar

    @staticmethod
    def _sekil(kenar):
        if kenar in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        if kenar in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            return Qt.SizeBDiagCursor
        if kenar & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        return Qt.SizeVerCursor

    def _imleci_ayarla(self, sekil) -> None:
        if sekil == self._imlec:
            return
        if self._imlec is not None:
            QApplication.restoreOverrideCursor()
        if sekil is not None:
            QApplication.setOverrideCursor(QCursor(sekil))
        self._imlec = sekil

    def eventFilter(self, nesne, olay):
        tur = olay.type()
        if tur not in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.Leave):
            return False
        if not isinstance(nesne, QWidget) or nesne.window() is not self.pencere:
            return False
        if tur == QEvent.Leave and nesne is self.pencere:
            self._imleci_ayarla(None)
            return False
        if tur == QEvent.Leave:
            return False
        nokta = self.pencere.mapFromGlobal(olay.globalPosition().toPoint())
        kenar = self._kenarlar(nokta)
        if tur == QEvent.MouseMove and not olay.buttons():
            self._imleci_ayarla(self._sekil(kenar) if kenar else None)
        elif tur == QEvent.MouseButtonPress and kenar and olay.button() == Qt.LeftButton:
            pencere = self.pencere.windowHandle()
            if pencere is not None and pencere.startSystemResize(kenar):
                self._imleci_ayarla(None)
                return True
        return False


# ---------------------------------------------------------------- önizleme

class Onizleme(QWidget):
    """Karşı tarafın gördüğü 16:9 görüntü. Köşedeki kamera(lar) fareyle sürüklenip taşınır."""

    def __init__(self, hat, ayarlar, parent=None):
        super().__init__(parent)
        self.hat, self.ayarlar = hat, ayarlar
        self.setMouseTracking(True)
        self.setMinimumSize(320, 180)
        self.setAccessibleName("Önizleme: karşı tarafın gördüğü")
        self._resim: QImage | None = None
        self._surukle = None   # (kaynak kimliği ya da None=ana kamera, fark x, fark y)

    def kareyi_al(self) -> None:
        kare = self.hat.son_kare()
        h, w = kare.shape[:2]
        self._resim = QImage(kare.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.update()

    def cerceve(self) -> QRectF:
        """16:9 görüntünün widget içindeki yeri (tamamı görünür, ortalanmış)."""
        W, H = self.width(), self.height()
        oran = self.hat.genislik / max(1, self.hat.yukseklik)
        w = min(W, H * oran)
        h = w / oran
        return QRectF((W - w) / 2, (H - h) / 2, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.cerceve()
        yol = QPainterPath()
        yol.addRoundedRect(r, 8, 8)
        p.setClipPath(yol)
        p.fillRect(r, qrenk("onizleme"))
        if self._resim is not None and not self._resim.isNull():
            p.drawImage(r, self._resim)

    # ---- kamerayı sürükleme

    def _cikis_noktasi(self, nokta):
        r = self.cerceve()
        x, y = (nokta.x() - r.x()) / r.width(), (nokta.y() - r.y()) / r.height()
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return None
        return x * self.hat.genislik, y * self.hat.yukseklik

    def _kutular(self):
        """Görünen köşe kameraları, öndeki önce: [(kimlik ya da None, (x, y, w, h))]."""
        from scenes.scene_manager import ek_kamera_yerlesimi
        if self.hat.panik or not self.hat.kamera_istegi:
            return []
        W, H = self.hat.genislik, self.hat.yukseklik
        sonuc = []
        for k in self.hat.sahneler.aktif.kaynaklar:
            if k.tur != "kamera" or not k.gorunur or k.ayar.get("yer") == "tam":
                continue
            if k.ana:
                sonuc.append((None, self.hat.kamera_yerlesimi.dikdortgen(W, H)))
            else:
                sonuc.append((k.kimlik, ek_kamera_yerlesimi(k).dikdortgen(W, H)))
        return sonuc

    def _ustundeki(self, nokta):
        p = self._cikis_noktasi(nokta)
        if p is None:
            return None
        for kimlik, (x, y, w, h) in self._kutular():
            if x <= p[0] <= x + w and y <= p[1] <= y + h:
                return kimlik, (x, y, w, h), p
        return None

    def mousePressEvent(self, e):
        bulunan = self._ustundeki(e.position()) if e.button() == Qt.LeftButton else None
        if bulunan is None:
            return super().mousePressEvent(e)
        kimlik, (x, y, w, h), p = bulunan
        self._surukle = (kimlik, p[0] - (x + w / 2), p[1] - (y + h / 2), w, h)
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._surukle is None:
            self.setCursor(Qt.OpenHandCursor if self._ustundeki(e.position()) else Qt.ArrowCursor)
            self.setToolTip("Kamerayı fareyle sürükleyip taşı" if self._ustundeki(e.position()) else "")
            return
        p = self._cikis_noktasi(e.position())
        if p is None:
            return
        kimlik, dx, dy, w, h = self._surukle
        W, H = self.hat.genislik, self.hat.yukseklik
        cx = min(max(p[0] - dx, w / 2), W - w / 2) / W
        cy = min(max(p[1] - dy, h / 2), H - h / 2) / H
        if kimlik is None:
            from dataclasses import replace
            self.hat.kamera_yerlesimi = replace(self.hat.kamera_yerlesimi, konum=(cx, cy))
        else:
            k = self.hat.sahneler.aktif.kaynak(kimlik)
            if k is not None:
                k.ayar["position"] = [round(cx, 4), round(cy, 4)]   # kaydı bırakınca

    def mouseReleaseEvent(self, e):
        if self._surukle is None:
            return super().mouseReleaseEvent(e)
        kimlik = self._surukle[0]
        self._surukle = None
        self.setCursor(Qt.OpenHandCursor)
        if kimlik is None:
            konum = self.hat.kamera_yerlesimi.konum
            if self.ayarlar is not None and konum is not None:
                self.ayarlar.ayarla("camera.position", [round(konum[0], 4), round(konum[1], 4)])
        else:
            k = self.hat.sahneler.aktif.kaynak(kimlik)
            if k is not None:
                self.hat.sahneler.kaynak_ayarla(kimlik, position=k.ayar.get("position"))


# ---------------------------------------------------------------- kontrol barı

def _ayrac() -> QFrame:
    a = QFrame(objectName="ayrac")
    a.setFixedWidth(1)
    a.setContentsMargins(0, 0, 0, 0)
    return a


class KontrolBari(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kontrolBari")
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(6, 6, 6, 6)
        kutu.setSpacing(4)
        kutu.addStretch(1)
        self.mikrofon = KaroDugme("mikrofon", "Mikrofon")
        self.sistem = KaroDugme("ses", "Sistem sesi")
        self.kamera = KaroDugme("kamera", "Kamera")
        self.bolge = KaroDugme("bolge", "Bölge")
        self.kalem = KaroDugme("kalem", "Kalem")
        self.kayit = KaroDugme("kayit", "Kayıt")
        self.kayit_grubu = KayitGrubu()
        self.kayit_grubu.setFixedHeight(60)
        self.panik = KaroDugme(None, "Panik")
        self.panik.setFont(self.panik.font())

        def ayrac():
            a = _ayrac()
            sarici = QVBoxLayout()
            sarici.setContentsMargins(4, 10, 4, 10)
            sarici.addWidget(a)
            return sarici

        for w in (self.mikrofon, self.sistem, self.kamera):
            kutu.addWidget(w)
        kutu.addLayout(ayrac())
        kutu.addWidget(self.bolge)
        kutu.addWidget(self.kalem)
        kutu.addLayout(ayrac())
        kutu.addWidget(self.kayit)
        kutu.addWidget(self.kayit_grubu)
        kutu.addLayout(ayrac())
        kutu.addWidget(self.panik)
        kutu.addStretch(1)
        # En geniş hâli (kayıt sürerken) sabit ölçü olsun: kayıt başlayınca sütunlar yer değiştirmesin
        self.en_genis = self.minimumSizeHint().width() - self.kayit.sizeHint().width() - kutu.spacing()
        self.kayit_grubu.hide()


class GosterDugmesi(_Dugme):
    """'Göster  Ekran 1 ⌄' (çerçeveli hap; 'Göster' ikincil gri)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("Göster: neyin paylaşılacağını seç")
        self.secili = ""
        self.setFixedHeight(32)
        self.ayarla("Ekran 1")

    def ayarla(self, metin: str) -> None:
        if metin == self.secili:
            return
        self.secili = metin
        self.setAccessibleName(f"Göster: {metin}")
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(yazi_tipi(13))
        self.setFixedWidth(12 + fm.horizontalAdvance("Göster") + 8 + fm.horizontalAdvance(metin) + 8 + 14 + 12)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(qrenk("beyaz", 0.08))
        p.setBrush(qrenk("panel"))
        p.drawRoundedRect(r, 16, 16)
        self._zemin(p, QRectF(self.rect()), 16)
        p.setFont(yazi_tipi(13))
        fm = p.fontMetrics()
        x = 12
        p.setPen(qrenk("yazi2"))
        p.drawText(QRectF(x, 0, 200, self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Göster")
        x += fm.horizontalAdvance("Göster") + 8
        p.setPen(qrenk("yazi"))
        p.drawText(QRectF(x, 0, self.width() - x, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.secili)
        pm = simge_pixmap("asagi", RENK["yazi2"], 14, dpr=self.devicePixelRatioF())
        p.drawPixmap(QPoint(self.width() - 26, (self.height() - 14) // 2), pm)


class OrtaSutun(QWidget):
    """Göster satırı, önizleme ve kontrol barı. Önizleme 16:9 kalır, bar hemen altında durur."""

    def __init__(self, goster_satiri: QWidget, onizleme: Onizleme, kontrol: KontrolBari, parent=None):
        super().__init__(parent)
        self.goster_satiri, self.onizleme, self.kontrol = goster_satiri, onizleme, kontrol
        for w in (goster_satiri, onizleme, kontrol):
            w.setParent(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _kh(self) -> int:
        return self.kontrol.sizeHint().height()

    def kontrol_genisligi(self) -> int:
        return self.kontrol.en_genis

    def heightForWidth(self, w: int) -> int:
        return 32 + 12 + round(w * 9 / 16) + 12 + self._kh()

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(self.kontrol_genisligi(), 32 + 12 + 180 + 12 + self._kh())

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(760, self.heightForWidth(760))

    def resizeEvent(self, _):
        W, H = self.width(), self.height()
        kh = self._kh()
        self.goster_satiri.setGeometry(0, 0, W, 32)
        bos = max(180, H - 32 - 12 - 12 - kh)
        ph = min(round(W * 9 / 16), bos)
        self.onizleme.setGeometry(0, 44, W, ph)
        y = 44 + round(self.onizleme.cerceve().height()) + 12
        self.kontrol.setGeometry(0, y, W, kh)


# ---------------------------------------------------------------- pencere

class AnaPencere(QMainWindow):
    def __init__(self, depo: DurumDeposu, komutlar: KomutYoneticisi, hat, onizleme_fps: int = 15,
                 ses=None, mikser=None, ayarlar=None, gurultu=None):
        super().__init__()
        self.depo, self.komutlar, self.hat, self.ayarlar = depo, komutlar, hat, ayarlar
        self.tepsiye_kucul = False       # UygulamaKabugu ayarlar
        self.tepsiye_kuculdu = None      # X ile tepsiye küçülünce (kabuk karar verir: tepsi ya da mini bar)
        self.uygulamadan_cik = None
        self.mini_moda_gec = None
        self.ayarlari_ac = None          # fn(sekme: str | None)
        self.pencere_sec = None          # fn() -> (hwnd, başlık) | None  (kaynak ekleme)
        self.bolge_sec = None            # fn(geri_cagri(monitor, oran, piksel))
        self.bas_konus_degisti = None    # fn(acik) -> bool
        self.setWindowTitle("RizeOn")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1320, 820)

        kok = QWidget(objectName="kok")
        self.setCentralWidget(kok)
        dikey = QVBoxLayout(kok)
        dikey.setContentsMargins(0, 0, 0, 0)
        dikey.setSpacing(0)

        # ---- başlık
        self.baslik = BaslikCubugu(self)
        self.gelismis_dugmesi = self.baslik.gelismis
        self.baslik.gelismis.toggled.connect(self._gelismis_goster)
        self.baslik.klasor.clicked.connect(lambda: self._calistir("kayit.klasor") if komutlar.var_mi("kayit.klasor")
                                           else self.kayit_klasorunu_ac())
        self.baslik.tekrar.clicked.connect(lambda: self._calistir("anlik_kayit.kaydet"))
        self.baslik.mini.clicked.connect(lambda: self.mini_moda_gec and self.mini_moda_gec())
        self.baslik.ayarlar.clicked.connect(lambda: self.ayarlari_ac and self.ayarlari_ac(None))
        dikey.addWidget(self.baslik)

        # ---- sol: sahneler + kaynaklar
        from ui.sahne_panelleri import KaynaklarPaneli, SahnelerPaneli
        self.sahneler_paneli = SahnelerPaneli(hat, komutlar, self._tus)
        self.kaynaklar_paneli = KaynaklarPaneli(
            hat, ayarlar, lambda: self.pencere_sec() if self.pencere_sec else None,
            lambda geri: self.bolge_sec(geri) if self.bolge_sec else None)
        self.sol_panel = QWidget()
        sol = QVBoxLayout(self.sol_panel)
        sol.setContentsMargins(0, 0, 0, 0)
        sol.setSpacing(12)
        sol.addWidget(self.sahneler_paneli)
        sol.addWidget(self.kaynaklar_paneli)
        sol.addStretch(1)

        # ---- orta
        self.goster = GosterDugmesi()
        self.goster.clicked.connect(self._goster_menusu)
        self.sahne_bilgisi = QLabel(objectName="soluk")
        self.sahne_bilgisi.setStyleSheet(f"color: {RENK['soluk']}; font-size: 12px;")
        goster_satiri = QWidget()
        gs = QHBoxLayout(goster_satiri)
        gs.setContentsMargins(0, 0, 0, 0)
        gs.addWidget(self.goster)
        gs.addStretch(1)
        gs.addWidget(self.sahne_bilgisi)
        self.onizleme = Onizleme(hat, ayarlar)
        self.kontrol = KontrolBari()
        self.orta = OrtaSutun(goster_satiri, self.onizleme, self.kontrol)
        self._kontrol_dugmeleri()

        # ---- sağ: mikser + anahtarlar
        self.sag_panel = QWidget()
        sag = QVBoxLayout(self.sag_panel)
        sag.setContentsMargins(0, 0, 0, 0)
        sag.setSpacing(12)
        self.mikser_paneli = None
        self.anahtar_paneli = None
        if ses is not None and mikser is not None:
            from ui.mixer_panel import AnahtarPaneli, MikserPaneli
            self.mikser_paneli = MikserPaneli(depo, komutlar, ses, mikser, ayarlar,
                                              duzenle=lambda: self.ayarlari_ac and self.ayarlari_ac("ses"))
            self.anahtar_paneli = AnahtarPaneli(
                ayarlar, mikser, hat, gurultu,
                lambda acik: self.bas_konus_degisti(acik) if self.bas_konus_degisti else True)
            sag.addWidget(self.mikser_paneli)
            sag.addWidget(self.anahtar_paneli)
        sag.addStretch(1)

        # ---- gövde (daralınca alt alta dizilir; sığmazsa kaydırılır)
        self.govde = QWidget()
        self.izgara = QGridLayout(self.govde)
        self.izgara.setContentsMargins(BOSLUK, BOSLUK, BOSLUK, BOSLUK)
        self.izgara.setSpacing(BOSLUK)
        self.kaydirma = QScrollArea()
        self.kaydirma.setWidgetResizable(True)
        self.kaydirma.setFrameShape(QFrame.NoFrame)
        self.kaydirma.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.kaydirma.setWidget(self.govde)
        self.kaydirma.viewport().setAutoFillBackground(False)
        self.govde.setAutoFillBackground(False)
        dikey.addWidget(self.kaydirma, 1)
        self._duzen = None

        # ---- alt bilgi
        self.alt_bilgi = QLabel()
        self.alt_bilgi.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.alt_bilgi.setObjectName("altBilgi")
        self.alt_bilgi.setStyleSheet(f"QLabel#altBilgi {{ color: {RENK['soluk']}; font-size: 11px; padding: 8px 4px; }}")
        self.alt_bilgi.setAccessibleName("İşlemci, ekran kartı ve kare hızı")
        # Çıkış (2.0.1'de Ayarlar'dan buraya taşındı): sakin köşede, basınca onay sorar
        self.cikis_dugmesi = HapDugme("Çıkış", "RizeOn'u tamamen kapat (tepside de kalmaz)")
        self.cikis_dugmesi.setAccessibleName("RizeOn'dan çık")
        self.cikis_dugmesi.clicked.connect(self._cikis_istendi)
        alt = QWidget(objectName="altSatir")
        alt.setAttribute(Qt.WA_StyledBackground)
        alt.setStyleSheet("QWidget#altSatir { border-top: 1px solid rgba(255, 255, 255, 15); }")
        alt_kutu = QHBoxLayout(alt)
        alt_kutu.setContentsMargins(12, 0, 12, 0)
        alt_kutu.setSpacing(8)
        alt_kutu.addWidget(self.alt_bilgi, 1)
        alt_kutu.addWidget(self.cikis_dugmesi)
        dikey.addWidget(alt)
        from core.sistem_olcer import SistemOlcer
        self.olcer = SistemOlcer()
        self.bilgi = self.alt_bilgi   # eski ad (testler)

        self._boyutlandirici = KenarBoyutlandirici(self)
        QApplication.instance().installEventFilter(self._boyutlandirici)

        # İlk açılışta (ayar hiç kaydedilmemişken) Gelişmiş açık gelir; sonra son seçim hatırlanır
        gelismis = bool(ayarlar.al("ui.advanced", True)) if ayarlar is not None else False
        self.baslik.gelismis.setChecked(gelismis)
        self._gelismis_goster(gelismis, kaydet=False)

        # ---- durum bağlantısı (iş parçacığı güvenli)
        self._kopru = _DurumKoprusu()
        self._kopru.degisti.connect(self._durumu_goster)
        depo.dinle(lambda eski, yeni: self._kopru.degisti.emit(yeni))
        self._durumu_goster(depo.durum)

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._onizlemeyi_guncelle)
        self._zamanlayici.start(max(1, 1000 // max(1, onizleme_fps)))
        self._olcum = QTimer(self)
        self._olcum.timeout.connect(self._alt_bilgiyi_yaz)
        self._olcum.start(1000)
        self._alt_bilgiyi_yaz()

    # ---------------- yardımcılar

    def _tus(self, komut: str) -> str:
        if self.ayarlar is None:
            return ""
        tus = (self.ayarlar.al("hotkeys", {}) or {}).get(komut, "")
        return tus_metni(tus) if tus else ""

    def _kontrol_dugmeleri(self) -> None:
        k = self.kontrol
        self.kontroller = {
            "ses.mikrofon": k.mikrofon, "ses.sistem": k.sistem, "kamera.ac_kapat": k.kamera,
            "bolge.sec": k.bolge, "kalem.ac_kapat": k.kalem, "kayit.ac_kapat": k.kayit, "panik": k.panik,
        }
        for komut, d in self.kontroller.items():
            d.clicked.connect(lambda _=False, c=komut: self._calistir(c))
        k.kayit_grubu.duraklat_basildi.connect(lambda: self._calistir("kayit.duraklat"))
        k.kayit_grubu.bitir_basildi.connect(lambda: self._calistir("kayit.ac_kapat"))
        self._ipuclarini_yaz()

    def _ipuclarini_yaz(self) -> None:
        """Kısayollar sadece ipuçlarında yazar (ayarlar değişince yeniden çağrılır)."""
        k = self.kontrol
        k.bolge.setToolTip(ipucu("Bölge: ekranın bir kısmını yakınlaştır ya da vurgula", self._tus("bolge.sec")))
        k.kalem.setToolTip(ipucu("Kalem: ekranın üstüne çiz", self._tus("kalem.ac_kapat")))
        k.kayit.setToolTip(ipucu("Kaydı başlat", self._tus("kayit.ac_kapat")))
        k.panik.setToolTip(ipucu("Panik: tüm çıkışı anında durdurur, bekleme ekranına geçer", self._tus("panik")))
        k.kayit_grubu.duraklat.ad_ayarla(k.kayit_grubu.duraklat.accessibleName(), self._tus("kayit.duraklat"))
        k.kayit_grubu.bitir.ad_ayarla("Kaydı bitir", self._tus("kayit.ac_kapat"))
        from core.anlik_tekrar import sure_etiketi
        etiket = sure_etiketi(self.ayarlar.al("record.replay_seconds", 120) if self.ayarlar is not None else 120)
        self.baslik.tekrar.setText(f"{etiket}'yı kaydet" if etiket.endswith("dk") else f"{etiket}'yi kaydet")
        self.baslik.tekrar.setVisible(self.ayarlar is None or bool(self.ayarlar.al("record.replay", True)))
        self.baslik.tekrar.setToolTip(ipucu(f"{etiket} MP4 olarak kaydedilir (bellekte tutulur, diske sürekli "
                                            "yazılmaz)", self._tus("anlik_kayit.kaydet")))
        self._ipucu_durumu = None

    def ayarlar_degisti(self) -> None:
        """Ayarlar penceresi kapanınca: kısayol ipuçları, sahne kısayolları, mikser, anahtarlar."""
        self._ipuclarini_yaz()
        self.sahneler_paneli.yenile(zorla=True)
        self.kaynaklar_paneli.yenile(zorla=True)
        if self.mikser_paneli is not None:
            self.mikser_paneli.modlari_yenile()
            self.mikser_paneli.haric_yenile()
        if self.anahtar_paneli is not None:
            self.anahtar_paneli.yenile()
        self._durumu_goster(self.depo.durum)

    def _gelismis_goster(self, acik: bool, kaydet: bool = True) -> None:
        self.sol_panel.setVisible(acik)
        if self.anahtar_paneli is not None:
            self.anahtar_paneli.setVisible(acik)
        self.setMinimumSize(*(MIN_GELISMIS if acik else MIN_SADE))
        self._duzen = None
        self._yerlesimi_guncelle()
        if kaydet and self.ayarlar is not None:
            self.ayarlar.ayarla("ui.advanced", acik)

    def _yerlesimi_guncelle(self) -> None:
        """Geniş pencerede yan yana sütunlar, dar pencerede alt alta."""
        gelismis = self.sol_panel.isVisibleTo(self) if self.isVisible() else self.baslik.gelismis.isChecked()
        W = self.kaydirma.viewport().width() or self.width()
        ic = W - 2 * BOSLUK
        orta_min = self.orta.kontrol_genisligi()
        sag_var = self.mikser_paneli is not None
        gerekli = orta_min + (SOL_GENISLIK + BOSLUK if gelismis else 0) + (SAG_GENISLIK + BOSLUK if sag_var else 0)
        if ic >= gerekli:
            duzen = "genis"
        elif ic >= SOL_GENISLIK + BOSLUK + SAG_GENISLIK:
            duzen = "dar"
        else:
            duzen = "cok_dar"
        if duzen != self._duzen:
            self._duzen = duzen
            g = self.izgara
            for w in (self.sol_panel, self.orta, self.sag_panel):
                g.removeWidget(w)
            for i in range(4):
                g.setColumnStretch(i, 0)
                g.setRowStretch(i, 0)
            self.sol_panel.setFixedWidth(SOL_GENISLIK) if duzen == "genis" else self.sol_panel.setMinimumWidth(0)
            if duzen != "genis":
                self.sol_panel.setMaximumWidth(16777215)
            if duzen == "genis":
                self.sag_panel.setFixedWidth(SAG_GENISLIK)
                g.addWidget(self.sol_panel, 0, 0, Qt.AlignTop)
                g.addWidget(self.orta, 0, 1)
                g.addWidget(self.sag_panel, 0, 2, Qt.AlignTop)
                g.setColumnStretch(1, 1)
                g.setRowStretch(0, 1)
            elif duzen == "dar":
                self.sag_panel.setMinimumWidth(0)
                self.sag_panel.setMaximumWidth(16777215)
                g.addWidget(self.orta, 0, 0, 1, 2)
                if gelismis:
                    g.addWidget(self.sol_panel, 1, 0, Qt.AlignTop)
                    g.addWidget(self.sag_panel, 1, 1, Qt.AlignTop)
                    g.setColumnStretch(0, 1)
                    g.setColumnStretch(1, 1)
                else:
                    g.addWidget(self.sol_panel, 1, 0, Qt.AlignTop)
                    g.addWidget(self.sag_panel, 1, 1, Qt.AlignTop)
                    g.setColumnStretch(1, 1)
            else:
                self.sag_panel.setMinimumWidth(0)
                self.sag_panel.setMaximumWidth(16777215)
                g.addWidget(self.orta, 0, 0)
                g.addWidget(self.sol_panel, 1, 0)
                g.addWidget(self.sag_panel, 2, 0)
                g.setColumnStretch(0, 1)
            self.orta.show()
        # dar düzende önizleme genişliğe göre uzar, gövde kaydırılır
        if duzen == "genis":
            self.orta.setMinimumHeight(self.orta.minimumSizeHint().height())
            self.orta.setMinimumWidth(orta_min)
        else:
            self.orta.setMinimumWidth(min(orta_min, ic))
            self.orta.setMinimumHeight(self.orta.heightForWidth(ic))

    def resizeEvent(self, olay):
        super().resizeEvent(olay)
        self._yerlesimi_guncelle()

    # ---------------- Göster menüsü

    def _goster_menusu(self) -> None:
        from capture.screen import monitorleri_listele
        d = self.depo.durum
        menu = QMenu(self)
        menu.setAccessibleName("Gösterilecek kaynak")
        monitor = int(self.ayarlar.al("video.monitor", 0)) if self.ayarlar is not None else 0
        monitorler = monitorleri_listele() or [(0, 0)]
        tum_ekran = d.kaynak_turu == "ekran" and not d.bolge
        for i, (w, h) in enumerate(monitorler):
            aciklama = f"Tüm ekran · {w}×{h}" if w else "Tüm ekran"
            menu_ogesi(menu, f"Ekran {i + 1}", aciklama, lambda _=False, n=i: self._calistir(f"kaynak.monitor:{n}"),
                       secili=tum_ekran and i == monitor)
        menu_ogesi(menu, "Pencere seç…", "Sadece bir uygulama", lambda: self._calistir("kaynak.sec"),
                   secili=d.kaynak_turu == "pencere")
        tus = self._tus("bolge.sec")
        menu_ogesi(menu, "Bölge seç…", "Kutu çiz" + (f" · {tus}" if tus else ""),
                   lambda: self._calistir("bolge.sec"),
                   secili=bool(d.bolge))
        menu.setMinimumWidth(240)
        menu.exec(self.goster.mapToGlobal(QPoint(0, self.goster.height() + 6)))

    def _goster_metni(self, d: Durum) -> str:
        if d.bolge:
            return "Seçili bölge"
        if d.kaynak_turu == "pencere":
            return kisalt(d.kaynak_adi or "Pencere")
        monitor = int(self.ayarlar.al("video.monitor", 0)) if self.ayarlar is not None else 0
        return f"Ekran {monitor + 1}"

    # ---------------- eski uyumluluk

    def kayit_klasorunu_ac(self) -> None:
        from ui.klasor import kayit_klasorunu_ac
        kayit_klasorunu_ac(self.ayarlar)

    def _calistir(self, komut: str) -> None:
        if not self.komutlar.var_mi(komut):
            return
        self.komutlar.calistir(komut)
        self._durumu_goster(self.depo.durum)  # düğme hemen doğru görünsün

    # ---------------- pencere olayları

    def showEvent(self, olay):
        super().showEvent(olay)
        self.hat.onizleme_gorunur = True
        from core.platform_win import koseleri_yuvarla, yakalamadan_gizle
        hwnd = int(self.winId())
        yakalamadan_gizle(hwnd)    # önizleme kendini yakalamasın (sonsuz ayna), karşı tarafa gitmesin
        koseleri_yuvarla(hwnd)     # Windows 11: çerçevesiz pencerenin köşeleri 8 px yuvarlak
        self._duzen = None
        QTimer.singleShot(0, self._yerlesimi_guncelle)

    def hideEvent(self, olay):
        super().hideEvent(olay)
        if not self.isMinimized():
            self.hat.onizleme_gorunur = False   # tepsiye inince kamera boşuna açık kalmasın

    def changeEvent(self, olay):
        super().changeEvent(olay)
        if olay.type() == QEvent.WindowStateChange:
            # Simge durumundayken de kamera açık kalır (pencere hâlâ açık sayılır)
            self.hat.onizleme_gorunur = self.isVisible() or self.isMinimized()
            self.baslik.durum_degisti()

    # ---------------- durum

    def _durumu_goster(self, d: Durum) -> None:
        k = self.kontrol
        k.mikrofon.durum(kapali=d.mikrofon_sessiz, metin="Sessizde" if d.mikrofon_sessiz else "Mikrofon")
        k.mikrofon.setAccessibleName("Mikrofon kapalı, aç" if d.mikrofon_sessiz else "Mikrofon açık, kapat")
        k.sistem.durum(kapali=d.sistem_sessiz)
        k.sistem.setAccessibleName("Sistem sesi kapalı, aç" if d.sistem_sessiz else "Sistem sesi açık, kapat")
        kamera_acik = self.hat.kamera_gorunur_acik
        kamera_sahnede = self.hat.kamera_sahnede
        k.kamera.durum(kapali=not kamera_acik)
        k.kamera.setAccessibleName(("Kamera açık, kapat" if kamera_acik else "Kamera kapalı, aç") if kamera_sahnede
                                   else "Bu sahnede kamera yok")
        ipucu_durumu = (d.mikrofon_sessiz, d.sistem_sessiz, kamera_acik, kamera_sahnede)
        if ipucu_durumu != getattr(self, "_ipucu_durumu", None):
            self._ipucu_durumu = ipucu_durumu
            k.mikrofon.setToolTip(ipucu("Mikrofonu " + ("aç" if d.mikrofon_sessiz else "kapat"), self._tus("ses.mikrofon")))
            k.sistem.setToolTip(ipucu("Sistem sesini " + ("aç" if d.sistem_sessiz else "kapat"), self._tus("ses.sistem")))
            k.kamera.setToolTip(ipucu("Kamerayı " + ("kapat" if kamera_acik else "aç"), self._tus("kamera.ac_kapat"))
                                if kamera_sahnede else "Bu sahnede kamera yok. Kaynaklar'dan Kamera ekleyebilirsin.")
        k.bolge.durum(secili=bool(d.bolge))
        k.kalem.durum(secili=d.kalem_acik)
        k.panik.durum(secili=d.panik, metin="Panik")
        k.panik.setAccessibleName("Panik açık, kapat" if d.panik else "Panik")
        kayitta = d.kayit == "açık"
        k.kayit.setVisible(not kayitta)
        k.kayit_grubu.setVisible(kayitta)
        if kayitta:
            k.kayit_grubu.guncelle(d.kayit_suresi, d.kayit_duraklatildi, self._tus("kayit.duraklat"))
        for komut, dugme in self.kontroller.items():
            dugme.setEnabled(self.komutlar.var_mi(komut) and (komut != "kamera.ac_kapat" or kamera_sahnede))
        self.baslik.tekrar.setEnabled(self.komutlar.var_mi("anlik_kayit.kaydet"))

        self.goster.ayarla(self._goster_metni(d))
        self.sahne_bilgisi.setText(f"{d.sahne_adi or self.hat.sahneler.aktif.ad} · {self.hat.yukseklik}p · "
                                   f"{self.hat.fps} FPS")
        if self.sol_panel.isVisible():
            self.sahneler_paneli.yenile()
            self.kaynaklar_paneli.yenile()
        if self.mikser_paneli is not None:
            self.mikser_paneli.durumu_goster(d)

    def _cikis_istendi(self) -> None:
        if self.uygulamadan_cik is not None:
            self.uygulamadan_cik()
        else:
            self.close()

    def _alt_bilgiyi_yaz(self) -> None:
        self.alt_bilgi.setText(self.olcer.metin(self.depo.durum.fps))

    def _onizlemeyi_guncelle(self) -> None:
        if not self.isVisible() or self.isMinimized():
            return  # görünmüyorken boşuna işlemci harcama
        self.onizleme.kareyi_al()
        if self.sol_panel.isVisible():
            # sahne başka yerden (kısayol) değiştiyse paneller güncellensin
            self.sahneler_paneli.yenile()
            self.kaynaklar_paneli.yenile()

    def closeEvent(self, olay):
        if self.tepsiye_kucul:
            # Kapat düğmesi uygulamayı kapatmaz; saatin yanına (sistem tepsisine) küçülür.
            olay.ignore()
            self.hide()
            if self.tepsiye_kuculdu is not None:
                self.tepsiye_kuculdu()
            return
        self._zamanlayici.stop()
        self._olcum.stop()
        QApplication.instance().removeEventFilter(self._boyutlandirici)
        self.olcer.kapat()
        super().closeEvent(olay)
