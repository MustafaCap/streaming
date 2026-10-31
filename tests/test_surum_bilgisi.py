"""Exe sürüm bilgisi (Windows Özellikler > Ayrıntılar) ve paketlenmiş exe duman testi."""

import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "kurulum"))

import surum_bilgisi  # noqa: E402

from core.surum import SURUM  # noqa: E402


class _Kayit:
    """PyInstaller'ın sınıfları yerine: eval edilen metni ağaç olarak saklar (Linux'ta test için)."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


def _cozumle(metin: str) -> _Kayit:
    adlar = ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct",
             "VarFileInfo", "VarStruct")
    return eval(metin, {ad: type(ad, (_Kayit,), {}) for ad in adlar})


def test_surum_sayilari():
    assert surum_bilgisi.sayilar("1.5.1") == (1, 5, 1, 0)
    assert surum_bilgisi.sayilar("2.0") == (2, 0, 0, 0)
    for kotu in ("1.x", "1.2.3.4.5", "70000.0"):
        with pytest.raises(ValueError):
            surum_bilgisi.sayilar(kotu)


def test_surum_core_surum_ile_ayni():
    assert surum_bilgisi.surum() == SURUM


def test_metin_alanlari():
    bilgi = _cozumle(surum_bilgisi.metin("1.5.1"))
    ffi = bilgi.kwargs["ffi"].kwargs
    assert ffi["filevers"] == ffi["prodvers"] == (1, 5, 1, 0)
    dize_bilgisi, dil_bilgisi = bilgi.kwargs["kids"]
    tablo = dize_bilgisi.args[0][0]
    assert tablo.args[0] == "041F04B0"
    alanlar = {s.args[0]: s.args[1] for s in tablo.args[1]}
    assert alanlar["ProductName"] == "Yayın Uygulaması"
    assert alanlar["FileVersion"] == alanlar["ProductVersion"] == "1.5.1"
    assert alanlar["OriginalFilename"] == "YayinUygulamasi.exe"
    assert "GPL" in alanlar["LegalCopyright"]
    assert dil_bilgisi.args[0][0].args == ("Translation", [0x041F, 1200])


def test_dosyaya_yazar_ve_utf8(tmp_path):
    import subprocess
    hedef = tmp_path / "surum.txt"
    subprocess.run([sys.executable, str(KOK / "kurulum" / "surum_bilgisi.py"), str(hedef)], check=True)
    metin = hedef.read_bytes().decode("utf-8")
    assert metin.startswith("# -*- coding: utf-8 -*-")
    assert f"'FileVersion', '{SURUM}'" in metin


@pytest.mark.skipif(sys.platform != "win32" or importlib.util.find_spec("PyInstaller") is None,
                    reason="PyInstaller'ın sürüm dosyası okuyucusu sadece Windows'ta çalışır")
def test_pyinstaller_okuyabiliyor(tmp_path):
    from PyInstaller.utils.win32 import versioninfo
    hedef = tmp_path / "surum.txt"
    hedef.write_text(surum_bilgisi.metin(), encoding="utf-8")
    bilgi = versioninfo.load_version_info_from_text_file(str(hedef))
    assert isinstance(bilgi, versioninfo.VSVersionInfo)
    assert "Yayın Uygulaması" in str(bilgi)


def test_duman_testi_hata_dosyaya_yazilir(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "DUMAN_MODULLERI", ("olmayan_modul_xyz",))
    sonuc = tmp_path / "sonuc.txt"
    assert main.duman_testi(str(sonuc)) == 1
    assert "olmayan_modul_xyz" in sonuc.read_text(encoding="utf-8")


def test_duman_testi_ffmpeg_yoksa_basarisiz(tmp_path, monkeypatch):
    import main
    from core import recorder
    monkeypatch.setattr(main, "DUMAN_MODULLERI", ("json",))
    monkeypatch.setattr(recorder, "ffmpeg_bul", lambda: None)
    sonuc = tmp_path / "sonuc.txt"
    assert main.duman_testi(str(sonuc)) == 1
    assert "ffmpeg" in sonuc.read_text(encoding="utf-8")


def test_duman_testi_basarili(tmp_path, monkeypatch):
    import main
    from core import recorder
    monkeypatch.setattr(main, "DUMAN_MODULLERI", ("json",))
    monkeypatch.setattr(recorder, "ffmpeg_bul", lambda: "ffmpeg.exe")
    sonuc = tmp_path / "sonuc.txt"
    assert main.duman_testi(str(sonuc)) == 0
    assert sonuc.read_text(encoding="utf-8").startswith(f"tamam · sürüm {SURUM}")
