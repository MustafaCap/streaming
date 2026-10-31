import numpy as np

from core.state import DurumDeposu
from core.video_pipeline import VideoHatti
from scenes.scene_manager import (KameraYerlesimi, Sahne, SahneYoneticisi, sahne_karesi,
                                  sahneleri_oku)
from tests.test_video_pipeline import SahteCikis, SahteKaynak, _bekle

W, H = 1280, 720
EKRAN = np.full((H, W, 3), 100, np.uint8)
KAMERA = np.full((480, 640, 3), 200, np.uint8)
YER = KameraYerlesimi()


def test_ayarlardan_sahne_okuma_ve_varsayilan():
    s = sahneleri_oku([{"name": "A", "screen": True, "camera": "corner"}, {"name": "B", "camera": "garip"}])
    assert s[0] == Sahne("A", ekran=True, kamera="corner")
    assert s[1].kamera is None
    assert len(sahneleri_oku([])) == 4
    assert len(sahneleri_oku("bozuk")) == 4


def test_ekran_ve_kose_kamerasi():
    kare = sahne_karesi(Sahne("x", ekran=True, kamera="corner"), W, H, EKRAN, KAMERA, True, YER, "")
    x, y, w, h = YER.dikdortgen(W, H)
    assert kare[y + h // 2, x + w // 2, 0] == 200   # köşede kamera
    assert kare[10, 10, 0] == 100                    # geri kalanı ekran
    assert EKRAN[y + h // 2, x + w // 2, 0] == 100   # ekran karesi bozulmadı


def test_kamera_kapaliyken_kose_bos_tam_ekranda_bilgi():
    kare = sahne_karesi(Sahne("x", ekran=True, kamera="corner"), W, H, EKRAN, KAMERA, False, YER, "")
    x, y, w, h = YER.dikdortgen(W, H)
    assert kare[y + h // 2, x + w // 2, 0] == 100
    tam = sahne_karesi(Sahne("k", kamera="full"), W, H, None, None, False, YER, "")
    assert tam.shape == (H, W, 3) and tam.max() > 30  # "Kamera kapalı" yazısı var


def test_tam_ekran_kamera_kirpilarak_doldurulur():
    kare = sahne_karesi(Sahne("k", kamera="full"), W, H, None, KAMERA, True, YER, "")
    assert kare.shape == (H, W, 3) and (kare == 200).all()


def test_bekleme_ve_kopuk_ekran_yazilabilir_kare_verir():
    b = sahne_karesi(Sahne("b", bekleme=True), W, H, None, None, True, YER, "Birazdan döneceğim")
    b[0, 0] = 1  # salt okunur önbellek kopyalanmış olmalı
    e = sahne_karesi(Sahne("e", ekran=True), W, H, None, None, True, YER, "")
    e[0, 0] = 1


def test_gecis_iki_kareyi_karistirir_ve_biter():
    zaman = [0.0]
    y = SahneYoneticisi([Sahne("a"), Sahne("b")], gecis_ms=300, saat=lambda: zaman[0])
    eski, yeni = np.zeros((4, 4, 3), np.uint8), np.full((4, 4, 3), 200, np.uint8)
    assert y.sec(1) and not y.sec(5)
    assert y.aktif.ad == "b"
    ilk = y.gecis_uygula(yeni, eski)
    assert ilk[0, 0, 0] == 0
    zaman[0] = 0.15
    orta = y.gecis_uygula(yeni, eski)
    assert 50 < orta[0, 0, 0] < 150
    zaman[0] = 0.31
    assert y.gecis_uygula(yeni, eski) is yeni
    assert not y.geciste


class SahteKamera:
    def __init__(self):
        self.acik, self.son_hata, self.baslatma = False, "", 0

    def baslat(self):
        self.acik = True
        self.baslatma += 1

    def durdur(self, bekle=False):
        self.acik = False

    def son_kare(self):
        return KAMERA if self.acik else None


def test_hat_kamerayi_sadece_gerektiginde_acar():
    depo, kamera = DurumDeposu(), SahteKamera()
    sahneler = SahneYoneticisi(sahneleri_oku([]), gecis_ms=0)
    hat = VideoHatti(depo, SahteKaynak(), SahteCikis(), fps=60, kamera=kamera, sahneler=sahneler)
    hat.baslat()
    try:
        assert _bekle(lambda: kamera.acik and depo.durum.webcam == "açık")
        hat.sahne_sec(1)  # sadece ekran
        assert _bekle(lambda: not kamera.acik and depo.durum.aktif_sahne == 1)
        assert depo.durum.sahne_adi == "Sadece ekran"
        hat.sahne_sec(2)
        assert _bekle(lambda: kamera.acik)
        hat.kamerayi_ayarla(False)
        assert _bekle(lambda: not kamera.acik and depo.durum.webcam == "kapalı")
    finally:
        hat.durdur()
