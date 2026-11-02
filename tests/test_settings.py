import json
from pathlib import Path

from core import paths
from core.settings import SURUM, Ayarlar


def test_ilk_acilista_varsayilanlar_yazilir():
    a = Ayarlar()
    assert a.al("video.width") == 1280
    assert paths.ayar_dosyasi().exists()


def test_eksik_alanlar_varsayilandan_tamamlanir():
    paths.ayar_dosyasi().write_text(json.dumps({"video": {"fps": 60}}), encoding="utf-8")
    a = Ayarlar()
    assert a.al("video.fps") == 60          # kullanıcının değeri korunur
    assert a.al("video.width") == 1280      # eksik olan varsayılandan gelir
    assert a.al("version") == SURUM


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
    assert a.al("hotkeys.panik") == "Ctrl+Shift+P"   # F12 -> Ctrl+Alt+P (1.x) -> Ctrl+Shift+P (2.0)
    assert a.al("hotkeys")["ses.mikrofon"] == "F2"
    assert json.loads(paths.ayar_dosyasi().read_text(encoding="utf-8"))["version"] == SURUM


def _v2_tuslari(**degisen):
    from core.settings import KISAYOL_TASIMA_3
    tuslar = {k: eski for k, (eski, _) in KISAYOL_TASIMA_3.items()}
    tuslar.update({"kayit.ac_kapat": "Ctrl+Shift+R", "kaynak.sec": "", "bas_konus": ""})
    tuslar.update(degisen)
    return tuslar


def test_kisayol_tasima_tablosu():
    from core.hotkeys import VARSAYILAN_KISAYOLLAR
    from core.settings import KISAYOL_TASIMA_3, YENI_KISAYOLLAR_3
    beklenen = {"bolge.sec": "Ctrl+Shift+S", "kalem.ac_kapat": "Ctrl+Shift+D", "ses.mikrofon": "Ctrl+Shift+M",
                "ses.sistem": "Ctrl+Shift+A", "kamera.ac_kapat": "Ctrl+Shift+C",
                "anlik_kayit.kaydet": "Ctrl+Shift+B", "panik": "Ctrl+Shift+P", "kayit.duraklat": "Ctrl+Shift+K",
                **{f"sahne.sec:{n}": f"Ctrl+Shift+{n}" for n in range(1, 5)}}
    assert {k: yeni for k, (_, yeni) in KISAYOL_TASIMA_3.items()} == beklenen
    assert KISAYOL_TASIMA_3["ses.mikrofon"][0] == "F8" and KISAYOL_TASIMA_3["kayit.duraklat"][0] == "Ctrl+Alt+D"
    # yeni varsayılanlar settings.default.json ve Ayarlar penceresindeki "Varsayılanlara dön" ile aynı
    for komut, tus in {**beklenen, **YENI_KISAYOLLAR_3}.items():
        assert VARSAYILAN_KISAYOLLAR[komut] == tus
    varsayilan = json.loads(paths.varsayilan_ayar_dosyasi().read_text(encoding="utf-8"))["hotkeys"]
    for komut, tus in VARSAYILAN_KISAYOLLAR.items():
        assert varsayilan[komut] == tus
    tuslar = list(VARSAYILAN_KISAYOLLAR.values())
    assert len(tuslar) == len(set(tuslar))   # iki işe aynı tuş verilmemiş


def test_degistirilmemis_kisayollar_tasinir_degistirilenler_kalir():
    paths.ayar_dosyasi().write_text(json.dumps({"version": 2, "hotkeys": _v2_tuslari(**{"ses.mikrofon": "F2"}),
                                                "pen_hotkeys": {"kalem.tur:1": "1"}}), encoding="utf-8")
    a = Ayarlar()
    t = a.al("hotkeys")
    assert t["ses.mikrofon"] == "F2"                       # kullanıcı değiştirmiş: dokunulmaz
    assert t["bolge.sec"] == "Ctrl+Shift+S" and t["anlik_kayit.kaydet"] == "Ctrl+Shift+B"
    assert t["sahne.sec:1"] == "Ctrl+Shift+1" and t["kayit.duraklat"] == "Ctrl+Shift+K"
    assert t["sahne.sec:9"] == "Ctrl+Shift+9" and t["ekran.goruntusu"] == "Ctrl+Shift+G"
    assert t["kalem.temizle"] == "Ctrl+Shift+X"
    assert a.al("pen_hotkeys")["kalem.tur:7"] == "7" and a.al("pen_hotkeys")["kalem.kapat"] == "Esc"
    assert a.al("audio.ptt") is False
    assert json.loads(paths.ayar_dosyasi().read_text(encoding="utf-8"))["version"] == SURUM


def test_cakisan_yeni_varsayilan_bos_kalir():
    # Kullanıcı mikrofonu Ctrl+Shift+S'ye almış: bölge Ctrl+Shift+S'ye taşınamaz, boş kalır.
    # Ekran görüntüsünün yeni tuşu da kullanıcının bas-konuş tuşuyla çakışıyor.
    paths.ayar_dosyasi().write_text(json.dumps({"version": 2, "hotkeys": _v2_tuslari(
        **{"ses.mikrofon": "ctrl+shift+s", "bas_konus": "Ctrl+Shift+G"})}), encoding="utf-8")
    a = Ayarlar()
    t = a.al("hotkeys")
    assert t["ses.mikrofon"] == "ctrl+shift+s" and t["bolge.sec"] == ""
    assert t["ekran.goruntusu"] == "" and t["bas_konus"] == "Ctrl+Shift+G"
    assert t["kalem.ac_kapat"] == "Ctrl+Shift+D"
    assert a.al("audio.ptt") is True                       # bas-konuş tuşu vardı: anahtar açık başlar


def test_yeni_kurulumda_tasima_yapilmaz():
    a = Ayarlar()
    assert a.al("hotkeys")["bolge.sec"] == "Ctrl+Shift+S" and a.al("audio.ptt") is False


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


def test_2_0_1_gelismis_gorunum_bir_kez_acik_gelir():
    paths.ayar_dosyasi().write_text(json.dumps({"version": 3, "ui": {"advanced": False}}), encoding="utf-8")
    a = Ayarlar()
    assert a.al("ui.advanced") is True and a.al("version") == SURUM
    a.ayarla("ui.advanced", False)
    a.kaydet()
    assert Ayarlar().al("ui.advanced") is False            # kapatınca hatırlanır, tekrar açılmaz


def test_surum5_tekrar_suresi_15_sn_olur_ama_degistirilmis_kalir(tmp_path):
    import json

    from core.settings import Ayarlar
    varsayilan = Path(__file__).resolve().parent.parent / "config" / "settings.default.json"
    for eski, beklenen in ((120, 15), (60, 60)):
        dosya = tmp_path / f"s{eski}.json"
        dosya.write_text(json.dumps({"version": 4, "record": {"replay_seconds": eski}}), encoding="utf-8")
        assert Ayarlar(dosya, varsayilan).al("record.replay_seconds") == beklenen
