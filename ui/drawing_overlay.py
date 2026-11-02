"""Birleşik bölge + kalem katmanı.

Yakalanan monitörün üstüne saydam bir katman açılır. İki hâli var:

  bölge (Bölge düğmesi, Ctrl+Shift+S): ekran kararır, fareyle kutu çizilir. İnce beyaz çerçeve,
      4 yuvarlak tutamak; altında Yakınlaştır / Vurgula ve boyut (ör. 580 × 190). Kutu çizilince
      hemen yayına uygulanır. Enter ya da çift tık: tamam. Esc: vazgeç (önceki hâle döner).
      Bölge açıkken tekrar Ctrl+Shift+S: tam ekrana dön.

  kalem (Kalem düğmesi, Ctrl+Shift+D): üst ortada sürüklenebilir kalem barı: Kalem, Fosforlu,
      Ok, Kare, Yazı, Lazer, Silgi · beyaz/kırmızı/sarı/mavi · ince/orta/kalın · temizle · Bitti.
      Yazı aracında: tıkla yaz (Enter kaydeder; boşken dışarı tık ya da Esc vazgeçer), var olan
      yazıyı tutup sürükleyerek yerini değiştir (Ctrl+Z eski yerine döndürür).
      Altta ipucu satırı. Bölge seçiliyse çerçevesi görünür, tutamaklarından düzenlenebilir.
      Kalem açıkken 1-7 araç, Ctrl+Z geri al, Del hepsini sil, Esc çık (sadece kalem açıkken
      yakalanan "kalem" kısayol grubu; kalem kapalıyken tuşlar normal şekilde uygulamalara gider).

Katman, bar ve ipuçları ekran yakalamaya girmez; karşı taraf çizimleri video hattının çıkış
karesine eklediği hâliyle görür (overlay/drawing.py). Böylece tam ekran oyunda katman
görünmese bile çizimler kayda ve sanal kameraya gider.
"""

import logging

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from core.hotkeys import gruplara_ayir, tus_metni
from core.platform_win import ozel_tam_ekran_mi, yakalamadan_gizle
from overlay.drawing import (FOSFOR_SAYDAMLIK, KALINLIK, KALINLIK_ADLARI, KALINLIK_CARPANI, KALINLIKLAR,
                             RENK_ADLARI, RENKLER, TUR_ADLARI, TURLER, VARSAYILAN_RENK, CizimDeposu)
from ui.bilesenler import HapDugme, SecimGrubu, SimgeDugme, TutmaYeri, _Dugme, ipucu
from ui.region_overlay import KARARTMA, SecimDuzenleyici, ekrani_bul
from ui.theme import ALFA, RENK, beyaz, qrenk, yazi_tipi

log = logging.getLogger(__name__)

SIMGE = {"kalem": "kalem", "fosforlu": "fosforlu", "ok": "ok", "kare": "kare", "yazi": "yazi", "lazer": "lazer",
         "silgi": "silgi"}
IPUCU = {"lazer": "İz bırakmaz, birkaç saniyede kaybolur", "silgi": "Değdiği çizimi siler"}
MODLAR = ("yakinlastir", "vurgula")
TAM_EKRAN_UYARISI = ("Tam ekran oyunda katman görünmez · oyunu kenarlıksız pencere moduna al "
                     "(çizimler yine yayına gider)")


# ---------------------------------------------------------------- kalem barı

class RenkDugmesi(_Dugme):
    def __init__(self, renk: str, ad: str, parent=None):
        super().__init__(parent)
        self.renk, self.secili = renk, False
        self.setFixedSize(28, 36)
        self.setAccessibleName(ad)
        self.setToolTip(ad)
        self._ad = ad

    def sec(self, secili: bool) -> None:
        self.secili = secili
        self.setAccessibleName(self._ad + (", seçili" if secili else ""))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._zemin(p, QRectF(self.rect()), 14)
        m = QPointF(self.width() / 2, self.height() / 2)
        if self.secili:   # seçili: koyu boşluk + açık gri halka
            p.setPen(QPen(qrenk("yazi"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(m, 9.5, 9.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.renk))
        p.drawEllipse(m, 7, 7)


class KalinlikDugmesi(_Dugme):
    CAP = {"ince": 4, "orta": 8, "kalin": 12}

    def __init__(self, kalinlik: str, parent=None):
        super().__init__(parent)
        self.kalinlik, self.secili = kalinlik, False
        self.setFixedSize(28, 36)
        self._ad = KALINLIK_ADLARI[kalinlik]
        self.setToolTip(self._ad)
        self.setAccessibleName(self._ad)

    def sec(self, secili: bool) -> None:
        self.secili = secili
        self.setAccessibleName(self._ad + (", seçili" if secili else ""))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._zemin(p, QRectF(self.rect()), 14, secili=self.secili)
        c = self.CAP[self.kalinlik]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f4f4f5") if self.secili else qrenk("soluk"))
        p.drawEllipse(QPointF(self.width() / 2, self.height() / 2), c / 2, c / 2)


def _cizgi() -> QWidget:
    a = QWidget()
    a.setFixedSize(13, 20)
    a.setObjectName("cubukAyrac")
    a.setStyleSheet(f"QWidget#cubukAyrac {{ border-left: 1px solid {beyaz(ALFA['kenarlik'])}; margin-left: 6px; }}")
    return a


class KalemCubugu(QWidget):
    """Üst ortada yüzen kalem barı (sürüklenebilir)."""

    def __init__(self, ekran, komutlar, tus_al, konum: QPoint | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAccessibleName("Kalem barı")
        kap = QWidget(self, objectName="cubuk")
        kap.setAttribute(Qt.WA_StyledBackground)
        kap.setStyleSheet(f"QWidget#cubuk {{ background: {RENK['yuzen']}; border: 1px solid "
                          f"{beyaz(ALFA['kenarlik'])}; border-radius: 22px; }}")
        kap.setFixedHeight(44)
        satir = QHBoxLayout(kap)
        satir.setContentsMargins(4, 0, 4, 0)
        satir.setSpacing(2)
        self.tutma = TutmaYeri(dikey_bosluk=4)
        satir.addWidget(self.tutma)
        self.arac_dugmeleri: dict[str, SimgeDugme] = {}
        for i, tur in enumerate(TURLER):
            d = SimgeDugme(SIMGE[tur], TUR_ADLARI[tur], tus_al(f"kalem.tur:{i + 1}"))
            if tur in IPUCU:
                d.setToolTip(ipucu(f"{TUR_ADLARI[tur]}: {IPUCU[tur]}", tus_al(f"kalem.tur:{i + 1}")))
            d.clicked.connect(lambda _=False, n=i + 1: komutlar.calistir(f"kalem.tur:{n}"))
            satir.addWidget(d)
            self.arac_dugmeleri[tur] = d
        satir.addWidget(_cizgi())
        self.renk_dugmeleri: list[RenkDugmesi] = []
        for i, (renk, ad) in enumerate(zip(RENKLER, RENK_ADLARI)):
            d = RenkDugmesi(renk, ad)
            d.clicked.connect(lambda _=False, n=i + 1: komutlar.calistir(f"kalem.renk:{n}"))
            satir.addWidget(d)
            self.renk_dugmeleri.append(d)
        satir.addWidget(_cizgi())
        self.kalinlik_dugmeleri: dict[str, KalinlikDugmesi] = {}
        for i, k in enumerate(KALINLIKLAR):
            d = KalinlikDugmesi(k)
            d.clicked.connect(lambda _=False, n=i + 1: komutlar.calistir(f"kalem.kalinlik:{n}"))
            satir.addWidget(d)
            self.kalinlik_dugmeleri[k] = d
        satir.addWidget(_cizgi())
        temizle = SimgeDugme("temizle", "Tüm çizimleri temizle", tus_al("kalem.temizle"))
        temizle.clicked.connect(lambda: komutlar.calistir("kalem.temizle"))
        satir.addWidget(temizle)
        satir.addWidget(_cizgi())
        self.bitti = HapDugme("Bitti", ipucu("Kalemi kapat", "Esc"))
        self.bitti.setFixedHeight(36)
        self.bitti.setStyleSheet("QPushButton { border-radius: 18px; padding: 0 14px; font-size: 13px; }")
        self.bitti.clicked.connect(lambda: komutlar.calistir("kalem.kapat"))
        satir.addWidget(self.bitti)
        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(kap)
        self.adjustSize()
        g = ekran.availableGeometry()
        if konum is not None and g.contains(konum):
            self.move(konum)
        else:
            self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 24)

    def guncelle(self, tur: str, renk: str, kalinlik: str) -> None:
        for t, d in self.arac_dugmeleri.items():
            d.durum(secili=t == tur)
            d.setAccessibleName(TUR_ADLARI[t] + (", seçili" if t == tur else ""))
        for d in self.renk_dugmeleri:
            d.sec(d.renk == renk)
        for k, d in self.kalinlik_dugmeleri.items():
            d.sec(k == kalinlik)

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()


# ---------------------------------------------------------------- katman

class Katman(QWidget):
    def __init__(self, ekran, depo: CizimDeposu, denetci, mod: str):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.ekran, self.depo, self.denetci = ekran, depo, denetci
        self.setGeometry(ekran.geometry())
        self.mod = mod
        self.duzenleyici = SecimDuzenleyici(self, denetci.hat.bolge.bolge if denetci.hat.bolge.aktif else None)
        self._surum = -1
        self._ciziyor = False
        self._fare: QPointF | None = None
        self._yazi_kutusu: QLineEdit | None = None
        self._tasinan = None          # sürüklenen yazı: (şekil, eski yer, tutma farkı)
        self._tikla_kapatti = False   # yazı kutusu katmana tıklanınca kapandı: o tık yeni kutu açmasın

        # Bölgenin altındaki Yakınlaştır / Vurgula + boyut
        self.bolge_bilgisi = QWidget(self)
        kutu = QHBoxLayout(self.bolge_bilgisi)
        kutu.setContentsMargins(0, 0, 0, 0)
        kutu.setSpacing(10)
        self.modlar = SecimGrubu(["Yakınlaştır", "Vurgula"],
                                 ["Seçili bölgeyi büyütüp tüm çıkışı ona ayırır", "Bölge aynı kalır, geri kalanı kararır"],
                                 kucuk=True, zemin=RENK["yuzen"], ad="Bölge modu")
        self.modlar.secildi.connect(lambda n: denetci.bolge_modu(MODLAR[n]))
        self.boyut = QLabel()
        self.boyut.setStyleSheet(f"color: {RENK['dugme']}; font-size: 12px;")
        kutu.addWidget(self.modlar)
        kutu.addWidget(self.boyut)
        self.bolge_bilgisi.hide()

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._gerekirse_ciz)
        self._zamanlayici.start(33)

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.imleci_ayarla()
        self.bilgiyi_yerlestir()

    def mod_degistir(self, mod: str) -> None:
        self.mod = mod
        self.imleci_ayarla()
        self.bilgiyi_yerlestir()
        self.update()

    def imleci_ayarla(self) -> None:
        if self.mod == "bolge":
            self.setCursor(Qt.CrossCursor)
            return
        tur = self.denetci.tur
        self.setCursor(Qt.IBeamCursor if tur == "yazi" else (Qt.BlankCursor if tur in ("lazer", "silgi")
                                                              else Qt.CrossCursor))

    def bilgiyi_yerlestir(self) -> None:
        d = self.duzenleyici
        if not d.var or (self.mod == "kalem" and not self.denetci.hat.bolge.aktif):
            self.bolge_bilgisi.hide()
            return
        mod = self.denetci.hat.bolge.mod or self.denetci.son_bolge_modu
        self.modlar.sec(MODLAR.index(mod) if mod in MODLAR else -1)
        w, h = d.piksel_boyutu(self.ekran.devicePixelRatio())
        self.boyut.setText(f"{w} × {h}")
        self.bolge_bilgisi.adjustSize()
        r = d.secim.normalized()
        y = r.bottom() + 10
        if y + self.bolge_bilgisi.height() > self.height() - 60:
            y = r.top() - self.bolge_bilgisi.height() - 10
        x = min(max(0, r.left()), self.width() - self.bolge_bilgisi.width())
        self.bolge_bilgisi.move(x, max(0, y))
        self.bolge_bilgisi.show()
        self.bolge_bilgisi.raise_()

    def _gerekirse_ciz(self) -> None:
        if self.depo.surum != self._surum or self.denetci.tur in ("lazer", "silgi"):
            self._surum = self.depo.surum
            self.update()

    def _oran(self, p: QPointF) -> tuple[float, float]:
        return p.x() / max(1, self.width()), p.y() / max(1, self.height())

    # ---- fare

    def mousePressEvent(self, e):
        nokta = e.position().toPoint()
        if self.mod == "bolge":
            if e.button() == Qt.RightButton:
                self.denetci.bolge_vazgec()
            elif e.button() == Qt.LeftButton:
                self.duzenleyici.bas(nokta)
                self.bolge_bilgisi.hide()
                self.update()
            return
        if self._yazi_kutusu is not None or self._tikla_kapatti:
            # Açık yazı kutusunun dışına tıklandı: yazılan varsa kaydedilir, boşsa vazgeçilir. Bu tık
            # yeni kutu açmaz, böylece bir şey yazmadan da kutudan kurtulunur.
            self._tikla_kapatti = False
            self._yazi_bitir(True)
            return
        if e.button() == Qt.RightButton:
            self.depo.geri_al()
            return
        if e.button() != Qt.LeftButton:
            return
        # kalemde: bölge varsa tutamaklarından düzenlenir, gerisi çizim
        if self.denetci.hat.bolge.aktif and self.duzenleyici.bas(nokta, yeni_kutu=False, icinden_tasi=False):
            return
        x, y = self._oran(e.position())
        if self.denetci.tur == "yazi":
            yazi = self._yazi_bul(e.position())
            if yazi is not None:
                # var olan yazıyı tutup sürükle
                eski = tuple(yazi.noktalar[0])
                self._tasinan = (yazi, eski, (x - eski[0], y - eski[1]))
                self.setCursor(Qt.ClosedHandCursor)
                return
            self._yazi_baslat(e.position())
            return
        self._ciziyor = True
        self.depo.basla(self.denetci.tur, self.denetci.renk, x, y, self.denetci.carpan)

    def mouseMoveEvent(self, e):
        nokta = e.position().toPoint()
        self._fare = e.position()
        if self.duzenleyici.surukleniyor:
            self.duzenleyici.tasi(nokta)
            self.update()
            return
        if self.mod == "bolge":
            self.setCursor(self.duzenleyici.imlec(nokta) or Qt.CrossCursor)
            return
        if self.denetci.hat.bolge.aktif:
            imlec = self.duzenleyici.imlec(nokta, icinden_tasi=False)
            if imlec is not None:
                self.setCursor(imlec)
            else:
                self.imleci_ayarla()
        x, y = self._oran(e.position())
        if self._tasinan is not None:
            yazi, _, (fx, fy) = self._tasinan
            self.depo.yazi_tasi(yazi, x - fx, y - fy)
            return
        bolge_tutamagi = self.denetci.hat.bolge.aktif and self.duzenleyici.imlec(nokta, icinden_tasi=False)
        if self.denetci.tur == "yazi" and self._yazi_kutusu is None and not bolge_tutamagi:
            self.setCursor(Qt.OpenHandCursor if self._yazi_bul(e.position()) is not None else Qt.IBeamCursor)
        if self._ciziyor:
            self.depo.surukle(x, y)
        elif self.denetci.tur == "lazer":
            self.depo.lazer_noktasi(x, y, self.denetci.renk)

    def mouseReleaseEvent(self, e):
        if self.duzenleyici.birak():
            if self.duzenleyici.var:
                self.denetci.bolge_uygula(self.duzenleyici.oranlar())
            self.bilgiyi_yerlestir()
            self.update()
            return
        if self._tasinan is not None and e.button() == Qt.LeftButton:
            yazi, eski, _ = self._tasinan
            self._tasinan = None
            self.depo.tasima_bitti(yazi, eski)
            self.setCursor(Qt.OpenHandCursor)
            return
        if self._ciziyor and e.button() == Qt.LeftButton:
            self._ciziyor = False
            self.depo.bitir()

    def mouseDoubleClickEvent(self, e):
        if self.mod == "bolge" and self.duzenleyici.var and \
                self.duzenleyici.secim.normalized().contains(e.position().toPoint()):
            self.denetci.bolge_tamam()

    def leaveEvent(self, e):
        self._fare = None
        super().leaveEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            if self._tasinan is not None:
                # sürüklemeyi iptal et, yazı eski yerine dönsün
                yazi, eski, _ = self._tasinan
                self._tasinan = None
                self.depo.yazi_tasi(yazi, *eski)
                self.imleci_ayarla()
            elif self.mod == "bolge":
                self.denetci.bolge_vazgec()
            else:
                self.denetci.kapat()
        elif self.mod == "bolge" and k in (Qt.Key_Return, Qt.Key_Enter):
            self.denetci.bolge_tamam()
        elif self.mod == "bolge" and k == Qt.Key_V and self.duzenleyici.var:
            self.denetci.bolge_modu("vurgula")
        elif self.mod == "bolge" and k == Qt.Key_Z and self.duzenleyici.var:
            self.denetci.bolge_modu("yakinlastir")

    # ---- yazı aracı

    def _yazi_alani(self, s) -> QRectF:
        """Ekrandaki yazının kapladığı dikdörtgen (çizimdeki yazı tipiyle ölçülür)."""
        kalin = max(1.0, s.kalinlik * self.height())
        fm = QFontMetricsF(yazi_tipi(max(8, round(kalin))))
        x, y = s.noktalar[0][0] * self.width(), s.noktalar[0][1] * self.height()
        return QRectF(x, y, fm.horizontalAdvance(s.metin), max(fm.height(), kalin * 1.3))

    def _yazi_bul(self, konum: QPointF):
        """Tıklanan yerdeki en öndeki yazı (yoksa None)."""
        sekiller, _ = self.depo.anlik()
        for s in reversed(sekiller):
            if s.tur == "yazi" and self._yazi_alani(s).adjusted(-6, -4, 6, 4).contains(konum):
                return s
        return None

    def _yazi_baslat(self, konum: QPointF) -> None:
        if self._yazi_kutusu is not None:
            self._yazi_bitir(True)
        boy = max(10, round(KALINLIK["yazi"] * self.denetci.carpan * self.height()))
        kutu = QLineEdit(self)
        f = yazi_tipi(boy)
        kutu.setFont(f)
        kutu.setStyleSheet(f"QLineEdit {{ background: rgba(0, 0, 0, 90); color: {self.denetci.renk};"
                           f" border: 1px dashed {beyaz(0.6)}; border-radius: 0; padding: 0 2px; font-size: {boy}px; }}")
        kutu.setPlaceholderText("Yaz, Enter")
        kutu.setAccessibleName("Ekrana yazılacak yazı")
        kutu.move(int(konum.x()), int(konum.y()))
        kutu.resize(max(260, self.width() // 4), boy + 10)
        kutu.returnPressed.connect(lambda: self._yazi_bitir(True))
        kutu.editingFinished.connect(lambda: self._yazi_bitir(True))
        kutu.installEventFilter(self)
        self._yazi_kutusu = kutu
        self._yazi_konumu = self._oran(konum)
        self.denetci.yazi_moduna_gir()  # 1-7, Del yazıya gitsin diye kalem kısayollarını bırak
        kutu.show()
        kutu.setFocus()

    def eventFilter(self, nesne, olay):
        if nesne is self._yazi_kutusu and olay.type() == olay.Type.KeyPress and olay.key() == Qt.Key_Escape:
            self._yazi_bitir(False)
            return True
        if nesne is self._yazi_kutusu and olay.type() == olay.Type.FocusOut and \
                olay.reason() == Qt.MouseFocusReason:
            # Odak, katmana yapılan tıkla gitti; kutu editingFinished ile kapanır, ardından gelen fare
            # basışı yeni kutu açmasın. Bayrak bu olay turunun sonunda kendiliğinden düşer.
            self._tikla_kapatti = True
            QTimer.singleShot(0, self._tik_bayragini_dusur)
        return super().eventFilter(nesne, olay)

    def _tik_bayragini_dusur(self) -> None:
        self._tikla_kapatti = False

    def _yazi_bitir(self, kaydet: bool) -> None:
        kutu = self._yazi_kutusu
        if kutu is None:
            return
        self._yazi_kutusu = None
        if kaydet and kutu.text().strip():
            x, y = self._yazi_konumu
            self.depo.yazi_ekle(self.denetci.renk, x, y, kutu.text(), self.denetci.carpan)
        kutu.deleteLater()
        self.denetci.yazi_modundan_cik()
        self.setFocus()

    # ---- çizim

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Neredeyse saydam zemin: Windows'ta tamamen saydam piksel tıklamayı alttaki pencereye geçirir.
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        bolge_var = self.denetci.hat.bolge.aktif or self.duzenleyici.surukleniyor
        if self.mod == "bolge":
            self.duzenleyici.ciz(p, KARARTMA)
        elif bolge_var:
            self.duzenleyici.ciz(p, QColor(9, 9, 11, 70))
        self._cizimler(p)
        if self.mod == "kalem" and self.denetci.tur == "silgi" and self._fare is not None:
            r = CizimDeposu.SILGI_YARICAPI * self.height()
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawEllipse(self._fare, r, r)
        p.setFont(yazi_tipi(12))
        p.setPen(qrenk("dugme"))
        p.drawText(QRectF(0, self.height() - 24 - 18, self.width(), 18), Qt.AlignCenter, self.denetci.ipucu_satiri())

    def _cizimler(self, p: QPainter) -> None:
        W, H = self.width(), self.height()
        sekiller, lazer = self.depo.anlik()

        def nokta(n):
            return QPointF(n[0] * W, n[1] * H)

        for s in sekiller:
            kalin = max(1.0, s.kalinlik * H)
            renk = QColor(s.renk)
            if s.tur in ("kalem", "fosforlu"):
                if s.tur == "fosforlu":
                    renk.setAlphaF(FOSFOR_SAYDAMLIK)
                p.setPen(QPen(renk, kalin, Qt.SolidLine, Qt.RoundCap if s.tur == "kalem" else Qt.FlatCap,
                              Qt.RoundJoin))
                if len(s.noktalar) == 1:
                    p.drawPoint(nokta(s.noktalar[0]))
                else:
                    yol = QPainterPath(nokta(s.noktalar[0]))
                    for n in s.noktalar[1:]:
                        yol.lineTo(nokta(n))
                    p.setBrush(Qt.NoBrush)
                    p.drawPath(yol)
            elif s.tur == "ok":
                a, b = nokta(s.noktalar[0]), nokta(s.noktalar[1])
                p.setPen(QPen(renk, kalin, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(a, b)
                d = b - a
                uz = max(1.0, (d.x() ** 2 + d.y() ** 2) ** 0.5)
                ux, uy = d.x() / uz, d.y() / uz
                boy = min(uz * 0.4, kalin * 5)
                sol = QPointF(b.x() - ux * boy - uy * boy * 0.5, b.y() - uy * boy + ux * boy * 0.5)
                sag = QPointF(b.x() - ux * boy + uy * boy * 0.5, b.y() - uy * boy - ux * boy * 0.5)
                p.setBrush(renk)
                p.drawPolygon(QPolygonF([b, sol, sag]))
            elif s.tur == "kare":
                p.setPen(QPen(renk, kalin))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(nokta(s.noktalar[0]), nokta(s.noktalar[1])).normalized())
            elif s.tur == "yazi":
                p.setFont(yazi_tipi(max(8, round(kalin))))
                p.setPen(renk)
                nk = nokta(s.noktalar[0])
                p.drawText(QRectF(nk.x(), nk.y(), W, kalin * 1.6), Qt.AlignLeft | Qt.AlignTop, s.metin)

        if lazer:
            renk = QColor(self.depo.lazer_rengi)
            kalin = max(2.0, KALINLIK["lazer"] * H)
            for i in range(1, len(lazer)):
                canlilik = 1.0 - lazer[i][2]
                if canlilik <= 0:
                    continue
                renk.setAlphaF(max(0.0, min(1.0, canlilik)))
                p.setPen(QPen(renk, kalin * canlilik, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(nokta(lazer[i - 1]), nokta(lazer[i]))
            if lazer[-1][2] < 0.3:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("white"))
                p.drawEllipse(nokta(lazer[-1]), kalin + 3, kalin + 3)
                p.setBrush(QColor(self.depo.lazer_rengi))
                p.drawEllipse(nokta(lazer[-1]), kalin + 1, kalin + 1)


# ---------------------------------------------------------------- denetleyici

class KatmanDenetleyici:
    """Kalem ve bölge komutlarını kaydeder; katmanı, kalem barını ve yakınlaştırma izini yönetir."""

    def __init__(self, komutlar, depo, hat, cizimler: CizimDeposu, kisayollar, ayarlar, bildir=None):
        self.komutlar, self.depo, self.hat, self.cizimler = komutlar, depo, hat, cizimler
        self.kisayollar, self.ayarlar = kisayollar, ayarlar
        self.bildir = bildir or (lambda metin: None)
        self.tur = "kalem"
        self.renk = RENKLER[VARSAYILAN_RENK]
        self.kalinlik = "orta"
        self.katman: Katman | None = None
        self.cubuk: KalemCubugu | None = None
        self._cubuk_konumu: QPoint | None = None
        self._iz = None
        self._onceki_bolge = None     # bölge düzenlemesi başlarken (bölge, mod) — Esc ile geri dönülür
        self._bolgeden_kaleme = False
        komutlar.kaydet("kalem.ac_kapat", "Kalemi aç/kapat", self._ac_kapat)
        komutlar.kaydet("kalem.kapat", "Kalemden / bölge seçiminden çık", self._kapat_komutu)
        komutlar.kaydet("kalem.tur", "Kalem aracı (1-7)", self._tur_sec)
        komutlar.kaydet("kalem.renk", "Kalem rengi (1-4)", self._renk_sec)
        komutlar.kaydet("kalem.kalinlik", "Kalem kalınlığı (1-3)", self._kalinlik_sec)
        komutlar.kaydet("kalem.geri_al", "Son çizimi geri al", self._geri_al)
        komutlar.kaydet("kalem.temizle", "Tüm çizimleri sil", self._temizle)

    # ---- durum

    @property
    def acik(self) -> bool:
        """Kalem açık mı (bölge seçimi değil)."""
        return self.katman is not None and self.cubuk is not None

    @property
    def carpan(self) -> float:
        return KALINLIK_CARPANI[self.kalinlik]

    @property
    def son_bolge_modu(self) -> str:
        mod = self.ayarlar.al("region.mode", "yakinlastir") if self.ayarlar is not None else "yakinlastir"
        return mod if mod in MODLAR else "yakinlastir"

    def _tus(self, komut: str) -> str:
        if self.ayarlar is None:
            return ""
        for grup in ("hotkeys", "pen_hotkeys"):
            tus = (self.ayarlar.al(grup, {}) or {}).get(komut, "")
            if tus:
                return tus_metni(tus)
        return ""

    def ipucu_satiri(self) -> str:
        if self.katman is not None and self.katman.mod == "bolge":
            parcalar = ["Kutu çiz", "Enter tamam", "Esc vazgeç"]
            if self.hat.bolge.aktif and self._tus("bolge.sec"):
                parcalar.append(f"{self._tus('bolge.sec')} tam ekran")
            return " · ".join(parcalar)
        parcalar = []
        if self._tus("kalem.ac_kapat"):
            parcalar.append(f"{self._tus('kalem.ac_kapat')} kalem")
        if self._tus("kalem.temizle"):
            parcalar.append(f"{self._tus('kalem.temizle')} temizle")
        parcalar.append("Esc çık")
        return " · ".join(parcalar)

    def _ekran(self):
        return ekrani_bul(getattr(self.hat.kaynak, "dikdortgen", None))

    def _penceredeyiz(self) -> bool:
        return getattr(self.depo.durum, "kaynak_turu", "ekran") == "pencere"

    # ---- kalem

    def _ac_kapat(self, _):
        if self.acik:
            self.kapat()
            return "Kalem kapandı"
        if self._penceredeyiz():
            return "Kalem tüm ekranda çalışır · Göster menüsünden bir ekran seç"
        self.ac()
        return TAM_EKRAN_UYARISI if ozel_tam_ekran_mi() else "Kalem açıldı"

    def ac(self) -> None:
        ekran = self._ekran()
        if self.katman is None:
            self.katman = Katman(ekran, self.cizimler, self, "kalem")
            self.katman.baslat()
        else:
            self.katman.mod_degistir("kalem")
        if self.cubuk is None:
            self.cubuk = KalemCubugu(ekran, self.komutlar, self._tus, self._cubuk_konumu)
            self.cubuk.tutma.birakildi.connect(self._cubuk_tasindi)
            self.cubuk.guncelle(self.tur, self.renk, self.kalinlik)
            self.cubuk.baslat()
        self._kalem_tuslari(True)
        self._izi_guncelle()
        self.depo.guncelle(kalem_acik=True, kalem_turu=self.tur)

    def _cubuk_tasindi(self) -> None:
        if self.cubuk is not None:
            self._cubuk_konumu = self.cubuk.pos()

    def kapat(self) -> None:
        """Kalemi (ve açıksa bölge seçimini) kapatır."""
        self._kalem_tuslari(False)
        kalem_acikti = self.cubuk is not None
        if self.katman is not None and self.katman.mod == "bolge":
            self._onceki_bolge = None   # bölge seçimi de kapanır, seçilen bölge kalır
        for w in (self.katman, self.cubuk):
            if w is not None:
                w.close()
                w.deleteLater()
        self.katman = self.cubuk = None
        self._bolgeden_kaleme = False
        if kalem_acikti and (self.ayarlar is None or self.ayarlar.al("pen.clear_on_close", True)):
            self.cizimler.temizle()
        self.depo.guncelle(kalem_acik=False)
        self._izi_guncelle()

    def _kapat_komutu(self, _):
        if self.katman is None:
            return None
        if self.katman.mod == "bolge":
            self.bolge_vazgec()
            return None
        self.kapat()
        return "Kalem kapandı"

    def _kalem_tuslari(self, acik: bool) -> None:
        if self.kisayollar is None:
            return
        if acik:
            ayar = dict(self.ayarlar.al("pen_hotkeys", {}) or {}) if self.ayarlar is not None else {}
            ayar.setdefault("kalem.kapat", "Esc")
            self.kisayollar.grup_ayarla("kalem", gruplara_ayir(ayar, self.komutlar))
        else:
            self.kisayollar.grubu_kaldir("kalem")

    def yazi_moduna_gir(self) -> None:
        self._kalem_tuslari(False)

    def yazi_modundan_cik(self) -> None:
        if self.acik:
            self._kalem_tuslari(True)

    def _arac_guncelle(self) -> None:
        if self.cubuk:
            self.cubuk.guncelle(self.tur, self.renk, self.kalinlik)
        if self.katman:
            self.katman.imleci_ayarla()

    def _tur_sec(self, param):
        try:
            tur = TURLER[int(param) - 1]
        except (TypeError, ValueError, IndexError):
            return None
        if not self.acik:
            return None
        self.tur = tur
        self._arac_guncelle()
        self.depo.guncelle(kalem_turu=tur)
        return None

    def _renk_sec(self, param):
        try:
            self.renk = RENKLER[int(param) - 1]
        except (TypeError, ValueError, IndexError):
            return None
        self._arac_guncelle()
        return None

    def _kalinlik_sec(self, param):
        try:
            self.kalinlik = KALINLIKLAR[int(param) - 1]
        except (TypeError, ValueError, IndexError):
            return None
        self._arac_guncelle()
        return None

    def _geri_al(self, _):
        self.cizimler.geri_al()
        return None

    def _temizle(self, _):
        if self.cizimler.bos:
            return None
        self.cizimler.temizle()
        return "Çizimler silindi"

    # ---- bölge

    def bolge_ac_kapat(self):
        """Bölge düğmesi / Ctrl+Shift+S."""
        if self.katman is not None and self.katman.mod == "bolge":
            self.bolge_vazgec()
            return "Bölge seçimi iptal edildi"
        if self.hat.bolge.aktif:
            self.bolge_temizle()
            return "Tam ekrana dönüldü"
        if self._penceredeyiz():
            return "Bölge tüm ekranda çalışır · Göster menüsünden bir ekran seç"
        self._onceki_bolge = None
        self._bolgeden_kaleme = self.katman is not None
        if self.katman is None:
            self.katman = Katman(self._ekran(), self.cizimler, self, "bolge")
            self.katman.baslat()
        else:
            self.katman.duzenleyici.secim = QRect()
            self.katman.mod_degistir("bolge")
            self.katman.activateWindow()
            self.katman.setFocus()
        self._izi_guncelle()
        return TAM_EKRAN_UYARISI if ozel_tam_ekran_mi() else None

    def bolge_uygula(self, oranlar) -> None:
        """Kutu çizildi ya da düzenlendi: hemen yayına uygulanır."""
        if self._onceki_bolge is None:
            self._onceki_bolge = (self.hat.bolge.bolge, self.hat.bolge.mod)
        mod = self.hat.bolge.mod or self.son_bolge_modu
        self.hat.bolge.sec(oranlar, mod)
        self.depo.guncelle(bolge=mod)

    def bolge_modu(self, mod: str) -> None:
        if self.katman is None or not self.katman.duzenleyici.var:
            return
        if self.ayarlar is not None:
            self.ayarlar.ayarla("region.mode", mod)
        if self._onceki_bolge is None:
            self._onceki_bolge = (self.hat.bolge.bolge, self.hat.bolge.mod)
        self.hat.bolge.sec(self.katman.duzenleyici.oranlar(), mod)
        self.depo.guncelle(bolge=mod)
        self.katman.bilgiyi_yerlestir()

    def bolge_tamam(self) -> None:
        self._onceki_bolge = None
        self._bolge_duzenlemesini_bitir()
        mod = self.hat.bolge.mod
        if mod:
            metin = "Bölge yakınlaştırıldı" if mod == "yakinlastir" else "Bölge vurgulanıyor"
            tus = self._tus("bolge.sec")
            self.bildir(f"{metin} · tam ekran için {tus}" if tus else metin)

    def bolge_vazgec(self) -> None:
        onceki, self._onceki_bolge = self._onceki_bolge, None
        if onceki is not None:
            bolge, mod = onceki
            if bolge and mod:
                self.hat.bolge.sec(bolge, mod)
                self.depo.guncelle(bolge=mod)
            else:
                self.hat.bolge.temizle()
                self.depo.guncelle(bolge="")
        self._bolge_duzenlemesini_bitir()

    def _bolge_duzenlemesini_bitir(self) -> None:
        if self.katman is None:
            return
        if self._bolgeden_kaleme or self.cubuk is not None:
            self._bolgeden_kaleme = False
            self.katman.duzenleyici = SecimDuzenleyici(self.katman,
                                                       self.hat.bolge.bolge if self.hat.bolge.aktif else None)
            self.katman.mod_degistir("kalem")
        else:
            self.katman.close()
            self.katman.deleteLater()
            self.katman = None
        self._izi_guncelle()

    def bolge_temizle(self) -> None:
        self.hat.bolge.temizle()
        self.depo.guncelle(bolge="")
        if self.katman is not None:
            self.katman.duzenleyici.secim = QRect()
            self.katman.bilgiyi_yerlestir()
            self.katman.update()
        self._izi_guncelle()

    def hepsini_kapat(self) -> None:
        """Pencere yakalamaya geçerken: kalem, bölge seçimi ve bölge kapanır."""
        if self.katman is not None:
            self.kapat()
        if self.hat.bolge.aktif:
            self.bolge_temizle()
        self._izi_guncelle()

    def _izi_guncelle(self) -> None:
        """Yakınlaştırma açık ve katman kapalıyken bölgenin ekrandaki yerini ince çerçeveyle gösterir."""
        goster = self.hat.bolge.mod == "yakinlastir" and self.katman is None
        if goster:
            from ui.region_marker import YakinlastirmaIzi
            if self._iz is None:
                self._iz = YakinlastirmaIzi()
            self._iz.goster(self._ekran(), self.hat.bolge.bolge)
        elif self._iz is not None:
            self._iz.hide()


KalemDenetleyici = KatmanDenetleyici   # eski ad
