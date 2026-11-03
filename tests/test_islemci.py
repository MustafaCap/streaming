"""2.0.5: işlemci tasarrufu. Değişmeyen ekran yeniden işlenmez, küçültme hızlı ama düzgün,
NV12 çevirme aynı kare için bir kez yapılır."""

import cv2
import numpy as np

from core import frames
from core.state import DurumDeposu
from core.video_pipeline import VideoHatti
from scenes.scene_manager import Sahne, SahneYoneticisi
from tests.test_video_pipeline import SahteCikis


class SabitKaynak:
    """dxcam gibi: ekran değişmedikçe aynı dizi nesnesini verir."""
    yontem = "sahte"

    def __init__(self):
        self.kare = np.full((1080, 1920, 3), 100, np.uint8)
        self.konum = None

    def grab(self):
        return self.kare

    def imlec(self):
        return self.konum

    def kapat(self):
        pass


def _hat(kaynak, **ayar):
    return VideoHatti(DurumDeposu(), kaynak, SahteCikis(), sahneler=SahneYoneticisi([Sahne("e", ekran=True)]),
                      **ayar)


def test_olcekle_dogru_boyut_ve_inter_area_ya_yakin():
    rng = np.random.default_rng(1)
    for kaynak, hedef in [((1080, 1920), (720, 1280)), ((2160, 3840), (720, 1280)), ((1440, 2560), (720, 1280)),
                          ((1200, 1920), (720, 1152)), ((768, 1366), (720, 1280)), ((300, 200), (720, 1280))]:
        kare = cv2.GaussianBlur(rng.integers(0, 256, (*kaynak, 3), dtype=np.uint8), (5, 5), 0)
        sonuc = frames.olcekle(kare, hedef[1], hedef[0])
        assert sonuc.shape == (*hedef, 3)
        ref = cv2.resize(kare, (hedef[1], hedef[0]), interpolation=cv2.INTER_AREA).astype(float)
        hata = np.abs(sonuc.astype(float) - ref).mean()
        assert hata < 6, (kaynak, hata)
    ayni = np.zeros((720, 1280, 3), np.uint8)
    assert frames.olcekle(ayni, 1280, 720) is ayni


def test_nv12_ayni_kare_icin_bir_kez_cevrilir_ve_dogru():
    rgb = np.random.default_rng(2).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    beklenen = np.empty(1280 * 720 * 3 // 2, np.uint8)
    frames.rgb_nv12(rgb, beklenen)
    a = frames.nv12(rgb)
    assert np.array_equal(a, beklenen) and not a.flags.writeable
    assert frames.nv12(rgb) is a                 # ikinci kez çevrilmedi
    assert frames.nv12(rgb.copy()) is not a      # başka kare nesnesi: yeniden çevrilir


def test_degismeyen_ekran_ayni_cikis_karesini_verir():
    kaynak = SabitKaynak()
    hat = _hat(kaynak, imlec_goster=True)
    k1 = hat._kare_uret()
    k2 = hat._kare_uret()
    assert k1 is k2 and not k1.flags.writeable and k1.shape == (720, 1280, 3)
    kaynak.kare = kaynak.kare.copy()             # yeni ekran karesi geldi
    assert hat._kare_uret() is not k1


def test_fare_oynayinca_kare_yenilenir_ve_ekran_bozulmaz():
    kaynak = SabitKaynak()
    hat = _hat(kaynak, imlec_goster=True)
    k1 = hat._kare_uret()
    kaynak.konum = (900, 500)
    k2 = hat._kare_uret()
    assert k2 is not k1 and (k2 == 255).any()    # imleç çizildi
    assert (kaynak.kare == 100).all()            # yakalayıcının karesine çizilmedi
    assert hat._kare_uret() is k2                # fare durdu: yeniden çizilmedi
    kaynak.konum = (910, 500)
    assert hat._kare_uret() is not k2


def test_ayni_boyuttaki_ekran_karesine_imlec_cizilmez():
    kaynak = SabitKaynak()
    kaynak.kare = np.full((720, 1280, 3), 100, np.uint8)
    kaynak.konum = (100, 100)
    hat = _hat(kaynak, imlec_goster=True)
    kare = hat._kare_uret()
    assert (kare == 255).any() and (kaynak.kare == 100).all() and kaynak.kare.flags.writeable


def test_bolge_animasyonunda_her_kare_yenilenir():
    kaynak = SabitKaynak()
    zaman = [0.0]
    from capture.region import BolgeSecimi
    hat = _hat(kaynak, bolge=BolgeSecimi(sure_ms=400, saat=lambda: zaman[0]))
    k1 = hat._kare_uret()
    hat.bolge.sec((0.25, 0.25, 0.5, 0.5))
    zaman[0] = 0.1
    k2 = hat._kare_uret()
    zaman[0] = 0.2
    k3 = hat._kare_uret()
    assert k1 is not k2 and k2 is not k3
    zaman[0] = 1.0
    k4 = hat._kare_uret()
    assert hat._kare_uret() is k4                # animasyon bitti: değişmiyor


def test_cizim_degisince_kare_yenilenir():
    from overlay.drawing import CizimDeposu
    kaynak = SabitKaynak()
    cizimler = CizimDeposu()
    hat = _hat(kaynak, cizimler=cizimler)
    k1 = hat._kare_uret()
    cizimler.basla("kalem", "#ff0000", 0.2, 0.2)
    cizimler.surukle(0.4, 0.4)
    cizimler.bitir()
    k2 = hat._kare_uret()
    assert k2 is not k1 and hat._kare_uret() is k2
    cizimler.geri_al()
    assert hat._kare_uret() is not k2
