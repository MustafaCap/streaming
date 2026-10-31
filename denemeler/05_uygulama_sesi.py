"""Deneme 5: Sadece TEK BİR uygulamanın sesini yakala (Process Loopback).

Ne deniyoruz?
  04 numaralı denemedeki yankı sorununun çözümü bu. Windows 10 2004+ / 11'de
  "Process Loopback" ile:
    - dahil modu : sadece seçilen uygulamanın (ör. oyun, Spotify) sesi alınır
    - hariç modu : seçilen uygulama (ör. Zoom, Discord) DIŞINDAKİ her şey alınır
  Bu deneme 10 saniye kaydedip bir WAV dosyasına yazar; sen de dinleyip
  doğru sesin geldiğini kontrol edersin.

  Bu, Python'dan doğrudan Windows COM arayüzlerini çağıran en deneysel dosya.
  Hata verirse çıktının tamamını bana gönder, birlikte düzeltelim.

Çalıştırma:
  python 05_uygulama_sesi.py --surec chrome.exe                 # sadece Chrome'un sesi
  python 05_uygulama_sesi.py --surec Discord.exe --haric        # Discord hariç her şey
  python 05_uygulama_sesi.py --surec spotify.exe --sure 15

Test: YouTube'da (Chrome) bir video oynat, aynı anda Spotify'da müzik çal.
  --surec chrome.exe ile kaydettiğin dosyada SADECE video sesi olmalı.
"""

import sys

sys.coinit_flags = 0  # COINIT_MULTITHREADED; comtypes import edilmeden ÖNCE olmalı

import argparse
import ctypes
import threading
import time
import wave
from ctypes import HRESULT, POINTER, Structure, byref, c_int, c_longlong, c_ulong, c_ulonglong, c_ushort, c_void_p
from ctypes import wintypes

import comtypes
import numpy as np
import psutil
from comtypes import COMMETHOD, GUID, COMObject, IUnknown

ORNEKLEME, KANAL, BIT = 48000, 2, 16

# ---------------------------------------------------------------- yapılar

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

# ---------------------------------------------------------------- COM arayüzleri

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
    """Windows, ses arayüzü hazır olunca bu nesnenin ActivateCompleted metodunu çağırır."""
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

# ---------------------------------------------------------------- yardımcılar

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

kernel32 = ctypes.windll.kernel32
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]


def ana_sureci_bul(ad: str) -> int:
    """Aynı isimli süreçler arasından en üstteki (ana) süreci bulur. Ör. Chrome'un çok süreci var."""
    adaylar = [p for p in psutil.process_iter(["pid", "name", "ppid"])
               if (p.info["name"] or "").lower() == ad.lower()]
    if not adaylar:
        raise SystemExit(f"[HATA] '{ad}' adında çalışan süreç yok. Görev Yöneticisi > Ayrıntılar'dan adını kontrol et.")
    pidler = {p.info["pid"] for p in adaylar}
    for p in adaylar:
        if p.info["ppid"] not in pidler:
            return p.info["pid"]
    return adaylar[0].info["pid"]


def ses_istemcisi_al(pid: int, haric: bool):
    params = AUDIOCLIENT_ACTIVATION_PARAMS()
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
    params.ProcessLoopbackParams.TargetProcessId = pid
    params.ProcessLoopbackParams.ProcessLoopbackMode = (
        PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE if haric
        else PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE)

    pv = PROPVARIANT()
    pv.vt = VT_BLOB
    pv.blob.cbSize = ctypes.sizeof(params)
    pv.blob.pBlobData = ctypes.cast(byref(params), c_void_p)

    etkinlestir = ctypes.WinDLL("Mmdevapi.dll").ActivateAudioInterfaceAsync
    etkinlestir.argtypes = [ctypes.c_wchar_p, POINTER(GUID), POINTER(PROPVARIANT),
                            POINTER(IActivateAudioInterfaceCompletionHandler),
                            POINTER(POINTER(IActivateAudioInterfaceAsyncOperation))]
    etkinlestir.restype = HRESULT

    tamamlayici = Tamamlayici()
    isleyici = tamamlayici.QueryInterface(IActivateAudioInterfaceCompletionHandler)
    islem = POINTER(IActivateAudioInterfaceAsyncOperation)()
    etkinlestir(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, byref(IAudioClient._iid_), byref(pv),
                isleyici, byref(islem))

    if not tamamlayici.bitti.wait(5):
        raise SystemExit("[HATA] Windows 5 saniye içinde cevap vermedi.")
    if tamamlayici.hata:
        raise SystemExit(f"[HATA] Etkinleştirme başarısız: {tamamlayici.hata}")
    return tamamlayici.istemci

# ---------------------------------------------------------------- ana akış

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--surec", required=True, help="ör. chrome.exe, Discord.exe, spotify.exe")
    ap.add_argument("--haric", action="store_true", help="bu uygulama HARİÇ her şeyi yakala")
    ap.add_argument("--sure", type=int, default=10, help="kaç saniye kaydedilsin")
    args = ap.parse_args()

    pid = ana_sureci_bul(args.surec)
    print(f"Hedef: {args.surec} (PID {pid}), mod: {'HARİÇ' if args.haric else 'SADECE BU'}")

    istemci = ses_istemcisi_al(pid, args.haric)

    fmt = WAVEFORMATEX(1, KANAL, ORNEKLEME, ORNEKLEME * KANAL * BIT // 8, KANAL * BIT // 8, BIT, 0)
    istemci.Initialize(AUDCLNT_SHAREMODE_SHARED,
                       AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                       | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                       200_000, 0, byref(fmt), None)  # 20 ms tampon
    olay = kernel32.CreateEventW(None, False, False, None)
    istemci.SetEventHandle(olay)
    ham = istemci.GetService(byref(IAudioCaptureClient._iid_))
    yakalayici = ctypes.cast(c_void_p(ham), POINTER(IAudioCaptureClient))

    parcalar = []
    istemci.Start()
    print(f"{args.sure} saniye kaydediliyor...")
    bitis = time.time() + args.sure
    son_rapor = 0.0
    try:
        while time.time() < bitis:
            kernel32.WaitForSingleObject(olay, 100)
            while yakalayici.GetNextPacketSize() > 0:
                veri, n, bayrak, _, _ = yakalayici.GetBuffer()
                bayt = n * fmt.nBlockAlign
                if bayrak & AUDCLNT_BUFFERFLAGS_SILENT:
                    parcalar.append(b"\x00" * bayt)
                else:
                    parcalar.append(ctypes.string_at(veri, bayt))
                yakalayici.ReleaseBuffer(n)
            if time.time() - son_rapor > 0.2 and parcalar:
                son = np.frombuffer(parcalar[-1], np.int16)
                seviye = (np.abs(son).max() / 32768) if len(son) else 0
                print(f"\rSeviye [{'#' * int(seviye * 30):<30}]", end="")
                son_rapor = time.time()
    finally:
        istemci.Stop()

    dosya = f"kayit_{args.surec.replace('.exe', '')}{'_haric' if args.haric else ''}.wav"
    with wave.open(dosya, "wb") as w:
        w.setnchannels(KANAL); w.setsampwidth(BIT // 8); w.setframerate(ORNEKLEME)
        w.writeframes(b"".join(parcalar))
    toplam_sn = sum(len(p) for p in parcalar) / fmt.nAvgBytesPerSec
    print(f"\nKaydedildi: {dosya} ({toplam_sn:.1f} sn ses). Çift tıklayıp dinle.")


if __name__ == "__main__":
    main()
