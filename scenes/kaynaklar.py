"""Ek kaynakların canlı yakalayıcıları: ikinci monitör, pencere, ekran bölgesi, ikinci kamera,
görsel ve video.

Video hattı her karede aktif sahneyi verir; bu sınıf sahnedeki görünür ek kaynakların son
karelerini {kaynak kimliği: kare} olarak döndürür. Sahnede olmayan (ya da gizlenen) kaynakların
yakalayıcıları kapatılır; böylece başka sahnedeki ikinci kamera boşuna açık kalmaz.
Ana ekran ve ana webcam burada değil, video hattının kendisinde.

Bu modül Qt'ye bağlı değildir.
"""

import logging
import time
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def gorsel_oku(yol: str) -> np.ndarray | None:
    """PNG/JPG/WebP okur (Türkçe karakterli yollar dahil). Saydamlık varsa RGBA döner."""
    import cv2
    try:
        veri = np.fromfile(yol, np.uint8)
        resim = cv2.imdecode(veri, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
    if resim is None:
        return None
    if resim.ndim == 2:
        return cv2.cvtColor(resim, cv2.COLOR_GRAY2RGB)
    if resim.shape[2] == 4:
        return cv2.cvtColor(resim, cv2.COLOR_BGRA2RGBA)
    return cv2.cvtColor(resim, cv2.COLOR_BGR2RGB)


class _Bolge:
    """Bir monitörün bir bölümünü yakalar (oranlar 0..1)."""

    def __init__(self, monitor: int, dikdortgen):
        from capture.screen import EkranKaynagi
        self.kaynak = EkranKaynagi(monitor, "mss")
        self.dikdortgen = dikdortgen

    def grab(self):
        kare = self.kaynak.grab()
        if kare is None:
            return None
        h, w = kare.shape[:2]
        x, y, bw, bh = self.dikdortgen
        x0, y0 = max(0, int(x * w)), max(0, int(y * h))
        x1, y1 = min(w, int((x + bw) * w)), min(h, int((y + bh) * h))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        return kare[y0:y1, x0:x1]

    def kapat(self):
        self.kaynak.kapat()


class _Pencere:
    """Pencereyi başlığına göre bulur (uygulama yeniden açılınca pencere numarası değişir)."""

    ARAMA_SN = 3.0

    def __init__(self, baslik: str, listele=None):
        self.baslik = baslik
        self._listele = listele
        self._kaynak = None
        self._son_arama = 0.0

    def _bul(self):
        from capture.window import PencereKaynagi, pencereleri_listele
        listele = self._listele or pencereleri_listele
        adaylar = listele()
        for hwnd, baslik, _ in adaylar:
            if baslik == self.baslik:
                return PencereKaynagi(hwnd, baslik)
        for hwnd, baslik, _ in adaylar:   # başlık biraz değişmiş olabilir (ör. sekme adı)
            if self.baslik and (self.baslik in baslik or baslik in self.baslik):
                return PencereKaynagi(hwnd, baslik)
        return None

    def grab(self):
        if self._kaynak is None:
            simdi = time.monotonic()
            if simdi - self._son_arama < self.ARAMA_SN:
                return None
            self._son_arama = simdi
            try:
                self._kaynak = self._bul()
            except Exception:
                self._kaynak = None
            if self._kaynak is None:
                return None
        kare = self._kaynak.grab()
        if kare is None and not self._kaynak.calisiyor:
            self._kaynak.kapat()
            self._kaynak = None
        return kare

    def kapat(self):
        if self._kaynak is not None:
            self._kaynak.kapat()
            self._kaynak = None


class _Kamera:
    def __init__(self, cihaz: int, w: int, h: int, fps: int):
        from capture.webcam import WebcamKaynagi
        self.kamera = WebcamKaynagi(cihaz, w, h, fps)

    def grab(self, acik: bool):
        if acik and not self.kamera.acik:
            self.kamera.baslat()
        elif not acik and self.kamera.acik:
            self.kamera.durdur()
        return self.kamera.son_kare() if acik else None

    def kapat(self):
        self.kamera.durdur()


class _Video:
    def __init__(self, yol: str, w: int, h: int):
        from core.standby import BeklemeVideosu
        self.yol, self.w, self.h = yol, w, h
        self.video = BeklemeVideosu()

    def grab(self):
        return self.video.kare(self.yol, self.w, self.h)

    def kapat(self):
        self.video.kapat()


class _Gorsel:
    def __init__(self, yol: str):
        self.resim = gorsel_oku(yol)
        if self.resim is not None:
            self.resim.setflags(write=False)

    def grab(self):
        return self.resim

    def kapat(self):
        pass


class EkKaynaklar:
    def __init__(self, genislik: int = 1280, yukseklik: int = 720, fps: int = 30, fabrika=None):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self._fabrika = fabrika or self._olustur
        self._acik: dict[str, tuple[tuple, object]] = {}   # kimlik -> (imza, yakalayıcı)

    @staticmethod
    def _imza(k) -> tuple:
        return (k.tur, tuple(sorted((a, str(v)) for a, v in k.ayar.items() if a not in ("position",))))

    def _olustur(self, k):
        a = k.ayar
        if k.tur == "ekran":
            from capture.screen import EkranKaynagi
            return EkranKaynagi(int(a.get("monitor", 0)), "mss")
        if k.tur == "bolge":
            return _Bolge(int(a.get("monitor", 0)), a.get("rect") or [0, 0, 1, 1])
        if k.tur == "pencere":
            return _Pencere(str(a.get("title", "")))
        if k.tur == "kamera":
            return _Kamera(int(a.get("device", 1)), self.genislik, self.yukseklik, self.fps)
        if k.tur == "video":
            return _Video(str(a.get("path", "")), self.genislik, self.yukseklik)
        if k.tur == "gorsel":
            return _Gorsel(str(a.get("path", "")))
        return None

    def kareler(self, sahne, kamera_acik: bool, kamera_kullaniliyor: bool = True) -> dict:
        """Sahnedeki görünür ek kaynakların son kareleri. Her karede video hattından çağrılır."""
        istenen = {}
        for k in sahne.kaynaklar:
            if not k.gorunur or k.ana or k.tur in ("bekleme", "kalem", "imlec", "metin"):
                continue
            istenen[k.kimlik] = k
        for kimlik in list(self._acik):
            if kimlik not in istenen or self._acik[kimlik][0] != self._imza(istenen[kimlik]):
                self._kapat(kimlik)
        sonuc = {}
        for kimlik, k in istenen.items():
            if kimlik not in self._acik:
                try:
                    yakalayici = self._fabrika(k)
                except Exception:
                    log.exception("Kaynak açılamadı: %s", k.ad)
                    yakalayici = None
                self._acik[kimlik] = (self._imza(k), yakalayici)
            yakalayici = self._acik[kimlik][1]
            if yakalayici is None:
                sonuc[kimlik] = None
                continue
            try:
                if k.tur == "kamera":
                    sonuc[kimlik] = yakalayici.grab(kamera_acik and kamera_kullaniliyor)
                else:
                    sonuc[kimlik] = yakalayici.grab()
            except Exception:
                log.exception("Kaynak okunamadı: %s", k.ad)
                sonuc[kimlik] = None
        return sonuc

    def _kapat(self, kimlik: str) -> None:
        _, yakalayici = self._acik.pop(kimlik, (None, None))
        if yakalayici is not None:
            try:
                yakalayici.kapat()
            except Exception:
                log.exception("Kaynak kapatılamadı")

    def kapat(self) -> None:
        for kimlik in list(self._acik):
            self._kapat(kimlik)


def video_kopyala(kaynak: str) -> str:
    """Video kaynakları da (bekleme videosu gibi) uygulama klasörüne kopyalanır: OpenCV Türkçe
    karakterli yolları açamıyor, kullanıcı dosyayı taşısa da kaynak bozulmaz."""
    import shutil

    from core import paths
    hedef_klasor = paths.veri_klasoru() / "kaynaklar"
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    if Path(kaynak).resolve().parent == hedef_klasor.resolve():
        return str(kaynak)
    hedef = hedef_klasor / f"video_{int(time.time() * 1000)}{Path(kaynak).suffix.lower()}"
    shutil.copyfile(kaynak, hedef)
    return str(hedef)
