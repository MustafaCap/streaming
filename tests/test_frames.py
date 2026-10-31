import numpy as np

from core import frames


def test_ayni_boyut_degismez():
    k = np.ones((720, 1280, 3), np.uint8)
    assert frames.sigdir(k, 1280, 720) is k


def test_genis_ekran_ust_alt_bant():
    k = np.full((1080, 2560, 3), 200, np.uint8)  # 21:9
    s = frames.sigdir(k, 1280, 720)
    assert s.shape == (720, 1280, 3)
    assert s[0, 640].max() == 0          # üst bant siyah
    assert s[360, 640].min() > 150       # orta görüntü


def test_dikey_kare_yan_bantlar():
    s = frames.sigdir(np.full((800, 400, 3), 200, np.uint8), 1280, 720)
    assert s[360, 0].max() == 0 and s[360, 640].min() > 150


def test_bilgi_karesi_boyutu():
    assert frames.bilgi_karesi(1280, 720, "Test").shape == (720, 1280, 3)
