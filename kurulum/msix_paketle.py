"""Microsoft Store paketi (MSIX) için klasör hazırlar: uygulama + AppxManifest.xml + logolar.

Store'a yüklenen MSIX'i Microsoft imzalar; bu yüzden kullanıcı Store'dan kurarken
SmartScreen uyarısı görmez. Paketin kimliği (Identity Name / Publisher) Partner Center'da
uygulama adı ayrılınca verilir; CI bunları depo değişkenlerinden okur:
  MSIX_KIMLIK_ADI   (Partner Center > Ürün kimliği > Package/Identity/Name)
  MSIX_YAYINCI      (Package/Identity/Publisher, "CN=..." ile başlar)
  MSIX_YAYINCI_ADI  (Package/Properties/PublisherDisplayName)
Değişkenler yoksa deneme değerleri kullanılır (paket derlenir ama Store kabul etmez).

Kullanım (CI):
  python kurulum/msix_paketle.py dist/YayinUygulamasi build/msix
  makeappx pack /o /d build\\msix /p YayinUygulamasi-Store.msix
"""

import os
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import surum_bilgisi  # noqa: E402

DENEME_ADI = "MustafaCap.YayinUygulamasi"
DENEME_YAYINCI = "CN=MustafaCap"
DENEME_YAYINCI_ADI = "Mustafa"

ACIKLAMA = ("Meet, Zoom ve Discord'da sanal kamera ve sanal mikrofon olarak görünen, internete "
            "bağlanmayan ekran, kamera ve ses paylaşım uygulaması.")

# (dosya adı, genişlik, yükseklik): Store'un istediği en küçük logo takımı
LOGOLAR = (
    ("StoreLogo.png", 50, 50),
    ("Square44x44Logo.png", 44, 44),
    ("Square150x150Logo.png", 150, 150),
    ("Wide310x150Logo.png", 310, 150),
)


def msix_surumu(surum_metni: str) -> str:
    """Store, sürümün dördüncü sayısının 0 olmasını ister: "1.5.1" -> "1.5.1.0"."""
    a, b, c, _ = surum_bilgisi.sayilar(surum_metni)
    return f"{a}.{b}.{c}.0"


def kimlik() -> tuple[str, str, str]:
    return (os.environ.get("MSIX_KIMLIK_ADI") or DENEME_ADI,
            os.environ.get("MSIX_YAYINCI") or DENEME_YAYINCI,
            os.environ.get("MSIX_YAYINCI_ADI") or DENEME_YAYINCI_ADI)


def manifest(surum_metni: str, ad: str, yayinci: str, yayinci_adi: str) -> str:
    urun = escape(surum_bilgisi.URUN)
    aciklama = escape(ACIKLAMA)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- kurulum/msix_paketle.py üretti; elle değiştirme. -->
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">
  <Identity Name={quoteattr(ad)} Publisher={quoteattr(yayinci)} Version="{msix_surumu(surum_metni)}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>{urun}</DisplayName>
    <PublisherDisplayName>{escape(yayinci_adi)}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>{aciklama}</Description>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="tr-TR" />
  </Resources>
  <Applications>
    <Application Id="YayinUygulamasi" Executable="YayinUygulamasi.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{urun}" Description="{aciklama}" BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
      </uap:VisualElements>
    </Application>
  </Applications>
  <Capabilities>
    <!-- Masaüstü uygulaması (Win32): ekran yakalama, kısayollar, sanal kamera belleği için tam yetki -->
    <rescap:Capability Name="runFullTrust" />
    <DeviceCapability Name="webcam" />
    <DeviceCapability Name="microphone" />
  </Capabilities>
</Package>
"""


def logolari_yaz(hedef: Path) -> None:
    from PIL import Image
    simge = Image.open(KOK / "kurulum" / "uygulama.ico")
    simge.size = max(simge.ico.sizes())   # .ico'daki en büyük boyutu (256) seç
    kaynak = simge.convert("RGBA")
    hedef.mkdir(parents=True, exist_ok=True)
    for ad, g, y in LOGOLAR:
        tuval = Image.new("RGBA", (g, y), (0, 0, 0, 0))
        kenar = min(g, y)
        kucuk = kaynak.resize((kenar, kenar), Image.LANCZOS)
        tuval.paste(kucuk, ((g - kenar) // 2, (y - kenar) // 2), kucuk)
        tuval.save(hedef / ad)


def hazirla(uygulama: Path, hedef: Path, surum_metni: str | None = None) -> Path:
    if not (uygulama / "YayinUygulamasi.exe").exists():
        raise FileNotFoundError(f"{uygulama} içinde YayinUygulamasi.exe yok (önce PyInstaller)")
    if hedef.exists():
        shutil.rmtree(hedef)
    shutil.copytree(uygulama, hedef)
    logolari_yaz(hedef / "Assets")
    ad, yayinci, yayinci_adi = kimlik()
    (hedef / "AppxManifest.xml").write_text(
        manifest(surum_metni or surum_bilgisi.surum(), ad, yayinci, yayinci_adi), encoding="utf-8")
    return hedef


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolu (cp1252) Türkçe harfte çökmesin
    if len(sys.argv) != 3:
        sys.exit("Kullanım: python kurulum/msix_paketle.py <PyInstaller klasörü> <hedef klasör>")
    yol = hazirla(Path(sys.argv[1]), Path(sys.argv[2]))
    ad, yayinci, _ = kimlik()
    deneme = " (DENEME kimliği: Store kabul etmez)" if ad == DENEME_ADI else ""
    print(f"MSIX klasörü hazır: {yol} · {ad} · {yayinci}{deneme}")
