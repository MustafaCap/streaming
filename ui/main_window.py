"""Ana pencere (Aşama 1 sürümü): durum rozetleri, önizleme, büyük Başlat/Durdur düğmesi.

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
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Yayın Uygulaması", objectName="baslik"))
        ust.addStretch()
        ust.addWidget(self.rozet_ekran)
        ust.addWidget(self.rozet_kamera)

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

    def _durumu_goster(self, d: Durum) -> None:
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
