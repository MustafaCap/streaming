"""Alt satırdaki "CPU · GPU · FPS" için ölçümler.

CPU: uygulamanın kendi işlemci kullanımı (tüm çekirdeklere bölünmüş, Görev Yöneticisi gibi).
GPU: Windows performans sayaçlarından 3D motorlarının toplam kullanımı (Görev Yöneticisi'ndeki
"GPU" sütunuyla aynı kaynak). Sayaç yoksa (eski sürücü, Windows dışı) None döner, arayüz "GPU –" yazar.
Hiçbiri internete çıkmaz; hepsi yerel sistem çağrısıdır.
"""

import logging
import sys

log = logging.getLogger(__name__)


class _GpuSayaci:
    SAYAC = "\\GPU Engine(*engtype_3D)\\Utilization Percentage"

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self._ct, self._wt = ctypes, wintypes
        self._pdh = ctypes.WinDLL("pdh")
        self._sorgu = wintypes.HANDLE()
        self._sayac = wintypes.HANDLE()
        if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._sorgu)) != 0:
            raise OSError("PdhOpenQuery")
        if self._pdh.PdhAddEnglishCounterW(self._sorgu, self.SAYAC, None, ctypes.byref(self._sayac)) != 0:
            raise OSError("PdhAddEnglishCounter")
        self._pdh.PdhCollectQueryData(self._sorgu)   # ilk örnek (oran için iki örnek gerekir)

    def oku(self) -> float | None:
        ct = self._ct

        class PDH_FMT_COUNTERVALUE(ct.Structure):
            _fields_ = [("CStatus", ct.c_ulong), ("doubleValue", ct.c_double)]

        class PDH_FMT_COUNTERVALUE_ITEM_W(ct.Structure):
            _fields_ = [("szName", ct.c_wchar_p), ("FmtValue", PDH_FMT_COUNTERVALUE)]

        PDH_FMT_DOUBLE, PDH_MORE_DATA = 0x200, 0x800007D2
        if self._pdh.PdhCollectQueryData(self._sorgu) != 0:
            return None
        boyut, adet = ct.c_ulong(0), ct.c_ulong(0)
        kod = self._pdh.PdhGetFormattedCounterArrayW(self._sayac, PDH_FMT_DOUBLE, ct.byref(boyut),
                                                     ct.byref(adet), None) & 0xFFFFFFFF
        if kod != PDH_MORE_DATA or boyut.value == 0:
            return None
        tampon = (ct.c_byte * boyut.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(self._sayac, PDH_FMT_DOUBLE, ct.byref(boyut), ct.byref(adet),
                                                  tampon) != 0:
            return None
        ogeler = ct.cast(tampon, ct.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
        # Aynı motoru kullanan işlemler toplanır; motor başına en çok %100.
        motorlar: dict[str, float] = {}
        for i in range(adet.value):
            o = ogeler[i]
            if o.FmtValue.CStatus != 0:
                continue
            ad = o.szName or ""
            motor = ad[ad.find("luid_"):] if "luid_" in ad else ad
            motorlar[motor] = motorlar.get(motor, 0.0) + o.FmtValue.doubleValue
        if not motorlar:
            return 0.0
        return min(100.0, max(motorlar.values()))

    def kapat(self) -> None:
        try:
            self._pdh.PdhCloseQuery(self._sorgu)
        except Exception:
            pass


class SistemOlcer:
    def __init__(self):
        self._islem = None
        self._cekirdek = 1
        try:
            import psutil
            self._islem = psutil.Process()
            self._islem.cpu_percent(None)
            self._cekirdek = psutil.cpu_count() or 1
        except Exception:
            log.info("CPU ölçümü kullanılamıyor")
        self._gpu = None
        if sys.platform == "win32":
            try:
                self._gpu = _GpuSayaci()
            except Exception:
                log.info("GPU sayacı kullanılamıyor")

    def cpu(self) -> float | None:
        if self._islem is None:
            return None
        try:
            return min(100.0, self._islem.cpu_percent(None) / self._cekirdek)
        except Exception:
            return None

    def gpu(self) -> float | None:
        if self._gpu is None:
            return None
        try:
            return self._gpu.oku()
        except Exception:
            return None

    def metin(self, fps: float) -> str:
        c, g = self.cpu(), self.gpu()
        cpu = f"CPU %{c:.0f}" if c is not None else "CPU –"
        gpu = f"GPU %{g:.0f}" if g is not None else "GPU –"
        return f"{cpu} · {gpu} · {fps:.0f} FPS"

    def kapat(self) -> None:
        if self._gpu is not None:
            self._gpu.kapat()
