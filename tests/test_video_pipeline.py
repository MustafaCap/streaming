import time

import numpy as np

from core.state import DurumDeposu
from core.video_pipeline import VideoHatti
from outputs.virtualcam import SanalKameraYok


class SahteKaynak:
    yontem = "sahte"

    def __init__(self, kopuk=False):
        self.kopuk = kopuk

    def grab(self):
        return None if self.kopuk else np.full((1080, 1920, 3), 100, np.uint8)

    def kapat(self):
        pass


class SahteCikis:
    def __init__(self, yok=False):
        self.yok, self.acik, self.gonderilen = yok, False, 0

    def ac(self):
        if self.yok:
            raise SanalKameraYok("sürücü yok")
        self.acik = True

    def gonder(self, kare):
        assert kare.shape == (720, 1280, 3)
        self.gonderilen += 1

    def kapat(self):
        self.acik = False


def _bekle(kosul, sure=2.0):
    son = time.time() + sure
    while time.time() < son:
        if kosul():
            return True
        time.sleep(0.02)
    return False


def test_cikis_acilinca_kare_gonderilir_kapaninca_durur():
    depo, cikis = DurumDeposu(), SahteCikis()
    hat = VideoHatti(depo, SahteKaynak(), cikis, fps=60)
    hat.baslat()
    try:
        assert _bekle(lambda: depo.durum.ekran_kaynagi == "çalışıyor")
        assert cikis.gonderilen == 0
        hat.cikisi_ayarla(True)
        assert _bekle(lambda: cikis.gonderilen > 5)
        assert depo.durum.cikis_acik and depo.durum.sanal_kamera == "açık"
        hat.cikisi_ayarla(False)
        assert _bekle(lambda: not depo.durum.cikis_acik)
        assert hat.son_kare().shape == (720, 1280, 3)
    finally:
        hat.durdur()


def test_surucu_yoksa_cokmez_ve_durum_yok_olur():
    depo = DurumDeposu()
    hat = VideoHatti(depo, SahteKaynak(), SahteCikis(yok=True), fps=60)
    hat.baslat()
    try:
        hat.cikisi_ayarla(True)
        assert _bekle(lambda: depo.durum.sanal_kamera == "yok")
        assert not depo.durum.cikis_acik and "OBS" in depo.durum.son_hata
        assert not hat.cikis_istegi
    finally:
        hat.durdur()


def test_kaynak_koparsa_bilgi_karesi_gosterilir():
    depo = DurumDeposu()
    hat = VideoHatti(depo, SahteKaynak(kopuk=True), SahteCikis(), fps=60)
    hat.baslat()
    try:
        assert _bekle(lambda: depo.durum.ekran_kaynagi == "koptu")
        assert hat.son_kare().shape == (720, 1280, 3)
    finally:
        hat.durdur()


class ImlecliKaynak(SahteKaynak):
    def __init__(self):
        super().__init__()
        self.kare = np.zeros((720, 1280, 3), np.uint8)  # çıkışla aynı boyut: sigdir kopyalamaz

    def grab(self):
        return self.kare

    def imlec(self):
        return (100, 100)


def test_imlec_cizilir_ama_kaynak_karesi_bozulmaz():
    kaynak = ImlecliKaynak()
    hat = VideoHatti(DurumDeposu(), kaynak, SahteCikis(), fps=60)
    kare = hat._kare_uret()
    assert kare[110, 103].min() > 200
    assert kaynak.kare.max() == 0


def test_panik_aninda_bekleme_ekrani_ve_imlec_vurgusu_cokmez():
    depo, cikis = DurumDeposu(), SahteCikis()
    hat = VideoHatti(depo, SahteKaynak(), cikis, fps=60, imlec_vurgusu=True)
    hat.baslat()
    try:
        assert _bekle(lambda: depo.durum.ekran_kaynagi == "çalışıyor")
        hat.panik = True
        assert _bekle(lambda: hat.son_kare()[360, 640].tolist() != [100, 100, 100])
        hat.panik = False
        assert _bekle(lambda: hat.son_kare()[5, 5].tolist() == [100, 100, 100])
    finally:
        hat.durdur()
