"""Ayarlar penceresi: genel, kamera, ses ve kısayollar.

Değişiklikler settings.json'a yazılır. Çoğu hemen uygulanır; monitör ve
kamera cihazı değişikliği uygulama yeniden açılınca geçerli olur.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from core.hotkeys import VARSAYILAN_KISAYOLLAR, GecersizTus, tus_coz, tus_metni
from ui.theme import QSS

log = logging.getLogger(__name__)

KOSELER = [("bottom-right", "Sağ alt"), ("bottom-left", "Sol alt"), ("top-right", "Sağ üst"), ("top-left", "Sol üst")]
SES_MODLARI = [("auto", "Tüm ses (Zoom/Discord hariç, yankı yapmaz)"), ("all", "Hoparlörden çıkan her şey"),
               ("app", "Sadece bir uygulama")]
VARSAYILAN_KALEM_TUSLARI = {"kalem.tur:1": "1", "kalem.tur:2": "2", "kalem.tur:3": "3", "kalem.tur:4": "4",
                            "kalem.tur:5": "5", "kalem.tur:6": "6", "kalem.geri_al": "Ctrl+Z", "kalem.temizle": "Del"}
KOMUT_ADLARI = {
    "bolge.sec": "Kare seç / tam ekran", "kalem.ac_kapat": "Kalemi aç/kapat", "ses.mikrofon": "Mikrofon aç/kapat",
    "ses.sistem": "Bilgisayar sesi aç/kapat", "kamera.ac_kapat": "Kamera aç/kapat",
    "anlik_kayit.kaydet": "Son 2 dakikayı kaydet", "panik": "Panik (bekleme ekranı)",
    "sahne.sec:1": "Sahne 1", "sahne.sec:2": "Sahne 2", "sahne.sec:3": "Sahne 3", "sahne.sec:4": "Sahne 4",
    "kayit.ac_kapat": "Yerel kaydı başlat/durdur", "bas_konus": "Bas-konuş tuşu",
    "kalem.tur:1": "Kalem: kalem", "kalem.tur:2": "Kalem: fosforlu", "kalem.tur:3": "Kalem: ok",
    "kalem.tur:4": "Kalem: kare", "kalem.tur:5": "Kalem: yazı", "kalem.tur:6": "Kalem: lazer",
    "kalem.geri_al": "Kalem: geri al", "kalem.temizle": "Kalem: hepsini sil",
}


def monitorler() -> list[str]:
    try:
        import mss
        with mss.mss() as sct:
            return [f"Monitör {i + 1}  ({m['width']}×{m['height']})" for i, m in enumerate(sct.monitors[1:])]
    except Exception:
        return ["Monitör 1"]


class AyarlarPenceresi(QDialog):
    def __init__(self, ayarlar, hat=None, ses=None, uygula=None, parent=None):
        """uygula(): kaydettikten sonra canlı uygulanacaklar için geri çağrı (kısayolları yeniden kaydetmek vb.)."""
        super().__init__(parent)
        self.ayarlar, self.hat, self.ses, self.uygula = ayarlar, hat, ses, uygula
        self.setWindowTitle("Ayarlar")
        self.setStyleSheet(QSS)
        self.resize(640, 560)
        sekmeler = QTabWidget()
        sekmeler.addTab(self._genel(), "Genel")
        sekmeler.addTab(self._kamera(), "Kamera")
        sekmeler.addTab(self._ses(), "Ses")
        sekmeler.addTab(self._kisayollar(), "Kısayollar")
        self.uyari = QLabel(objectName="hata")
        self.uyari.setWordWrap(True)
        dugmeler = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        dugmeler.button(QDialogButtonBox.Save).setText("Kaydet")
        dugmeler.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        dugmeler.accepted.connect(self._kaydet)
        dugmeler.rejected.connect(self.reject)
        hakkinda = dugmeler.addButton("Hakkında", QDialogButtonBox.HelpRole)
        hakkinda.clicked.connect(self._hakkinda)
        kok = QVBoxLayout(self)
        kok.addWidget(sekmeler, 1)
        kok.addWidget(self.uyari)
        kok.addWidget(dugmeler)

    def showEvent(self, olay):
        super().showEvent(olay)
        from core.platform_win import yakalamadan_gizle
        yakalamadan_gizle(int(self.winId()))  # ayarlar karşı tarafa görünmesin

    def _hakkinda(self) -> None:
        from ui.hakkinda import hakkinda_goster
        hakkinda_goster(self)

    def _al(self, yol, varsayilan=None):
        return self.ayarlar.al(yol, varsayilan)

    # ---------------- sekmeler

    def _genel(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.monitor = QComboBox()
        self.monitor.addItems(monitorler())
        self.monitor.setCurrentIndex(min(self._al("video.monitor", 0), self.monitor.count() - 1))
        self.imlec = QCheckBox("Fare imlecini yayında göster")
        self.imlec.setChecked(self._al("video.show_cursor", True))
        self.bildirim = QCheckBox("Kısayola basınca köşede bildirim göster")
        self.bildirim.setChecked(self._al("ui.toasts", True))
        self.tepsi = QCheckBox("Pencereyi kapatınca sistem tepsisinde çalışmaya devam et")
        self.tepsi.setChecked(self._al("ui.minimize_to_tray", True))
        self.bekleme = QLineEdit(self._al("standby_text", "Birazdan döneceğim"))
        self.bekleme_gorseli = QLineEdit(self._al("standby_image", ""))
        self.bekleme_gorseli.setPlaceholderText("İsteğe bağlı: resim (PNG/JPG) ya da kısa video (MP4/GIF)")
        gozat = QPushButton("Seç…", objectName="sahne")
        gozat.clicked.connect(self._gorsel_sec)
        gorsel_satiri = QHBoxLayout()
        gorsel_satiri.addWidget(self.bekleme_gorseli, 1)
        gorsel_satiri.addWidget(gozat)
        self.vurgu = QCheckBox("İmlecin etrafında halka, tıklayınca dalga efekti")
        self.vurgu.setChecked(self._al("video.cursor_highlight", False))
        self.gecis = QSpinBox()
        self.gecis.setRange(0, 2000)
        self.gecis.setSingleStep(50)
        self.gecis.setSuffix(" ms")
        self.gecis.setValue(self._al("transition_ms", 300))
        self.dnd = QCheckBox("Yayın başlarken 'Rahatsız Etme'yi açmayı hatırlat")
        self.dnd.setChecked(self._al("ui.dnd_reminder", True))
        f.addRow("Yakalanan ekran", self.monitor)
        f.addRow("", self.imlec)
        f.addRow("", self.vurgu)
        f.addRow("Bekleme ekranı yazısı", self.bekleme)
        f.addRow("Bekleme ekranı resmi/videosu", gorsel_satiri)
        f.addRow("Sahne geçiş süresi", self.gecis)
        from core.recorder import KODLAYICILAR, varsayilan_klasor
        self.kayit_klasoru = QLineEdit(self._al("record.folder", "") or "")
        self.kayit_klasoru.setPlaceholderText(str(varsayilan_klasor()))
        klasor_sec = QPushButton("Seç…", objectName="sahne")
        klasor_sec.clicked.connect(self._klasor_sec)
        klasor_satiri = QHBoxLayout()
        klasor_satiri.addWidget(self.kayit_klasoru, 1)
        klasor_satiri.addWidget(klasor_sec)
        klasor_ac = QPushButton("Aç", objectName="sahne")
        klasor_ac.setToolTip("Kayıt klasörünü Gezgin'de aç")
        klasor_ac.clicked.connect(self._klasoru_ac)
        klasor_satiri.addWidget(klasor_ac)
        self.kodlayici = QComboBox()
        self.kodlayici.addItem("Otomatik (ekran kartına göre)", "auto")
        for k in KODLAYICILAR:
            self.kodlayici.addItem(k, k)
        self.kodlayici.setCurrentIndex(max(0, self.kodlayici.findData(self._al("record.encoder", "auto"))))
        f.addRow("Kayıt klasörü", klasor_satiri)
        f.addRow("Kayıt kodlayıcısı", self.kodlayici)
        self.kayit_kamera = QCheckBox("Kayıtta kamera da açık olsun (yayın kapalıyken kayıt normalde kamerasız başlar)")
        self.kayit_kamera.setChecked(self._al("record.camera", False))
        f.addRow("", self.kayit_kamera)
        f.addRow("", self.bildirim)
        f.addRow("", self.tepsi)
        f.addRow("", self.dnd)
        return w

    def _gorsel_sec(self) -> None:
        from ui.bekleme_secici import dosya_sec
        yol = dosya_sec(self)
        if yol:
            self.bekleme_gorseli.setText(yol)

    def _klasor_sec(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        yol = QFileDialog.getExistingDirectory(self, "Kayıt klasörü", self.kayit_klasoru.text())
        if yol:
            self.kayit_klasoru.setText(yol)

    def _klasoru_ac(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from core.recorder import varsayilan_klasor
        from pathlib import Path
        klasor = Path(self.kayit_klasoru.text().strip() or varsayilan_klasor())
        try:
            klasor.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(klasor)))

    def _kamera(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.kamera_no = QSpinBox()
        self.kamera_no.setRange(0, 9)
        self.kamera_no.setValue(self._al("camera.device", 0))
        self.ayna = QCheckBox("Ayna görüntüsü (sağ-sol çevir)")
        self.ayna.setChecked(self._al("camera.mirror", False))
        self.kose = QComboBox()
        for k, ad in KOSELER:
            self.kose.addItem(ad, k)
        self.kose.setCurrentIndex(max(0, self.kose.findData(self._al("camera.corner", "bottom-right"))))
        self.boyut = QSlider(Qt.Horizontal)
        self.boyut.setRange(10, 60)
        self.boyut.setValue(round(self._al("camera.size", 0.25) * 100))
        boyut_etiket = QLabel(f"%{self.boyut.value()}")
        self.boyut.valueChanged.connect(lambda v: boyut_etiket.setText(f"%{v}"))
        satir = QHBoxLayout()
        satir.addWidget(self.boyut, 1)
        satir.addWidget(boyut_etiket)
        self.bulanik = QCheckBox("Arka planı bulanıklaştır")
        self.bulanik.setChecked(self._al("camera.blur", False))
        f.addRow("Kamera numarası (0 = ilk kamera)", self.kamera_no)
        f.addRow("", self.ayna)
        f.addRow("Köşe", self.kose)
        f.addRow("Köşedeki boyutu", satir)
        f.addRow("", self.bulanik)
        return w

    def _ses(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ses_modu = QComboBox()
        for k, ad in SES_MODLARI:
            self.ses_modu.addItem(ad, k)
        self.ses_modu.setCurrentIndex(max(0, self.ses_modu.findData(self._al("audio.system_mode", "auto"))))
        self.dahil = QLineEdit(self._al("audio.include_app", ""))
        self.dahil.setPlaceholderText("ör. valorant.exe (Görev Yöneticisi > Ayrıntılar)")
        self.haric = QLineEdit(", ".join(self._al("audio.exclude_apps", []) or []))
        self.kisma = QCheckBox("Konuşunca bilgisayar sesini otomatik kıs")
        self.kisma.setChecked(self._al("audio.ducking", False))
        f.addRow("Bilgisayar sesi", self.ses_modu)
        f.addRow("Sadece bu uygulama", self.dahil)
        f.addRow("Hariç tutulanlar", self.haric)
        self.kisma_seviye = QSlider(Qt.Horizontal)
        self.kisma_seviye.setRange(5, 80)
        self.kisma_seviye.setValue(round(self._al("audio.ducking_level", 0.3) * 100))
        kisma_etiket = QLabel(f"%{self.kisma_seviye.value()}")
        self.kisma_seviye.valueChanged.connect(lambda v: kisma_etiket.setText(f"%{v}"))
        kisma_satiri = QHBoxLayout()
        kisma_satiri.addWidget(self.kisma_seviye, 1)
        kisma_satiri.addWidget(kisma_etiket)
        f.addRow("", self.kisma)
        f.addRow("Kısınca kalan ses", kisma_satiri)
        aciklama = QLabel("Hariç tutulanlar listesinden çalışan ilk uygulamanın sesi gönderilmez; "
                          "böylece toplantıdaki kişiler kendi seslerini yankı olarak duymaz. "
                          "Meet tarayıcıda çalıştığı için yankı olursa kulaklık kullan ya da msedge.exe'yi ekle.",
                          objectName="ikincil")
        aciklama.setWordWrap(True)
        f.addRow(aciklama)
        return w

    def _kisayollar(self) -> QWidget:
        w = QWidget()
        kutu = QVBoxLayout(w)
        self.tablo = QTableWidget(0, 2)
        self.tablo.setHorizontalHeaderLabels(["İşlem", "Tuş"])
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tablo.verticalHeader().setVisible(False)
        self._tabloyu_doldur(self._al("hotkeys", {}) or {}, self._al("pen_hotkeys", {}) or {})
        sifirla = QPushButton("Varsayılanlara dön", objectName="sahne")
        sifirla.clicked.connect(lambda: self._tabloyu_doldur(
            {**VARSAYILAN_KISAYOLLAR, "bas_konus": ""}, VARSAYILAN_KALEM_TUSLARI))
        ipucu = QLabel("Örnek: F8, Ctrl+1, Ctrl+Shift+R, Alt+M, Del. Boş bırakırsan o kısayol kapanır. "
                       "Kalem tuşları sadece kalem açıkken çalışır.", objectName="ikincil")
        ipucu.setWordWrap(True)
        kutu.addWidget(self.tablo, 1)
        kutu.addWidget(ipucu)
        kutu.addWidget(sifirla, 0, Qt.AlignLeft)
        return w

    def _tabloyu_doldur(self, genel: dict, kalem: dict) -> None:
        satirlar = [("hotkeys", k, v) for k, v in genel.items()] + [("pen_hotkeys", k, v) for k, v in kalem.items()]
        self.tablo.setRowCount(len(satirlar))
        for i, (grup, komut, tus) in enumerate(satirlar):
            ad = QTableWidgetItem(KOMUT_ADLARI.get(komut, komut))
            ad.setFlags(Qt.ItemIsEnabled)
            ad.setData(Qt.UserRole, (grup, komut))
            self.tablo.setItem(i, 0, ad)
            self.tablo.setItem(i, 1, QTableWidgetItem(tus_metni(tus) if tus else ""))

    # ---------------- kaydet

    def _kisayollari_oku(self):
        gruplar = {"hotkeys": {}, "pen_hotkeys": {}}
        hatalar, kullanilan = [], {}
        for i in range(self.tablo.rowCount()):
            grup, komut = self.tablo.item(i, 0).data(Qt.UserRole)
            tus = (self.tablo.item(i, 1).text() if self.tablo.item(i, 1) else "").strip()
            if tus:
                try:
                    tus_coz(tus)
                except GecersizTus as e:
                    hatalar.append(f"{KOMUT_ADLARI.get(komut, komut)}: {e}")
                    continue
                tus = tus_metni(tus)
                anahtar = (grup, tus)
                if anahtar in kullanilan:
                    hatalar.append(f"{tus} iki kez kullanılmış ({KOMUT_ADLARI.get(kullanilan[anahtar], '')})")
                kullanilan[anahtar] = komut
            gruplar[grup][komut] = tus
        return gruplar, hatalar

    def _kaydet(self) -> None:
        gruplar, hatalar = self._kisayollari_oku()
        if hatalar:
            self.uyari.setText("Kısayollarda sorun var:\n" + "\n".join(hatalar))
            return
        a = self.ayarlar
        yeniden_baslat = (self.monitor.currentIndex() != a.al("video.monitor", 0)
                          or self.kamera_no.value() != a.al("camera.device", 0))
        a.ayarla("video.monitor", self.monitor.currentIndex())
        a.ayarla("video.show_cursor", self.imlec.isChecked())
        a.ayarla("ui.toasts", self.bildirim.isChecked())
        a.ayarla("ui.minimize_to_tray", self.tepsi.isChecked())
        a.ayarla("ui.dnd_reminder", self.dnd.isChecked())
        a.ayarla("standby_text", self.bekleme.text().strip() or "Birazdan döneceğim")
        gorsel = self.bekleme_gorseli.text().strip()
        if gorsel != a.al("standby_image", ""):
            from core.standby import uygulamaya_kopyala, video_mu
            if video_mu(gorsel):   # elle yazılan video yolu da kopyalansın (Türkçe karakter sorunu)
                try:
                    gorsel = uygulamaya_kopyala(gorsel)
                except OSError:
                    log.warning("Bekleme videosu kopyalanamadı: %s", gorsel)
        a.ayarla("standby_image", gorsel)
        a.ayarla("record.folder", self.kayit_klasoru.text().strip())
        a.ayarla("record.encoder", self.kodlayici.currentData())
        a.ayarla("record.camera", self.kayit_kamera.isChecked())
        a.ayarla("video.cursor_highlight", self.vurgu.isChecked())
        a.ayarla("audio.ducking_level", self.kisma_seviye.value() / 100)
        a.ayarla("transition_ms", self.gecis.value())
        a.ayarla("camera.device", self.kamera_no.value())
        a.ayarla("camera.mirror", self.ayna.isChecked())
        if self.kose.currentData() != a.al("camera.corner", "bottom-right"):
            a.ayarla("camera.position", None)   # köşe seçilince sürükleyerek verilen yer unutulur
        a.ayarla("camera.corner", self.kose.currentData())
        a.ayarla("camera.size", self.boyut.value() / 100)
        a.ayarla("camera.blur", self.bulanik.isChecked())
        a.ayarla("audio.system_mode", self.ses_modu.currentData())
        a.ayarla("audio.include_app", self.dahil.text().strip())
        a.ayarla("audio.exclude_apps", [x.strip() for x in self.haric.text().split(",") if x.strip()])
        a.ayarla("audio.ducking", self.kisma.isChecked())
        a.ayarla("hotkeys", gruplar["hotkeys"])
        a.ayarla("pen_hotkeys", gruplar["pen_hotkeys"])
        a.kaydet()
        self._canli_uygula()
        if self.uygula is not None:
            try:
                self.uygula()
            except Exception:
                log.exception("Ayarlar uygulanırken hata")
        if yeniden_baslat:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Ayarlar", "Monitör ve kamera değişikliği uygulamayı yeniden "
                                    "açınca geçerli olur.")
        self.accept()

    def _canli_uygula(self) -> None:
        a, hat = self.ayarlar, self.hat
        if hat is not None:
            from scenes.scene_manager import KameraYerlesimi
            hat.imlec_goster = a.al("video.show_cursor", True)
            hat.bekleme_metni = a.al("standby_text", "Birazdan döneceğim")
            hat.bekleme_gorseli = a.al("standby_image", "")
            hat.imlec_vurgusu = a.al("video.cursor_highlight", False)
            hat.kamera_yerlesimi = KameraYerlesimi.ayarlardan(a.al("camera", {}))
            hat.sahneler.gecis_sn = max(0, a.al("transition_ms", 300)) / 1000
            if hat.kamera is not None:
                hat.kamera.ayna = a.al("camera.mirror", False)
                if hasattr(hat.kamera, "bulaniklastir"):
                    hat.kamera.bulaniklastir = a.al("camera.blur", False)
        if self.ses is not None:
            self.ses.mikser.kisma_acik = a.al("audio.ducking", False)
            self.ses.mikser.kisma_seviyesi = a.al("audio.ducking_level", 0.3)
            self.ses.haric_uygulamalar = a.al("audio.exclude_apps", [])
            self.ses.sistem_ayarla(a.al("audio.system_mode", "auto"), a.al("audio.include_app", ""))

