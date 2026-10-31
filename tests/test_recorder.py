import shutil
import threading
import time

import numpy as np
import pytest

from core.recorder import Kayitci, ffmpeg_bul, kodlayici_sec

pytestmark = pytest.mark.skipif(ffmpeg_bul() is None, reason="FFmpeg yok")


def test_kodlayici_secimi_calisan_birini_bulur():
    assert kodlayici_sec(ffmpeg_bul(), "mpeg4") == "mpeg4"


def test_kayit_goruntu_ve_sesi_birlestirir(tmp_path):
    k = Kayitci(320, 240, 30, klasor=tmp_path, kodlayici="mpeg4")
    assert k.baslat() and k.kayitta
    kare = np.zeros((240, 320, 3), np.uint8)
    for i in range(30):
        kare[:] = i * 8
        k.kare_yaz(kare.copy())
        k.ses_yaz(np.full((1600, 2), 0.1, np.float32))
        time.sleep(1 / 30)
    bitti = threading.Event()
    sonuc = {}
    k.durdur(lambda dosya, hata: (sonuc.update(dosya=dosya, hata=hata), bitti.set()))
    assert bitti.wait(60)
    assert sonuc["hata"] == "" and sonuc["dosya"].exists() and sonuc["dosya"].stat().st_size > 1000
    assert [p.name for p in tmp_path.iterdir()] == [sonuc["dosya"].name]  # geçici dosyalar silindi
    if shutil.which("ffprobe"):
        import subprocess
        akislar = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                  str(sonuc["dosya"])], capture_output=True, text=True).stdout.split()
        assert sorted(akislar) == ["audio", "video"]


def test_ffmpeg_yoksa_hata_verir(tmp_path, monkeypatch):
    import core.recorder as r
    monkeypatch.setattr(r, "ffmpeg_bul", lambda: None)
    k = Kayitci(320, 240, 30, klasor=tmp_path)
    assert not k.baslat() and "FFmpeg" in k.son_hata
