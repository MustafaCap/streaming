"""Rust sürümünün paket klasörünü kuruluma ve Store'a hazırlar.

CI'da (rust.yml) exe ve FFmpeg paket/RizeOn'a kopyalandıktan sonra çalışır:

    python rust/paket/paketle.py paket/RizeOn build

Ne üretir:
  <paket>/LICENSE.txt                              uygulamanın lisansı (GPLv3)
  <paket>/lisanslar/UCUNCU_PARTI_LISANSLAR.txt     exe'ye giren Rust kütüphaneleri ve lisansları
  <paket>/lisanslar/<ad>-<sürüm>/...               her kütüphanenin kendi lisans dosyaları
  <build>/kurulum_lisans.txt                       kurulum programının lisans sayfası
  <build>/msix/                                    Store paketi klasörü (makeappx pack ile paketlenir)
  <build>/surum.txt                                Windows'un istediği dört sayılı sürüm (3.0.0)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
RUST = KOK / "rust"
sys.path.insert(0, str(KOK / "kurulum"))

HEDEF_PLATFORM = "x86_64-pc-windows-msvc"
LISANS_DOSYASI = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|UNLICENSE|COPYRIGHT)", re.I)


def surum() -> str:
    """Cargo.toml'daki sürümün sayı kısmı: "3.0.0-alpha.1" -> "3.0.0"."""
    metin = (RUST / "Cargo.toml").read_text(encoding="utf-8")
    tam = re.search(r'^version\s*=\s*"([^"]+)"', metin, re.M).group(1)
    return tam.split("-")[0].split("+")[0]


def kutuphaneler() -> list[dict]:
    """Windows exe'sine giren (geliştirme ve derleme bağımlılıkları hariç) kütüphaneler."""
    cikti = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform", HEDEF_PLATFORM],
        cwd=RUST, check=True, capture_output=True, text=True, encoding="utf-8").stdout
    veri = json.loads(cikti)
    paketler = {p["id"]: p for p in veri["packages"]}
    dugumler = {d["id"]: d for d in veri["resolve"]["nodes"]}
    kok = veri["resolve"]["root"]
    gorulen, yigin = set(), [kok]
    while yigin:
        kimlik = yigin.pop()
        if kimlik in gorulen:
            continue
        gorulen.add(kimlik)
        for dep in dugumler[kimlik]["deps"]:
            # Sadece normal bağımlılıklar exe'ye girer (dev/build bağımlılıkları girmez)
            if any(t["kind"] is None for t in dep["dep_kinds"]):
                yigin.append(dep["pkg"])
    gorulen.discard(kok)
    return sorted((paketler[k] for k in gorulen), key=lambda p: (p["name"].lower(), p["version"]))


MIT_METNI = """MIT License

Copyright (c) {yazarlar}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def apache_metni(paketler: list[dict]) -> str | None:
    """Apache-2.0 metni her kütüphanede aynıdır; pakette dosyası olan ilk kütüphaneden alınır."""
    for p in paketler:
        f = Path(p["manifest_path"]).parent / "LICENSE-APACHE"
        if f.is_file():
            return f.read_text(encoding="utf-8", errors="replace")
    return None


def lisanslari_topla(hedef: Path) -> int:
    klasor = hedef / "lisanslar"
    if klasor.exists():
        shutil.rmtree(klasor)
    klasor.mkdir(parents=True)
    shutil.copyfile(KOK / "LICENSE", hedef / "LICENSE.txt")
    satirlar = []
    liste = kutuphaneler()
    apache = apache_metni(liste)
    for p in liste:
        ad = f"{p['name']}-{p['version']}"
        lisans = p.get("license") or (f"bkz. {p['license_file']}" if p.get("license_file") else "belirtilmemiş")
        kaynak = Path(p["manifest_path"]).parent
        dosyalar = [f for f in kaynak.iterdir() if f.is_file() and LISANS_DOSYASI.match(f.name)]
        if dosyalar:
            (klasor / ad).mkdir()
            for f in dosyalar:
                shutil.copyfile(f, klasor / ad / f.name)
        else:
            # Bazı kütüphaneler (ör. egui) lisans dosyasını crate'e koymaz; SPDX adına göre metin yazılır
            (klasor / ad).mkdir()
            if "MIT" in lisans:
                yazarlar = ", ".join(a.split(" <")[0] for a in p.get("authors") or []) or f"{p['name']} yazarları"
                (klasor / ad / "LICENSE-MIT").write_text(MIT_METNI.format(yazarlar=yazarlar), encoding="utf-8")
            if "Apache-2.0" in lisans and apache:
                (klasor / ad / "LICENSE-APACHE").write_text(apache, encoding="utf-8")
        satirlar.append((f"{p['name']} {p['version']}", lisans))
    if (hedef / "ffmpeg" / "LICENSE.txt").is_file():
        satirlar.append(("FFmpeg (ayrı program)", "LGPL-2.1-or-later  [ffmpeg/LICENSE.txt]"))
    genislik = max(len(a) for a, _ in satirlar) + 2
    metin = [
        "RizeOn — kullanılan açık kaynak parçalar",
        "",
        "Uygulamanın kendisi GNU GPL sürüm 3 ile dağıtılır (../LICENSE.txt).",
        "Kaynak kod: https://github.com/MustafaCap/streaming",
        "Her parçanın lisans metni bu klasörde, kendi adını taşıyan alt klasördedir.",
        "",
    ] + [f"{a.ljust(genislik)}{l}" for a, l in satirlar]
    (klasor / "UCUNCU_PARTI_LISANSLAR.txt").write_text("\n".join(metin) + "\n", encoding="utf-8-sig")
    return len(satirlar)


def kurulum_metni(cikti: Path) -> None:
    """Inno Setup lisans sayfası: Türkçe özet + GPLv3 tam metni (BOM'lu UTF-8)."""
    ozet = (KOK / "kurulum" / "lisans_ozeti.txt").read_text(encoding="utf-8")
    gpl = (KOK / "LICENSE").read_text(encoding="utf-8")
    cikti.write_text(ozet + "\n" + gpl, encoding="utf-8-sig")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        sys.exit("Kullanım: python rust/paket/paketle.py <paket klasörü> <build klasörü>")
    paket, build = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    build.mkdir(parents=True, exist_ok=True)
    s = surum()
    (build / "surum.txt").write_text(s, encoding="ascii")
    print(f"{lisanslari_topla(paket)} parçanın lisansı toplandı")
    kurulum_metni(build / "kurulum_lisans.txt")
    import msix_paketle  # kurulum/msix_paketle.py (Python sürümüyle aynı kimlik ve manifest)
    yol = msix_paketle.hazirla(paket, build / "msix", s)
    print(f"Sürüm {s} · MSIX klasörü: {yol}")


if __name__ == "__main__":
    main()
