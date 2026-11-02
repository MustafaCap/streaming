"""Sanal çıkış sorunları: kısa uyarı metni ve "Nasıl düzeltilir?" yardım penceresi.

Yardım metni uygulamanın içindedir; hiçbir sayfa açılmaz, internete bağlanılmaz.
Sorun sürdükçe tepsi menüsünde de bir satır görünür (Tepsi.sorun_ayarla).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

KAMERA_SORUNLARI = {"yok": "bulunamadı", "hata": "açılamadı", "koptu": "koptu"}


def cikis_sorunu(d) -> str:
    """Durumdan kısa sorun metni ('' = sorun yok). Duraklatılmış çıkış sorun sayılmaz."""
    kamera = KAMERA_SORUNLARI.get(getattr(d, "sanal_kamera", ""), "")
    mikrofon = getattr(d, "sanal_mikrofon", "") == "yok"
    if kamera == "bulunamadı" and mikrofon:
        return "Sanal kamera ve mikrofon bulunamadı"
    if kamera:
        return f"Sanal kamera {kamera}"
    if mikrofon:
        return "Sanal mikrofon bulunamadı"
    return ""


def yardim_metni(sorun: str = "") -> str:
    kamera = (
        "<h3>Sanal kamera (OBS Virtual Camera)</h3>"
        "<ol>"
        "<li>OBS Studio'yu kur (obsproject.com).</li>"
        "<li>OBS'yi aç, <b>Sanal Kamerayı Başlat</b>'a bir kez bas ve OBS'yi kapat.</li>"
        "<li>RizeOn birkaç saniye içinde kendiliğinden bağlanır; yeniden başlatman gerekmez.</li>"
        "</ol>"
        "<p>OBS açıkken kendi sanal kamerası çalışıyorsa RizeOn bağlanamaz: OBS'de "
        "<b>Sanal Kamerayı Durdur</b>'a bas ya da OBS'yi kapat.</p>"
    )
    mikrofon = (
        "<h3>Sanal mikrofon (VB-Cable)</h3>"
        "<ol>"
        "<li>VB-Cable'ı indir (vb-audio.com/Cable) ve zip'i bir klasöre çıkar.</li>"
        "<li><b>VBCABLE_Setup_x64.exe</b>'ye sağ tıkla, <b>Yönetici olarak çalıştır</b>, "
        "<b>Install Driver</b>'a bas.</li>"
        "<li>Bilgisayarı yeniden başlat.</li>"
        "</ol>"
        "<p>Windows'un varsayılan mikrofonu gerçek mikrofonun kalsın. <b>CABLE Output</b>'u sadece "
        "Zoom, Meet ya da Discord'un içinde mikrofon olarak seç.</p>"
    )
    if sorun.startswith("Sanal mikrofon"):
        govde = mikrofon
    elif sorun.startswith("Sanal kamera") and "mikrofon" not in sorun:
        govde = kamera
    else:
        govde = kamera + mikrofon
    return (f"<p><b>{sorun}.</b></p>" if sorun else "") + govde + (
        "<p>Görüntülü görüşme uygulamasında kamera <b>OBS Virtual Camera</b>, mikrofon "
        "<b>CABLE Output (VB-Audio Virtual Cable)</b> olmalı.</p>")


class YardimPenceresi(QDialog):
    def __init__(self, sorun: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Nasıl düzeltilir?")
        yazi = QLabel(yardim_metni(sorun))
        yazi.setWordWrap(True)
        yazi.setTextFormat(Qt.RichText)
        yazi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dugmeler = QDialogButtonBox(QDialogButtonBox.Close)
        dugmeler.button(QDialogButtonBox.Close).setText("Kapat")
        dugmeler.rejected.connect(self.reject)
        kok = QVBoxLayout(self)
        kok.setContentsMargins(20, 16, 20, 16)
        kok.addWidget(yazi)
        kok.addWidget(dugmeler)
        # Kaydırılan metnin yüksekliği genişliğe bağlı: genişliği sabitleyince pencere metne göre boylanır
        yazi.setFixedWidth(440)
        yazi.setMinimumHeight(yazi.heightForWidth(440))
        self.adjustSize()

    def showEvent(self, olay):
        super().showEvent(olay)
        from core.platform_win import yakalamadan_gizle
        yakalamadan_gizle(int(self.winId()))


def yardim_goster(sorun: str = "", parent=None) -> None:
    YardimPenceresi(sorun, parent).exec()
