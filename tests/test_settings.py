import json

from core import paths
from core.settings import Ayarlar


def test_ilk_acilista_varsayilanlar_yazilir():
    a = Ayarlar()
    assert a.al("video.width") == 1280
    assert paths.ayar_dosyasi().exists()


def test_eksik_alanlar_varsayilandan_tamamlanir():
    paths.ayar_dosyasi().write_text(json.dumps({"video": {"fps": 60}}), encoding="utf-8")
    a = Ayarlar()
    assert a.al("video.fps") == 60          # kullanıcının değeri korunur
    assert a.al("video.width") == 1280      # eksik olan varsayılandan gelir
    assert a.al("version") == 2


def test_bozuk_dosya_uygulamayi_cokertmez():
    paths.ayar_dosyasi().write_text("{bu json değil", encoding="utf-8")
    a = Ayarlar()
    assert a.al("video.fps") == 30
    assert paths.ayar_dosyasi().with_suffix(".bozuk.json").exists()


def test_ayarla_ve_tekrar_yukle():
    a = Ayarlar()
    a.ayarla("video.monitor", 1)
    assert Ayarlar().al("video.monitor") == 1


def test_olmayan_yol_varsayilan_doner():
    assert Ayarlar().al("yok.boyle.bir.sey", "x") == "x"


def test_eski_f12_panik_tusu_tasinir():
    paths.ayar_dosyasi().write_text(json.dumps({"version": 1, "hotkeys": {"panik": "F12", "ses.mikrofon": "F2"}}),
                                    encoding="utf-8")
    a = Ayarlar()
    assert a.al("hotkeys.panik") == "Ctrl+Alt+P"
    assert a.al("hotkeys")["ses.mikrofon"] == "F2"
    assert json.loads(paths.ayar_dosyasi().read_text(encoding="utf-8"))["version"] == 2


def test_yanlis_turdeki_deger_varsayilana_doner():
    paths.ayar_dosyasi().write_text(json.dumps({"video": {"width": "geniş", "fps": 60.0, "show_cursor": "evet"},
                                                "audio": {"mic_gain": 2}, "camera": {"position": [0.5, 0.5]}}),
                                    encoding="utf-8")
    a = Ayarlar()
    assert a.al("video.width") == 1280                   # metin -> varsayılan
    assert a.al("video.fps") == 60 and isinstance(a.al("video.fps"), int)   # 60.0 -> 60
    assert a.al("video.show_cursor") is True             # "evet" bool değil -> varsayılan
    assert a.al("audio.mic_gain") == 2.0 and isinstance(a.al("audio.mic_gain"), float)
    assert a.al("camera.position") == [0.5, 0.5]         # türü serbest alan korunur


def test_kaydedilemezse_cokmez(monkeypatch):
    a = Ayarlar()

    def kilitli(*_a, **_k):
        raise PermissionError("dosya başka bir program tarafından kullanılıyor")

    monkeypatch.setattr(type(paths.ayar_dosyasi()), "replace", kilitli)
    a.ayarla("video.monitor", 2)                          # hata fırlatmamalı
    assert a.al("video.monitor") == 2
    assert a.kaydet() is False
