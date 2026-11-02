"""Gelişmiş görünümün sol sütunu: Sahneler ve Kaynaklar panelleri.

Sahneler: + ile "Yeni sahne 1, 2…" eklenir ve seçilir; çift tıklayınca yeniden adlandırılır;
sağ tıklayınca silinir. İlk 9 sahnenin kısayolu (Ctrl+Shift+1…9) sağda soluk yazar.

Kaynaklar: aktif sahnenin kaynakları, üstteki öndedir. Göz düğmesi gizler/gösterir, satırın
üzerine gelince çıkan × kaldırır. Sağ tık: öne/arkaya al, yeniden adlandır, kaldır.
+ menüsü: Ekran, Uygulama penceresi, Ekran bölgesi, Kamera, Görsel, Video, Metin.

Sahne verisi video hattındaki SahneYoneticisi'nde durur; panel sadece onu gösterir ve değiştirir.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu,
                               QVBoxLayout, QWidget)

from scenes.scene_manager import EKLENEBILIR, Kaynak, yeni_kaynak_adi
from ui.bilesenler import SimgeDugme, menu_ogesi
from ui.theme import ALFA, RENK, qrenk

log = logging.getLogger(__name__)

GORSEL_FILTRE = "Görseller (*.png *.jpg *.jpeg *.bmp *.webp)"
VIDEO_FILTRE = "Videolar (*.mp4 *.webm *.avi *.mov *.mkv *.gif *.wmv *.m4v)"


def _panel_basligi(metin: str, dugme: QWidget) -> QHBoxLayout:
    satir = QHBoxLayout()
    satir.setContentsMargins(0, 0, 0, 4)
    satir.addWidget(QLabel(metin, objectName="baslik"))
    satir.addStretch()
    satir.addWidget(dugme)
    return satir


class _Satir(QWidget):
    """Üzerine gelince açık gri, seçiliyken biraz daha açık zemin."""

    tiklandi = Signal()
    cift_tiklandi = Signal()
    sag_tiklandi = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.TabFocus)
        self.secili = False
        self._klavye_odagi = False

    def focusInEvent(self, e):
        self._klavye_odagi = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason)
        super().focusInEvent(e)
        self.update()

    def event(self, e):
        if e.type() in (e.Type.HoverEnter, e.Type.HoverLeave):
            self.update()
            self.uzerinde_degisti(e.type() == e.Type.HoverEnter)
        return super().event(e)

    def uzerinde_degisti(self, uzerinde: bool) -> None:
        pass

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alfa = ALFA["seçili"] if self.secili else 0.0
        if self.underMouse():
            alfa = max(alfa, ALFA["uzerine"]) + (0.02 if self.secili else 0)
        if alfa:
            p.setPen(Qt.NoPen)
            p.setBrush(qrenk("beyaz", alfa))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        if self.hasFocus() and self._klavye_odagi:
            p.setPen(qrenk("beyaz", 0.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.tiklandi.emit()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.cift_tiklandi.emit()

    def contextMenuEvent(self, e):
        self.sag_tiklandi.emit(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.tiklandi.emit()
        elif e.key() == Qt.Key_F2:
            self.cift_tiklandi.emit()
        elif e.key() == Qt.Key_Menu:
            self.sag_tiklandi.emit(self.mapToGlobal(self.rect().center()))
        else:
            super().keyPressEvent(e)


class SahneSatiri(_Satir):
    yeniden_adlandirildi = Signal(str)

    def __init__(self, ad: str, tus: str, secili: bool, parent=None):
        super().__init__(parent)
        self.secili = secili
        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"Sahne: {ad}" + (" (seçili)" if secili else ""))
        if tus:
            self.setToolTip(tus)
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(10, 0, 10, 0)
        kutu.setSpacing(8)
        self.ad = QLabel(ad)
        self.ad.setStyleSheet(f"color: {RENK['beyaz'] if secili else RENK['dugme']};")
        kutu.addWidget(self.ad, 1)
        self.tus = QLabel(tus)
        self.tus.setStyleSheet(f"color: {RENK['soluk']}; font-size: 11px;")
        kutu.addWidget(self.tus)
        self.duzenleyici = None

    def duzenle(self) -> None:
        """Satırın yerinde ad kutusu açar: Enter kaydeder, Esc vazgeçer."""
        if self.duzenleyici is not None:
            return
        self.duzenleyici = QLineEdit(self.ad.text(), self)
        self.duzenleyici.setAccessibleName("Sahne adı")
        self.duzenleyici.setMaxLength(60)
        self.duzenleyici.setGeometry(self.rect().adjusted(2, 4, -2, -4))
        self.duzenleyici.selectAll()
        self.duzenleyici.show()
        self.duzenleyici.setFocus()
        self.duzenleyici.editingFinished.connect(self._bitti)
        self.duzenleyici.installEventFilter(self)

    def eventFilter(self, nesne, olay):
        if nesne is self.duzenleyici and olay.type() == olay.Type.KeyPress and olay.key() == Qt.Key_Escape:
            self.duzenleyici.blockSignals(True)
            self.duzenleyici.deleteLater()
            self.duzenleyici = None
            return True
        return super().eventFilter(nesne, olay)

    def _bitti(self) -> None:
        if self.duzenleyici is None:
            return
        metin = self.duzenleyici.text().strip()
        self.duzenleyici.blockSignals(True)
        self.duzenleyici.deleteLater()
        self.duzenleyici = None
        if metin and metin != self.ad.text():
            self.yeniden_adlandirildi.emit(metin)


class SahnelerPaneli(QFrame):
    def __init__(self, hat, komutlar, tus_al, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.hat, self.komutlar, self._tus_al = hat, komutlar, tus_al
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(12, 12, 12, 12)
        kutu.setSpacing(2)
        ekle = SimgeDugme("arti", "Sahne ekle", boyut=28, simge_boyu=14)
        ekle.clicked.connect(self.sahne_ekle)
        kutu.addLayout(_panel_basligi("Sahneler", ekle))
        self._liste = QVBoxLayout()
        self._liste.setSpacing(2)
        kutu.addLayout(self._liste)
        self.satirlar: list[SahneSatiri] = []
        self._imza = None
        self.yenile()

    def yenile(self, zorla: bool = False) -> None:
        sy = self.hat.sahneler
        imza = (sy.surum, sy.indeks, len(sy.sahneler), tuple(self._tus_al(f"sahne.sec:{i + 1}")
                                                              for i in range(min(9, len(sy.sahneler)))))
        if imza == self._imza and not zorla:
            return
        self._imza = imza
        for s in self.satirlar:
            s.setParent(None)
            s.deleteLater()
        self.satirlar = []
        for i, sahne in enumerate(sy.sahneler):
            satir = SahneSatiri(sahne.ad, self._tus_al(f"sahne.sec:{i + 1}") if i < 9 else "", i == sy.indeks)
            satir.tiklandi.connect(lambda n=i: self.komutlar.calistir(f"sahne.sec:{n + 1}"))
            satir.cift_tiklandi.connect(satir.duzenle)
            satir.yeniden_adlandirildi.connect(lambda ad, n=i: sy.yeniden_adlandir(n, ad))
            satir.sag_tiklandi.connect(lambda yer, n=i, s=satir: self._menu(n, s, yer))
            self._liste.addWidget(satir)
            self.satirlar.append(satir)

    def sahne_ekle(self) -> None:
        n = self.hat.sahneler.ekle()
        if n < 0:
            return
        self.komutlar.calistir(f"sahne.sec:{n + 1}")
        self.yenile()

    def _menu(self, indeks: int, satir: SahneSatiri, yer) -> None:
        menu = QMenu(self)
        menu.addAction("Yeniden adlandır", satir.duzenle)
        sil = menu.addAction("Sil", lambda: self._sil(indeks))
        sil.setEnabled(len(self.hat.sahneler.sahneler) > 1)
        menu.exec(yer)

    def _sil(self, indeks: int) -> None:
        if self.hat.sahneler.sil(indeks):
            self.komutlar.calistir(f"sahne.sec:{self.hat.sahneler.indeks + 1}")
            self.yenile()


class KaynakSatiri(_Satir):
    goz_basildi = Signal()
    kaldir_basildi = Signal()

    def __init__(self, kaynak: Kaynak, bilgi: str, parent=None):
        super().__init__(parent)
        self.kaynak = kaynak
        self.setMinimumHeight(44)
        self.setAccessibleName(f"Kaynak: {kaynak.ad}" + ("" if kaynak.gorunur else " (gizli)"))
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(10, 2, 2, 2)
        kutu.setSpacing(2)
        yazi = QVBoxLayout()
        yazi.setSpacing(0)
        self.ad = QLabel(kaynak.ad)
        self.bilgi = QLabel(bilgi)
        # gizli kaynak: yazı sönük (ama kontrast için en az soluk gri)
        self.ad.setStyleSheet(f"color: {RENK['yazi'] if kaynak.gorunur else RENK['soluk']};")
        self.bilgi.setStyleSheet(f"color: {RENK['soluk']}; font-size: 11px;")
        yazi.addWidget(self.ad)
        if bilgi:
            yazi.addWidget(self.bilgi)
        kutu.addLayout(yazi, 1)
        ad = kaynak.ad
        self.goz = SimgeDugme("goz" if kaynak.gorunur else "goz_kapali",
                              f"{ad}: görünür, gizle" if kaynak.gorunur else f"{ad}: gizli, göster",
                              boyut=28, simge_boyu=14, renk=RENK["yazi2"])
        self.goz.clicked.connect(self.goz_basildi.emit)
        self.kaldir = SimgeDugme("kapat", f"{ad} kaynağını kaldır", boyut=28, simge_boyu=14, renk=RENK["yazi2"])
        self.kaldir.clicked.connect(self.kaldir_basildi.emit)
        kutu.addWidget(self.goz)
        kutu.addWidget(self.kaldir)
        self._kaldiri_goster(False)

    def _kaldiri_goster(self, goster: bool) -> None:
        # × sadece üzerine gelince ya da klavyeyle odaklanınca görünür; yeri hep ayrılı (satır kaymasın)
        self.kaldir.gizli = not goster
        self.kaldir.update()

    def uzerinde_degisti(self, uzerinde: bool) -> None:
        self._kaldiri_goster(uzerinde or self.kaldir.hasFocus())


class KaynaklarPaneli(QFrame):
    def __init__(self, hat, ayarlar, pencere_sec, bolge_sec, parent=None):
        """pencere_sec(): (hwnd, başlık) ya da None. bolge_sec(geri_cagri): seçilen bölgeyi verir."""
        super().__init__(parent)
        self.setObjectName("panel")
        self.hat, self.ayarlar = hat, ayarlar
        self._pencere_sec, self._bolge_sec = pencere_sec, bolge_sec
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(12, 12, 12, 12)
        kutu.setSpacing(2)
        self.ekle = SimgeDugme("arti", "Kaynak ekle", boyut=28, simge_boyu=14)
        self.ekle.clicked.connect(self._ekle_menusu)
        kutu.addLayout(_panel_basligi("Kaynaklar", self.ekle))
        self._liste = QVBoxLayout()
        self._liste.setSpacing(2)
        kutu.addLayout(self._liste)
        self.bos = QLabel("Bu sahnede kaynak yok", objectName="soluk")
        self.bos.setContentsMargins(10, 8, 10, 8)
        kutu.addWidget(self.bos)
        self.satirlar: list[KaynakSatiri] = []
        self._imza = None
        self.yenile()

    # ---- liste

    def yenile(self, zorla: bool = False) -> None:
        sy = self.hat.sahneler
        imza = (sy.surum, sy.indeks, getattr(self.hat, "bekleme_gorseli", ""))
        if imza == self._imza and not zorla:
            return
        self._imza = imza
        for s in self.satirlar:
            s.setParent(None)
            s.deleteLater()
        self.satirlar = []
        sahne = sy.aktif
        for k in sahne.kaynaklar:
            satir = KaynakSatiri(k, self.bilgi(k))
            satir.goz_basildi.connect(lambda kim=k.kimlik: self._goz(kim))
            satir.kaldir_basildi.connect(lambda kim=k.kimlik: self._kaldir(kim))
            satir.sag_tiklandi.connect(lambda yer, kk=k: self._menu(kk, yer))
            satir.cift_tiklandi.connect(lambda kk=k: self._duzenle(kk))
            self._liste.addWidget(satir)
            self.satirlar.append(satir)
        self.bos.setVisible(not sahne.kaynaklar)

    def bilgi(self, k: Kaynak) -> str:
        a = k.ayar
        if k.tur == "ekran":
            if k.ana:
                return "Göster'deki görüntü"
            return f"Monitör {int(a.get('monitor', 0)) + 1}"
        if k.tur == "pencere":
            return str(a.get("title", ""))[:40]
        if k.tur == "bolge":
            r = a.get("rect") or [0, 0, 1, 1]
            boyut = a.get("pixels")
            if boyut:
                return f"{boyut[0]} × {boyut[1]}"
            return f"%{round(r[2] * 100)} × %{round(r[3] * 100)}"
        if k.tur == "kamera":
            if k.ana:
                return "Webcam · " + ("tam ekran" if a.get("yer") == "tam" else "köşede")
            return f"Cihaz {int(a.get('device', 1)) + 1}"
        if k.tur in ("gorsel", "video"):
            return Path(str(a.get("path", ""))).name
        if k.tur == "metin":
            return str(a.get("text", ""))[:40]
        if k.tur == "kalem":
            return "Saydam"
        if k.tur == "imlec":
            return "Halka"
        if k.tur == "bekleme":
            from core.standby import video_mu
            yol = getattr(self.hat, "bekleme_gorseli", "") or ""
            return "Video" if video_mu(yol) else (Path(yol).name if yol else "Yazı")
        return ""

    def _goz(self, kimlik: str) -> None:
        self.hat.sahneler.kaynak_gorunurluk(kimlik)
        self.yenile()

    def _kaldir(self, kimlik: str) -> None:
        self.hat.sahneler.kaynak_sil(kimlik)
        self.yenile()

    def _menu(self, k: Kaynak, yer) -> None:
        menu = QMenu(self)
        liste = self.hat.sahneler.aktif.kaynaklar
        i = next((n for n, x in enumerate(liste) if x.kimlik == k.kimlik), 0)
        on = menu.addAction("Öne al", lambda: self._tasi(k.kimlik, -1))
        on.setEnabled(i > 0)
        arka = menu.addAction("Arkaya al", lambda: self._tasi(k.kimlik, 1))
        arka.setEnabled(i < len(liste) - 1)
        menu.addSeparator()
        menu.addAction("Yeniden adlandır", lambda: self._yeniden_adlandir(k))
        if k.tur == "metin":
            menu.addAction("Yazıyı düzenle…", lambda: self._duzenle(k))
        if k.tur == "bekleme":
            menu.addAction("Resim ya da kısa video seç…", self._bekleme_sec)
            yazi = menu.addAction("Sadece yazı kullan", lambda: self._bekleme_uygula(""))
            yazi.setEnabled(bool(getattr(self.hat, "bekleme_gorseli", "")))
            menu.addAction("Bekleme yazısını değiştir…", self._bekleme_yazisi)
        if k.tur == "kamera" and not k.ana:
            menu.addAction("Köşede" if k.ayar.get("yer") == "tam" else "Tam ekran",
                           lambda: self._kamera_yeri(k))
        menu.addSeparator()
        menu.addAction("Kaldır", lambda: self._kaldir(k.kimlik))
        menu.exec(yer)

    def _tasi(self, kimlik: str, yon: int) -> None:
        self.hat.sahneler.kaynak_tasi(kimlik, yon)
        self.yenile()

    def _yeniden_adlandir(self, k: Kaynak) -> None:
        ad, tamam = QInputDialog.getText(self, "Yeniden adlandır", "Kaynak adı:", text=k.ad)
        if tamam and ad.strip():
            with self.hat.sahneler._kilit:
                k.ad = ad.strip()[:60]
            self.hat.sahneler._haber_ver()
            self.yenile()

    def _duzenle(self, k: Kaynak) -> None:
        if k.tur == "metin":
            metin, tamam = QInputDialog.getText(self, "Metin", "Görünecek yazı:", text=str(k.ayar.get("text", "")))
            if tamam:
                self.hat.sahneler.kaynak_ayarla(k.kimlik, text=metin[:120])
                self.yenile()
        elif k.tur == "bekleme":
            self._bekleme_sec()

    def _kamera_yeri(self, k: Kaynak) -> None:
        self.hat.sahneler.kaynak_ayarla(k.kimlik, yer="kose" if k.ayar.get("yer") == "tam" else "tam")
        self.yenile()

    # ---- bekleme ekranı içeriği (sahne düzenlerken seçilir)

    def _bekleme_sec(self) -> None:
        from ui.bekleme_secici import dosya_sec
        yol = dosya_sec(self)
        if yol:
            self._bekleme_uygula(yol)

    def _bekleme_uygula(self, yol: str) -> None:
        if self.ayarlar is not None:
            from ui.bekleme_secici import uygula
            uygula(self.ayarlar, self.hat, yol)
        else:
            self.hat.bekleme_gorseli = yol
        self.yenile(zorla=True)

    def _bekleme_yazisi(self) -> None:
        metin, tamam = QInputDialog.getText(self, "Bekleme ekranı", "Yazı:", text=self.hat.bekleme_metni)
        if tamam and metin.strip():
            self.hat.bekleme_metni = metin.strip()[:120]
            if self.ayarlar is not None:
                self.ayarlar.ayarla("standby_text", self.hat.bekleme_metni)

    # ---- kaynak ekleme

    def _ekle_menusu(self) -> None:
        menu = QMenu(self)
        menu.setAccessibleName("Kaynak türleri")
        for tur, ad, aciklama in EKLENEBILIR:
            menu_ogesi(menu, ad, aciklama, lambda _=False, t=tur: self.kaynak_ekle(t))
        menu.exec(self.ekle.mapToGlobal(self.ekle.rect().bottomLeft()))

    def _ekle(self, tur: str, **ayar) -> None:
        sahne = self.hat.sahneler.aktif
        k = Kaynak(tur, yeni_kaynak_adi(sahne, tur), ayar=ayar)
        if not self.hat.sahneler.kaynak_ekle(k):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Kaynaklar", "Bir sahnede en çok 20 kaynak olabilir.")
            return
        self.yenile()

    def kaynak_ekle(self, tur: str) -> None:
        if tur == "ekran":
            from capture.screen import monitorleri_listele
            monitorler = monitorleri_listele() or [(0, 0)]
            if len(monitorler) == 1:
                self._ekle("ekran", monitor=0)
                return
            menu = QMenu(self)
            for i, (w, h) in enumerate(monitorler):
                menu_ogesi(menu, f"Ekran {i + 1}", f"Tüm ekran · {w}×{h}", lambda _=False, n=i: self._ekle("ekran", monitor=n))
            menu.exec(self.ekle.mapToGlobal(self.ekle.rect().bottomLeft()))
        elif tur == "pencere":
            secilen = self._pencere_sec()
            if secilen:
                self._ekle("pencere", title=secilen[1])
        elif tur == "bolge":
            self._bolge_sec(lambda monitor, rect, piksel: self._ekle("bolge", monitor=monitor, rect=list(rect),
                                                                     pixels=list(piksel)))
        elif tur == "kamera":
            ana = int(self.ayarlar.al("camera.device", 0)) if self.ayarlar is not None else 0
            menu = QMenu(self)
            for n in range(4):
                if n == ana:
                    continue
                menu_ogesi(menu, f"Cihaz {n + 1}", "İkinci webcam, telefon ya da yakalama kartı",
                           lambda _=False, d=n: self._ekle("kamera", device=d, yer="kose"))
            menu.exec(self.ekle.mapToGlobal(self.ekle.rect().bottomLeft()))
        elif tur == "gorsel":
            yol, _ = QFileDialog.getOpenFileName(self, "Görsel seç", "", GORSEL_FILTRE)
            if yol:
                self._ekle("gorsel", path=yol)
        elif tur == "video":
            yol, _ = QFileDialog.getOpenFileName(self, "Video seç", "", VIDEO_FILTRE)
            if yol:
                from scenes.kaynaklar import video_kopyala
                try:
                    yol = video_kopyala(yol)
                except OSError as e:
                    log.warning("Video kopyalanamadı: %s", e)
                    return
                self._ekle("video", path=yol)
        elif tur == "metin":
            metin, tamam = QInputDialog.getText(self, "Metin", "Görünecek yazı (ör. adın):")
            if tamam and metin.strip():
                self._ekle("metin", text=metin.strip()[:120])
