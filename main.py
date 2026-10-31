"""Yayın Uygulaması - başlangıç noktası.

Çalıştırma:  python main.py
"""

import logging
import sys

from core import network_guard

network_guard.kur()  # her şeyden önce: uygulama hiçbir dış bağlantı açamaz

from core import logging_setup  # noqa: E402
from core.commands import KomutYoneticisi  # noqa: E402
from core.settings import Ayarlar  # noqa: E402
from core.state import DurumDeposu  # noqa: E402

log = logging.getLogger("main")


def komutlari_kaydet(komutlar: KomutYoneticisi, depo: DurumDeposu, hat) -> None:
    def cikis_ac_kapat(_):
        acilacak = not hat.cikis_istegi
        hat.cikisi_ayarla(acilacak)
        return "Yayın başlatılıyor" if acilacak else "Yayın durduruldu"

    komutlar.kaydet("cikis.ac_kapat", "Yayını başlat/durdur", cikis_ac_kapat)

    def sahne_sec(param):
        try:
            numara = int(param)
        except (TypeError, ValueError):
            return "Sahne numarası gerekli"
        if not hat.sahne_sec(numara - 1):
            return f"{numara}. sahne yok"
        return f"Sahne: {hat.sahneler.aktif.ad}"

    komutlar.kaydet("sahne.sec", "Sahne seç (1-4)", sahne_sec)

    def kamera_ac_kapat(_):
        if hat.kamera is None:
            return "Kamera yok"
        acilacak = not hat.kamera_istegi
        hat.kamerayi_ayarla(acilacak)
        return "Kamera açıldı" if acilacak else "Kamera kapatıldı"

    komutlar.kaydet("kamera.ac_kapat", "Kamerayı aç/kapat", kamera_ac_kapat)


def main() -> int:
    logging_setup.kur()
    log.info("Uygulama başlıyor")
    ayarlar = Ayarlar()

    from PySide6.QtWidgets import QApplication

    from capture.screen import EkranKaynagi
    from capture.webcam import WebcamKaynagi
    from scenes.scene_manager import KameraYerlesimi, SahneYoneticisi, sahneleri_oku
    from core.video_pipeline import VideoHatti
    from outputs.virtualcam import SanalKameraCikisi
    from ui.main_window import AnaPencere

    app = QApplication(sys.argv)
    app.setApplicationName("Yayın Uygulaması")

    w, h, fps = ayarlar.al("video.width"), ayarlar.al("video.height"), ayarlar.al("video.fps")
    depo = DurumDeposu()
    komutlar = KomutYoneticisi()
    hat = VideoHatti(depo,
                     kaynak=EkranKaynagi(ayarlar.al("video.monitor", 0), ayarlar.al("video.capture_backend", "dxcam")),
                     cikis=SanalKameraCikisi(w, h, fps),
                     genislik=w, yukseklik=h, fps=fps,
                     imlec_goster=ayarlar.al("video.show_cursor", True),
                     kamera=WebcamKaynagi(ayarlar.al("camera.device", 0), w, h, fps,
                                          ayna=ayarlar.al("camera.mirror", False)),
                     sahneler=SahneYoneticisi(sahneleri_oku(ayarlar.al("scenes", [])),
                                              ayarlar.al("transition_ms", 300)),
                     kamera_yerlesimi=KameraYerlesimi.ayarlardan(ayarlar.al("camera", {})),
                     bekleme_metni=ayarlar.al("standby_text", "Birazdan döneceğim"),
                     kamera_acik=ayarlar.al("camera.enabled", True))
    komutlari_kaydet(komutlar, depo, hat)
    komutlar.dinle(lambda ad, mesaj: log.info("Komut: %s%s", ad, f" ({mesaj})" if mesaj else ""))

    pencere = AnaPencere(depo, komutlar, hat, onizleme_fps=ayarlar.al("ui.preview_fps", 15))
    hat.baslat()
    pencere.show()
    kod = app.exec()
    log.info("Uygulama kapandı")
    return kod


if __name__ == "__main__":
    sys.exit(main())
