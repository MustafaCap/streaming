"""Windows'a özgü küçük yardımcılar (ctypes). Windows dışında hiçbir şey yapmaz."""

import logging
import sys

log = logging.getLogger(__name__)

WDA_EXCLUDEFROMCAPTURE = 0x11


def yakalamadan_gizle(hwnd: int) -> bool:
    """Pencere ekranda görünür ama ekran yakalamaya (bizim yakalamamız, Zoom paylaşımı) girmez.

    Aşama 0'daki 2. denemede bu bilgisayarda çalıştığı doğrulandı.
    Önizleme penceresi için şart: yoksa önizleme kendini yakalar ve sonsuz ayna oluşur.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    ok = bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    if not ok:
        log.warning("Pencere yakalamadan gizlenemedi (hata %d)", ctypes.GetLastError())
    return ok
