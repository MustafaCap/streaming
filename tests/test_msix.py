"""Microsoft Store paketi (MSIX) klasörü: manifest geçerli XML, sürüm Store biçiminde, logolar doğru boyutta."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "kurulum"))

import msix_paketle  # noqa: E402

NS = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
      "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
      "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"}


def test_msix_surumu_dorduncu_sayi_sifir():
    assert msix_paketle.msix_surumu("1.5.1") == "1.5.1.0"
    assert msix_paketle.msix_surumu("2.0") == "2.0.0.0"


def test_manifest_alanlari_ve_kacis():
    xml = msix_paketle.manifest("1.5.1", "12345Ad.Uygulama", 'CN=AB12 "x" & y', "Mustafa & Co")
    kok = ET.fromstring(xml.split("\n", 1)[1])
    kimlik = kok.find("m:Identity", NS)
    assert kimlik.get("Name") == "12345Ad.Uygulama"
    assert kimlik.get("Publisher") == 'CN=AB12 "x" & y'
    assert kimlik.get("Version") == "1.5.1.0"
    assert kok.find("m:Properties/m:PublisherDisplayName", NS).text == "Mustafa & Co"
    uyg = kok.find("m:Applications/m:Application", NS)
    assert uyg.get("Executable") == "RizeOn.exe"
    assert uyg.get("EntryPoint") == "Windows.FullTrustApplication"
    yetkiler = {e.get("Name") for e in kok.find("m:Capabilities", NS)}
    assert yetkiler == {"runFullTrust", "webcam", "microphone"}


def test_kimlik_degiskenlerden(monkeypatch):
    monkeypatch.delenv("MSIX_KIMLIK_ADI", raising=False)
    assert msix_paketle.kimlik()[0] == msix_paketle.DENEME_ADI
    monkeypatch.setenv("MSIX_KIMLIK_ADI", "123.Gercek")
    monkeypatch.setenv("MSIX_YAYINCI", "CN=ABC")
    monkeypatch.setenv("MSIX_YAYINCI_ADI", "Mustafa")
    assert msix_paketle.kimlik() == ("123.Gercek", "CN=ABC", "Mustafa")


def test_hazirla_klasor_ve_logolar(tmp_path):
    uyg = tmp_path / "dist"
    uyg.mkdir()
    (uyg / "RizeOn.exe").write_bytes(b"MZ")
    (uyg / "_internal").mkdir()
    hedef = msix_paketle.hazirla(uyg, tmp_path / "msix", "1.5.1")
    assert (hedef / "RizeOn.exe").exists() and (hedef / "_internal").is_dir()
    ET.fromstring((hedef / "AppxManifest.xml").read_text(encoding="utf-8").split("\n", 1)[1])
    for ad, g, y in msix_paketle.LOGOLAR:
        with Image.open(hedef / "Assets" / ad) as im:
            assert im.size == (g, y)
            assert im.getbbox() is not None, f"{ad} boş"


def test_exe_yoksa_hata(tmp_path):
    with pytest.raises(FileNotFoundError):
        msix_paketle.hazirla(tmp_path, tmp_path / "msix")
