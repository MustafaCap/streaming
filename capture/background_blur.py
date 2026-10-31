"""Webcam arka plan bulanıklaştırma.

Google MediaPipe'ın "Selfie Segmentation" modeli (Apache 2.0, models/ klasöründe)
OpenCV'nin kendi DNN modülüyle çalıştırılır; ayrıca MediaPipe kurmak gerekmez.
Model kişiyi (1) ve arka planı (0) ayıran 256x144'lük bir maske verir; maske
yumuşatılıp büyütülür, arka plan bulanıklaştırılıp kişiyle birleştirilir.

Webcam'in kendi iş parçacığında çalışır; video hattını yavaşlatmaz.
Model yüklenemezse görüntü olduğu gibi geçer, uygulama çökmez.
"""

import logging

import cv2
import numpy as np

from core import paths

log = logging.getLogger(__name__)

MODEL = "selfie_segmentation_landscape.tflite"
GIRIS_W, GIRIS_H = 256, 144


class ArkaPlanBulaniklastirici:
    def __init__(self, guc: int = 21, her_n_karede: int = 2):
        self.guc = guc                    # bulanıklık (tek sayı, büyüdükçe daha bulanık)
        self.her_n_karede = her_n_karede  # model her N karede bir çalışır (işlemci tasarrufu)
        self._ag = None
        self._yuklenemedi = False
        self._maske: np.ndarray | None = None
        self._sayac = 0
        self.hata = ""

    def _yukle(self) -> bool:
        if self._ag is not None:
            return True
        if self._yuklenemedi:
            return False
        yol = paths.uygulama_klasoru() / "models" / MODEL
        try:
            # Dosyayı kendimiz okuyup bellekten veriyoruz: OpenCV, Windows'ta Türkçe karakterli
            # kurulum yollarını (ör. "D:\\Programlar\\Yayın") açamıyor.
            self._ag = cv2.dnn.readNetFromTFLite(np.fromfile(str(yol), np.uint8))
            return True
        except Exception as e:
            self._yuklenemedi = True
            self.hata = f"Bulanıklaştırma modeli yüklenemedi: {e}"
            log.warning(self.hata)
            return False

    def maske(self, rgb: np.ndarray) -> np.ndarray | None:
        """0..1 arası kişi maskesi (GIRIS_H x GIRIS_W)."""
        if not self._yukle():
            return None
        giris = cv2.resize(rgb, (GIRIS_W, GIRIS_H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        self._ag.setInput(giris.transpose(2, 0, 1)[None].copy())
        return np.clip(self._ag.forward().reshape(GIRIS_H, GIRIS_W), 0.0, 1.0)

    def isle(self, rgb: np.ndarray) -> np.ndarray:
        self._sayac += 1
        if self._maske is None or self._sayac % self.her_n_karede == 0:
            try:
                yeni = self.maske(rgb)
            except Exception as e:
                self.hata = f"Bulanıklaştırma hatası: {e}"
                log.warning(self.hata)
                self._yuklenemedi, self._ag = True, None
                yeni = None
            if yeni is None:
                return rgb
            # zamanla yumuşatma: kenarlar titremesin
            yeni = cv2.GaussianBlur(yeni.astype(np.float32), (0, 0), 1.2)  # kenarları küçük maskede yumuşat
            self._maske = yeni if self._maske is None else (0.6 * yeni + 0.4 * self._maske).astype(np.float32)
        h, w = rgb.shape[:2]
        m = cv2.resize(self._maske, (w, h), interpolation=cv2.INTER_LINEAR)
        # arka planı küçük çözünürlükte bulanıklaştır (hızlı), sonra büyüt
        kucuk = cv2.resize(rgb, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
        kucuk = cv2.GaussianBlur(kucuk, (0, 0), self.guc / 4)
        arka = cv2.resize(kucuk, (w, h), interpolation=cv2.INTER_LINEAR)
        return cv2.blendLinear(rgb, arka, m, 1.0 - m)
