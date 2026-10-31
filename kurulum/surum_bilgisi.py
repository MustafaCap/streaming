"""RizeOn.exe'nin Windows "Özellikler > Ayrıntılar" bilgisini (sürüm kaynağı) üretir.

Exe'de üretici, ürün adı, sürüm ve telif bilgisi yazar. İmzalama servisleri (SignPath) bu
bilgilerin her sürümde tutarlı olmasını ister; antivirüsler de bilgisi boş exe'lere daha
şüpheli bakar.

Kullanım (CI):  python kurulum/surum_bilgisi.py build/surum_bilgisi.txt
                pyinstaller ... --version-file build/surum_bilgisi.txt
"""

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

URUN = "RizeOn"
URETICI = "Mustafa"
EXE = "RizeOn.exe"
TELIF = "Copyright (C) 2026 Mustafa. GNU GPL sürüm 3 ile lisanslıdır."
ACIKLAMA = "RizeOn - ekran, kamera ve ses paylaşımı"
KAYNAK = "https://github.com/MustafaCap/streaming"
# Türkçe (0x041F), Unicode kod sayfası (1200 = 0x04B0)
DIL, KOD_SAYFASI = 0x041F, 1200


def surum() -> str:
    metin = (KOK / "core" / "surum.py").read_text(encoding="utf-8")
    return re.search(r'SURUM = "([^"]+)"', metin).group(1)


def sayilar(surum_metni: str) -> tuple[int, int, int, int]:
    """"1.5.1" -> (1, 5, 1, 0). Windows sürüm alanı dört sayı ister."""
    parcalar = [int(p) for p in surum_metni.split(".")]
    if not 1 <= len(parcalar) <= 4 or any(not 0 <= p <= 0xFFFF for p in parcalar):
        raise ValueError(f"Geçersiz sürüm numarası: {surum_metni}")
    return tuple(parcalar + [0] * (4 - len(parcalar)))


def metin(surum_metni: str | None = None) -> str:
    s = surum_metni or surum()
    n = sayilar(s)
    alanlar = [
        ("CompanyName", URETICI),
        ("FileDescription", ACIKLAMA),
        ("FileVersion", s),
        ("InternalName", "RizeOn"),
        ("LegalCopyright", TELIF),
        ("OriginalFilename", EXE),
        ("ProductName", URUN),
        ("ProductVersion", s),
        ("Comments", f"Özgür ve açık kaynak. Kaynak kod: {KAYNAK}"),
    ]
    dizeler = ",\n".join(f"          StringStruct({ad!r}, {deger!r})" for ad, deger in alanlar)
    return f"""# -*- coding: utf-8 -*-
# kurulum/surum_bilgisi.py üretti; elle değiştirme.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={n},
    prodvers={n},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '{DIL:04X}{KOD_SAYFASI:04X}',
        [
{dizeler}
        ])
    ]),
    VarFileInfo([VarStruct('Translation', [{DIL:#06x}, {KOD_SAYFASI}])])
  ]
)
"""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolu (cp1252) Türkçe harfte çökmesin
    hedef = Path(sys.argv[1] if len(sys.argv) > 1 else KOK / "build" / "surum_bilgisi.txt")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(metin(), encoding="utf-8")
    print(f"Sürüm bilgisi yazıldı: {hedef} ({surum()})")
