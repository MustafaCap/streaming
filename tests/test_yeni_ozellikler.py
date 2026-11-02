"""2.0.0'ın yeni özellikleri: anlık tekrar, ekran görüntüsü, gürültü azaltma, sanal çıkış uyarıları."""

import os
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from core.anlik_tekrar import TS, AnlikTekrar, TsParcalayici, dosya_adi, sureyi_sinirla
from core.audio_mixer import SesKaristirici
from core.gurultu import CERCEVE, GurultuAzaltici


# ---- anlık tekrar

def test_tekrar_suresi_sinirlari_ve_dosya_adi():
    assert sureyi_sinirla(10) == 30 and sureyi_sinirla(999) == 300 and sureyi_sinirla("x") == 120
    assert dosya_adi(datetime(2026, 11, 2, 9, 5, 7)) == "Tekrar_2026-11-02_09-05-07.mp4"


def _paket(pid, pusi=False, rai=False, yuk=b""):
    bas = bytes([0x47, (0x40 if pusi else 0) | (pid >> 8), pid & 0xFF])
    if rai:
        af = bytes([1, 0x40])
        govde = bas + bytes([0x30]) + af + yuk
    else:
        govde = bas + bytes([0x10]) + yuk
    return govde + b"\xff" * (TS - len(govde))


def _pes(pts):
    p = bytes([0x21 | ((pts >> 29) & 0x0E), (pts >> 22) & 0xFF, 0x01 | ((pts >> 14) & 0xFE),
               (pts >> 7) & 0xFF, 0x01 | ((pts << 1) & 0xFE)])
    return b"\x00\x00\x01\xe0\x00\x00\x80\x80\x05" + p


def test_ts_anahtar_karede_bolunur():
    parcalar = []
    ts = TsParcalayici(lambda pts, veri: parcalar.append((pts, len(veri) // TS)))
    pat = _paket(0, pusi=True, yuk=bytes([0, 0, 0xB0, 13, 0, 1, 0xC1, 0, 0, 0, 1, 0xF0, 0x00]))
    pmt = _paket(0x1000, pusi=True)
    akis = pat + pmt
    akis += _paket(0x100, pusi=True, yuk=_pes(1000))                 # anahtar kareden önce: atılır
    akis += _paket(0x100, pusi=True, rai=True, yuk=_pes(9000)) + _paket(0x100) + _paket(0x100)
    akis += _paket(0x100, pusi=True, rai=True, yuk=_pes(99000)) + _paket(0x100)
    for i in range(0, len(akis), 100):     # parça parça gelse de doğru bölünür
        ts.besle(akis[i:i + 100])
    assert len(ts.baslik) == 2 * TS
    assert parcalar == [(9000, 3)]


def _ffmpeg():
    from core.recorder import ffmpeg_bul
    return ffmpeg_bul()


@pytest.mark.skipif(_ffmpeg() is None, reason="FFmpeg yok")
def test_tekrar_bellekte_tutar_ve_mp4_yazar(tmp_path):
    t = AnlikTekrar(160, 120, 20, kodlayici="mpeg4", ffmpeg=_ffmpeg())
    t.sure_sn = 2   # test için kısa (normalde en az 30 sn)
    assert t.baslat()
    try:
        taban = np.tile(np.arange(160, dtype=np.uint8)[None, :, None], (120, 1, 3))
        for i in range(20 * 4):
            t.kare_yaz(np.roll(taban, i * 3, axis=1))
            t.ses_yaz(np.full((960, 2), 0.1, np.float32))
            time.sleep(1 / 20)
        time.sleep(0.3)
        assert t.tutulan_sure <= 3.5            # eski parçalar atıldı
        assert t.bellek > 0
        assert not list(tmp_path.iterdir())     # kaydedene kadar diske hiçbir şey yazılmaz
        bitti, sonuc = threading.Event(), []
        assert t.kaydet(tmp_path, lambda d, h: (sonuc.append((d, h)), bitti.set()))
        assert bitti.wait(30)
        dosya, hata = sonuc[0]
        assert hata == "" and dosya.name.startswith("Tekrar_") and dosya.suffix == ".mp4"
        assert [f.name for f in tmp_path.iterdir()] == [dosya.name]   # geçici dosyalar silindi
    finally:
        t.durdur()
    assert t.bellek == 0 and not t.acik


def test_kapali_tekrar_bellek_kullanmaz():
    t = AnlikTekrar(160, 120, 20)
    t.kare_yaz(np.zeros((120, 160, 3), np.uint8))
    t.ses_yaz(np.zeros((480, 2), np.float32))
    assert t.bellek == 0
    assert not t.kaydet() and "kapalı" in t.son_hata


# ---- mikser dinleyicileri (kayıt ve tekrar aynı sesi alır)

def test_mikser_birden_fazla_dinleyici():
    m = SesKaristirici()
    m.kanal_ekle("mikrofon", "Mikrofon")
    a, b = [], []
    m.dinleyici_ekle(a.append)
    m.dinleyici_ekle(b.append)
    m.dinleyici_ekle(a.append)       # iki kez eklenmez
    m.karistir(480)
    assert len(a) == 1 and len(b) == 1
    m.dinleyici_sil(a.append)
    m.karistir(480)
    assert len(a) == 1 and len(b) == 2


# ---- gürültü azaltma

def test_dll_yoksa_gurultu_kapali_kalir_ve_ses_dokunulmaz():
    g = GurultuAzaltici(True, Path("/yok/rnnoise.dll"))
    assert not g.kullanilabilir and not g.acik
    blok = np.ones(441, np.float32)
    assert g.isle(blok) is blok


def _rnnoise_yolu():
    from core.gurultu import dll_yolu
    yol = dll_yolu() or (Path(os.environ["RNNOISE_TEST"]) if os.environ.get("RNNOISE_TEST") else None)
    return yol


@pytest.mark.skipif(_rnnoise_yolu() is None, reason="RNNoise DLL yok (CI'da derlenir)")
def test_rnnoise_ayni_uzunlukta_doner_ve_gurultuyu_azaltir():
    g = GurultuAzaltici(True, _rnnoise_yolu())
    assert g.acik
    gurultu = (np.random.default_rng(0).standard_normal(48000) * 0.05).astype(np.float32)
    cikis = []
    for i in range(0, len(gurultu), 441):   # 480'in katı olmayan bloklar da çalışır
        b = gurultu[i:i + 441]
        o = g.isle(b)
        assert len(o) == len(b)
        cikis.append(o)
    cikis = np.concatenate(cikis)[CERCEVE * 10:]
    assert np.sqrt((cikis ** 2).mean()) < 0.5 * np.sqrt((gurultu ** 2).mean())


# ---- ekran görüntüsü

def test_ekran_goruntusu_turkce_klasore_png(tmp_path):
    from PIL import Image

    from main import ekran_goruntusu_kaydet
    kare = np.zeros((90, 160, 3), np.uint8)
    kare[:, :, 0] = 200
    klasor = tmp_path / "Görüntüler ğüşıöç"
    zaman = datetime(2026, 11, 2, 10, 0, 0)
    d1 = ekran_goruntusu_kaydet(kare, klasor, zaman)
    d2 = ekran_goruntusu_kaydet(kare, klasor, zaman)      # aynı saniye: üzerine yazmaz
    assert d1.name == "Goruntu_2026-11-02_10-00-00.png" and d2 != d1 and d2.exists()
    im = Image.open(d1)
    assert im.size == (160, 90) and im.getpixel((5, 5))[:3] == (200, 0, 0)


# ---- sanal çıkış uyarıları

def test_cikis_sorunu_metinleri():
    from core.state import Durum
    from ui.yardim import cikis_sorunu, yardim_metni
    assert cikis_sorunu(Durum(sanal_kamera="açık", sanal_mikrofon="açık")) == ""
    assert cikis_sorunu(Durum(sanal_kamera="kapalı")) == ""          # duraklatıldı: sorun değil
    assert cikis_sorunu(Durum(sanal_mikrofon="yok")) == "Sanal mikrofon bulunamadı"
    assert cikis_sorunu(Durum(sanal_kamera="yok")) == "Sanal kamera bulunamadı"
    assert cikis_sorunu(Durum(sanal_kamera="yok", sanal_mikrofon="yok")) == "Sanal kamera ve mikrofon bulunamadı"
    assert "VB-Cable" in yardim_metni("Sanal mikrofon bulunamadı")
    assert "OBS" in yardim_metni("Sanal kamera bulunamadı") and "VB-Cable" not in yardim_metni("Sanal kamera bulunamadı")
    assert "http" not in yardim_metni()   # yardım uygulamanın içinde; bağlantı yok


# ---- ayarlar penceresi: yeni seçenekler

def test_ayarlar_yeni_secenekler(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from core.settings import Ayarlar
    from ui.settings_dialog import AyarlarPenceresi

    class Ses:
        mikser = SesKaristirici()
        secilen = None

        def mikrofonlar(self):
            return ["USB Mikrofon"]

        def mikrofon_sec(self, ad):
            self.secilen = ad

        def sistem_ayarla(self, *a):
            pass

    a = Ayarlar(tmp_path / "settings.json")
    a.ayarla("audio.modes", {"sesim": [10, 10], "dengeli": [80, 80], "oyun": [70, 100]})
    ses, cikildi = Ses(), []
    p = AyarlarPenceresi(a, ses=ses, cikis=lambda: cikildi.append(1),
                         basarisiz=["genel:" + (a.al("hotkeys", {}).get("panik") or "Ctrl+Alt+P")])
    assert p.tekrar.isChecked() and p.tekrar_suresi.value() == 120
    assert p.mikrofon.count() == 2
    isaretli = [p.tablo.item(i, 0).text() for i in range(p.tablo.rowCount())
                if p.tablo.item(i, 0).text().startswith("⚠")]
    assert len(isaretli) == 1
    p._modlari_sifirla()
    assert a.al("audio.modes")["sesim"] != [10, 10]
    p.tekrar.setChecked(False)
    p.tekrar_suresi.setValue(60)
    p.goruntu_klasoru.setText(str(tmp_path / "foto"))
    p.mikrofon.setCurrentIndex(1)
    p._kaydet()
    assert a.al("record.replay") is False and a.al("record.replay_seconds") == 60
    assert a.al("screenshot.folder") == str(tmp_path / "foto")
    assert a.al("audio.mic_device") == "USB Mikrofon" and ses.secilen == "USB Mikrofon"
    p2 = AyarlarPenceresi(a, ses=ses, cikis=lambda: cikildi.append(1))
    p2._cik()
    assert cikildi == [1]
