import sys
import threading
import time
import types

import numpy as np
import pytest

from core.audio_mixer import ORNEKLEME, SesKaristirici, Tampon, db
from core.state import DurumDeposu
from tests.test_video_pipeline import _bekle


# ------------------------------------------------------------------ mikser (saf numpy)

def test_tampon_on_tampon_ve_alt_tasma():
    t = Tampon()
    t.yaz(np.full((480, 1), 0.5, np.float32))
    assert (t.oku(480) == 0).all()          # 10 ms < 40 ms ön tampon: henüz sessizlik
    t.yaz(np.full((1920, 1), 0.5, np.float32))
    blok = t.oku(480)
    assert blok.shape == (480, 2) and np.allclose(blok, 0.5)  # mono -> stereo
    t.oku(2000)                               # kalan 1920, 2000 istenirse yetmez -> alt taşma
    assert t.alt_tasma == 1


def test_tampon_eski_sesi_atar_ve_hiz_donusturur():
    t = Tampon()
    t.yaz(np.zeros((ORNEKLEME, 2), np.float32))  # 1 sn yaz, en fazla 0,25 sn tutulur
    assert len(t._veri) == int(ORNEKLEME * Tampon.EN_FAZLA_SN)
    t2 = Tampon(giris_hizi=44100)
    t2.yaz(np.zeros((441, 2), np.float32))
    assert len(t2._veri) == 480


def _dolu(kanal, deger, n=4800):
    kanal.tampon.yaz(np.full((n, 2), deger, np.float32))
    kanal.bagli = True


def test_karistirma_kazanc_susturma_ve_sinirlama():
    m = SesKaristirici()
    mik, sis = m.kanal_ekle("mikrofon", "Mikrofon"), m.kanal_ekle("sistem", "Bilgisayar sesi", kazanc=0.5)
    _dolu(mik, 0.2)
    _dolu(sis, 0.4)
    blok = m.karistir(480)
    assert np.allclose(blok, 0.2 + 0.2)
    assert m.seviyeler()["sistem"] == pytest.approx(0.2)

    mik.sessiz = True
    assert np.allclose(m.karistir(480), 0.2)
    assert m.seviyeler()["mikrofon"] == 0

    mik.sessiz, mik.kazanc = False, 5.0     # kazanç 2'de sınırlanır
    assert mik.kazanc == 2.0
    blok = m.karistir(480)
    assert blok.max() == pytest.approx(0.6)  # 0.2*2 + 0.4*0.5


def test_sinirlayici_kirpar():
    m = SesKaristirici()
    a, b = m.kanal_ekle("a", "A", kazanc=2.0), m.kanal_ekle("b", "B", kazanc=2.0)
    _dolu(a, 0.4)
    _dolu(b, 0.4)
    blok = m.karistir(480)
    assert blok.max() == pytest.approx(1.0) and m.cikis_seviyesi == 1.0


def test_db():
    assert db(1.0) == pytest.approx(0.0)
    assert db(0.0) == -60.0


# ------------------------------------------------------------------ ses motoru (sahte PyAudio)

class _SahteAkis:
    def __init__(self, cagri, cikis, kanal, kapanacak):
        self.cagri, self.cikis, self.kanal = cagri, cikis, kanal
        self._aktif = True
        self.kapanacak = kapanacak
        self._is = threading.Thread(target=self._dongu, daemon=True)
        self._is.start()

    def _dongu(self):
        while self._aktif:
            if self.kapanacak.is_set():  # cihaz çıkarıldı: geri çağrılar durur
                time.sleep(0.01)
                continue
            veri = None if self.cikis else np.full((480, self.kanal), 0.3, np.float32).tobytes()
            sonuc = self.cagri(veri, 480, None, 0)
            if self.cikis:
                _SahteAkis.son_cikis = np.frombuffer(sonuc[0], np.float32)
            time.sleep(0.01)

    def is_active(self):
        return self._aktif

    def stop_stream(self):
        self._aktif = False

    def close(self):
        self._aktif = False


def _sahte_pyaudio(cihazlar, varsayilan_mik, kopma):
    mod = types.ModuleType("pyaudiowpatch")
    mod.paFloat32, mod.paContinue = 1, 0
    mod.acilanlar = []

    class PyAudio:
        def get_device_count(self):
            return len(cihazlar)

        def get_device_info_by_index(self, i):
            return cihazlar[i]

        def get_host_api_info_by_index(self, i):
            return {"name": ["MME", "Windows WASAPI"][i]}

        def get_default_input_device_info(self):
            return next(d for d in cihazlar if d["name"] == varsayilan_mik)

        def get_default_wasapi_loopback(self):
            return next(d for d in cihazlar if "Loopback" in d["name"])

        def open(self, output=False, input=False, channels=2, input_device_index=None,
                 output_device_index=None, stream_callback=None, **kw):
            idx = output_device_index if output else input_device_index
            mod.acilanlar.append(cihazlar[idx]["name"])
            return _SahteAkis(stream_callback, output, channels, kopma)

        def terminate(self):
            pass

    mod.PyAudio = PyAudio
    return mod


def _cihaz(i, ad, giris=0, cikis=0, host=0, hiz=48000):
    return {"index": i, "name": ad, "maxInputChannels": giris, "maxOutputChannels": cikis,
            "hostApi": host, "defaultSampleRate": hiz}


@pytest.fixture
def motor_kur(monkeypatch):
    from core.audio_engine import SesMotoru
    olusturulan = []

    def kur(cihazlar, varsayilan_mik, **kw):
        kopma = threading.Event()
        mod = _sahte_pyaudio(cihazlar, varsayilan_mik, kopma)
        monkeypatch.setitem(sys.modules, "pyaudiowpatch", mod)
        depo, mikser = DurumDeposu(), SesKaristirici()
        mikser.kanal_ekle("mikrofon", "Mikrofon")
        mikser.kanal_ekle("sistem", "Bilgisayar sesi")
        motor = SesMotoru(depo, mikser, **kw)
        olusturulan.append(motor)
        return motor, depo, mikser, mod, kopma

    yield kur
    for m in olusturulan:
        m.durdur()


CIHAZLAR = [
    _cihaz(0, "Microsoft Ses Eşleyicisi - Input", giris=2),
    _cihaz(1, "CABLE Output (VB-Audio Virtual", giris=2),
    _cihaz(2, "Mikrofon (Realtek(R) Audio)", giris=2),
    _cihaz(3, "CABLE Input (VB-Audio Virtual C", cikis=2),
    _cihaz(4, "Hoparlör (Realtek) [Loopback]", giris=2, host=1, hiz=44100),
]


def test_varsayilan_mikrofon_cable_ise_gercek_mikrofonu_secer(motor_kur):
    motor, depo, mikser, mod, _ = motor_kur(CIHAZLAR, "CABLE Output (VB-Audio Virtual", sistem_modu="all")
    motor.baslat()
    assert _bekle(lambda: motor.mikrofonlar() == ["Mikrofon (Realtek(R) Audio)"])
    assert mod.acilanlar == []            # yayın kapalıyken cihaz açılmaz
    motor.ac(True)
    assert _bekle(lambda: depo.durum.sanal_mikrofon == "açık" and depo.durum.mikrofon == "açık"
                  and depo.durum.sistem_sesi == "açık", 3)
    assert depo.durum.mikrofon_adi == "Mikrofon (Realtek(R) Audio)"
    assert "CABLE Output (VB-Audio Virtual" not in mod.acilanlar
    assert _bekle(lambda: mikser.seviyeler()["mikrofon"] > 0.2)
    motor.ac(False)
    assert _bekle(lambda: depo.durum.sanal_mikrofon == "kapalı", 3)


def test_cable_secilirse_reddedilir_ve_vbcable_yoksa_yok_gorunur(motor_kur):
    motor, depo, *_ = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)",
                                mikrofon_adi="CABLE Output (VB-Audio Virtual", sistem_modu="all")
    motor.ac(True)
    motor.baslat()
    assert _bekle(lambda: depo.durum.mikrofon == "yok", 3)
    assert "CABLE" in depo.durum.ses_hatasi

    motor2, depo2, *_ = motor_kur([c for c in CIHAZLAR if "CABLE Input" not in c["name"]],
                                  "Mikrofon (Realtek(R) Audio)", sistem_modu="all")
    motor2.ac(True)
    motor2.baslat()
    assert _bekle(lambda: depo2.durum.sanal_mikrofon == "yok", 3)
    assert "VB-Cable" in depo2.durum.ses_hatasi


def test_cihaz_koparsa_cokmez_yeniden_baglanir(motor_kur):
    motor, depo, mikser, mod, kopma = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)", sistem_modu="all")
    motor.ac(True)
    motor.baslat()
    assert _bekle(lambda: depo.durum.mikrofon == "açık", 3)
    acilma = len(mod.acilanlar)
    kopma.set()                                    # bütün cihazlar sustu
    time.sleep(2.0)
    kopma.clear()
    assert _bekle(lambda: len(mod.acilanlar) > acilma and depo.durum.mikrofon == "açık", 5)


class _AcilmayanSurecSesi:
    def __init__(self, pid, haric, yaz):
        self.hata = "Process Loopback desteklenmiyor"
        self.calisiyor = False

    def baslat(self):
        return False

    def durdur(self):
        pass


def _oturum_yok():
    raise OSError("Element not found")


def test_surec_sesi_acilamazsa_hoparlor_loopbacke_gecer(motor_kur, monkeypatch):
    # Eski Windows: ses oturumları listelenemez ve Process Loopback açılmaz -> "all" moduna düşmeli.
    # (Gerçek Windows'ta, ör. CI'da, Process Loopback çalışabildiği için sahtesiyle denenir.)
    from capture import app_audio
    monkeypatch.setattr(app_audio, "ses_oturumu_pidleri", _oturum_yok)
    monkeypatch.setattr(app_audio, "SurecSesi", _AcilmayanSurecSesi)
    motor, depo, *_ = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)", sistem_modu="auto")
    motor.ac(True)
    motor.baslat()
    assert _bekle(lambda: depo.durum.sistem_sesi == "açık", 8)
    assert depo.durum.sistem_kaynagi == "Hoparlörden çıkan tüm ses"


def test_otomatik_ses_kisma_ve_bas_konus_ve_panik():
    m = SesKaristirici()
    mik, sis = m.kanal_ekle("mikrofon", "Mikrofon"), m.kanal_ekle("sistem", "Bilgisayar sesi")
    m.kisma_acik, m.kisma_seviyesi = True, 0.3
    _dolu(sis, 0.5, n=48000)
    _dolu(mik, 0.2, n=48000)
    for _ in range(20):            # 200 ms konuşma
        m.karistir(480)
    assert m.konusuyor and sis.carpan == pytest.approx(0.3)
    mik.kapi = False               # bas-konuş tuşu bırakıldı -> mikrofon susar, ses geri açılır
    for _ in range(150):           # 1,5 sn
        m.karistir(480)
    assert sis.carpan == pytest.approx(1.0) and m.seviyeler()["mikrofon"] == 0
    m.ana_sessiz = True
    assert (m.karistir(480) == 0).all()


def test_yayin_kapatip_acinca_mikrofon_yeniden_acilir(motor_kur):
    """1.0.0 hatası: kayıt ya da yayın bir kez kapanınca mikrofon bir daha açılmıyordu."""
    motor, depo, mikser, mod, _ = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)", sistem_modu="all")
    motor.baslat()
    motor.kayit_icin_ac(True)                       # Ctrl+Shift+R (yayın kapalı)
    assert _bekle(lambda: depo.durum.mikrofon == "açık", 3)
    motor.kayit_icin_ac(False)                      # kayıt bitti -> cihazlar kapanır
    assert _bekle(lambda: depo.durum.sanal_mikrofon == "kapalı", 3)
    motor.ac(True)                                  # sonra yayın
    assert _bekle(lambda: depo.durum.mikrofon == "açık", 3)
    assert mod.acilanlar.count("Mikrofon (Realtek(R) Audio)") == 2
    assert _bekle(lambda: mikser.seviyeler()["mikrofon"] > 0.2)


# ------------------------------------------------------------------ uygulama bazlı yakalama ("auto")

def test_yakalanacak_surecler_zoomu_kendimizi_ve_atalarimizi_atar():
    from capture.app_audio import yakalanacak_surecler
    tablo = {
        1: (0, "explorer.exe"),
        5: (1, "yayinuygulamasi.exe"), 6: (5, "ffmpeg.exe"),   # biz ve alt sürecimiz
        10: (1, "msedge.exe"), 11: (10, "msedge.exe"),          # Edge ve ses alt süreci
        20: (1, "zoom.exe"), 21: (20, "zoomaudio.exe"),
        30: (1, "spotify.exe"),
        40: (0, "launcher.exe"), 41: (40, "discord.exe"),       # Discord'u açan uygulama
    }
    oturumlar = {1, 5, 6, 10, 11, 20, 21, 30, 40}
    sonuc = yakalanacak_surecler(oturumlar, ["Zoom.exe", "Discord.exe"], 5, tablo)
    # explorer (bizim atamız), biz, ffmpeg, Zoom ağacı ve Discord'un atası yok; Edge tek ağaç olarak
    assert sonuc == {10, 30}


class _SahteSurecSesi:
    olusan = []

    def __init__(self, pid, haric, yaz):
        self.pid, self.haric, self.yaz = pid, haric, yaz
        self.calisiyor = True
        _SahteSurecSesi.olusan.append(self)

    def baslat(self):
        self.yaz(np.full((480, 2), 0.1, np.float32))
        return True

    def durdur(self):
        self.calisiyor = False


def test_auto_mod_her_uygulamayi_ayri_yakalar(motor_kur, monkeypatch):
    from capture import app_audio
    tablo = {1: (0, "explorer.exe"), 5: (1, "python.exe"), 10: (1, "msedge.exe"),
             20: (1, "zoom.exe"), 30: (1, "spotify.exe")}
    oturumlar = {10, 20}
    _SahteSurecSesi.olusan = []
    monkeypatch.setattr(app_audio, "surec_tablosu", lambda: dict(tablo))
    monkeypatch.setattr(app_audio, "ses_oturumu_pidleri", lambda: set(oturumlar))
    monkeypatch.setattr(app_audio, "kendi_pid", lambda: 5)
    monkeypatch.setattr(app_audio, "SurecSesi", _SahteSurecSesi)
    motor, depo, mikser, *_ = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)", sistem_modu="auto")
    motor.ac(True)
    motor.baslat()
    assert _bekle(lambda: depo.durum.sistem_sesi == "açık", 3)
    assert [s.pid for s in _SahteSurecSesi.olusan] == [10]          # Zoom yakalanmaz
    assert all(not s.haric for s in _SahteSurecSesi.olusan)         # hep "dahil" modu
    assert depo.durum.sistem_kaynagi == "msedge (zoom hariç)"
    oturumlar.add(30)                                                # Spotify çalmaya başladı
    assert _bekle(lambda: [s.pid for s in _SahteSurecSesi.olusan] == [10, 30], 4)
    oturumlar.discard(10)                                            # Edge sustu/kapandı
    assert _bekle(lambda: not _SahteSurecSesi.olusan[0].calisiyor, 4)
    assert set(mikser.kanallar["sistem"].alt_tamponlar) == {30}


def test_oturumlar_listelenemezse_kendimiz_haric_tek_yakalama(motor_kur, monkeypatch):
    from capture import app_audio
    _SahteSurecSesi.olusan = []
    monkeypatch.setattr(app_audio, "ses_oturumu_pidleri", _oturum_yok)
    monkeypatch.setattr(app_audio, "kendi_pid", lambda: 5)
    monkeypatch.setattr(app_audio, "SurecSesi", _SahteSurecSesi)
    motor, depo, *_ = motor_kur(CIHAZLAR, "Mikrofon (Realtek(R) Audio)", sistem_modu="auto")
    motor.ac(True)
    motor.baslat()
    assert _bekle(lambda: depo.durum.sistem_sesi == "açık", 3)
    assert [(s.pid, s.haric) for s in _SahteSurecSesi.olusan] == [(5, True)]   # yankı olmasın: kendimiz hariç
    assert depo.durum.sistem_kaynagi == "Tüm bilgisayar sesi"


def test_kanal_alt_tamponlari_toplanir():
    m = SesKaristirici()
    sis = m.kanal_ekle("sistem", "Bilgisayar sesi")
    sis.bagli = True
    sis.alt_tampon_ekle(1).yaz(np.full((4800, 2), 0.1, np.float32))
    sis.alt_tampon_ekle(2).yaz(np.full((4800, 2), 0.2, np.float32))
    assert np.allclose(m.karistir(480), 0.3)
    sis.alt_tampon_sil(1)
    assert np.allclose(m.karistir(480), 0.2)
