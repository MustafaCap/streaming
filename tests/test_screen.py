import numpy as np

from capture import screen


class _Bozuk:
    ad = "dxcam"

    def __init__(self, monitor):
        raise RuntimeError("DirectX yok")


class _Calisan:
    ad = "mss"

    def __init__(self, monitor):
        self.sayac = 0

    def yakala(self):
        self.sayac += 1
        if self.sayac == 3:
            raise OSError("monitör çıkarıldı")
        return np.zeros((10, 10, 3), np.uint8)

    def kapat(self):
        pass


def test_dxcam_olmazsa_mss_e_gecer_ve_koparsa_toparlanir(monkeypatch):
    monkeypatch.setattr(screen, "YONTEMLER", {"dxcam": _Bozuk, "mss": _Calisan})
    k = screen.EkranKaynagi(tercih="dxcam")
    k.YENIDEN_DENEME_SN = 0
    assert k.grab() is not None and k.yontem == "mss"
    assert k.grab() is not None
    assert k.grab() is None and not k.calisiyor     # koptu, hata fırlatmadı
    assert k.grab() is not None and k.calisiyor     # yeniden bağlandı
