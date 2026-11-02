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


def klasorde_goster(dosya) -> None:
    """Dosyayı Gezgin'de seçili olarak gösterir (Windows dışında klasörü açar)."""
    import subprocess
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(dosya)])
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dosya.parent)))
    except Exception:
        log.exception("Klasör açılamadı")


def dosyayi_ac(dosya) -> None:
    """Dosyayı varsayılan programla açar (video oynatıcı, resim görüntüleyici)."""
    try:
        if sys.platform == "win32":
            os.startfile(str(dosya))  # noqa: S606 (yerel dosya)
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dosya)))
    except Exception:
        log.exception("Dosya açılamadı")


def ekran_goruntusu_kaydet(kare, klasor, zaman=None):
    """Çıkış karesini (çizimler dahil) PNG olarak kaydeder. PIL ile yazılır: Türkçe karakterli yollar da çalışır."""
    from datetime import datetime
    from pathlib import Path

    import numpy as np
    from PIL import Image
    klasor = Path(klasor)
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / (zaman or datetime.now()).strftime("Goruntu_%Y-%m-%d_%H-%M-%S.png")
    sira = 2
    while hedef.exists():   # aynı saniyede iki kez basılırsa üzerine yazma
        hedef = hedef.with_name(f"{hedef.stem.split('~')[0]}~{sira}.png")
        sira += 1
    Image.fromarray(np.ascontiguousarray(kare[:, :, :3])).save(hedef, "PNG")
    return hedef


def goruntu_klasoru(ayarlar):
    from pathlib import Path

    from core.recorder import varsayilan_klasor
    klasor = ayarlar.al("screenshot.folder", "") if ayarlar is not None else ""
    if klasor:
        return Path(klasor)
    kayit = ayarlar.al("record.folder", "") if ayarlar is not None else ""
    return Path(kayit) if kayit else varsayilan_klasor()


def komutlari_kaydet(komutlar: KomutYoneticisi, depo: DurumDeposu, hat, ses=None, mikser=None,
                     ayarlar=None, kayitci=None, bildir=None, tekrar=None) -> None:
    def cikis_ac_kapat(_):
        """Sanal çıkış (OBS Virtual Camera + VB-Cable) arka planda hep açıktır; tepsiden duraklatılabilir."""
        acilacak = not hat.cikis_istegi
        hat.cikisi_ayarla(acilacak)
        if ses is not None:
            ses.ac(acilacak)  # görüntü ve ses birlikte durur/sürer
        return "Sanal çıkış açıldı" if acilacak else "Sanal çıkış duraklatıldı · kamera ve mikrofon gönderilmiyor"

    komutlar.kaydet("cikis.ac_kapat", "Sanal çıkışı duraklat/sürdür", cikis_ac_kapat)

    def sahne_sec(param):
        try:
            numara = int(param)
        except (TypeError, ValueError):
            return "Sahne numarası gerekli"
        if not hat.sahne_sec(numara - 1):
            return f"{numara}. sahne yok"
        return f"Sahne: {hat.sahneler.aktif.ad}"

    komutlar.kaydet("sahne.sec", "Sahne seç (1-9)", sahne_sec)

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
            depo.guncelle(kayit="hata" if hata and dosya is None else "kapalı", kayit_duraklatildi=False)
            if ses is not None:
                ses.kayit_icin_ac(False)
            if bildir is not None:
                if dosya:
                    bildir("Kayıt kaydedildi", eylem=("Klasörde göster", lambda: klasorde_goster(dosya)))
                else:
                    bildir(f"Kayıt kaydedilemedi: {hata}")

        def kayit_ac_kapat(_):
            if kayitci.kayitta:
                if mikser is not None:
                    mikser.dinleyici_sil(kayitci.ses_yaz)
                kayitci.durdur(kayit_bitti)
                depo.guncelle(kayit_duraklatildi=False)
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
                mikser.dinleyici_ekle(kayitci.ses_yaz)
            if ses is not None:
                ses.kayit_icin_ac(True)
            depo.guncelle(kayit="açık")
            return "Kayıt başladı"

        komutlar.kaydet("kayit.ac_kapat", "Yerel kaydı başlat/durdur", kayit_ac_kapat)
        komutlar.kaydet("kayit.durdur", "Yerel kaydı durdur",
                        lambda p: kayit_ac_kapat(p) if kayitci.kayitta else None)

        def kayit_duraklat(_):
            if not kayitci.kayitta:
                return "Kayıt açık değil"
            if kayitci.duraklatildi:
                if not kayitci.devam_et():
                    return f"Kayda devam edilemedi: {kayitci.son_hata}"
                depo.guncelle(kayit_duraklatildi=False)
                return "Kayda devam ediliyor"
            kayitci.duraklat()
            depo.guncelle(kayit_duraklatildi=True)
            return "Kayıt duraklatıldı · devam etmek için tekrar bas"

        komutlar.kaydet("kayit.duraklat", "Kaydı duraklat/devam et", kayit_duraklat)

    def ekran_goruntusu(_):
        try:
            dosya = ekran_goruntusu_kaydet(hat.son_kare(), goruntu_klasoru(ayarlar))
        except Exception as e:
            log.exception("Ekran görüntüsü kaydedilemedi")
            return f"Ekran görüntüsü kaydedilemedi: {e}"
        if bildir is not None:
            bildir("Ekran görüntüsü kaydedildi", eylem=("Aç", lambda: dosyayi_ac(dosya)))
        return None

    komutlar.kaydet("ekran.goruntusu", "Ekran görüntüsü al", ekran_goruntusu)

    if tekrar is not None:
        def tekrar_bitti(dosya, hata):
            if bildir is None:
                return
            if dosya:
                from core.anlik_tekrar import sure_etiketi
                bildir(f"{sure_etiketi(tekrar.sure_sn)} kaydedildi", eylem=("Aç", lambda: dosyayi_ac(dosya)))
            else:
                bildir(f"Tekrar kaydedilemedi: {hata}")

        def tekrar_kaydet(_):
            if not tekrar.acik:
                return "Anlık tekrar kapalı · Ayarlar > Genel'den açabilirsin"
            klasor = (ayarlar.al("record.folder", "") if ayarlar is not None else "") or None
            if not tekrar.kaydet(klasor, tekrar_bitti):
                return tekrar.son_hata
            return None

        komutlar.kaydet("anlik_kayit.kaydet", "Son 2 dakikayı kaydet", tekrar_kaydet)

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
    from ui import gizlilik
    from ui.theme import QSS
    gizlilik.kur(app)        # uygulamanın hiçbir penceresi (menüler, bildirimler dahil) yakalamaya girmez
    app.setStyleSheet(QSS)   # tüm pencereler aynı gri tema

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
                     sahneler=SahneYoneticisi(sahneleri_oku(ayarlar.al("scenes", []),
                                                            ayarlar.al("video.cursor_highlight", False)),
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
    from core.gurultu import GurultuAzaltici
    gurultu = GurultuAzaltici(ayarlar.al("audio.noise_suppression", False))
    ses.gurultu = gurultu
    from core.recorder import Kayitci
    kayitci = Kayitci(w, h, fps, ayarlar.al("record.folder", "") or None, ayarlar.al("record.encoder", "auto"))
    hat.kayitci = kayitci
    from core.anlik_tekrar import AnlikTekrar
    tekrar = AnlikTekrar(w, h, fps, ayarlar.al("record.replay_seconds", 120), ayarlar.al("record.encoder", "auto"))
    hat.tekrar = tekrar
    mikser.dinleyici_ekle(tekrar.ses_yaz)
    # Sahne ve kaynak değişiklikleri hemen kaydedilir (uygulama çökse de kaybolmaz)
    hat.sahneler.degisti = lambda: ayarlar.ayarla("scenes", hat.sahneler.sozluk_listesi())
    kabuk_ref = []

    def bildir(mesaj, eylem=None):
        log.info(mesaj)
        if kabuk_ref:
            kabuk_ref[0].bildir(mesaj, eylem=eylem)

    komutlari_kaydet(komutlar, depo, hat, ses, mikser, ayarlar, kayitci, bildir, tekrar)
    komutlar.dinle(lambda ad, mesaj: log.info("Komut: %s%s", ad, f" ({mesaj})" if mesaj else ""))

    pencere = AnaPencere(depo, komutlar, hat, onizleme_fps=ayarlar.al("ui.preview_fps", 15),
                         ses=ses, mikser=mikser, ayarlar=ayarlar, gurultu=gurultu)
    kabuk = UygulamaKabugu(app, pencere, komutlar, depo, hat, ayarlar, cizimler, ses)
    kabuk_ref.append(kabuk)
    app.setQuitOnLastWindowClosed(not pencere.tepsiye_kucul)

    from core.hotkeys import BasKonus

    def bas_konus_degisti(basili: bool) -> None:
        mikser.kanallar["mikrofon"].kapi = basili or not bas_konus.aktif
        depo.guncelle(bas_konus=bas_konus.aktif, konusuyor=basili)

    bas_konus = BasKonus(bas_konus_degisti)
    kabuk.bas_konus_kur(bas_konus, bas_konus_degisti)
    # Sanal çıkış (OBS Virtual Camera + VB-Cable) arka planda hep açık; arayüzde düğmesi yok.
    # Sürücü yoksa video hattı birkaç saniyede bir yeniden dener; tepsiden duraklatılabilir.
    hat.cikisi_ayarla(True)
    hat.baslat()
    ses.baslat()
    ses.ac(True)
    if ayarlar.al("record.replay", True):
        # FFmpeg ilk açılışta kodlayıcı denemesi yapar; arayüzü bekletmesin
        threading.Thread(target=tekrar.baslat, name="tekrar-baslat", daemon=True).start()
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
    tekrar.durdur()
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
    "core.audio_engine", "scenes.scene_manager", "core.platform_win", "capture.window", "ui.pencere_secici",
    "ui.gizlilik", "ui.icons", "PySide6.QtSvg", "ui.bilesenler", "ui.sahne_panelleri", "scenes.kaynaklar",
    "core.sistem_olcer", "core.ses_modlari", "core.gurultu", "core.anlik_tekrar", "ui.yardim", "ui.logo_veri",
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
        from core.gurultu import GurultuAzaltici, dll_yolu
        if getattr(sys, "frozen", False) and not GurultuAzaltici(True).acik:
            raise RuntimeError(f"RNNoise yüklenemedi: {dll_yolu()}")
        sonuc, kod = (f"tamam · sürüm {SURUM} · {len(DUMAN_MODULLERI)} modül · ffmpeg: {ffmpeg} · "
                      f"rnnoise: {dll_yolu()}\n", 0)
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
