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


def koseleri_yuvarla(hwnd: int) -> bool:
    """Windows 11: çerçevesiz pencerenin köşeleri de sistem gibi yuvarlak olsun (8 px)."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
    try:
        deger = ctypes.c_int(DWMWCP_ROUND)
        sonuc = ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                                                           ctypes.byref(deger), ctypes.sizeof(deger))
        return sonuc == 0
    except (AttributeError, OSError):
        return False   # Windows 10: köşeler köşeli kalır, sorun değil


def ozel_tam_ekran_mi() -> bool:
    """Önde bir oyun özel tam ekranda (exclusive fullscreen) mı çalışıyor?

    O modda Windows saydam pencereleri oyunun üstünde göstermeyebilir; kalem çizimleri yine
    yayına gider ama kullanıcı ekranda görmez. SHQueryUserNotificationState bunu söyler.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    QUNS_RUNNING_D3D_FULL_SCREEN = 3
    durum = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(durum)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return durum.value == QUNS_RUNNING_D3D_FULL_SCREEN
