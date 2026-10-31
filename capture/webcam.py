"""Webcam kaynağı.

Kamera ayrı bir iş parçacığında okunur; video hattı her zaman "en son kareyi"
alır ve kamerayı asla beklemez. Kamera çıkarılırsa uygulama çökmez:
son_kare() None döner ve birkaç saniyede bir yeniden bağlanmaya çalışılır.
Kamera kapatılınca (F10) cihaz gerçekten bırakılır, kameranın ışığı söner.
"""

import logging
import sys
import threading
import time

import cv2

log = logging.getLogger(__name__)


class WebcamKaynagi:
    YENIDEN_DENEME_SN = 3.0
    ESKI_KARE_SN = 1.0  # bu kadar süredir yeni kare yoksa kamera kopmuş sayılır

    def __init__(self, cihaz: int = 0, genislik: int = 1280, yukseklik: int = 720, fps: int = 30,
                 ayna: bool = False, bulaniklastir: bool = False):
        self.cihaz, self.genislik, self.yukseklik, self.fps = cihaz, genislik, yukseklik, fps
        self.ayna = ayna
        self.bulaniklastir = bulaniklastir  # arka plan bulanıklaştırma (Ayarlar > Kamera)
        self._bulanik = None
        self._kare = None
        self._kare_zamani = 0.0
        self._kilit = threading.Lock()
        self._calis = threading.Event()
        self._is: threading.Thread | None = None
        self.son_hata = ""

    @property
    def acik(self) -> bool:
        """Kullanıcı kamerayı açtı mı (cihaz bağlı olmasa bile)."""
        return self._calis.is_set()

    @property
    def calisiyor(self) -> bool:
        return self.acik and (time.monotonic() - self._kare_zamani) < self.ESKI_KARE_SN

    def baslat(self) -> None:
        if self._calis.is_set():
            return
        eski = self._is
        if eski is not None and eski.is_alive():
            eski.join(timeout=3)  # önceki iş parçacığı cihazı bıraksın
        # Her iş parçacığının kendi "çalış" bayrağı var: eskisi (ör. yavaş açılan bir kamerada
        # takılıp join'i aştıysa) yeni bayrağı görüp çalışmaya devam edemez, kapanıp cihazı bırakır.
        self._calis = threading.Event()
        self._calis.set()
        self._is = threading.Thread(target=self._dongu, args=(self._calis,), name="webcam", daemon=True)
        self._is.start()

    def durdur(self, bekle: bool = False) -> None:
        """Kamerayı bırakır. bekle=False iken video hattını bekletmez; cihaz arka planda kapanır."""
        self._calis.clear()
        if bekle and self._is is not None:
            self._is.join(timeout=3)
        with self._kilit:
            self._kare = None
        self._kare_zamani = 0.0

    def son_kare(self):
        """RGB numpy dizisi ya da kamera yoksa/kopmuşsa None."""
        if not self.calisiyor:
            return None
        with self._kilit:
            return self._kare

    def _ac(self):
        arka_uc = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.cihaz, arka_uc)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.genislik)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.yukseklik)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def _dongu(self, calis: threading.Event) -> None:
        cap = None
        try:
            while calis.is_set():
                try:
                    cap = self._bir_kare(cap, calis)
                except Exception:
                    # Beklenmedik hata (sürücü, bulanıklaştırma vb.): kamerayı bırak, biraz bekle, yeniden dene.
                    log.exception("Kamera okunurken hata; yeniden bağlanılacak")
                    self.son_hata = "Kamera hatası, yeniden bağlanılıyor"
                    if cap is not None:
                        cap.release()
                        cap = None
                    self._bekle(self.YENIDEN_DENEME_SN, calis)
        finally:
            if cap is not None:
                cap.release()   # ne olursa olsun cihaz bırakılır, kameranın ışığı söner
                log.info("Kamera bırakıldı")

    def _bir_kare(self, cap, calis: threading.Event):
        if cap is None:
            cap = self._ac()
            if cap is None:
                self.son_hata = f"{self.cihaz} numaralı kamera açılamadı"
                log.warning(self.son_hata + " (Windows Ayarlar > Gizlilik > Kamera izni açık mı?)")
                self._bekle(self.YENIDEN_DENEME_SN, calis)
                return None
            if not calis.is_set():   # açılırken kapatıldıysa hemen bırak
                return cap
            log.info("Kamera açıldı: %d", self.cihaz)
            self.son_hata = ""
        ok, kare = cap.read()
        if not ok or kare is None:
            log.warning("Kameradan kare alınamadı, yeniden bağlanılacak")
            cap.release()
            self._bekle(1.0, calis)
            return None
        kare = cv2.cvtColor(kare, cv2.COLOR_BGR2RGB)
        if self.ayna:
            kare = cv2.flip(kare, 1)
        if self.bulaniklastir:
            if self._bulanik is None:
                from capture.background_blur import ArkaPlanBulaniklastirici
                self._bulanik = ArkaPlanBulaniklastirici()
            kare = self._bulanik.isle(kare)
        if calis.is_set():
            with self._kilit:
                self._kare = kare
                self._kare_zamani = time.monotonic()
        return cap

    def _bekle(self, sn: float, calis: threading.Event) -> None:
        bitis = time.monotonic() + sn
        while calis.is_set() and time.monotonic() < bitis:
            time.sleep(0.05)
