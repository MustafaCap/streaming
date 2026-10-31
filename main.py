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


def komutlari_kaydet(komutlar: KomutYoneticisi, depo: DurumDeposu, hat, ses=None, mikser=None,
                     ayarlar=None) -> None:
    hatirlatildi = [False]

    def cikis_ac_kapat(_):
        acilacak = not hat.cikis_istegi
        hat.cikisi_ayarla(acilacak)
        if ses is not None:
            ses.ac(acilacak)  # görüntü ve ses birlikte başlar/durur
        if not acilacak:
            return "Yayın durduruldu"
        if ayarlar is not None and ayarlar.al("ui.dnd_reminder", True) and not hatirlatildi[0]:
            # Windows bildirimleri ekran yakalamaya girer ve başka uygulamaların penceresini
            # gizlemenin resmi yolu yok; en güvenlisi Rahatsız Etme modu (brif 14. özellik).
            hatirlatildi[0] = True
            return "Yayın başladı · bildirimler görünmesin: Rahatsız Etme'yi aç (Win+N)"
        return "Yayın başlatılıyor"

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

    def panik(_):
        hat.panik = not hat.panik
        if mikser is not None:
            mikser.ana_sessiz = hat.panik  # panikte ses de gitmez
        depo.guncelle(panik=hat.panik)
        return "Panik: bekleme ekranı, ses kapalı" if hat.panik else "Panik kapandı"

    komutlar.kaydet("panik", "Panik: bekleme ekranına geç", panik)

    if mikser is not None:
        def susturma(anahtar, durum_alani, ayar, ad):
            def calistir(_):
                kanal = mikser.kanallar[anahtar]
                kanal.sessiz = not kanal.sessiz
                depo.guncelle(**{durum_alani: kanal.sessiz})
                if ayarlar is not None:
                    ayarlar.ayarla(ayar, kanal.sessiz)
                    ayarlar.kaydet()
                return f"{ad} {'kapandı' if kanal.sessiz else 'açıldı'}"
            return calistir

        komutlar.kaydet("ses.mikrofon", "Mikrofonu aç/kapat",
                        susturma("mikrofon", "mikrofon_sessiz", "audio.mic_muted", "Mikrofon"))
        komutlar.kaydet("ses.sistem", "Bilgisayar sesini aç/kapat",
                        susturma("sistem", "sistem_sessiz", "audio.system_muted", "Bilgisayar sesi"))


def main() -> int:
    logging_setup.kur()
    log.info("Uygulama başlıyor")
    ayarlar = Ayarlar()

    from PySide6.QtWidgets import QApplication

    from capture.screen import EkranKaynagi
    from capture.webcam import WebcamKaynagi
    from core.audio_engine import SesMotoru
    from core.audio_mixer import SesKaristirici
    from scenes.scene_manager import KameraYerlesimi, SahneYoneticisi, sahneleri_oku
    from core.video_pipeline import VideoHatti
    from overlay.drawing import CizimDeposu
    from outputs.virtualcam import SanalKameraCikisi
    from ui.icons import uygulama_ikonu
    from ui.main_window import AnaPencere
    from ui.shell import UygulamaKabugu

    app = QApplication(sys.argv)
    app.setApplicationName("Yayın Uygulaması")
    app.setWindowIcon(uygulama_ikonu())
    app.setQuitOnLastWindowClosed(False)  # pencere kapanınca tepside çalışmaya devam

    w, h, fps = ayarlar.al("video.width"), ayarlar.al("video.height"), ayarlar.al("video.fps")
    depo = DurumDeposu()
    komutlar = KomutYoneticisi()
    cizimler = CizimDeposu()
    hat = VideoHatti(depo, cizimler=cizimler,
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
                     kamera_acik=ayarlar.al("camera.enabled", True),
                     imlec_vurgusu=ayarlar.al("video.cursor_highlight", False),
                     bekleme_gorseli=ayarlar.al("standby_image", ""))
    mikser = SesKaristirici()
    mikser.kanal_ekle("mikrofon", "Mikrofon", ayarlar.al("audio.mic_gain", 1.0), ayarlar.al("audio.mic_muted", False))
    mikser.kanal_ekle("sistem", "Bilgisayar sesi", ayarlar.al("audio.system_gain", 0.7),
                      ayarlar.al("audio.system_muted", False))
    mikser.kisma_acik = ayarlar.al("audio.ducking", False)
    mikser.kisma_seviyesi = ayarlar.al("audio.ducking_level", 0.3)
    depo.guncelle(mikrofon_sessiz=mikser.kanallar["mikrofon"].sessiz,
                  sistem_sessiz=mikser.kanallar["sistem"].sessiz)
    ses = SesMotoru(depo, mikser, mikrofon_adi=ayarlar.al("audio.mic_device", ""),
                    sistem_modu=ayarlar.al("audio.system_mode", "auto"),
                    haric_uygulamalar=ayarlar.al("audio.exclude_apps", None),
                    dahil_uygulama=ayarlar.al("audio.include_app", ""))
    komutlari_kaydet(komutlar, depo, hat, ses, mikser, ayarlar)
    komutlar.dinle(lambda ad, mesaj: log.info("Komut: %s%s", ad, f" ({mesaj})" if mesaj else ""))

    pencere = AnaPencere(depo, komutlar, hat, onizleme_fps=ayarlar.al("ui.preview_fps", 15),
                         ses=ses, mikser=mikser, ayarlar=ayarlar)
    kabuk = UygulamaKabugu(app, pencere, komutlar, depo, hat, ayarlar, cizimler, ses)
    app.setQuitOnLastWindowClosed(not pencere.tepsiye_kucul)

    from core.hotkeys import BasKonus

    def bas_konus_degisti(basili: bool) -> None:
        mikser.kanallar["mikrofon"].kapi = basili or not bas_konus.aktif
        depo.guncelle(bas_konus=bas_konus.aktif, konusuyor=basili)

    bas_konus = BasKonus(bas_konus_degisti)
    kabuk.bas_konus_kur(bas_konus, bas_konus_degisti)
    hat.baslat()
    ses.baslat()
    kabuk.baslat()
    pencere.show()
    kod = app.exec()
    bas_konus.durdur()
    kabuk.durdur()
    hat.durdur()
    ses.durdur()
    log.info("Uygulama kapandı")
    return kod


if __name__ == "__main__":
    sys.exit(main())
