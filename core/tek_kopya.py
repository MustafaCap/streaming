"""Uygulamanın tek kopya çalışması.

Pencere kapatılınca uygulama tepside çalışmaya devam eder. Kullanıcı exe'yi
tekrar açarsa yeni bir kopya başlamaz; çalışan kopyanın penceresi öne gelir.

Windows'un adlandırılmış nesneleri kullanılır (ağ bağlantısı yok):
  - mutex  : "zaten çalışıyor mu?"
  - olay   : ikinci kopya bu olayı tetikler, ilk kopya pencereyi gösterir
"""

import logging
import sys
import threading

log = logging.getLogger(__name__)

MUTEX_ADI = "Local\\RizeOn_TekKopya"
OLAY_ADI = "Local\\RizeOn_PencereyiGoster"
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0


class TekKopya:
    def __init__(self, mutex_adi: str = MUTEX_ADI, olay_adi: str = OLAY_ADI):
        self.mutex_adi, self.olay_adi = mutex_adi, olay_adi
        self._mutex = None
        self._olay = None
        self._is = None
        self._calis = threading.Event()
        self.ilk = True
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.restype = wintypes.HANDLE
            k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            self._mutex = k.CreateMutexW(None, False, mutex_adi)
            self.ilk = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        except Exception:
            log.exception("Tek kopya denetimi yapılamadı")
            self.ilk = True

    def digerini_one_getir(self) -> bool:
        """Çalışan kopyaya "pencereni göster" der."""
        if sys.platform != "win32":
            return False
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenEventW.restype = wintypes.HANDLE
        k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.SetEvent.argtypes = [wintypes.HANDLE]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        olay = k.OpenEventW(EVENT_MODIFY_STATE, False, self.olay_adi)
        if not olay:
            return False
        k.SetEvent(olay)
        k.CloseHandle(olay)
        return True

    def dinle(self, goster) -> None:
        """İlk kopyada: başka bir kopya açılmak istenince goster() çağrılır (bu iş parçacığından)."""
        if sys.platform != "win32" or self._is is not None:
            return
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateEventW.restype = wintypes.HANDLE
        k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        self._olay = k.CreateEventW(None, False, False, self.olay_adi)   # otomatik sıfırlanan
        if not self._olay:
            return
        self._calis.set()

        def dongu():
            while self._calis.is_set():
                if k.WaitForSingleObject(self._olay, 500) == WAIT_OBJECT_0 and self._calis.is_set():
                    try:
                        goster()
                    except Exception:
                        log.exception("Pencere gösterilemedi")

        self._is = threading.Thread(target=dongu, name="tek-kopya", daemon=True)
        self._is.start()

    def kapat(self) -> None:
        self._calis.clear()
        if self._is is not None:
            self._is.join(timeout=2)
            self._is = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32")
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            for h in (self._olay, self._mutex):
                if h:
                    k.CloseHandle(h)
        self._olay = self._mutex = None
