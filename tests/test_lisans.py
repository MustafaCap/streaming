"""Lisans dosyaları: GPLv3 metni, üçüncü parti lisansların toplanması, kurulum lisans sayfası."""

import importlib.util
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _betik():
    spec = importlib.util.spec_from_file_location("lisanslar", KOK / "kurulum" / "lisanslar.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_uygulama_gplv3_ile_lisanslanir():
    metin = (KOK / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in metin and "Version 3, 29 June 2007" in metin


def test_ucuncu_parti_lisanslar_toplanir(tmp_path):
    gereksinim = tmp_path / "requirements.txt"
    gereksinim.write_text("# yorum\nnumpy\nolmayan-paket-xyz\nPyAudioWPatch; sys_platform == \"nope\"\n",
                          encoding="utf-8")
    paket = tmp_path / "paket"
    satirlar = _betik().topla(paket, gereksinim)

    assert (paket / "LICENSE.txt").read_text(encoding="utf-8").startswith(
        (KOK / "LICENSE").read_text(encoding="utf-8")[:200])
    adlar = [a for a, _ in satirlar]
    assert any(a.lower().startswith("numpy ") for a in adlar)
    assert not any("olmayan" in a or "pyaudiowpatch" in a.lower() for a in adlar)
    numpy_klasoru = next((paket / "lisanslar").glob("numpy-*"))
    assert any(numpy_klasoru.iterdir()), "numpy'nin lisans dosyası kopyalanmalı"
    liste = (paket / "lisanslar" / "UCUNCU_PARTI_LISANSLAR.txt").read_text(encoding="utf-8-sig")
    assert "GPL sürüm 3" in liste and "numpy" in liste


def test_bilinen_paketlerin_lisans_notu_var():
    betik = _betik()
    assert "GPLv2" in betik.NOTLAR["pyvirtualcam"]
    assert "LGPLv3" in betik.NOTLAR["pyside6"]


def test_kurulum_lisans_sayfasi_bomlu_ozet_ve_gpl_icerir(tmp_path):
    cikti = _betik().kurulum_metni(tmp_path / "kurulum_lisans.txt")
    ham = cikti.read_bytes()
    assert ham.startswith(b"\xef\xbb\xbf"), "Inno Setup Türkçe harfleri BOM ile tanır"
    metin = ham.decode("utf-8-sig")
    assert metin.index("HİÇBİR GARANTİ") < metin.index("GNU GENERAL PUBLIC LICENSE")
    assert "https://github.com/MustafaCap/streaming" in metin


def test_kurulum_betigi_lisans_sayfasini_gosterir():
    iss = (KOK / "kurulum" / "kurulum.iss").read_text(encoding="utf-8-sig")
    assert "LicenseFile=..\\build\\kurulum_lisans.txt" in iss
