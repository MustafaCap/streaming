import numpy as np

from capture.background_blur import ArkaPlanBulaniklastirici


def test_model_yuklenir_ve_goruntu_boyutu_korunur():
    b = ArkaPlanBulaniklastirici(her_n_karede=1)
    kare = np.random.randint(0, 255, (720, 1280, 3), np.uint8)
    sonuc = b.isle(kare)
    assert b.hata == "" and b._ag is not None
    assert sonuc.shape == kare.shape and sonuc.dtype == np.uint8
    assert not np.array_equal(sonuc, kare)  # arka plan bulanıklaştı


def test_model_yoksa_goruntu_aynen_gecer(monkeypatch):
    import capture.background_blur as bb
    monkeypatch.setattr(bb, "MODEL", "olmayan.tflite")
    b = bb.ArkaPlanBulaniklastirici()
    kare = np.zeros((90, 160, 3), np.uint8)
    assert b.isle(kare) is kare and "yüklenemedi" in b.hata
