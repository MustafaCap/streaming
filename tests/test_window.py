"""Pencere yakalama: kırpma, siyah gelirse ekrandan yakalama, küçültme ve kapanma (sahte Windows ile)."""

import numpy as np

from capture.window import SIYAH_ESIGI, PencereKaynagi, kirp, pencereleri_listele


class SahteApi:
    def __init__(self):
        self.var, self.simge, self.siyah = True, False, False
        self.pencere, self.cerceve = (100, 50, 520, 370), (107, 50, 513, 363)   # görünmez kenarlıklar
        self.ekrandan_cagri = 0
        self.kapandi = False

    def var_mi(self, hwnd):
        return self.var

    def simge_mi(self, hwnd):
        return self.simge

    def dikdortgenler(self, hwnd):
        return self.pencere, self.cerceve

    def printwindow(self, hwnd, w, h):
        kare = np.zeros((h, w, 4), np.uint8)
        if not self.siyah:
            kare[..., 0] = 10    # B
            kare[..., 2] = 200   # R
        return kare

    def ekrandan(self, cerceve):
        self.ekrandan_cagri += 1
        return np.full((cerceve[3] - cerceve[1], cerceve[2] - cerceve[0], 3), 7, np.uint8)

    def kapat(self):
        self.kapandi = True


def test_kirpma_gorunen_cerceveyi_alir_ve_rgb_yapar():
    bgra = np.zeros((320, 420, 4), np.uint8)
    bgra[..., 0], bgra[..., 2] = 1, 3
    rgb = kirp(bgra, (100, 50, 520, 370), (107, 50, 513, 363))
    assert rgb.shape == (313, 406, 3)
    assert tuple(rgb[0, 0]) == (3, 0, 1)


def test_pencere_yakalanir_ve_dikdortgen_cerceve_olur():
    api = SahteApi()
    k = PencereKaynagi(1, "Not Defteri", api=api)
    kare = k.grab()
    assert kare.shape == (313, 406, 3) and tuple(kare[5, 5]) == (200, 0, 10)
    assert k.dikdortgen == (107, 50, 406, 313)
    assert k.yontem == "pencere" and k.calisiyor


def test_siyah_gelirse_ekrandan_yakalamaya_gecer():
    api = SahteApi()
    api.siyah = True
    k = PencereKaynagi(1, "Oyun", api=api)
    for _ in range(SIYAH_ESIGI - 1):
        assert k.grab() is None            # henüz önceki görüntü yok
    kare = k.grab()
    assert k.ekrandan and k.yontem == "pencere (ekrandan)"
    assert kare.shape == (313, 406, 3) and api.ekrandan_cagri == 1


def test_kucultulunce_son_goruntu_kapaninca_none():
    api = SahteApi()
    k = PencereKaynagi(1, "Tarayıcı", api=api)
    ilk = k.grab()
    api.simge = True
    assert k.grab() is ilk
    api.var = False
    assert k.grab() is None and k.son_hata == "Pencere kapandı" and not k.calisiyor
    k.kapat()
    assert api.kapandi


def test_hata_firlatmaz():
    class Bozuk(SahteApi):
        def dikdortgenler(self, hwnd):
            raise OSError("erişim engellendi")

    k = PencereKaynagi(1, "x", api=Bozuk())
    assert k.grab() is None and "erişim" in k.son_hata


def test_windows_degilse_liste_bos(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    assert pencereleri_listele() == []
