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


def main() -> int:
    logging_setup.kur()
    log.info("Uygulama başlıyor")
    ayarlar = Ayarlar()

    from PySide6.QtWidgets import QApplication

    from capture.screen import EkranKaynagi
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
                     imlec_goster=ayarlar.al("video.show_cursor", True))
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
