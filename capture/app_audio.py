"""Uygulama bazlı bilgisayar sesi (Windows "Process Loopback", Win10 2004+ / Win11).

Neden? Normal "hoparlör loopback" her şeyi yakalar; Zoom/Discord'daki karşı
tarafın sesi de geri gönderilir ve kendi seslerini yankı olarak duyarlar.
Process Loopback ile:
  - hariç modu: seçilen uygulama (ör. Zoom.exe) DIŞINDAKİ bütün sesler
  - dahil modu: sadece seçilen uygulamanın sesi (ör. bir oyun)
Hedef olarak kendi sürecimizi "hariç" verirsek bütün bilgisayar sesi gelir,
ama kendi çıkardığımız ses gelmez (geri besleme olmaz).

Aşama 0, deneme 5'te Mustafa'nın bilgisayarında Edge ile doğrulandı.
COM çağrıları ayrı bir iş parçacığında, çok iş parçacıklı (MTA) modda yapılır;
arayüzün (Qt) ana iş parçacığına dokunulmaz.
"""

import ctypes
import logging
import os
import threading
from ctypes import POINTER, Structure, byref, c_int, c_longlong, c_ulong, c_ulonglong, c_ushort, c_void_p
from ctypes import wintypes

import numpy as np

HRESULT = getattr(ctypes, "HRESULT", ctypes.c_long)  # sadece Windows'ta var; diğerlerinde içe aktarma çökmesin

log = logging.getLogger(__name__)

ORNEKLEME, KANAL, BIT = 48000, 2, 16

VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE = 1
VT_BLOB = 65
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
COINIT_MULTITHREADED = 0x0


def surec_bul(ad: str) -> int | None:
    """Adı verilen uygulamanın ana sürecini bulur (Chrome/Edge gibi çok süreçli uygulamalarda en üstteki)."""
    import psutil
    adaylar = []
    for p in psutil.process_iter(["pid", "name", "ppid"]):
        try:
            if (p.info["name"] or "").lower() == ad.lower():
                adaylar.append(p.info)
        except Exception:
            continue
    if not adaylar:
        return None
    pidler = {a["pid"] for a in adaylar}
    for a in adaylar:
        if a["ppid"] not in pidler:
            return a["pid"]
    return adaylar[0]["pid"]


def _com_tanimlari():
    """comtypes tanımlarını ilk kullanımda yükler (Windows dışında modül yine de içe aktarılabilsin)."""
    global _COM
    if "_COM" in globals():
        return _COM
    import comtypes
    from comtypes import COMMETHOD, GUID, COMObject, IUnknown

    class WAVEFORMATEX(Structure):
        _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                    ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                    ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                    ("cbSize", wintypes.WORD)]

    class AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS(Structure):
        _fields_ = [("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", c_int)]

    class AUDIOCLIENT_ACTIVATION_PARAMS(Structure):
        _fields_ = [("ActivationType", c_int),
                    ("ProcessLoopbackParams", AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS)]

    class BLOB(Structure):
        _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]

    class PROPVARIANT(Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort),
                    ("blob", BLOB)]

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetBuffer",
                      (["out"], POINTER(POINTER(ctypes.c_ubyte)), "ppData"),
                      (["out"], POINTER(ctypes.c_uint32), "pNumFramesToRead"),
                      (["out"], POINTER(wintypes.DWORD), "pdwFlags"),
                      (["out"], POINTER(c_ulonglong), "pu64DevicePosition"),
                      (["out"], POINTER(c_ulonglong), "pu64QPCPosition")),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], ctypes.c_uint32, "NumFramesRead")),
            COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(ctypes.c_uint32), "pNumFrames")),
        ]

    class IAudioClient(IUnknown):
        _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Initialize",
                      (["in"], wintypes.DWORD, "ShareMode"), (["in"], wintypes.DWORD, "StreamFlags"),
                      (["in"], c_longlong, "hnsBufferDuration"), (["in"], c_longlong, "hnsPeriodicity"),
                      (["in"], POINTER(WAVEFORMATEX), "pFormat"), (["in"], POINTER(GUID), "AudioSessionGuid")),
            COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(ctypes.c_uint32), "n")),
            COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(c_longlong), "lat")),
            COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(ctypes.c_uint32), "n")),
            COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], wintypes.DWORD, "ShareMode"),
                      (["in"], POINTER(WAVEFORMATEX), "pFormat"),
                      (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppClosest")),
            COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(POINTER(WAVEFORMATEX)), "ppFormat")),
            COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(c_longlong), "d"),
                      (["out"], POINTER(c_longlong), "m")),
            COMMETHOD([], HRESULT, "Start"),
            COMMETHOD([], HRESULT, "Stop"),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "SetEventHandle", (["in"], wintypes.HANDLE, "h")),
            COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "riid"),
                      (["out"], POINTER(c_void_p), "ppv")),
        ]

    class IActivateAudioInterfaceAsyncOperation(IUnknown):
        _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetActivateResult",
                      (["out"], POINTER(ctypes.c_long), "activateResult"),
                      (["out"], POINTER(POINTER(IUnknown)), "activatedInterface")),
        ]

    class IActivateAudioInterfaceCompletionHandler(IUnknown):
        _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
        _methods_ = [
            COMMETHOD([], HRESULT, "ActivateCompleted",
                      (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "op")),
        ]

    class IAgileObject(IUnknown):
        _iid_ = GUID("{94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90}")
        _methods_ = []

    class Tamamlayici(COMObject):
        """Windows, ses arayüzü hazır olunca ActivateCompleted'ı çağırır."""
        _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

        def __init__(self):
            super().__init__()
            self.bitti = threading.Event()
            self.istemci = None
            self.hata = None

        def ActivateCompleted(self, this, op):
            try:
                op.AddRef()  # comtypes kapsam dışında Release çağıracağı için
                hr, unk = op.GetActivateResult()
                if hr < 0:
                    self.hata = f"GetActivateResult HRESULT=0x{hr & 0xFFFFFFFF:08X}"
                else:
                    self.istemci = unk.QueryInterface(IAudioClient)
            except Exception as e:  # noqa: BLE001
                self.hata = repr(e)
            finally:
                self.bitti.set()
            return 0

    _COM = dict(comtypes=comtypes, GUID=GUID, WAVEFORMATEX=WAVEFORMATEX,
                AUDIOCLIENT_ACTIVATION_PARAMS=AUDIOCLIENT_ACTIVATION_PARAMS, PROPVARIANT=PROPVARIANT,
                IAudioCaptureClient=IAudioCaptureClient, IAudioClient=IAudioClient,
                IActivateAudioInterfaceAsyncOperation=IActivateAudioInterfaceAsyncOperation,
                IActivateAudioInterfaceCompletionHandler=IActivateAudioInterfaceCompletionHandler,
                Tamamlayici=Tamamlayici)
    return _COM


class SurecSesi:
    """Bir sürecin (ve alt süreçlerinin) sesini yakalar ya da hariç tutar.

    yaz: her pakette çağrılır, (n, 2) float32 numpy dizisi alır.
    """

    def __init__(self, pid: int, haric: bool, yaz):
        self.pid, self.haric, self._yaz = pid, haric, yaz
        self._calis = threading.Event()
        self._hazir = threading.Event()
        self._is: threading.Thread | None = None
        self.hata = ""

    @property
    def calisiyor(self) -> bool:
        return self._is is not None and self._is.is_alive() and not self.hata

    def baslat(self, bekle_sn: float = 5.0) -> bool:
        """Yakalamayı başlatır; Windows hazır olana kadar bekler. Başarısızsa False (ve self.hata)."""
        self._calis.set()
        self._is = threading.Thread(target=self._dongu, name="surec-sesi", daemon=True)
        self._is.start()
        if not self._hazir.wait(bekle_sn):
            self.hata = self.hata or "Windows ses arayüzü zamanında cevap vermedi"
        if self.hata:
            self.durdur()
            return False
        return True

    def durdur(self) -> None:
        self._calis.clear()
        if self._is is not None and self._is is not threading.current_thread():
            self._is.join(timeout=2)
        self._is = None

    def _istemci_al(self, com):
        params = com["AUDIOCLIENT_ACTIVATION_PARAMS"]()
        params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
        params.ProcessLoopbackParams.TargetProcessId = self.pid
        params.ProcessLoopbackParams.ProcessLoopbackMode = (
            PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE if self.haric
            else PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE)
        pv = com["PROPVARIANT"]()
        pv.vt = VT_BLOB
        pv.blob.cbSize = ctypes.sizeof(params)
        pv.blob.pBlobData = ctypes.cast(byref(params), c_void_p)

        etkinlestir = ctypes.WinDLL("Mmdevapi.dll").ActivateAudioInterfaceAsync
        etkinlestir.argtypes = [ctypes.c_wchar_p, POINTER(com["GUID"]), POINTER(com["PROPVARIANT"]),
                                POINTER(com["IActivateAudioInterfaceCompletionHandler"]),
                                POINTER(POINTER(com["IActivateAudioInterfaceAsyncOperation"]))]
        etkinlestir.restype = HRESULT
        tamamlayici = com["Tamamlayici"]()
        isleyici = tamamlayici.QueryInterface(com["IActivateAudioInterfaceCompletionHandler"])
        islem = POINTER(com["IActivateAudioInterfaceAsyncOperation"])()
        etkinlestir(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, byref(com["IAudioClient"]._iid_), byref(pv),
                    isleyici, byref(islem))
        if not tamamlayici.bitti.wait(5):
            raise RuntimeError("Windows 5 saniye içinde cevap vermedi")
        if tamamlayici.hata:
            raise RuntimeError(tamamlayici.hata)
        return tamamlayici.istemci

    def _dongu(self) -> None:
        com, kernel32 = None, None
        istemci, yakalayici, olay = None, None, None
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateEventW.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            com = _com_tanimlari()
            com["comtypes"].CoInitializeEx(COINIT_MULTITHREADED)
            istemci = self._istemci_al(com)
            fmt = com["WAVEFORMATEX"](1, KANAL, ORNEKLEME, ORNEKLEME * KANAL * BIT // 8,
                                      KANAL * BIT // 8, BIT, 0)
            istemci.Initialize(AUDCLNT_SHAREMODE_SHARED,
                               AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                               | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                               200_000, 0, byref(fmt), None)  # 20 ms
            olay = kernel32.CreateEventW(None, False, False, None)
            istemci.SetEventHandle(olay)
            ham = istemci.GetService(byref(com["IAudioCaptureClient"]._iid_))
            yakalayici = ctypes.cast(c_void_p(ham), POINTER(com["IAudioCaptureClient"]))
            istemci.Start()
            self._hazir.set()
            log.info("Uygulama sesi yakalanıyor: pid=%d, %s", self.pid, "hariç" if self.haric else "sadece bu")
            while self._calis.is_set():
                kernel32.WaitForSingleObject(olay, 100)
                while yakalayici.GetNextPacketSize() > 0:
                    veri, n, bayrak, _, _ = yakalayici.GetBuffer()
                    if n:
                        if bayrak & AUDCLNT_BUFFERFLAGS_SILENT:
                            blok = np.zeros((n, KANAL), np.float32)
                        else:
                            ham_veri = ctypes.string_at(veri, n * KANAL * BIT // 8)
                            blok = np.frombuffer(ham_veri, np.int16).reshape(-1, KANAL).astype(np.float32) / 32768.0
                        self._yaz(blok)
                    yakalayici.ReleaseBuffer(n)
        except Exception as e:  # noqa: BLE001
            self.hata = f"Uygulama sesi yakalanamadı: {e}"
            log.warning(self.hata)
        finally:
            self._hazir.set()
            try:
                if istemci is not None:
                    istemci.Stop()
            except Exception:
                pass
            if olay:
                kernel32.CloseHandle(olay)
            istemci = yakalayici = None  # COM nesneleri CoUninitialize'dan önce bırakılmalı
            if com is not None:
                try:
                    com["comtypes"].CoUninitialize()
                except Exception:
                    pass


def kendi_pid() -> int:
    return os.getpid()

