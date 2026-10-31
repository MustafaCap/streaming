"""RizeOn - başlangıç noktası.

Çalıştırma:  python main.py
"""

import logging
import os
import sys
import threading

from core import network_guard

network_guard.kur()  # her şeyden önce: uygulama hiçbir dış bağlantı açamaz

from core import logging_setup  # noqa: E402
from core.commands import KomutYoneticisi  # noqa: E402
from core.settings import Ayarlar  # noqa: E402
from core.state import DurumDeposu  # noqa: E402

log = logging.getLogger("main")

KAPANIS_SURESI_SN = 15


def _zorla_cik(kod: int) -> None:
    logging.shutdown()   # log dosyasına yazılanlar kaybolmasın
    os._exit(kod)


def kapanis_bekcisi(sn: float = KAPANIS_SURESI_SN, cik=_zorla_cik) -> threading.Timer:
    """Kapanış takılırsa (bir sürücü cevap vermezse) süreç arkada kalmasın: kamera ve mikrofon açık kalırdı."""
    def zorla():
        log.error("Kapanış %s saniyede bitmedi; uygulama zorla kapatılıyor", sn)
        cik(1)
    zamanlayici = threading.Timer(sn, zorla)
    zamanlayici.daemon = True
    zamanlayici.start()
    return zamanlayici


def komutlari_kaydet(komutlar: KomutYoneticisi, depo: DurumDeposu, hat, ses=None, mikser=None,
                     ayarlar=None, kayitci=None, bildir=None) -> None:
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

    if kayitci is not None:
        def kayit_bitti(dosya, hata):
            depo.guncelle(kayit="hata" if hata and dosya is None else "kapalı")
            if ses is not None:
                ses.kayit_icin_ac(False)
            if bildir is not None:
                bildir(f"Kayıt kaydedildi: {dosya.name} · 📁 Kayıtlar düğmesiyle aç" if dosya else f"Kayıt kaydedilemedi: {hata}")

        kamera_onceki = [None]   # kayıt için kamerayı kapattıysak eski hâli (kayıt bitince geri gelir)

        def kayit_ac_kapat(_):
            if kayitci.kayitta:
                if mikser is not None:
                    mikser.kayit_dinleyici = None
                kayitci.durdur(kayit_bitti)
                if kamera_onceki[0] is not None:
                    hat.kamerayi_ayarla(kamera_onceki[0])
                    kamera_onceki[0] = None
                return "Kayıt durdu, dosya hazırlanıyor"
            if ayarlar is not None:
                from pathlib import Path
                klasor = ayarlar.al("record.folder", "")
                if klasor:
                    kayitci.klasor = Path(klasor)
                kayitci.kodlayici_tercihi = ayarlar.al("record.encoder", "auto")
            if not kayitci.baslat():
                depo.guncelle(kayit="hata")
                return f"Kayıt başlamadı: {kayitci.son_hata}"
            if mikser is not None:
                mikser.kayit_dinleyici = kayitci.ses_yaz
            if ses is not None:
                ses.kayit_icin_ac(True)
            depo.guncelle(kayit="açık")
            kamerasiz = (ayarlar is not None and not ayarlar.al("record.camera", False)
                         and not hat.cikis_istegi and hat.kamera_istegi)
            if kamerasiz:
                # Yayın kapalıyken kayıt kamerasız başlar (F10 ile açılabilir); yayındaysan görüntü değişmez.
                kamera_onceki[0] = True
                hat.kamerayi_ayarla(False)
            return f"Kayıt başladı{' (kamerasız)' if kamerasiz else ''} · {kayitci.klasor}"

        komutlar.kaydet("kayit.ac_kapat", "Yerel kaydı başlat/durdur", kayit_ac_kapat)
        komutlar.kaydet("kayit.durdur", "Yerel kaydı durdur",
                        lambda p: kayit_ac_kapat(p) if kayitci.kayitta else None)

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
    from core.surum import SURUM
    from core.tek_kopya import TekKopya
    tek = TekKopya()
    if not tek.ilk:
        # Uygulama zaten çalışıyor (belki tepside): yenisini açma, onun penceresini öne getir.
        log.info("Uygulama zaten açık; çalışan pencere öne getiriliyor")
        tek.digerini_one_getir()
        return 0
    log.info("Uygulama başlıyor (sürüm %s)", SURUM)
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
    app.setApplicationName("RizeOn")
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
                                          ayna=ayarlar.al("camera.mirror", False),
                                          bulaniklastir=ayarlar.al("camera.blur", False)),
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
    from core.recorder import Kayitci
    kayitci = Kayitci(w, h, fps, ayarlar.al("record.folder", "") or None, ayarlar.al("record.encoder", "auto"))
    hat.kayitci = kayitci
    kabuk_ref = []

    def bildir(mesaj):
        log.info(mesaj)
        if kabuk_ref:
            kabuk_ref[0].bildir(mesaj)

    komutlari_kaydet(komutlar, depo, hat, ses, mikser, ayarlar, kayitci, bildir)
    komutlar.dinle(lambda ad, mesaj: log.info("Komut: %s%s", ad, f" ({mesaj})" if mesaj else ""))

    pencere = AnaPencere(depo, komutlar, hat, onizleme_fps=ayarlar.al("ui.preview_fps", 15),
                         ses=ses, mikser=mikser, ayarlar=ayarlar)
    kabuk = UygulamaKabugu(app, pencere, komutlar, depo, hat, ayarlar, cizimler, ses)
    kabuk_ref.append(kabuk)
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
    tek.dinle(lambda: kabuk.komut_gonder("pencere.goster"))

    def kayit_hatasi(mesaj):
        # Disk doldu / FFmpeg kapandı: kaydı durdur, o ana kadarki kısım kaydedilir.
        bildir(f"Kayıt durduruldu: {mesaj}")
        kabuk.komut_gonder("kayit.durdur")

    kayitci.hata_olunca = kayit_hatasi

    def yarim_kayitlari_kurtar():
        from core.recorder import ffmpeg_bul, yarim_kayitlari_kurtar as kurtar
        try:
            for dosya in kurtar(kayitci.klasor, kayitci.ffmpeg or ffmpeg_bul()):
                bildir(f"Yarım kalan kayıt kurtarıldı: {dosya.name}")
        except Exception:
            log.exception("Yarım kayıtlar kurtarılamadı")

    threading.Thread(target=yarim_kayitlari_kurtar, name="kayit-kurtar", daemon=True).start()
    pencere.show()
    kod = app.exec()
    if kayitci.kayitta:
        bitti = threading.Event()
        kayitci.durdur(lambda d, h: bitti.set())
        bitti.wait(60)  # kapanırken kayıt yarım kalmasın
    kapanis_bekcisi()
    bas_konus.durdur()
    kabuk.durdur()
    hat.durdur()
    ses.durdur()
    tek.kapat()
    log.info("Uygulama kapandı")
    return kod


def acilis_hatasi_goster(hata: BaseException) -> None:
    """Açılışta bir şey bozulursa exe sessizce kapanmasın: kullanıcıya söyle, log klasörünü aç."""
    from core import paths
    try:
        klasor = paths.log_klasoru()
    except Exception:
        klasor = None
    metin = (f"RizeOn açılamadı.\n\n{type(hata).__name__}: {hata}\n\n"
             "Ayrıntılar log dosyasında yazıyor"
             + (f":\n{klasor}\n\nLog klasörü açılsın mı?" if klasor else "."))
    if sys.platform != "win32":
        print(metin, file=sys.stderr)
        return
    import ctypes
    MB_YESNO, MB_OK, MB_ICONERROR, IDYES = 0x4, 0x0, 0x10, 6
    cevap = ctypes.windll.user32.MessageBoxW(None, metin, "RizeOn", (MB_YESNO if klasor else MB_OK) | MB_ICONERROR)
    if klasor and cevap == IDYES:
        os.startfile(klasor)


# Paketlenmiş exe'de yüklenebilmesi gereken modüller (CI'daki "Modüller Windows'ta yükleniyor mu?" ile aynı)
DUMAN_MODULLERI = (
    "PySide6.QtWidgets", "numpy", "cv2", "pyaudiowpatch", "comtypes", "psutil", "mss",
    "ui.main_window", "ui.mixer_panel", "ui.shell", "ui.tray", "ui.toast", "ui.region_overlay",
    "ui.drawing_overlay", "ui.mini_bar", "ui.settings_dialog", "ui.hakkinda", "outputs.obs_kamera",
    "outputs.virtualcam", "overlay.cursor", "overlay.drawing", "core.recorder", "capture.background_blur",
    "capture.region", "core.hotkeys", "capture.screen", "capture.webcam", "capture.app_audio",
    "core.audio_engine", "scenes.scene_manager", "core.platform_win",
)


def duman_testi(sonuc_yolu: str) -> int:
    """`RizeOn.exe --duman-testi sonuc.txt`: pencere açmadan exe'nin çalıştığını denetler (CI).

    Paketlenmiş exe'de eksik DLL / modül varsa burada çıkar. Sonucu dosyaya yazar, çünkü
    pencereli exe'nin konsolu yok. Hata penceresi göstermez (CI'da kimse kapatamaz)."""
    import importlib
    import traceback
    try:
        for ad in DUMAN_MODULLERI:
            importlib.import_module(ad)
        from core.recorder import ffmpeg_bul
        from core.surum import SURUM
        ffmpeg = ffmpeg_bul()
        if ffmpeg is None:
            raise RuntimeError("ffmpeg\\ffmpeg.exe bulunamadı")
        sonuc, kod = f"tamam · sürüm {SURUM} · {len(DUMAN_MODULLERI)} modül · ffmpeg: {ffmpeg}\n", 0
    except BaseException:
        sonuc, kod = traceback.format_exc(), 1
    with open(sonuc_yolu, "w", encoding="utf-8") as f:
        f.write(sonuc)
    return kod


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--duman-testi":
        sys.exit(duman_testi(sys.argv[2]))
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:   # açılışta ya da kapanışta beklenmedik hata
        log.critical("Uygulama hatayla kapandı", exc_info=True)
        acilis_hatasi_goster(e)
        sys.exit(1)
