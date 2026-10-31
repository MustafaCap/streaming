"""OBS Virtual Camera sürücüsüne doğrudan görüntü gönderir (pyvirtualcam'in yerine).

OBS Studio'nun kurduğu "OBS Virtual Camera" sürücüsü (Zoom, Meet vb. içinde
yüklenen bir DirectShow filtresi) görüntüyü "OBSVirtualCamVideo" adlı paylaşılan
bellekten okur. Bu dosya o belleği oluşturur ve kareleri NV12 biçiminde yazar.
Ağ yok, sürücü kurmak yok: sadece aynı oturumdaki programların gördüğü bir
bellek alanı. Biçim OBS'nin shared/obs-shared-memory-queue koduyla aynıdır
(OBS Studio: GPLv2 veya sonrası, bu uygulamanın GPLv3 lisansıyla uyumlu).

Bellek düzeni:
  Başlık (80 bayt, 96'ya yuvarlanır)
     0  uint32 write_idx    son yazılan karenin sayacı
     4  uint32 read_idx     okuyucunun alacağı karenin sayacı
     8  uint32 state        0 geçersiz, 1 başlıyor, 2 hazır, 3 duruyor
    12  uint32 offsets[3]   üç kare yuvasının başlangıcı
    24  uint32 type         0 = video
    28  uint32 cx, cy       genişlik, yükseklik
    40  uint64 interval     kare aralığı, 100 ns biriminde (10_000_000 / fps)
    48  uint32 reserved[8]
  Üç kare yuvası (her biri 32 bayta hizalı):
    [uint64 zaman damgası + 24 bayt boşluk][NV12 kare: Y düzlemi + iç içe UV düzlemi]
Yazıcı sayacı bir artırır, karenin yuvasına (sayaç % 3) yazar, sonra read_idx'i
o sayaca eşitler. Okuyucu hep en son tamamlanmış kareyi alır.
"""

from __future__ import annotations

import ctypes
import sys
import time

import cv2
import numpy as np

BELLEK_ADI = "OBSVirtualCamVideo"
SURUCU_CLSID = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
CIHAZ_ADI = "OBS Virtual Camera"

BASLIK_BOYUTU = 96
KARE_BASLIGI = 32
DURUM_BASLIYOR, DURUM_HAZIR, DURUM_DURUYOR = 1, 2, 3


class KameraAcilamadi(RuntimeError):
    pass


class _Baslik(ctypes.Structure):
    _fields_ = [("write_idx", ctypes.c_uint32), ("read_idx", ctypes.c_uint32), ("state", ctypes.c_uint32),
                ("offsets", ctypes.c_uint32 * 3), ("type", ctypes.c_uint32),
                ("cx", ctypes.c_uint32), ("cy", ctypes.c_uint32),
                ("interval", ctypes.c_uint64), ("reserved", ctypes.c_uint32 * 8)]


assert ctypes.sizeof(_Baslik) == 80


def _hizala(n: int, h: int = 32) -> int:
    return (n + h - 1) & ~(h - 1)


def bellek_duzeni(genislik: int, yukseklik: int) -> tuple[list[int], int, int]:
    """(üç yuvanın ofseti, toplam bellek boyutu, bir NV12 karenin boyutu)"""
    kare = genislik * yukseklik * 3 // 2
    ofsetler, boyut = [], BASLIK_BOYUTU
    for _ in range(3):
        ofsetler.append(boyut)
        boyut = _hizala(boyut + KARE_BASLIGI + kare)
    return ofsetler, boyut, kare


def rgb_nv12(rgb: np.ndarray, hedef: np.ndarray) -> None:
    """RGB kareyi NV12'ye (BT.601, sınırlı aralık) çevirip hedef diziye yazar."""
    y, x = rgb.shape[:2]
    i420 = cv2.cvtColor(rgb, cv2.COLOR_RGB2YUV_I420).reshape(-1)
    alan, ceyrek = x * y, (x // 2) * (y // 2)
    hedef[:alan] = i420[:alan]
    uv = hedef[alan:alan + 2 * ceyrek]
    uv[0::2] = i420[alan:alan + ceyrek]              # U
    uv[1::2] = i420[alan + ceyrek:alan + 2 * ceyrek]  # V


class KareKuyrugu:
    """Verilen adresteki (en az bellek_duzeni()[1] bayt) OBS kare kuyruğu."""

    def __init__(self, adres: int, genislik: int, yukseklik: int, fps: float):
        if genislik % 2 or yukseklik % 2:
            raise ValueError("Genişlik ve yükseklik çift sayı olmalı")
        self.genislik, self.yukseklik = genislik, yukseklik
        self.ofsetler, self.boyut, self.kare_boyutu = bellek_duzeni(genislik, yukseklik)
        ctypes.memset(adres, 0, BASLIK_BOYUTU)
        self.baslik = _Baslik.from_address(adres)
        b = self.baslik
        b.state = DURUM_BASLIYOR
        for i, o in enumerate(self.ofsetler):
            b.offsets[i] = o
        b.type = 0
        b.cx, b.cy = genislik, yukseklik
        b.interval = int(10_000_000 / max(1.0, float(fps)))
        self._kareler = [np.ctypeslib.as_array((ctypes.c_uint8 * self.kare_boyutu).from_address(adres + o + KARE_BASLIGI))
                         for o in self.ofsetler]
        self._zamanlar = [ctypes.c_uint64.from_address(adres + o) for o in self.ofsetler]

    def yaz(self, rgb: np.ndarray) -> None:
        if rgb.shape[:2] != (self.yukseklik, self.genislik):
            rgb = cv2.resize(rgb, (self.genislik, self.yukseklik), interpolation=cv2.INTER_AREA)
        sayac = (self.baslik.write_idx + 1) & 0xFFFFFFFF
        self.baslik.write_idx = sayac
        yuva = sayac % 3
        rgb_nv12(np.ascontiguousarray(rgb), self._kareler[yuva])
        self._zamanlar[yuva].value = time.perf_counter_ns()
        self.baslik.read_idx = sayac      # kare tamamlandı: okuyucu artık bunu alır
        self.baslik.state = DURUM_HAZIR

    def durdur(self) -> None:
        self.baslik.state = DURUM_DURUYOR
        self._kareler, self._zamanlar = [], []


def surucu_kurulu() -> bool:
    """OBS Virtual Camera sürücüsü Windows'a kayıtlı mı (OBS kurulup sanal kamera bir kez başlatılmış mı)."""
    if sys.platform != "win32":
        return False
    import winreg
    for gorunum in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{SURUCU_CLSID}", 0, gorunum))
            return True
        except OSError:
            continue
    return False


class ObsSanalKamera:
    """Paylaşılan belleği açar; gonder() ile kare yazılır, kapat() ile sürücüye 'durdu' denir."""

    FILE_MAP_READ, FILE_MAP_ALL_ACCESS, PAGE_READWRITE = 0x0004, 0x000F001F, 0x04
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, genislik: int, yukseklik: int, fps: float):
        if sys.platform != "win32":
            raise KameraAcilamadi("Sanal kamera sadece Windows'ta çalışır")
        if not surucu_kurulu():
            raise KameraAcilamadi("OBS Virtual Camera sürücüsü bulunamadı. OBS Studio'yu kur, bir kez "
                                  "'Sanal Kamerayı Başlat'a bas ve kapat.")
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k.OpenFileMappingW.restype = wintypes.HANDLE
        k.CreateFileMappingW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.LPCWSTR]
        k.CreateFileMappingW.restype = wintypes.HANDLE
        k.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        k.MapViewOfFile.restype = wintypes.LPVOID
        k.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k = k
        self._tutamak = self._adres = None

        mevcut = k.OpenFileMappingW(self.FILE_MAP_READ, False, BELLEK_ADI)
        if mevcut:
            k.CloseHandle(mevcut)
            raise KameraAcilamadi("OBS sanal kamerası şu an başka bir programda açık (OBS'nin kendisi olabilir)")
        _, boyut, _ = bellek_duzeni(genislik, yukseklik)
        tutamak = k.CreateFileMappingW(wintypes.HANDLE(-1), None, self.PAGE_READWRITE, 0, boyut, BELLEK_ADI)
        hata = ctypes.get_last_error()
        if not tutamak:
            raise KameraAcilamadi(f"Paylaşılan bellek oluşturulamadı (Windows hata kodu {hata})")
        if hata == self.ERROR_ALREADY_EXISTS:
            k.CloseHandle(tutamak)
            raise KameraAcilamadi("OBS sanal kamerası şu an başka bir programda açık")
        adres = k.MapViewOfFile(tutamak, self.FILE_MAP_ALL_ACCESS, 0, 0, 0)
        if not adres:
            hata = ctypes.get_last_error()
            k.CloseHandle(tutamak)
            raise KameraAcilamadi(f"Paylaşılan bellek açılamadı (Windows hata kodu {hata})")
        self._tutamak, self._adres = tutamak, adres
        self.kuyruk = KareKuyrugu(adres, genislik, yukseklik, fps)

    def gonder(self, rgb: np.ndarray) -> None:
        self.kuyruk.yaz(rgb)

    def kapat(self) -> None:
        if self._adres:
            self.kuyruk.durdur()   # sürücü OBS'nin bekleme görüntüsüne döner
            self._k.UnmapViewOfFile(self._adres)
        if self._tutamak:
            self._k.CloseHandle(self._tutamak)
        self._tutamak = self._adres = None
