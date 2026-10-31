import numpy as np

from capture.region import TAM, BolgeSecimi, Gorunum, normalize, uygula


def test_normalize_tasani_kirpar():
    assert normalize(0.9, 0.9, 0.5, 0.5) == (0.9, 0.9, 0.09999999999999998, 0.09999999999999998)
    x, y, w, h = normalize(-0.2, 0.1, 0.001, 0.3)
    assert x == 0 and w == 0.02


def test_yakinlastirma_animasyonu_ve_geri_donus():
    zaman = [0.0]
    b = BolgeSecimi(sure_ms=400, saat=lambda: zaman[0])
    assert b.gorunum().kirpma == TAM and not b.aktif
    b.sec((0.5, 0.5, 0.5, 0.5))
    assert b.gorunum().kirpma == TAM            # t=0
    zaman[0] = 0.2
    orta = b.gorunum().kirpma
    assert 0.1 < orta[0] < 0.4
    zaman[0] = 0.5
    assert b.gorunum().kirpma == (0.5, 0.5, 0.5, 0.5) and b.aktif
    b.temizle()
    zaman[0] = 1.0
    assert b.gorunum().kirpma == TAM and not b.aktif


def test_yakinlastirilan_bolge_ciktiyi_doldurur_ve_donusum_dogru():
    ham = np.zeros((1080, 1920, 3), np.uint8)
    ham[540:, 960:] = 200                        # sağ alt çeyrek parlak
    kare, donusum = uygula(ham, Gorunum((0.5, 0.5, 0.5, 0.5), None, 0), 1280, 720)
    assert kare.shape == (720, 1280, 3) and (kare > 150).all()
    assert donusum(960, 540) == (0, 0)
    assert donusum(1920, 1080) == (1280, 720)


def test_vurgulama_disari_karartir():
    ham = np.full((720, 1280, 3), 200, np.uint8)
    kare, _ = uygula(ham, Gorunum(TAM, (0.25, 0.25, 0.5, 0.5), 1.0), 1280, 720, 0.65)
    assert kare[10, 10, 0] < 100                 # dışarısı karardı
    assert kare[360, 640, 0] == 200              # içerisi parlak
    assert ham[10, 10, 0] == 200                 # ham kare bozulmadı
