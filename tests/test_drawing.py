import numpy as np

from overlay.drawing import CizimDeposu, cizimleri_uygula, hex_rgb


def _donusum(x, y):  # 1920x1080 monitör -> 1280x720 çıkış
    return x * 2 / 3, y * 2 / 3


def test_cizim_geri_al_temizle():
    d = CizimDeposu()
    d.basla("kalem", "#FF8A3D", 0.1, 0.1)
    d.surukle(0.2, 0.2)
    d.surukle(0.3, 0.3)
    d.bitir()
    d.basla("kare", "#FFFFFF", 0.5, 0.5)
    d.surukle(0.5001, 0.5001)  # çok küçük kare atılır
    d.bitir()
    sekiller, _ = d.anlik()
    assert [s.tur for s in sekiller] == ["kalem"] and len(sekiller[0].noktalar) == 3
    assert d.geri_al() and not d.geri_al()
    d.yazi_ekle("#FFFFFF", 0.1, 0.1, "Merhaba ğüşİ")
    d.temizle()
    assert d.bos


def test_cizim_cikis_karesine_dogru_yerde_eklenir():
    d = CizimDeposu()
    d.basla("kare", "#FF8A3D", 0.25, 0.25)
    d.surukle(0.75, 0.75)
    d.bitir()
    kare = np.zeros((720, 1280, 3), np.uint8)
    sonuc = cizimleri_uygula(kare, d, 1920, 1080, _donusum)
    assert tuple(sonuc[180, 640]) == hex_rgb("#FF8A3D")   # üst kenarın ortası (y = 0.25*720)
    assert sonuc[360, 640].sum() == 0                      # içi boş
    assert kare.sum() == 0                                 # giriş karesi bozulmadı


def test_cizim_yoksa_kopyalamaz_ve_lazer_kaybolur():
    zaman = [0.0]
    d = CizimDeposu(saat=lambda: zaman[0])
    kare = np.zeros((720, 1280, 3), np.uint8)
    assert cizimleri_uygula(kare, d, 1920, 1080, _donusum) is kare
    d.basla("lazer", "#FFFFFF", 0.5, 0.5)
    d.surukle(0.6, 0.5)
    d.bitir()
    assert cizimleri_uygula(kare, d, 1920, 1080, _donusum).sum() > 0
    zaman[0] = 5.0
    assert d.bos or not d.anlik()[1]


def test_fosforlu_ve_yazi_ve_ok_cizilir():
    d = CizimDeposu()
    for tur in ("fosforlu", "ok"):
        d.basla(tur, "#FFD43B", 0.1, 0.5)
        d.surukle(0.9, 0.5)
        d.bitir()
    d.yazi_ekle("#FFFFFF", 0.1, 0.1, "Şuraya bak")
    kare = np.full((720, 1280, 3), 50, np.uint8)
    sonuc = cizimleri_uygula(kare, d, 1920, 1080, _donusum)
    assert 50 < sonuc[360, 400, 1] < 255  # fosforlu yarı saydam (ok üstte olabilir)
    assert sonuc[60:120, 120:300].max() == 255  # yazı
