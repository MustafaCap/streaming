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
