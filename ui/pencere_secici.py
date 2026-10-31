"""Kaynak seçme penceresi: en üstte "Tüm ekran", altında açık pencereler (başlık ve program adı).

secilen: None (vazgeçildi), "ekran" ya da (hwnd, başlık).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ui.theme import QSS


class PencereSecici(QDialog):
    def __init__(self, parent=None, listele=None):
        super().__init__(parent)
        from capture.window import pencereleri_listele
        self._listele = listele or pencereleri_listele
        self.secilen = None
        self.setWindowTitle("Ne gösterilsin?")
        self.setStyleSheet(QSS)
        self.resize(520, 440)
        aciklama = QLabel("Bir pencere seçersen yayında ve kayıtta sadece o pencere görünür. Üstüne başka "
                          "pencere gelse de o pencere gösterilir.")
        aciklama.setWordWrap(True)
        aciklama.setObjectName("ikincil")
        self.liste = QListWidget()
        self.liste.itemDoubleClicked.connect(lambda _: self._sec())
        self.liste.currentRowChanged.connect(lambda _: self._dugmeleri_guncelle())
        self.bos = QLabel("Başka açık pencere bulunamadı.", objectName="ikincil")
        yenile = QPushButton("⟳  Yenile", objectName="sahne")
        yenile.clicked.connect(self.yenile)
        self.sec_dugmesi = QPushButton("Göster", objectName="sahne")
        self.sec_dugmesi.setDefault(True)
        self.sec_dugmesi.clicked.connect(self._sec)
        vazgec = QPushButton("Vazgeç", objectName="sahne")
        vazgec.clicked.connect(self.reject)
        alt = QHBoxLayout()
        alt.addWidget(yenile)
        alt.addStretch()
        alt.addWidget(vazgec)
        alt.addWidget(self.sec_dugmesi)
        kutu = QVBoxLayout(self)
        kutu.addWidget(aciklama)
        kutu.addWidget(self.liste, 1)
        kutu.addWidget(self.bos)
        kutu.addLayout(alt)
        self.yenile()

    def yenile(self) -> None:
        self.liste.clear()
        ekran = QListWidgetItem("🖥   Tüm ekran")
        ekran.setData(Qt.UserRole, "ekran")
        self.liste.addItem(ekran)
        for hwnd, baslik, program in self._listele():
            oge = QListWidgetItem(f"🗔   {baslik}" + (f"   —   {program}" if program else ""))
            oge.setData(Qt.UserRole, (hwnd, baslik))
            oge.setToolTip(baslik)
            self.liste.addItem(oge)
        self.liste.setCurrentRow(0)
        self.bos.setVisible(self.liste.count() == 1)
        self._dugmeleri_guncelle()

    def _dugmeleri_guncelle(self) -> None:
        self.sec_dugmesi.setEnabled(self.liste.currentItem() is not None)

    def _sec(self) -> None:
        oge = self.liste.currentItem()
        if oge is None:
            return
        self.secilen = oge.data(Qt.UserRole)
        self.accept()
