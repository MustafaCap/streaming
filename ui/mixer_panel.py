"""Ses mikseri paneli: her kanal için açık/kapalı düğmesi, seviye kaydırıcısı ve seviye göstergesi."""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from core.audio_mixer import db
from core.state import Durum
from ui.theme import RENK


class SeviyeGostergesi(QWidget):
    """Yatay ses seviyesi çubuğu (-60 dB .. 0 dB). Yumuşak düşer, tepe değeri kısa süre kalır."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self._deger = 0.0
        self._tepe, self._tepe_sayac = 0.0, 0

    def ayarla(self, seviye: float) -> None:
        hedef = (db(seviye) + 60.0) / 60.0
        self._deger = hedef if hedef > self._deger else self._deger * 0.85 + hedef * 0.15
        if hedef >= self._tepe:
            self._tepe, self._tepe_sayac = hedef, 15
        elif self._tepe_sayac > 0:
            self._tepe_sayac -= 1
        else:
            self._tepe = max(0.0, self._tepe - 0.02)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RENK["kenarlik"]))
        p.drawRoundedRect(r, 4, 4)
        w = r.width() * min(1.0, self._deger)
        if w > 1:
            renk = RENK["acik"] if self._deger < 0.85 else (RENK["panik"] if self._deger < 0.97 else RENK["kapali"])
            p.setBrush(QColor(renk))
            p.drawRoundedRect(QRectF(r.x(), r.y(), w, r.height()), 4, 4)
        if self._tepe > 0.02:
            x = r.x() + r.width() * min(1.0, self._tepe) - 2
            p.setBrush(QColor(RENK["yazi"]))
            p.drawRect(QRectF(x, r.y(), 2, r.height()))


class _KanalSatiri(QWidget):
    def __init__(self, baslik: str, kisayol: str, komut: str, kanal, komutlar, ayarlar, ayar_yolu: str):
        super().__init__()
        self.kanal, self.komutlar = kanal, komutlar
        self.baslik = QLabel(baslik)
        self.baslik.setStyleSheet("font-weight: 600; background: transparent;")
        self.dugme = QPushButton(objectName="sahne")
        self.dugme.setCheckable(True)
        self.dugme.setToolTip(kisayol)
        self.dugme.clicked.connect(lambda: komutlar.calistir(komut))
        self._kisayol = kisayol
        ust = QHBoxLayout()
        ust.addWidget(self.baslik)
        ust.addStretch()
        ust.addWidget(self.dugme)

        self.kaydirici = QSlider(Qt.Horizontal)
        self.kaydirici.setRange(0, 200)
        self.kaydirici.setValue(round(kanal.kazanc * 100))
        self.yuzde = QLabel(f"%{self.kaydirici.value()}", objectName="ikincil")
        self.yuzde.setFixedWidth(42)

        def degisti(v):
            kanal.kazanc = v / 100.0
            self.yuzde.setText(f"%{v}")

        def birakildi():
            if ayarlar is not None:
                ayarlar.ayarla(ayar_yolu, kanal.kazanc)
                ayarlar.kaydet()

        self.kaydirici.valueChanged.connect(degisti)
        self.kaydirici.sliderReleased.connect(birakildi)
        orta = QHBoxLayout()
        orta.addWidget(self.kaydirici, 1)
        orta.addWidget(self.yuzde)

        self.gosterge = SeviyeGostergesi()
        self.bilgi = QLabel(objectName="ikincil")
        self.bilgi.setWordWrap(True)

        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(0, 0, 0, 0)
        kutu.setSpacing(6)
        kutu.addLayout(ust)
        kutu.addLayout(orta)
        kutu.addWidget(self.gosterge)
        kutu.addWidget(self.bilgi)

    def durum(self, sessiz: bool, cihaz_durumu: str, aciklama: str) -> None:
        self.dugme.setChecked(not sessiz)
        # renk tek başına durum anlatmasın: yazı ve üstü çizili simge
        self.dugme.setText(f"{'🔇 Kapalı' if sessiz else '🔊 Açık'} · {self._kisayol}")
        if cihaz_durumu == "yok":
            self.bilgi.setText(f"⚠ {aciklama or 'Bulunamadı'}")
            self.bilgi.setStyleSheet(f"color: {RENK['kapali']}; background: transparent; font-size: 12px;")
        else:
            self.bilgi.setText(aciklama)
            self.bilgi.setStyleSheet("")


class MikserPaneli(QFrame):
    def __init__(self, depo, komutlar, ses, mikser, ayarlar):
        super().__init__(objectName="panel")
        self.depo, self.ses, self.mikser, self.ayarlar = depo, ses, mikser, ayarlar
        self.setMinimumWidth(270)
        self.setMaximumWidth(340)

        baslik = QLabel("Ses mikseri")
        baslik.setStyleSheet("font-size: 15px; font-weight: 600; background: transparent;")

        self.mik_secim = QComboBox()
        self.mik_secim.setToolTip("Hangi mikrofon kullanılsın? (CABLE listede yoktur)")
        self.mik_secim.activated.connect(self._mikrofon_secildi)
        yenile = QPushButton("↻", objectName="sahne")
        yenile.setToolTip("Mikrofon listesini yenile")
        yenile.setFixedWidth(36)
        yenile.clicked.connect(self._yenile)
        secim = QHBoxLayout()
        secim.addWidget(self.mik_secim, 1)
        secim.addWidget(yenile)

        self.mik = _KanalSatiri("Mikrofon", "F8", "ses.mikrofon", mikser.kanallar["mikrofon"],
                                komutlar, ayarlar, "audio.mic_gain")
        self.sistem = _KanalSatiri("Bilgisayar sesi", "F9", "ses.sistem", mikser.kanallar["sistem"],
                                   komutlar, ayarlar, "audio.system_gain")

        self.cikis_gosterge = SeviyeGostergesi()
        self.cikis_bilgi = QLabel(objectName="ikincil")
        self.cikis_bilgi.setWordWrap(True)

        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(14, 12, 14, 12)
        kutu.setSpacing(10)
        kutu.addWidget(baslik)
        kutu.addWidget(self.mik)
        kutu.addLayout(secim)
        kutu.addSpacing(6)
        kutu.addWidget(self.sistem)
        kutu.addSpacing(6)
        kutu.addWidget(QLabel("Sanal mikrofona giden (CABLE)", objectName="ikincil"))
        kutu.addWidget(self.cikis_gosterge)
        kutu.addWidget(self.cikis_bilgi)
        kutu.addStretch()

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._seviyeleri_guncelle)
        self._zamanlayici.start(50)
        self._liste_zamanlayici = QTimer(self)
        self._liste_zamanlayici.timeout.connect(self._listeyi_doldur)
        self._liste_zamanlayici.start(2000)
        self._listeyi_doldur()

    def _listeyi_doldur(self) -> None:
        liste = self.ses.mikrofonlar()
        mevcut = [self.mik_secim.itemData(i) for i in range(self.mik_secim.count())]
        yeni = [""] + liste
        if mevcut == yeni:
            return
        self.mik_secim.blockSignals(True)
        self.mik_secim.clear()
        self.mik_secim.addItem("Windows varsayılanı", "")
        for ad in liste:
            self.mik_secim.addItem(ad, ad)
        secili = self.ses.mikrofon_adi
        i = self.mik_secim.findData(secili)
        if i < 0 and secili:
            self.mik_secim.addItem(f"{secili} (bağlı değil)", secili)
            i = self.mik_secim.count() - 1
        self.mik_secim.setCurrentIndex(max(0, i))
        self.mik_secim.blockSignals(False)

    def _mikrofon_secildi(self, i: int) -> None:
        ad = self.mik_secim.itemData(i) or ""
        self.ses.mikrofon_sec(ad)
        if self.ayarlar is not None:
            self.ayarlar.ayarla("audio.mic_device", ad)
            self.ayarlar.kaydet()

    def _yenile(self) -> None:
        self.ses.yenile()
        QTimer.singleShot(1500, self._listeyi_doldur)

    def _seviyeleri_guncelle(self) -> None:
        s = self.mikser.seviyeler()
        self.mik.gosterge.ayarla(s.get("mikrofon", 0.0))
        self.sistem.gosterge.ayarla(s.get("sistem", 0.0))
        self.cikis_gosterge.ayarla(s.get("cikis", 0.0))

    def durumu_goster(self, d: Durum) -> None:
        self.mik.durum(d.mikrofon_sessiz, d.mikrofon, d.mikrofon_adi if d.mikrofon != "yok" else d.ses_hatasi)
        self.sistem.durum(d.sistem_sessiz, d.sistem_sesi, d.sistem_kaynagi)
        if d.sanal_mikrofon == "açık":
            self.cikis_bilgi.setText("Zoom/Meet/Discord'da mikrofon olarak 'CABLE Output'u seç")
        elif d.sanal_mikrofon in ("yok", "hata"):
            self.cikis_bilgi.setText(f"⚠ {d.ses_hatasi}")
        else:
            self.cikis_bilgi.setText("Yayın başlayınca ses gönderilir")
