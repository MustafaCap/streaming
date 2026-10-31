"""Yerel kayıt (MP4) — FFmpeg ile.

Çıkışa giden görüntü (karşı tarafın gördüğü) ve VB-Cable'a giden ses
(mikrofon + bilgisayar sesi) kaydedilir.

  görüntü: video hattı her kareyi kare_yaz() ile verir -> kuyruk -> FFmpeg (stdin)
  ses    : mikser her 10 ms'lik bloğu ses_yaz() ile verir -> kuyruk -> geçici WAV
  durunca: FFmpeg görüntü + sesi tek MP4'te birleştirir (görüntü yeniden kodlanmaz)

Kodlayıcı ekran kartına göre seçilir: NVIDIA (h264_nvenc) -> Intel (h264_qsv) ->
AMD (h264_amf) -> Windows Media Foundation (h264_mf) -> mpeg4 (her yerde çalışır).
Uygulamayla birlikte gelen FFmpeg LGPL sürümüdür (ücretli dağıtıma uygun).
Hiçbir ağ bağlantısı açılmaz.
"""

import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

KODLAYICILAR = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf", "mpeg4"]
KODLAYICI_AYARLARI = {
    "h264_nvenc": ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"],
    "h264_qsv": ["-preset", "medium", "-global_quality", "23"],
    "h264_amf": ["-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24"],
    "h264_mf": ["-b:v", "8M", "-hw_encoding", "1"],
    "mpeg4": ["-q:v", "4"],
}
_PENCERESIZ = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: siyah konsol açılmasın


def ffmpeg_bul() -> str | None:
    """Uygulamanın yanındaki ffmpeg\\ffmpeg.exe, yoksa PATH'teki ffmpeg."""
    adaylar = []
    if getattr(sys, "frozen", False):
        adaylar.append(Path(sys.executable).parent / "ffmpeg" / "ffmpeg.exe")
    adaylar.append(Path(__file__).resolve().parent.parent / "ffmpeg" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    for a in adaylar:
        if a.exists():
            return str(a)
    return shutil.which("ffmpeg")


_kodlayici_onbellek: dict = {}


def kodlayici_sec(ffmpeg: str, tercih: str = "auto") -> str:
    """Bu bilgisayarda gerçekten çalışan ilk kodlayıcıyı bulur (küçük bir deneme kodlamasıyla)."""
    anahtar = (ffmpeg, tercih)
    if anahtar in _kodlayici_onbellek:
        return _kodlayici_onbellek[anahtar]
    sira = KODLAYICILAR if tercih in ("", "auto") else [tercih] + [k for k in KODLAYICILAR if k != tercih]
    secilen = "mpeg4"
    for k in sira:
        try:
            sonuc = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30",
                 "-frames:v", "5", "-pix_fmt", "nv12" if k != "mpeg4" else "yuv420p", "-c:v", k, "-f", "null", "-"],
                capture_output=True, timeout=15, creationflags=_PENCERESIZ)
            if sonuc.returncode == 0:
                secilen = k
                break
            log.info("Kodlayıcı kullanılamıyor: %s (%s)", k, sonuc.stderr.decode(errors="replace").strip()[:200])
        except Exception as e:
            log.info("Kodlayıcı denenemedi: %s (%s)", k, e)
    _kodlayici_onbellek[anahtar] = secilen
    log.info("Kayıt kodlayıcısı: %s", secilen)
    return secilen


def varsayilan_klasor() -> Path:
    return Path.home() / "Videos" / "YayinUygulamasi"


class Kayitci:
    def __init__(self, genislik: int, yukseklik: int, fps: int, klasor: str | Path | None = None,
                 kodlayici: str = "auto", ffmpeg: str | None = None):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self.klasor = Path(klasor) if klasor else varsayilan_klasor()
        self.kodlayici_tercihi = kodlayici
        self.ffmpeg = ffmpeg
        self._surec: subprocess.Popen | None = None
        self._kareler: queue.Queue = queue.Queue(maxsize=90)
        self._sesler: queue.Queue = queue.Queue(maxsize=2000)
        self._video_is = self._ses_is = None
        self._kayitta = False
        self._baslangic = 0.0
        self.son_dosya: Path | None = None
        self.son_hata = ""
        self.atlanan_kare = 0
        self._kilit = threading.Lock()

    @property
    def kayitta(self) -> bool:
        return self._kayitta

    @property
    def sure(self) -> int:
        return int(time.monotonic() - self._baslangic) if self._kayitta else 0

    def baslat(self) -> bool:
        with self._kilit:
            if self._kayitta:
                return True
            ffmpeg = self.ffmpeg or ffmpeg_bul()
            if not ffmpeg:
                self.son_hata = "FFmpeg bulunamadı (uygulama klasöründe ffmpeg\\ffmpeg.exe olmalı)"
                return False
            self.ffmpeg = ffmpeg
            try:
                self.klasor.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.son_hata = f"Kayıt klasörü oluşturulamadı: {e}"
                return False
            ad = datetime.now().strftime("Kayit_%Y-%m-%d_%H-%M-%S")
            self._hedef = self.klasor / f"{ad}.mp4"
            self._gecici_video = self.klasor / f".{ad}.video.mp4"
            self._gecici_ses = self.klasor / f".{ad}.ses.wav"
            kod = kodlayici_sec(ffmpeg, self.kodlayici_tercihi)
            komut = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                     "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.genislik}x{self.yukseklik}",
                     "-framerate", str(self.fps), "-use_wallclock_as_timestamps", "1", "-i", "-",
                     "-fps_mode", "cfr", "-r", str(self.fps),
                     "-pix_fmt", "nv12" if kod != "mpeg4" else "yuv420p", "-c:v", kod,
                     *KODLAYICI_AYARLARI.get(kod, []), str(self._gecici_video)]
            try:
                self._surec = subprocess.Popen(komut, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.PIPE, creationflags=_PENCERESIZ)
            except Exception as e:
                self.son_hata = f"FFmpeg başlatılamadı: {e}"
                return False
            self._kareler = queue.Queue(maxsize=90)
            self._sesler = queue.Queue(maxsize=2000)
            self.atlanan_kare = 0
            self._wav = wave.open(str(self._gecici_ses), "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(2)
            self._wav.setframerate(48000)
            self._ses_yazildi = False
            self._kayitta = True
            self._baslangic = time.monotonic()
            self.son_hata = ""
            self._video_is = threading.Thread(target=self._video_dongu, name="kayit-video", daemon=True)
            self._ses_is = threading.Thread(target=self._ses_dongu, name="kayit-ses", daemon=True)
            self._video_is.start()
            self._ses_is.start()
            log.info("Kayıt başladı: %s (%s)", self._hedef, kod)
            return True

    def kare_yaz(self, kare: np.ndarray) -> None:
        """Video hattından her karede çağrılır; asla beklemez (kuyruk doluysa kare atlanır)."""
        if not self._kayitta:
            return
        try:
            self._kareler.put_nowait(kare)
        except queue.Full:
            self.atlanan_kare += 1

    def ses_yaz(self, blok: np.ndarray) -> None:
        """Mikserden her 10 ms'de çağrılır (ses iş parçacığı); asla beklemez."""
        if not self._kayitta:
            return
        try:
            self._sesler.put_nowait(blok)
        except queue.Full:
            pass

    def _video_dongu(self) -> None:
        surec = self._surec
        while True:
            kare = self._kareler.get()
            if kare is None:
                break
            try:
                surec.stdin.write(np.ascontiguousarray(kare).tobytes())
            except Exception as e:
                hata = surec.stderr.read().decode(errors="replace")[-300:] if surec.stderr else ""
                self.son_hata = f"Kayıt yazılamadı: {e} {hata}".strip()
                log.warning(self.son_hata)
                break

    def _ses_dongu(self) -> None:
        while True:
            blok = self._sesler.get()
            if blok is None:
                break
            veri = (np.clip(blok, -1.0, 1.0) * 32767).astype("<i2").tobytes()
            self._wav.writeframes(veri)
            self._ses_yazildi = True

    def durdur(self, bitti=None) -> None:
        """Kaydı bitirir; birleştirme arka planda yapılır, bitince bitti(dosya_yolu|None, hata) çağrılır."""
        with self._kilit:
            if not self._kayitta:
                return
            self._kayitta = False
            surec, video_is, ses_is = self._surec, self._video_is, self._ses_is
            self._surec = None
        self._kareler.put(None)
        self._sesler.put(None)
        threading.Thread(target=self._bitir, args=(surec, video_is, ses_is, bitti), name="kayit-bitir",
                         daemon=True).start()

    def _bitir(self, surec, video_is, ses_is, bitti) -> None:
        hata = ""
        try:
            video_is.join(timeout=10)
            ses_is.join(timeout=10)
            try:
                surec.stdin.close()
            except Exception:
                pass
            try:
                surec.wait(timeout=30)
            except subprocess.TimeoutExpired:
                surec.kill()
            self._wav.close()
            if not self._gecici_video.exists() or self._gecici_video.stat().st_size == 0:
                hata = self.son_hata or "Görüntü kaydedilemedi"
            elif self._ses_yazildi:
                sonuc = subprocess.run(
                    [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(self._gecici_video),
                     "-i", str(self._gecici_ses), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                     "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(self._hedef)],
                    capture_output=True, timeout=600, creationflags=_PENCERESIZ)
                if sonuc.returncode != 0:
                    log.warning("Ses birleştirilemedi: %s", sonuc.stderr.decode(errors="replace")[-300:])
                    os.replace(self._gecici_video, self._hedef)  # en azından görüntü kalsın
                    hata = "Ses eklenemedi; sadece görüntü kaydedildi"
            else:
                os.replace(self._gecici_video, self._hedef)
        except Exception as e:
            log.exception("Kayıt bitirilirken hata")
            hata = f"Kayıt bitirilemedi: {e}"
        finally:
            for f in (self._gecici_video, self._gecici_ses):
                try:
                    if f.exists():
                        f.unlink()
                except OSError:
                    pass
        dosya = self._hedef if self._hedef.exists() else None
        self.son_dosya = dosya
        log.info("Kayıt bitti: %s %s", dosya, hata)
        if bitti is not None:
            try:
                bitti(dosya, hata)
            except Exception:
                log.exception("Kayıt bitti geri çağrısında hata")
