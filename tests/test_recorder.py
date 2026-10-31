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


def _kayit_et(k, saniye=1.0):
    kare = np.zeros((240, 320, 3), np.uint8)
    for i in range(int(30 * saniye)):
        kare[:] = (i * 8) % 255
        k.kare_yaz(kare.copy())
        k.ses_yaz(np.full((1600, 2), 0.1, np.float32))
        time.sleep(1 / 30)


def _akislar(dosya):
    import subprocess
    return sorted(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                  str(dosya)], capture_output=True, text=True).stdout.split())


def test_cokmede_yarim_kalan_kayit_sonraki_acilista_kurtarilir(tmp_path):
    from core.recorder import yarim_kayitlari_kurtar
    k = Kayitci(320, 240, 30, klasor=tmp_path, kodlayici="mpeg4")
    assert k.baslat()
    _kayit_et(k, 2.0)
    time.sleep(0.5)
    # Çökme: durdur() hiç çağrılmadan FFmpeg ölür, ses dosyası yarım kalır
    k._surec.kill()
    k._surec.wait()
    k._ses_dosyasi.flush()
    k._ses_dosyasi.close()
    k._kayitta = False
    gecici = sorted(p.name for p in tmp_path.iterdir())
    assert any(n.endswith(".video.mkv") for n in gecici) and any(n.endswith(".ses.pcm") for n in gecici)

    assert yarim_kayitlari_kurtar(tmp_path, ffmpeg_bul()) == []   # şu an yazılıyor olabilir: dokunulmaz
    import os
    eski_zaman = time.time() - 60
    for f in tmp_path.iterdir():
        os.utime(f, (eski_zaman, eski_zaman))
    kurtarilan = yarim_kayitlari_kurtar(tmp_path, ffmpeg_bul())
    assert len(kurtarilan) == 1 and kurtarilan[0].name.endswith("_kurtarildi.mp4")
    assert kurtarilan[0].stat().st_size > 1000
    assert [p.name for p in tmp_path.iterdir()] == [kurtarilan[0].name]   # geçici dosyalar temizlendi
    if shutil.which("ffprobe"):
        assert _akislar(kurtarilan[0]) == ["audio", "video"]


def test_kayit_yazilamazsa_bir_kez_bildirilir_ve_eldeki_kaydedilir(tmp_path):
    k = Kayitci(320, 240, 30, klasor=tmp_path, kodlayici="mpeg4")
    hatalar = []
    k.hata_olunca = hatalar.append
    assert k.baslat()
    _kayit_et(k, 1.0)
    time.sleep(0.3)
    k._surec.kill()            # FFmpeg beklenmedik şekilde kapandı (disk doldu gibi)
    _kayit_et(k, 0.5)
    assert len(hatalar) == 1 and "yazılamadı" in hatalar[0]
    bitti = threading.Event()
    sonuc = {}
    k.durdur(lambda dosya, hata: (sonuc.update(dosya=dosya, hata=hata), bitti.set()))
    assert bitti.wait(60)
    assert sonuc["dosya"] is not None and sonuc["dosya"].exists()   # o ana kadarki kısım kurtarıldı


def test_paketlenmis_surumde_path_teki_ffmpeg_kullanilmaz(monkeypatch, tmp_path):
    import sys as _sys

    import core.recorder as r
    monkeypatch.setattr(_sys, "frozen", True, raising=False)
    monkeypatch.setattr(_sys, "executable", str(tmp_path / "RizeOn.exe"))
    assert r.ffmpeg_bul() is None
