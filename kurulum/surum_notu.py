"""CHANGELOG.md'den bir sürümün notunu çıkarır (Releases sayfası için).

    python kurulum/surum_notu.py 1.5.0 surum_notu.md
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def surum_notu(surum: str, degisiklikler: Path = KOK / "CHANGELOG.md") -> str:
    satirlar, icinde = [], False
    for satir in degisiklikler.read_text(encoding="utf-8").splitlines():
        if satir.startswith("## "):
            if icinde:
                break
            icinde = satir[3:].split()[0] == surum
            continue
        if icinde:
            satirlar.append(satir)
    if not icinde and not satirlar:
        raise SystemExit(f"CHANGELOG.md'de {surum} sürümü yok")
    return "\n".join(satirlar).strip() + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) not in (2, 3):
        sys.exit("kullanım: python kurulum/surum_notu.py <sürüm> [çıktı.md]")
    notu = surum_notu(sys.argv[1])
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(notu, encoding="utf-8")   # PowerShell yönlendirmesi Türkçe harfleri bozmasın
    else:
        print(notu, end="")
