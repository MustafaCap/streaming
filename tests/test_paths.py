"""Ad değişikliği (Yayın Uygulaması -> RizeOn): eski ayarlar, loglar ve bekleme görüntüleri yeni klasöre taşınır."""

import json

from core import paths


def _eski_klasor(taban):
    eski = taban / paths.ESKI_AD
    (eski / "logs").mkdir(parents=True)
    (eski / "bekleme").mkdir()
    (eski / "bekleme" / "resim.png").write_bytes(b"png")
    (eski / "settings.json").write_text(json.dumps({
        "standby_image": str(eski / "bekleme" / "resim.png"),
        "audio": {"mic_muted": True},
        "baska": "C:\\Videolar\\x.mp4",
    }), encoding="utf-8")
    return eski


def test_eski_klasor_tasinir_ve_yollar_duzelir(tmp_path, monkeypatch):
    monkeypatch.setenv("YAYIN_VERI_KLASORU", str(tmp_path))
    eski = _eski_klasor(tmp_path)
    yeni = paths.veri_klasoru()
    assert yeni == tmp_path / "RizeOn"
    assert not eski.exists()
    assert (yeni / "bekleme" / "resim.png").read_bytes() == b"png"
    ayar = json.loads((yeni / "settings.json").read_text(encoding="utf-8"))
    assert ayar["standby_image"] == str(yeni / "bekleme" / "resim.png")
    assert ayar["audio"] == {"mic_muted": True}
    assert ayar["baska"] == "C:\\Videolar\\x.mp4"


def test_yeni_klasor_varsa_eskiye_dokunulmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("YAYIN_VERI_KLASORU", str(tmp_path))
    eski = _eski_klasor(tmp_path)
    (tmp_path / "RizeOn").mkdir()
    paths.veri_klasoru()
    assert eski.exists()
    assert not (tmp_path / "RizeOn" / "settings.json").exists()


def test_tasinamazsa_kopyalar(tmp_path, monkeypatch):
    eski = _eski_klasor(tmp_path)
    yeni = tmp_path / "RizeOn"

    def kilitli(self, hedef):
        raise PermissionError("eski sürüm açık")

    monkeypatch.setattr(type(eski), "rename", kilitli)
    assert paths.eski_klasoru_tasi(eski, yeni)
    assert eski.exists() and (yeni / "bekleme" / "resim.png").exists()


def test_eski_klasor_yoksa_bos_yeni_klasor(tmp_path, monkeypatch):
    monkeypatch.setenv("YAYIN_VERI_KLASORU", str(tmp_path))
    assert paths.veri_klasoru().is_dir()
    assert not paths.eski_klasoru_tasi(tmp_path / "yok", tmp_path / "RizeOn2")
