"""Pakete giren her parçanın lisans metnini toplar (GPL, LGPL ve Apache bunu ister).

CI'da PyInstaller'dan ve FFmpeg kopyalandıktan sonra çalışır:

    python kurulum/lisanslar.py dist/YayinUygulamasi

Ne üretir:
  <paket>/LICENSE.txt                              uygulamanın kendi lisansı (GPLv3)
  <paket>/lisanslar/UCUNCU_PARTI_LISANSLAR.txt     kullanılan parçaların listesi ve lisansları
  <paket>/lisanslar/<ad>-<sürüm>/...               her Python paketinin kendi lisans dosyaları
  build/kurulum_lisans.txt                         kurulum programının lisans sayfası
                                                   (Türkçe özet + GPLv3 tam metni, UTF-8 BOM'lu)
"""

from __future__ import annotations

import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

try:
    from packaging.requirements import Requirement
except ImportError:  # pip her zaman yanında getirir
    from pip._vendor.packaging.requirements import Requirement

KOK = Path(__file__).resolve().parent.parent
KAYNAK = "https://github.com/MustafaCap/streaming"

# Paket bilgisinde lisans yazmayan ya da eksik yazan parçalar için açıklama
NOTLAR = {
    "pyvirtualcam": "GPLv2. Paketin lisans bilgisinde 'veya sonraki sürüm' ifadesi yok.",
    "pyside6": "LGPLv3 (Qt for Python). Qt kütüphaneleri ayrı DLL olarak pakette, değiştirilebilir.",
    "pyside6-essentials": "LGPLv3 (Qt for Python)",
    "pyside6-addons": "LGPLv3 (Qt for Python)",
    "shiboken6": "LGPLv3 (Qt for Python)",
    "opencv-python": "Apache-2.0. İçindeki FFmpeg (opencv_videoio_ffmpeg) LGPLv2.1.",
    "numpy": "BSD-3-Clause. İçindeki OpenBLAS BSD, gfortran çalışma kitaplığı GPLv3 + GCC çalışma zamanı istisnası.",
    "pyaudiowpatch": "MIT. İçindeki PortAudio MIT benzeri lisanslı.",
}

# pip ile gelmeyen parçalar: (ad, lisans, paket içindeki lisans dosyası)
DIGERLERI = [
    ("FFmpeg (BtbN LGPL derlemesi)", "LGPLv2.1 veya sonrası. Kaynak: https://github.com/BtbN/FFmpeg-Builds",
     "ffmpeg/LICENSE.txt"),
    ("MediaPipe Selfie Segmentation modeli", "Apache-2.0",
     "_internal/models/LICENSE-mediapipe-Apache-2.0.txt"),
    ("Python", "PSF License (PyInstaller paketin içine Python çalışma zamanını koyar)", "lisanslar/Python/LICENSE.txt"),
    ("PyInstaller başlatıcısı", "GPLv2 + başlatıcı istisnası (paketlenen programın lisansını etkilemez)",
     "lisanslar/PyInstaller/COPYING.txt"),
]

LISANS_DOSYASI = re.compile(r"^(licen[cs]e|copying|notice|authors)", re.IGNORECASE)


def gereksinimler(dosya: Path) -> list[str]:
    adlar = []
    for satir in dosya.read_text(encoding="utf-8").splitlines():
        satir = satir.split("#", 1)[0].strip()
        if not satir:
            continue
        g = Requirement(satir)
        if g.marker is None or g.marker.evaluate():
            adlar.append(g.name)
    return adlar


def bagimliliklari_topla(adlar: list[str]) -> dict[str, metadata.Distribution]:
    """Verilen paketler ve onların bağımlılıkları (pakete giren her şey)."""
    bulunan: dict[str, metadata.Distribution] = {}
    sira = list(adlar)
    while sira:
        ad = sira.pop()
        anahtar = ad.lower().replace("_", "-")
        if anahtar in bulunan:
            continue
        try:
            dist = metadata.distribution(ad)
        except metadata.PackageNotFoundError:
            continue
        bulunan[anahtar] = dist
        for gereken in dist.requires or []:
            g = Requirement(gereken)
            if g.marker is None or g.marker.evaluate({"extra": ""}):
                sira.append(g.name)
    return dict(sorted(bulunan.items()))


def lisans_adi(anahtar: str, dist: metadata.Distribution) -> str:
    if anahtar in NOTLAR:
        return NOTLAR[anahtar]
    md = dist.metadata
    ifade = md.get("License-Expression")
    if ifade:
        return ifade
    siniflar = [s.split("::")[-1].strip() for s in md.get_all("Classifier") or [] if s.startswith("License ::")]
    if siniflar:
        return ", ".join(siniflar)
    lisans = (md.get("License") or "").strip()
    if lisans and "\n" not in lisans and len(lisans) < 80:
        return lisans
    return "paketin lisans dosyasına bakın"


def lisans_dosyalari(dist: metadata.Distribution) -> list[tuple[Path, Path]]:
    """(dosyanın yeri, dist-info içindeki göreli yolu) çiftleri; alt klasörler korunur."""
    dosyalar = []
    for f in dist.files or []:
        parcalar = Path(str(f)).parts
        bilgi = next((i for i, p in enumerate(parcalar[:-1]) if p.endswith((".dist-info", ".egg-info"))), None)
        if bilgi is None or not ("licenses" in parcalar or LISANS_DOSYASI.match(parcalar[-1])):
            continue
        yol = Path(dist.locate_file(f))
        if yol.is_file():
            dosyalar.append((yol, Path(*parcalar[bilgi + 1:])))
    return dosyalar


def topla(hedef: Path, gereksinim_dosyasi: Path = KOK / "requirements.txt") -> list[tuple[str, str]]:
    """Lisansları hedef pakete kopyalar; (parça, lisans) listesini döndürür."""
    hedef = Path(hedef)
    klasor = hedef / "lisanslar"
    klasor.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(KOK / "LICENSE", hedef / "LICENSE.txt")

    satirlar: list[tuple[str, str]] = []
    for anahtar, dist in bagimliliklari_topla(gereksinimler(gereksinim_dosyasi)).items():
        ad, surum = dist.metadata["Name"], dist.version
        alt = klasor / f"{ad}-{surum}"
        for dosya, goreli in lisans_dosyalari(dist):
            (alt / goreli).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dosya, alt / goreli)
        satirlar.append((f"{ad} {surum}", lisans_adi(anahtar, dist)))

    _python_ve_pyinstaller(klasor)
    for ad, lisans, dosya in DIGERLERI:
        if (hedef / dosya).is_file():
            satirlar.append((ad, f"{lisans}  [{dosya}]"))
    _liste_yaz(klasor / "UCUNCU_PARTI_LISANSLAR.txt", satirlar)
    return satirlar


def _python_ve_pyinstaller(klasor: Path) -> None:
    python_lisansi = Path(sys.base_prefix) / "LICENSE.txt"
    if python_lisansi.is_file():
        (klasor / "Python").mkdir(exist_ok=True)
        shutil.copyfile(python_lisansi, klasor / "Python" / "LICENSE.txt")
    try:
        dosyalar = lisans_dosyalari(metadata.distribution("pyinstaller"))
    except metadata.PackageNotFoundError:
        return
    if dosyalar:
        (klasor / "PyInstaller").mkdir(exist_ok=True)
        shutil.copyfile(dosyalar[0][0], klasor / "PyInstaller" / "COPYING.txt")


def _liste_yaz(dosya: Path, satirlar: list[tuple[str, str]]) -> None:
    metin = [
        "Yayın Uygulaması — kullanılan açık kaynak parçalar",
        "",
        "Uygulamanın kendisi GNU GPL sürüm 3 ile dağıtılır (../LICENSE.txt).",
        f"Kaynak kod: {KAYNAK}",
        "Her parçanın lisans metni bu klasörde, kendi adını taşıyan alt klasördedir.",
        "",
    ]
    genislik = max(len(a) for a, _ in satirlar) + 2
    metin += [f"{a.ljust(genislik)}{l}" for a, l in satirlar]
    dosya.write_text("\n".join(metin) + "\n", encoding="utf-8-sig")


def kurulum_metni(cikti: Path = KOK / "build" / "kurulum_lisans.txt") -> Path:
    """Inno Setup lisans sayfası: Türkçe özet + GPLv3 tam metni (BOM'lu UTF-8, Türkçe harfler için)."""
    cikti.parent.mkdir(parents=True, exist_ok=True)
    ozet = (KOK / "kurulum" / "lisans_ozeti.txt").read_text(encoding="utf-8")
    gpl = (KOK / "LICENSE").read_text(encoding="utf-8")
    cikti.write_text(ozet + "\n" + gpl, encoding="utf-8-sig")
    return cikti


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolu cp1252: Türkçe harfler çökertmesin
    if len(sys.argv) != 2:
        sys.exit("kullanım: python kurulum/lisanslar.py dist/YayinUygulamasi")
    liste = topla(Path(sys.argv[1]))
    print(f"{len(liste)} parçanın lisansı toplandı")
    print("Kurulum lisans sayfası:", kurulum_metni())
