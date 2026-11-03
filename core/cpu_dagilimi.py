"""İşlemcinin uygulama içinde nereye gittiğini log dosyasına yazar (teşhis için).

Her 30 saniyede bir, uygulamanın her iş parçacığının (video hattı, ses, webcam, anlık tekrar...)
ve alt süreçlerin (FFmpeg) o sürede harcadığı işlemciyi Görev Yöneticisi gibi tüm çekirdeklere
oranla yazar. Örnek satır:
  CPU dağılımı (30 sn): toplam %7.9 | video-hatti %3.1, ffmpeg %2.4, diğer %1.2, ses %0.8 ...
Adı olmayan iş parçacıkları (OpenCV'nin yardımcıları, Qt, ses sürücüsü) "diğer" altında toplanır.
Hiçbir yere bir şey göndermez; sadece yerel log.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)


def _adlar() -> dict[int, str]:
    adlar = {}
    for t in threading.enumerate():
        if t.native_id is not None:
            adlar[t.native_id] = t.name
    return adlar


class CpuDagilimi:
    def __init__(self, psutil_modulu=None):
        import psutil
        self._ps = psutil_modulu or psutil
        self._islem = self._ps.Process()
        self._cekirdek = self._ps.cpu_count() or 1
        self._onceki = self._sure_al()
        self._onceki_zaman = time.monotonic()

    def _sure_al(self) -> dict[str, float]:
        """{grup adı: toplam işlemci saniyesi}"""
        adlar = _adlar()
        sureler: dict[str, float] = {}
        for t in self._islem.threads():
            ad = adlar.get(t.id, "diğer")
            if ad.startswith("Thread-") or ad.startswith("Dummy-"):
                ad = "diğer"
            sureler[ad] = sureler.get(ad, 0.0) + t.user_time + t.system_time
        for cocuk in self._islem.children(recursive=True):
            try:
                ad = cocuk.name().lower().removesuffix(".exe")
                c = cocuk.cpu_times()
                # süreç kimliği de anahtarda: kapanıp yeniden açılan FFmpeg yeni bir sayaçla başlar
                sureler[f"{ad}#{cocuk.pid}"] = c.user + c.system
            except Exception:
                continue
        return sureler

    def ornek(self) -> tuple[float, dict[str, float]]:
        """Son ölçümden bu yana (toplam %, {grup: %}), tüm çekirdeklere oranla."""
        simdi_zaman = time.monotonic()
        simdi = self._sure_al()
        gecen = max(1e-6, simdi_zaman - self._onceki_zaman)
        oran: dict[str, float] = {}
        for anahtar, sure in simdi.items():
            fark = sure - self._onceki.get(anahtar, 0.0)
            if fark <= 0:
                continue
            ad = anahtar.split("#")[0]
            oran[ad] = oran.get(ad, 0.0) + 100.0 * fark / gecen / self._cekirdek
        self._onceki, self._onceki_zaman = simdi, simdi_zaman
        return sum(oran.values()), oran


def metin(toplam: float, oran: dict[str, float], sn: float) -> str:
    parcalar = ", ".join(f"{ad} %{deger:.1f}" for ad, deger in sorted(oran.items(), key=lambda x: -x[1])
                         if deger >= 0.05)
    return f"CPU dağılımı ({sn:.0f} sn): toplam %{toplam:.1f} | {parcalar}"


def baslat(aralik_sn: float = 30.0) -> threading.Thread | None:
    """Arka planda her aralik_sn'de bir log'a yazar. psutil yoksa hiçbir şey yapmaz."""
    try:
        olcer = CpuDagilimi()
    except Exception:
        log.info("CPU dağılımı ölçülemiyor")
        return None

    def dongu():
        while True:
            time.sleep(aralik_sn)
            try:
                toplam, oran = olcer.ornek()
                log.info(metin(toplam, oran, aralik_sn))
            except Exception:
                log.debug("CPU dağılımı okunamadı", exc_info=True)

    t = threading.Thread(target=dongu, name="cpu-olcer", daemon=True)
    t.start()
    return t
