"""Çizim kalemi arayüzü: şeffaf çizim katmanı + üstte araç çubuğu + kalem komutları.

F7 kalemi açar/kapatır. Kalem açıkken:
  1-6     : kalem, fosforlu, ok, kare, yazı, lazer
  Ctrl+Z  : son çizimi geri al
  Del     : hepsini sil
  Esc     : kalemi kapat
Bu tuşlar sadece kalem açıkken yakalanır (global kısayol grubu "kalem");
kalem kapalıyken normal şekilde oyuna/uygulamaya gider.

Katman ve araç çubuğu ekran yakalamaya girmez; karşı taraf çizimleri video
hattının çıkış karesine eklediği haliyle görür (overlay/drawing.py).
"""

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from core.hotkeys import gruplara_ayir
from core.platform_win import yakalamadan_gizle
from overlay.drawing import (FOSFOR_SAYDAMLIK, KALINLIK, LAZER_RENGI, RENKLER, TUR_ADLARI, TURLER,
                             CizimDeposu)
from ui.theme import QSS, RENK

log = logging.getLogger(__name__)


class CizimKatmani(QWidget):
    def __init__(self, ekran, depo: CizimDeposu, denetci):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.depo, self.denetci = depo, denetci
        self.setGeometry(ekran.geometry())
        self._surum = -1
        self._ciziyor = False
        self._yazi_kutusu: QLineEdit | None = None
        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._gerekirse_ciz)
        self._zamanlayici.start(33)

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._imleci_ayarla()

    def _imleci_ayarla(self) -> None:
        tur = self.denetci.tur
        self.setCursor(Qt.IBeamCursor if tur == "yazi" else (Qt.BlankCursor if tur == "lazer" else Qt.CrossCursor))

    def _gerekirse_ciz(self) -> None:
        if self.depo.surum != self._surum or self.denetci.tur == "lazer":
            self._surum = self.depo.surum
            self.update()

    def _oran(self, e) -> tuple[float, float]:
        p = e.position()
        return p.x() / max(1, self.width()), p.y() / max(1, self.height())

    # ---- fare

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.depo.geri_al()
            return
        if e.button() != Qt.LeftButton:
            return
        x, y = self._oran(e)
        if self.denetci.tur == "yazi":
            self._yazi_baslat(e.position())
            return
        self._ciziyor = True
        self.depo.basla(self.denetci.tur, self.denetci.renk, x, y)

    def mouseMoveEvent(self, e):
        x, y = self._oran(e)
        if self._ciziyor:
            self.depo.surukle(x, y)
        elif self.denetci.tur == "lazer":
            self.depo.lazer_noktasi(x, y)

    def mouseReleaseEvent(self, e):
        if self._ciziyor and e.button() == Qt.LeftButton:
            self._ciziyor = False
            self.depo.bitir()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.denetci.kapat()

    # ---- yazı aracı

    def _yazi_baslat(self, konum: QPointF) -> None:
        if self._yazi_kutusu is not None:
            self._yazi_bitir(True)
        boy = max(10, round(KALINLIK["yazi"] * self.height()))
        kutu = QLineEdit(self)
        kutu.setFont(QFont("Segoe UI", -1))
        f = kutu.font()
        f.setPixelSize(boy)
        kutu.setFont(f)
        kutu.setStyleSheet(f"background: rgba(0,0,0,90); color: {self.denetci.renk};"
                           f" border: 1px dashed {RENK['vurgu']}; padding: 0px 2px;")
        kutu.setPlaceholderText("Yaz, Enter")
        kutu.move(int(konum.x()), int(konum.y()))
        kutu.resize(max(260, self.width() // 4), boy + 10)
        kutu.returnPressed.connect(lambda: self._yazi_bitir(True))
        kutu.editingFinished.connect(lambda: self._yazi_bitir(True))
        kutu.installEventFilter(self)
        self._yazi_kutusu = kutu
        self._yazi_konumu = (konum.x() / self.width(), konum.y() / self.height())
        self.denetci.yazi_moduna_gir()  # 1-6, Del yazıya gitsin diye kalem kısayollarını bırak
        kutu.show()
        kutu.setFocus()

    def eventFilter(self, nesne, olay):
        if nesne is self._yazi_kutusu and olay.type() == olay.Type.KeyPress and olay.key() == Qt.Key_Escape:
            self._yazi_bitir(False)
            return True
        return super().eventFilter(nesne, olay)

    def _yazi_bitir(self, kaydet: bool) -> None:
        kutu = self._yazi_kutusu
        if kutu is None:
            return
        self._yazi_kutusu = None
        if kaydet and kutu.text().strip():
            x, y = self._yazi_konumu
            self.depo.yazi_ekle(self.denetci.renk, x, y, kutu.text())
        kutu.deleteLater()
        self.denetci.yazi_modundan_cik()
        self.setFocus()

    # ---- çizim

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Neredeyse saydam zemin: Windows'ta tamamen saydam piksel tıklamayı alttaki pencereye geçirir.
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
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
                kalem = QPen(renk, kalin, Qt.SolidLine,
                             Qt.RoundCap if s.tur == "kalem" else Qt.FlatCap, Qt.RoundJoin)
                p.setPen(kalem)
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
                f = QFont("Segoe UI")
                f.setPixelSize(max(8, round(kalin)))
                p.setFont(f)
                p.setPen(renk)
                nk = nokta(s.noktalar[0])
                p.drawText(QRectF(nk.x(), nk.y(), W, kalin * 1.6), Qt.AlignLeft | Qt.AlignTop, s.metin)

        if lazer:
            renk = QColor(LAZER_RENGI)
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
                p.setBrush(QColor(LAZER_RENGI))
                p.drawEllipse(nokta(lazer[-1]), kalin + 1, kalin + 1)


class AracCubugu(QWidget):
    """Ekranın üst ortasında: 1-6 araçlar, 4 renk, Geri al, Temizle, Kapat."""

    def __init__(self, ekran, komutlar):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(QSS + f"""
            QWidget#cubuk {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']}; border-radius: 12px; }}
            QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
                           padding: 6px 10px; font-size: 13px; }}
            QPushButton:hover {{ border-color: {RENK['kenarlik']}; }}
            QPushButton:checked {{ border-color: {RENK['vurgu']}; color: {RENK['vurgu']}; }}
        """)
        self.setAttribute(Qt.WA_TranslucentBackground)
        kap = QWidget(self, objectName="cubuk")
        satir = QHBoxLayout(kap)
        satir.setContentsMargins(8, 6, 8, 6)
        satir.setSpacing(4)
        self.arac_dugmeleri = {}
        for i, tur in enumerate(TURLER):
            d = QPushButton(f"{i + 1}  {TUR_ADLARI[tur]}")
            d.setCheckable(True)
            d.setFocusPolicy(Qt.NoFocus)
            d.clicked.connect(lambda _=False, n=i + 1: komutlar.calistir(f"kalem.tur:{n}"))
            satir.addWidget(d)
            self.arac_dugmeleri[tur] = d
        satir.addSpacing(8)
        self.renk_dugmeleri = {}
        for i, renk in enumerate(RENKLER):
            d = QPushButton()
            d.setCheckable(True)
            d.setFixedSize(28, 28)
            d.setFocusPolicy(Qt.NoFocus)
            d.clicked.connect(lambda _=False, n=i + 1: komutlar.calistir(f"kalem.renk:{n}"))
            self.renk_dugmeleri[renk] = d
            satir.addWidget(d)
        satir.addSpacing(8)
        for metin, komut in (("↶ Geri al", "kalem.geri_al"), ("🗑 Temizle", "kalem.temizle"),
                             ("✕ Kapat · F7", "kalem.ac_kapat")):
            d = QPushButton(metin)
            d.setFocusPolicy(Qt.NoFocus)
            d.clicked.connect(lambda _=False, k=komut: komutlar.calistir(k))
            satir.addWidget(d)
        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(kap)
        self.adjustSize()
        g = ekran.availableGeometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 12)

    def guncelle(self, tur: str, renk: str) -> None:
        for t, d in self.arac_dugmeleri.items():
            d.setChecked(t == tur)
        for r, d in self.renk_dugmeleri.items():
            secili = r == renk
            d.setChecked(secili)
            kenar = RENK["yazi"] if secili else RENK["kenarlik"]
            d.setStyleSheet(f"background: {r}; border: 2px solid {kenar}; border-radius: 14px; padding: 0;")

    def baslat(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()


class KalemDenetleyici:
    """Kalem komutlarını kaydeder; katmanı ve araç çubuğunu açıp kapatır."""

    def __init__(self, komutlar, depo, hat, cizimler: CizimDeposu, kisayollar, ayarlar):
        self.komutlar, self.depo, self.hat, self.cizimler = komutlar, depo, hat, cizimler
        self.kisayollar, self.ayarlar = kisayollar, ayarlar
        self.tur = "kalem"
        self.renk = RENKLER[0]
        self.katman: CizimKatmani | None = None
        self.cubuk: AracCubugu | None = None
        komutlar.kaydet("kalem.ac_kapat", "Kalemi aç/kapat", self._ac_kapat)
        komutlar.kaydet("kalem.tur", "Kalem türü (1-6)", self._tur_sec)
        komutlar.kaydet("kalem.renk", "Kalem rengi (1-4)", self._renk_sec)
        komutlar.kaydet("kalem.geri_al", "Son çizimi geri al", self._geri_al)
        komutlar.kaydet("kalem.temizle", "Tüm çizimleri sil", self._temizle)

    @property
    def acik(self) -> bool:
        return self.katman is not None

    def _ac_kapat(self, _):
        if self.acik:
            self.kapat()
            return "Kalem kapandı"
        if getattr(self.depo.durum, "kaynak_turu", "ekran") == "pencere":
            return "Kalem tüm ekranda çalışır · Göster düğmesinden Tüm ekran'ı seç"
        self.ac()
        return "Kalem açıldı"

    def ac(self) -> None:
        from ui.region_overlay import ekrani_bul
        ekran = ekrani_bul(getattr(self.hat.kaynak, "dikdortgen", None))
        self.katman = CizimKatmani(ekran, self.cizimler, self)
        self.cubuk = AracCubugu(ekran, self.komutlar)
        self.cubuk.guncelle(self.tur, self.renk)
        self.katman.baslat()
        self.cubuk.baslat()
        self._kalem_tuslari(True)
        self.depo.guncelle(kalem_acik=True, kalem_turu=self.tur)

    def kapat(self) -> None:
        self._kalem_tuslari(False)
        for w in (self.katman, self.cubuk):
            if w is not None:
                w.close()
                w.deleteLater()
        self.katman = self.cubuk = None
        if self.ayarlar is None or self.ayarlar.al("pen.clear_on_close", True):
            self.cizimler.temizle()
        self.depo.guncelle(kalem_acik=False)

    def _kalem_tuslari(self, acik: bool) -> None:
        if self.kisayollar is None:
            return
        if acik:
            ayar = self.ayarlar.al("pen_hotkeys", {}) if self.ayarlar is not None else {}
            self.kisayollar.grup_ayarla("kalem", gruplara_ayir(ayar, self.komutlar))
        else:
            self.kisayollar.grubu_kaldir("kalem")

    def yazi_moduna_gir(self) -> None:
        self._kalem_tuslari(False)

    def yazi_modundan_cik(self) -> None:
        if self.acik:
            self._kalem_tuslari(True)

    def _tur_sec(self, param):
        try:
            tur = TURLER[int(param) - 1]
        except (TypeError, ValueError, IndexError):
            return None
        if not self.acik:
            return None
        self.tur = tur
        if self.cubuk:
            self.cubuk.guncelle(self.tur, self.renk)
        if self.katman:
            self.katman._imleci_ayarla()
        self.depo.guncelle(kalem_turu=tur)
        return TUR_ADLARI[tur]

    def _renk_sec(self, param):
        try:
            self.renk = RENKLER[int(param) - 1]
        except (TypeError, ValueError, IndexError):
            return None
        if self.cubuk:
            self.cubuk.guncelle(self.tur, self.renk)
        return None

    def _geri_al(self, _):
        self.cizimler.geri_al()
        return None

    def _temizle(self, _):
        self.cizimler.temizle()
        return "Çizimler silindi"
