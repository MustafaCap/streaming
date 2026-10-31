import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from core.standby import BeklemeVideosu, uygulamaya_kopyala, video_mu  # noqa: E402


def _video_yaz(yol, kareler=10, fps=10):
    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"MJPG"), fps, (64, 48))
    if not yazici.isOpened():
        pytest.skip("Bu ortamda video yazılamıyor")
    for i in range(kareler):
        yazici.write(np.full((48, 64, 3), i * 20, np.uint8))
    yazici.release()


def test_video_uzantisi():
    assert video_mu("a.MP4") and video_mu("x/y.gif") and not video_mu("a.png") and not video_mu("")


def test_video_dongude_ve_kendi_hizinda_oynar(tmp_path):
    yol = tmp_path / "bekleme.avi"
    _video_yaz(yol)
    zaman = [0.0]
    v = BeklemeVideosu(saat=lambda: zaman[0])
    ilk = v.kare(str(yol), 128, 72)
    assert ilk is not None and ilk.shape == (72, 128, 3)
    assert v.kare(str(yol), 128, 72) is ilk          # zaman ilerlemedi: aynı kare
    zaman[0] = 0.35                                     # 10 FPS -> ~3 kare sonra
    assert v._okunan == 1
    v.kare(str(yol), 128, 72)
    assert v._okunan == 4
    for t in range(1, 30):                              # 1 sn'lik video biter, başa sarar, çökmez
        zaman[0] = 0.35 + t * 0.1
        assert v.kare(str(yol), 128, 72) is not None
    v.kapat()


def test_acilamayan_video_none_doner(tmp_path):
    v = BeklemeVideosu()
    assert v.kare(str(tmp_path / "yok.mp4"), 128, 72) is None
    assert v.hata


def test_kopyalama_turkce_yol(tmp_path, monkeypatch):
    kaynak = tmp_path / "Masaüstü"
    kaynak.mkdir()
    dosya = kaynak / "kısa video.avi"
    _video_yaz(dosya)
    hedef = uygulamaya_kopyala(str(dosya))
    assert hedef.endswith(".avi") and "bekleme_" in hedef
    assert uygulamaya_kopyala(hedef) == hedef
    assert BeklemeVideosu().kare(hedef, 64, 36) is not None
