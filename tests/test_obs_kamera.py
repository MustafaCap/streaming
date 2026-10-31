"""OBS sanal kamera kuyruğu: bellek düzeni OBS sürücüsünün beklediğiyle aynı olmalı."""

import ctypes
import sys

import numpy as np
import pytest

from outputs import obs_kamera
from outputs.obs_kamera import (BASLIK_BOYUTU, DURUM_BASLIYOR, DURUM_DURUYOR, DURUM_HAZIR, KARE_BASLIGI,
                                KareKuyrugu, bellek_duzeni)


def _kuyruk(gen=64, yuk=36, fps=30):
    _, boyut, _ = bellek_duzeni(gen, yuk)
    bellek = (ctypes.c_uint8 * boyut)()
    return bellek, KareKuyrugu(ctypes.addressof(bellek), gen, yuk, fps)


def test_bellek_duzeni_obs_ile_ayni():
    ofsetler, boyut, kare = bellek_duzeni(1280, 720)
    assert kare == 1280 * 720 * 3 // 2
    assert ofsetler[0] == 96                       # 80 baytlık başlık 32'ye yuvarlanır
    assert ofsetler[1] == (96 + 32 + kare + 31) & ~31
    assert ofsetler[2] == (ofsetler[1] + 32 + kare + 31) & ~31
    assert boyut == (ofsetler[2] + 32 + kare + 31) & ~31
    assert all(o % 32 == 0 for o in ofsetler)


def test_baslik_alanlari_dogru_yerde():
    assert obs_kamera._Baslik.state.offset == 8
    assert obs_kamera._Baslik.offsets.offset == 12
    assert obs_kamera._Baslik.cx.offset == 28 and obs_kamera._Baslik.cy.offset == 32
    assert obs_kamera._Baslik.interval.offset == 40


def test_acilinca_baslik_hazirlanir():
    bellek, k = _kuyruk(64, 36, 30)
    ham = bytes(bellek)
    alanlar = np.frombuffer(ham[:40], np.uint32)
    assert alanlar[2] == DURUM_BASLIYOR
    assert list(alanlar[3:6]) == k.ofsetler
    assert alanlar[6] == 0 and alanlar[7] == 64 and alanlar[8] == 36
    assert int.from_bytes(ham[40:48], "little") == 10_000_000 // 30


def test_kare_nv12_olarak_yazilir_ve_hazir_isaretlenir():
    bellek, k = _kuyruk(64, 36)
    kirmizi = np.zeros((36, 64, 3), np.uint8)
    kirmizi[..., 0] = 255
    k.yaz(kirmizi)
    ham = np.frombuffer(bytes(bellek), np.uint8)
    basl = np.frombuffer(ham[:12].tobytes(), np.uint32)
    assert basl[0] == 1 and basl[1] == 1 and basl[2] == DURUM_HAZIR
    yuva = k.ofsetler[1]                            # sayaç 1 -> yuva 1 % 3
    assert int.from_bytes(ham[yuva:yuva + 8].tobytes(), "little") > 0   # zaman damgası
    kare = ham[yuva + KARE_BASLIGI: yuva + KARE_BASLIGI + k.kare_boyutu]
    y, uv = kare[:64 * 36], kare[64 * 36:]
    assert abs(int(y.mean()) - 82) <= 1             # BT.601 sınırlı aralık: kırmızı Y≈82
    assert abs(int(uv[0::2].mean()) - 90) <= 1      # U
    assert abs(int(uv[1::2].mean()) - 240) <= 1     # V
    # diğer yuvalara dokunulmadı
    assert not ham[k.ofsetler[0] + KARE_BASLIGI:k.ofsetler[0] + KARE_BASLIGI + 100].any()


def test_yuvalar_sirayla_kullanilir_ve_farkli_boyut_olceklenir():
    bellek, k = _kuyruk(64, 36)
    for i in range(1, 5):
        k.yaz(np.full((72, 128, 3), 255, np.uint8))  # büyük kare küçültülür
        basl = np.frombuffer(bytes(bellek)[:8], np.uint32)
        assert basl[0] == i and basl[1] == i
    ham = np.frombuffer(bytes(bellek), np.uint8)
    for o in k.ofsetler:
        assert ham[o + KARE_BASLIGI] == 235          # beyaz: Y=235


def test_durdurunca_surucuye_durdu_denir():
    bellek, k = _kuyruk()
    k.yaz(np.zeros((36, 64, 3), np.uint8))
    k.durdur()
    assert np.frombuffer(bytes(bellek)[8:12], np.uint32)[0] == DURUM_DURUYOR


def test_tek_sayili_boyut_reddedilir():
    _, boyut, _ = bellek_duzeni(64, 36)
    bellek = (ctypes.c_uint8 * boyut)()
    with pytest.raises(ValueError):
        KareKuyrugu(ctypes.addressof(bellek), 63, 36, 30)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows dışında sürücü yok")
def test_windows_disinda_acilmaz_ama_cokmez():
    from outputs.virtualcam import SanalKameraCikisi, SanalKameraYok
    cikis = SanalKameraCikisi(1280, 720, 30)
    with pytest.raises(SanalKameraYok):
        cikis.ac()
    assert not cikis.acik
    cikis.gonder(np.zeros((720, 1280, 3), np.uint8))   # kapalıyken sessizce yok sayılır
    cikis.kapat()


@pytest.mark.skipif(sys.platform != "win32", reason="sadece Windows")
def test_windows_bellek_ac_yaz_kapat(monkeypatch):
    """Gerçek paylaşılan bellek: sürücü kontrolünü atlayıp aç, yaz, başka okuyucu görsün, kapat."""
    monkeypatch.setattr(obs_kamera, "surucu_kurulu", lambda: True)
    monkeypatch.setattr(obs_kamera, "BELLEK_ADI", "RizeOnTest_OBSVirtualCamVideo")
    kamera = obs_kamera.ObsSanalKamera(64, 36, 30)
    try:
        with pytest.raises(obs_kamera.KameraAcilamadi):
            obs_kamera.ObsSanalKamera(64, 36, 30)        # ikinci kez açılamaz (kullanımda)
        kamera.gonder(np.zeros((36, 64, 3), np.uint8))
        assert kamera.kuyruk.baslik.state == DURUM_HAZIR
    finally:
        kamera.kapat()
    yeniden = obs_kamera.ObsSanalKamera(64, 36, 30)     # kapatınca bellek bırakılır
    yeniden.kapat()
    assert BASLIK_BOYUTU == 96
