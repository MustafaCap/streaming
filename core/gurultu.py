"""Gürültü azaltma: RNNoise (xiph.org, BSD-3-Clause) ile klavye, fan ve uğultu sesini bastırır.

RNNoise küçük bir sinir ağıdır; 48 kHz mono sesi 480 örneklik (10 ms) bloklarla işler.
DLL uygulamayla birlikte gelir (dist\\RizeOn\\rnnoise\\rnnoise.dll, lisansı yanında); CI kaynak
koddan derler. DLL yoksa (ör. geliştirirken) kullanilabilir False olur ve arayüzdeki anahtar
devre dışı kalır; ses olduğu gibi geçer.

Mikrofon geri çağrısında çalışır: hızlıdır (10 ms ses için ~0,1 ms) ve 10 ms gecikme ekler.
"""

import ctypes
import logging
import sys
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

CERCEVE = 480          # RNNoise blok boyu (48 kHz'de 10 ms)
OLCEK = 32768.0        # RNNoise 16 bit tam sayı aralığında float bekler


def dll_yolu() -> Path | None:
    ad = {"win32": "rnnoise.dll", "darwin": "librnnoise.dylib"}.get(sys.platform, "librnnoise.so")
    if getattr(sys, "frozen", False):
        adaylar = [Path(sys.executable).parent / "rnnoise" / ad]
    else:
        kok = Path(__file__).resolve().parent.parent
        adaylar = [kok / "rnnoise" / ad, kok / "rnnoise" / ".libs" / ad]
    for yol in adaylar:
        if yol.is_file():
            return yol
    return None


def _yukle(yol: Path | None):
    if yol is None:
        return None
    try:
        lib = ctypes.CDLL(str(yol))
        lib.rnnoise_create.restype = ctypes.c_void_p
        lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        lib.rnnoise_destroy.restype = None
        lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        lib.rnnoise_process_frame.restype = ctypes.c_float
        lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                              ctypes.POINTER(ctypes.c_float)]
        return lib
    except (OSError, AttributeError) as e:
        log.warning("RNNoise yüklenemedi (%s): %s", yol, e)
        return None


class GurultuAzaltici:
    def __init__(self, acik: bool = False, yol: Path | None = None):
        self._lib = _yukle(yol if yol is not None else dll_yolu())
        self._durum = None
        self._kilit = threading.Lock()
        self._giris = np.zeros(0, np.float32)
        self._cikis = np.zeros(0, np.float32)
        self._acik = False
        self._cerceve_in = (ctypes.c_float * CERCEVE)()
        self._cerceve_out = (ctypes.c_float * CERCEVE)()
        self._in_np = np.frombuffer(self._cerceve_in, np.float32)     # aynı belleğe numpy görünümü
        self._out_np = np.frombuffer(self._cerceve_out, np.float32)
        self.acik = acik
        if self._lib is not None:
            log.info("Gürültü azaltma kullanılabilir (RNNoise)")

    @property
    def kullanilabilir(self) -> bool:
        return self._lib is not None

    @property
    def acik(self) -> bool:
        return self._acik

    @acik.setter
    def acik(self, deger: bool) -> None:
        deger = bool(deger) and self.kullanilabilir
        with self._kilit:
            if deger and self._durum is None:
                self._durum = self._lib.rnnoise_create(None)
                if not self._durum:
                    log.warning("RNNoise başlatılamadı")
                    self._durum = None
                    deger = False
            # Açılınca 1 blok sessizlik: çıkış her zaman giriş kadar uzun olsun (10 ms gecikme)
            self._giris = np.zeros(0, np.float32)
            self._cikis = np.zeros(CERCEVE, np.float32)
            self._acik = deger

    def isle(self, blok: np.ndarray) -> np.ndarray:
        """Mono float32 (-1..1) blok alır, aynı uzunlukta temizlenmiş blok döndürür. Kapalıyken dokunmaz."""
        if not self._acik:
            return blok
        with self._kilit:
            durum = self._durum
            if durum is None:
                return blok
            giris = np.concatenate((self._giris, np.asarray(blok, np.float32).reshape(-1)))
            parcalar = [self._cikis]
            i = 0
            while len(giris) - i >= CERCEVE:
                np.multiply(giris[i:i + CERCEVE], OLCEK, out=self._in_np)
                self._lib.rnnoise_process_frame(durum, self._cerceve_out, self._cerceve_in)
                parcalar.append(self._out_np / OLCEK)   # bölme yeni dizi üretir
                i += CERCEVE
            self._giris = giris[i:]
            cikis = np.concatenate(parcalar)
            n = len(blok)
            self._cikis = cikis[n:]
            return cikis[:n]

    def kapat(self) -> None:
        with self._kilit:
            self._acik = False
            if self._durum is not None and self._lib is not None:
                self._lib.rnnoise_destroy(self._durum)
            self._durum = None

    def __del__(self):
        try:
            self.kapat()
        except Exception:
            pass
