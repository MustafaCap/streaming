"""Tek bir pencereyi yakalama (yayında ya da kayıtta sadece seçilen pencere görünür).

Windows'un PrintWindow işlevi kullanılır (PW_RENDERFULLCONTENT): pencerenin üstüne
başka bir pencere gelse de seçilen pencerenin kendisi yakalanır. Ek kütüphane gerekmez.

Bazı programlar (bazı oyunlar, donanım hızlandırmalı video oynatıcılar) PrintWindow'a
siyah görüntü verir. Üst üste siyah gelirse pencerenin ekrandaki yeri yakalanır
("ekrandan"). Bu durumda üstüne gelen pencereler de görünür.

Pencere simge durumuna küçültülürse son görüntü gösterilir. Pencere kapanırsa grab()
None döner ve önizlemede kaynak "koptu" görünür.
Hiçbir ağ bağlantısı açılmaz.
"""

import logging
import os
import sys

import numpy as np

log = logging.getLogger(__name__)

SIYAH_ESIGI = 3          # bu kadar üst üste siyah kare gelirse ekrandan yakalamaya geçilir
_KUCUK = 40              # bundan küçük pencereler listelenmez (araç ipuçları vb.)


def kirp(bgra: np.ndarray, pencere, cerceve) -> np.ndarray:
    """PrintWindow tüm pencereyi (görünmez kenarlıklarla) verir; görünen çerçeveye kırpar.
    pencere/cerceve: (sol, üst, sağ, alt). Dönen: RGB."""
    h, w = bgra.shape[:2]
    x0 = max(0, min(w, cerceve[0] - pencere[0]))
    y0 = max(0, min(h, cerceve[1] - pencere[1]))
    x1 = max(x0, min(w, cerceve[2] - pencere[0]))
    y1 = max(y0, min(h, cerceve[3] - pencere[1]))
    if x1 - x0 < 2 or y1 - y0 < 2:
        x0, y0, x1, y1 = 0, 0, w, h
    return np.ascontiguousarray(bgra[y0:y1, x0:x1, 2::-1])


def siyah_mi(kare: np.ndarray) -> bool:
    # Her pikseli taramak yerine seyrek örnek: 1080p'de bile çok hızlı
    return int(kare[::16, ::16].max()) == 0


class _WinApi:
    """ctypes ile Windows işlevleri. Testlerde sahte bir nesneyle değiştirilir."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        # Kendi kopyalarımız: türleri değiştirmek uygulamanın başka yerlerini etkilemesin
        self.user32 = ctypes.WinDLL("user32")
        self.gdi32 = ctypes.WinDLL("gdi32")
        self.dwmapi = ctypes.WinDLL("dwmapi")
        H, wt = ctypes.c_void_p, wintypes
        # 64 bit'te tutamaçlar kırpılmasın diye türler açıkça yazılır
        for fn, args, res in (
                (self.user32.GetDC, [H], H), (self.user32.ReleaseDC, [H, H], ctypes.c_int),
                (self.user32.PrintWindow, [H, H, wt.UINT], wt.BOOL),
                (self.user32.IsWindow, [H], wt.BOOL), (self.user32.IsIconic, [H], wt.BOOL),
                (self.user32.GetWindowRect, [H, ctypes.c_void_p], wt.BOOL),
                (self.dwmapi.DwmGetWindowAttribute, [H, wt.DWORD, ctypes.c_void_p, wt.DWORD], ctypes.c_long),
                (self.gdi32.CreateCompatibleDC, [H], H), (self.gdi32.CreateCompatibleBitmap, [H, ctypes.c_int, ctypes.c_int], H),
                (self.gdi32.SelectObject, [H, H], H), (self.gdi32.DeleteObject, [H], wt.BOOL),
                (self.gdi32.DeleteDC, [H], wt.BOOL),
                (self.gdi32.GetDIBits, [H, H, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT], ctypes.c_int)):
            fn.argtypes, fn.restype = args, res
        self._dc = self._bmp = None
        self._boyut = (0, 0)

    def var_mi(self, hwnd) -> bool:
        return bool(self.user32.IsWindow(hwnd))

    def simge_mi(self, hwnd) -> bool:
        return bool(self.user32.IsIconic(hwnd))

    def dikdortgenler(self, hwnd):
        """(pencere, görünen çerçeve) — ikisi de (sol, üst, sağ, alt), fiziksel piksel."""
        r = self.wt.RECT()
        if not self.user32.GetWindowRect(hwnd, self.ct.byref(r)):
            return None
        pencere = (r.left, r.top, r.right, r.bottom)
        c = self.wt.RECT()
        if self.dwmapi.DwmGetWindowAttribute(hwnd, 9, self.ct.byref(c), self.ct.sizeof(c)) == 0:  # EXTENDED_FRAME_BOUNDS
            return pencere, (c.left, c.top, c.right, c.bottom)
        return pencere, pencere

    def printwindow(self, hwnd, w: int, h: int):
        """Pencerenin BGRA görüntüsü (h, w, 4) ya da None."""
        ct = self.ct
        ekran_dc = self.user32.GetDC(None)
        try:
            if self._dc is None:
                self._dc = self.gdi32.CreateCompatibleDC(ekran_dc)
            if self._boyut != (w, h):
                if self._bmp:
                    self.gdi32.DeleteObject(self._bmp)
                self._bmp = self.gdi32.CreateCompatibleBitmap(ekran_dc, w, h)
                self._boyut = (w, h)
            self.gdi32.SelectObject(self._dc, self._bmp)
            if not self.user32.PrintWindow(hwnd, self._dc, 2):   # PW_RENDERFULLCONTENT
                return None

            class BITMAPINFOHEADER(ct.Structure):
                _fields_ = [("biSize", ct.c_uint32), ("biWidth", ct.c_int32), ("biHeight", ct.c_int32),
                            ("biPlanes", ct.c_uint16), ("biBitCount", ct.c_uint16), ("biCompression", ct.c_uint32),
                            ("biSizeImage", ct.c_uint32), ("biXPelsPerMeter", ct.c_int32),
                            ("biYPelsPerMeter", ct.c_int32), ("biClrUsed", ct.c_uint32),
                            ("biClrImportant", ct.c_uint32)]

            bilgi = BITMAPINFOHEADER()
            bilgi.biSize = ct.sizeof(BITMAPINFOHEADER)
            bilgi.biWidth, bilgi.biHeight = w, -h      # eksi: satırlar yukarıdan aşağı
            bilgi.biPlanes, bilgi.biBitCount = 1, 32
            tampon = np.empty((h, w, 4), np.uint8)
            satir = self.gdi32.GetDIBits(self._dc, self._bmp, 0, h, tampon.ctypes.data_as(ct.c_void_p),
                                         ct.byref(bilgi), 0)
            return tampon if satir == h else None
        finally:
            self.user32.ReleaseDC(None, ekran_dc)

    def ekrandan(self, cerceve):
        """Pencerenin ekrandaki yerini yakalar (üstündeki pencereler de görünür). RGB."""
        import cv2
        import mss
        if not hasattr(self, "_sct"):
            self._sct = mss.mss()
        sol, ust, sag, alt = cerceve
        kare = np.asarray(self._sct.grab({"left": sol, "top": ust, "width": sag - sol, "height": alt - ust}))
        return cv2.cvtColor(kare, cv2.COLOR_BGRA2RGB)

    def kapat(self):
        if self._bmp:
            self.gdi32.DeleteObject(self._bmp)
        if self._dc:
            self.gdi32.DeleteDC(self._dc)
        self._dc = self._bmp = None
        self._boyut = (0, 0)
        if hasattr(self, "_sct"):
            try:
                self._sct.close()
            except Exception:
                pass
            del self._sct


class PencereKaynagi:
    """EkranKaynagi ile aynı arayüz: grab(), yontem, calisiyor, imlec(), dikdortgen, kapat()."""

    def __init__(self, hwnd: int, baslik: str = "", api=None):
        self.hwnd = hwnd
        self.baslik = baslik
        self._api = api
        self._son = None
        self._siyah_sayisi = 0
        self.ekrandan = False          # PrintWindow siyah verdiği için ekrandan mı yakalanıyor
        self.son_hata = ""
        self.dikdortgen = None         # görünen çerçeve (sol, üst, gen, yük); imleç ve kalem için

    @property
    def yontem(self) -> str:
        return "pencere (ekrandan)" if self.ekrandan else "pencere"

    @property
    def calisiyor(self) -> bool:
        return self._api is not None and self.son_hata == ""

    def _api_al(self):
        if self._api is None:
            if sys.platform != "win32":
                raise RuntimeError("Pencere yakalama sadece Windows'ta var")
            self._api = _WinApi()
        return self._api

    def grab(self):
        """RGB numpy dizisi ya da pencere yoksa None. Asla hata fırlatmaz."""
        try:
            api = self._api_al()
            if not api.var_mi(self.hwnd):
                if not self.son_hata:
                    log.info("Yakalanan pencere kapandı: %s", self.baslik)
                self.son_hata = "Pencere kapandı"
                return None
            if api.simge_mi(self.hwnd):
                return self._son          # küçültülmüş: son görüntü kalsın
            dd = api.dikdortgenler(self.hwnd)
            if dd is None:
                return self._son
            pencere, cerceve = dd
            self.dikdortgen = (cerceve[0], cerceve[1], cerceve[2] - cerceve[0], cerceve[3] - cerceve[1])
            if self.ekrandan:
                kare = api.ekrandan(cerceve)
            else:
                w, h = pencere[2] - pencere[0], pencere[3] - pencere[1]
                if w < 2 or h < 2:
                    return self._son
                bgra = api.printwindow(self.hwnd, w, h)
                kare = None if bgra is None else kirp(bgra, pencere, cerceve)
                if kare is None or siyah_mi(kare):
                    self._siyah_sayisi += 1
                    if self._siyah_sayisi >= SIYAH_ESIGI:
                        log.info("Pencere doğrudan yakalanamadı, ekrandan yakalanıyor: %s", self.baslik)
                        self.ekrandan = True
                        kare = api.ekrandan(cerceve)
                    else:
                        return self._son
                else:
                    self._siyah_sayisi = 0
            self.son_hata = ""
            self._son = kare
            return kare
        except Exception as e:
            if self.son_hata != str(e):
                log.warning("Pencere yakalanamadı (%s): %s", self.baslik, e)
            self.son_hata = str(e)
            return None

    def imlec(self):
        if self.dikdortgen is None:
            return None
        from capture.screen import fare_konumu
        konum = fare_konumu()
        if konum is None:
            return None
        sol, ust, w, h = self.dikdortgen
        x, y = konum[0] - sol, konum[1] - ust
        return (x, y) if 0 <= x < w and 0 <= y < h else None

    def kapat(self):
        if self._api is not None:
            try:
                self._api.kapat()
            except Exception:
                pass


def pencereleri_listele() -> list[tuple[int, str, str]]:
    """Seçilebilecek açık pencereler: [(hwnd, başlık, program adı)]. Windows değilse boş liste."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    bizim = os.getpid()
    sonuc = []

    def program_adi(pid):
        try:
            import psutil
            return psutil.Process(pid).name()
        except Exception:
            return ""

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def her_biri(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):   # GW_OWNER: açılır pencereler
                return True
            if user32.GetWindowLongW(hwnd, -20) & 0x80:                         # WS_EX_TOOLWINDOW
                return True
            gizli = wintypes.DWORD()
            if dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(gizli), 4) == 0 and gizli.value:  # CLOAKED
                return True
            uzunluk = user32.GetWindowTextLengthW(hwnd)
            if uzunluk == 0:
                return True
            tampon = ctypes.create_unicode_buffer(uzunluk + 1)
            user32.GetWindowTextW(hwnd, tampon, uzunluk + 1)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left < _KUCUK or r.bottom - r.top < _KUCUK:
                if not user32.IsIconic(hwnd):
                    return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == bizim:
                return True                       # RizeOn'un kendi pencereleri
            sinif = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, sinif, 256)
            if sinif.value in ("Progman", "Shell_TrayWnd", "WorkerW"):
                return True
            sonuc.append((int(hwnd), tampon.value, program_adi(pid.value)))
        except Exception:
            pass
        return True

    user32.EnumWindows(her_biri, 0)
    return sonuc
