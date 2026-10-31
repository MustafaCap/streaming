"""Ana pencere: durum rozetleri, sahne düğmeleri, önizleme, büyük Başlat/Durdur düğmesi.

Aşama 7'de brifteki tam tasarıma (sahneler, mikser, mini mod) genişleyecek.
"""

import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from core.commands import KomutYoneticisi
from core.platform_win import yakalamadan_gizle
from core.state import Durum, DurumDeposu
from ui.theme import QSS, rozet_stili

log = logging.getLogger(__name__)


class _DurumKoprusu(QObject):
    """Video iş parçacığından gelen durum değişikliklerini Qt ana iş parçacığına taşır."""
    degisti = Signal(object)


class AnaPencere(QMainWindow):
    def __init__(self, depo: DurumDeposu, komutlar: KomutYoneticisi, hat, onizleme_fps: int = 15):
        super().__init__()
        self.depo, self.komutlar, self.hat = depo, komutlar, hat
        self.setWindowTitle("Yayın Uygulaması")
        self.setStyleSheet(QSS)
        self.resize(1000, 700)

        # --- üst çubuk: ad + durum rozetleri
        self.rozet_kamera = QLabel(objectName="rozet")
        self.rozet_ekran = QLabel(objectName="rozet")
        self.rozet_webcam = QLabel(objectName="rozet")
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Yayın Uygulaması", objectName="baslik"))
        ust.addStretch()
        ust.addWidget(self.rozet_ekran)
        ust.addWidget(self.rozet_webcam)
        ust.addWidget(self.rozet_kamera)

        # --- sahne düğmeleri (Ctrl+1..4) + kamera aç/kapat (F10)
        sahne_satiri = QHBoxLayout()
        self.sahne_dugmeleri = []
        for i, sahne in enumerate(hat.sahneler.sahneler):
            d = QPushButton(f"{i + 1}  {sahne.ad}", objectName="sahne")
            d.setCheckable(True)
            d.setToolTip(f"Ctrl+{i + 1}" if i < 9 else "")
            d.clicked.connect(lambda _=False, n=i + 1: self._sahne_tiklandi(n))
            sahne_satiri.addWidget(d)
            self.sahne_dugmeleri.append(d)
        sahne_satiri.addStretch()
        self.kamera_dugmesi = QPushButton(objectName="sahne")
        self.kamera_dugmesi.setCheckable(True)
        self.kamera_dugmesi.setToolTip("F10")
        self.kamera_dugmesi.clicked.connect(lambda: self.komutlar.calistir("kamera.ac_kapat"))
        sahne_satiri.addWidget(self.kamera_dugmesi)

        # --- önizleme (karşı tarafın gördüğü)
        self.onizleme = QLabel(objectName="onizleme")
        self.onizleme.setAlignment(Qt.AlignCenter)
        self.onizleme.setMinimumSize(480, 270)
        self.onizleme.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --- alt: büyük düğme + bilgi
        self.dugme = QPushButton(objectName="buyuk")
        self.dugme.clicked.connect(lambda: self.komutlar.calistir("cikis.ac_kapat"))
        self.bilgi = QLabel(objectName="ikincil")
        self.hata = QLabel(objectName="hata")
        self.hata.setWordWrap(True)
        alt_sag = QVBoxLayout()
        alt_sag.addWidget(self.bilgi)
        alt_sag.addWidget(self.hata)
        alt = QHBoxLayout()
        alt.addWidget(self.dugme)
        alt.addSpacing(16)
        alt.addLayout(alt_sag, 1)
        alt_panel = QFrame(objectName="panel")
        alt_panel.setLayout(alt)

        kok = QVBoxLayout()
        kok.setContentsMargins(16, 12, 16, 16)
        kok.addLayout(ust)
        kok.addLayout(sahne_satiri)
        kok.addWidget(self.onizleme, 1)
        kok.addWidget(alt_panel)
        orta = QWidget()
        orta.setLayout(kok)
        self.setCentralWidget(orta)

        # --- durum bağlantısı (iş parçacığı güvenli)
        self._kopru = _DurumKoprusu()
        self._kopru.degisti.connect(self._durumu_goster)
        depo.dinle(lambda eski, yeni: self._kopru.degisti.emit(yeni))
        self._durumu_goster(depo.durum)

        # --- önizleme zamanlayıcısı
        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._onizlemeyi_guncelle)
        self._zamanlayici.start(max(1, 1000 // onizleme_fps))

    def showEvent(self, olay):
        super().showEvent(olay)
        # Önizleme kendini yakalamasın (sonsuz ayna) ve karşı tarafa gitmesin.
        yakalamadan_gizle(int(self.winId()))

    def _sahne_tiklandi(self, numara: int) -> None:
        self.komutlar.calistir(f"sahne.sec:{numara}")
        self._durumu_goster(self.depo.durum)  # düğme hemen doğru görünsün

    def _durumu_goster(self, d: Durum) -> None:
        secili = self.hat.sahneler.indeks
        for i, dugme in enumerate(self.sahne_dugmeleri):
            dugme.setChecked(i == secili)
        kamera_acik = self.hat.kamera_istegi
        self.kamera_dugmesi.setChecked(kamera_acik)
        self.kamera_dugmesi.setText("Kamera: Açık" if kamera_acik else "Kamera: Kapalı")
        self.rozet_webcam.setText(f"Webcam: {d.webcam.capitalize()}")
        self.rozet_webcam.setStyleSheet(rozet_stili(d.webcam))

        self.rozet_kamera.setText(f"Sanal kamera: {d.sanal_kamera.capitalize()}")
        self.rozet_kamera.setStyleSheet(rozet_stili(d.sanal_kamera))
        ekran = d.ekran_kaynagi + (f" ({d.yakalama_yontemi})" if d.yakalama_yontemi else "")
        self.rozet_ekran.setText(f"Ekran: {ekran.capitalize()}")
        self.rozet_ekran.setStyleSheet(rozet_stili(d.ekran_kaynagi))

        self.dugme.setText("■  Yayını durdur" if d.cikis_acik else "▶  Yayını başlat")
        self.dugme.setProperty("acik", "true" if d.cikis_acik else "false")
        self.dugme.style().unpolish(self.dugme)
        self.dugme.style().polish(self.dugme)

        self.bilgi.setText(f"{d.fps:.0f} FPS  ·  kare başına {d.kare_suresi_ms:.1f} ms"
                           + ("  ·  Meet/Zoom/Discord'da kamera olarak 'OBS Virtual Camera'yı seç"
                              if d.cikis_acik else ""))
        self.hata.setText(d.son_hata)

    def _onizlemeyi_guncelle(self) -> None:
        kare = self.hat.son_kare()
        h, w = kare.shape[:2]
        resim = QImage(kare.data, w, h, 3 * w, QImage.Format_RGB888)
        hedef = self.onizleme.size()
        self.onizleme.setPixmap(QPixmap.fromImage(resim).scaled(
            hedef, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, olay):
        self._zamanlayici.stop()
        self.hat.durdur()
        super().closeEvent(olay)
