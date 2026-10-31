"""Yerel kayıt (MP4) — FFmpeg ile.

Çıkışa giden görüntü (karşı tarafın gördüğü) ve VB-Cable'a giden ses
(mikrofon + bilgisayar sesi) kaydedilir.

  görüntü: video hattı her kareyi kare_yaz() ile verir -> kuyruk -> FFmpeg (stdin) -> geçici MKV
  ses    : mikser her 10 ms'lik bloğu ses_yaz() ile verir -> kuyruk -> geçici ham PCM dosyası
  durunca: FFmpeg görüntü + sesi tek MP4'te birleştirir (görüntü yeniden kodlanmaz)

Duraklat / devam et: duraklatınca o anki görüntü parçası kapatılır ve ses yazılmaz.
Devam edince yeni bir görüntü parçası başlar. Sonda parçalar sırayla uç uca eklenir,
böylece duraklatılan süre videoya girmez.

Çökmeye dayanıklı: kayıt sürerken uygulama çökerse, elektrik giderse ya da görev
yöneticisinden kapatılırsa geçici dosyalar açılabilir kalır (MKV ve başlıksız PCM,
MP4/WAV gibi sonda yazılan bir içindekiler tablosuna ihtiyaç duymaz). Uygulama bir
sonraki açılışta yarım kalan kaydı bulup "..._kurtarildi.mp4" olarak birleştirir.
Disk dolarsa kayıt durdurulur ve kullanıcıya söylenir.

Kodlayıcı ekran kartına göre seçilir: NVIDIA (h264_nvenc) -> Intel (h264_qsv) ->
AMD (h264_amf) -> Windows Media Foundation (h264_mf) -> mpeg4 (her yerde çalışır).
Uygulamayla birlikte gelen FFmpeg LGPL sürümüdür.
Hiçbir ağ bağlantısı açılmaz.
"""

import collections
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
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
SES_HIZI, SES_KANALI = 48000, 2
GECICI_VIDEO, GECICI_SES = ".video.mkv", ".ses.pcm"
# İlk parça ".Kayit_....video.mkv", duraklatıp devam edince ".Kayit_....video.2.mkv", ".3" ...
_GECICI_AD = re.compile(r"^\.(Kayit_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.video(?:\.(\d+))?\.mkv$")


def parca_yolu(klasor: Path, ad: str, sira: int) -> Path:
    """sira 1 ise eski adla aynı (önceki sürümlerin yarım kayıtları da kurtarılabilsin)."""
    return klasor / (f".{ad}{GECICI_VIDEO}" if sira == 1 else f".{ad}.video.{sira}.mkv")


def _gizle(yol: Path) -> None:
    """Geçici dosyalar Kayıtlar klasöründe görünmesin (Windows'ta nokta ile başlamak gizlemez)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(yol), 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            pass


def ffmpeg_bul() -> str | None:
    """Uygulamanın yanındaki ffmpeg\\ffmpeg.exe. Sadece geliştirirken PATH'teki ffmpeg de kullanılır
    (dağıtılan pakette başka bir programın ffmpeg'i çalıştırılmasın)."""
    if getattr(sys, "frozen", False):
        paketteki = Path(sys.executable).parent / "ffmpeg" / "ffmpeg.exe"
        return str(paketteki) if paketteki.exists() else None
    yerel = Path(__file__).resolve().parent.parent / "ffmpeg" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if yerel.exists():
        return str(yerel)
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
    return Path.home() / "Videos" / "RizeOn"


def _concat_satiri(yol: Path) -> str:
    # FFmpeg concat listesinde tek tırnak '\'' ile yazılır
    return "file '" + str(yol).replace("\\", "/").replace("'", "'\\''") + "'\n"


def _birlestir(ffmpeg: str, video, ses: Path | None, hedef: Path) -> tuple[bool, str]:
    """Geçici görüntü parça(lar)ını (MKV) + ham sesi (PCM) tek MP4'te birleştirir. (başarılı mı, hata metni)"""
    parcalar = [Path(v) for v in video] if isinstance(video, (list, tuple)) else [Path(video)]
    liste = None
    if len(parcalar) == 1:
        girdi = ["-i", str(parcalar[0])]
    else:
        liste = hedef.with_name(f".{hedef.stem}.liste.txt")
        try:
            liste.write_text("".join(_concat_satiri(v) for v in parcalar), encoding="utf-8")
        except OSError as e:
            return False, str(e)
        girdi = ["-f", "concat", "-safe", "0", "-i", str(liste)]
    try:
        return _birlestir_calistir(ffmpeg, girdi, ses, hedef)
    finally:
        if liste is not None:
            try:
                liste.unlink(missing_ok=True)
            except OSError:
                pass


def _birlestir_calistir(ffmpeg: str, girdi: list, ses: Path | None, hedef: Path) -> tuple[bool, str]:
    komut = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *girdi]
    if ses is not None:
        komut += ["-f", "s16le", "-ar", str(SES_HIZI), "-ac", str(SES_KANALI), "-i", str(ses),
                  "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-shortest"]
    else:
        komut += ["-map", "0:v"]
    komut += ["-c:v", "copy", "-movflags", "+faststart", str(hedef)]
    try:
        sonuc = subprocess.run(komut, capture_output=True, timeout=1800, creationflags=_PENCERESIZ)
    except Exception as e:
        return False, str(e)
    if sonuc.returncode != 0 or not hedef.exists() or hedef.stat().st_size == 0:
        try:
            hedef.unlink(missing_ok=True)
        except OSError:
            pass
        return False, sonuc.stderr.decode(errors="replace").strip()[-300:]
    return True, ""


def yarim_kayitlari_kurtar(klasor: Path, ffmpeg: str | None) -> list[Path]:
    """Önceki çalışmada çökme/elektrik kesintisi yüzünden yarım kalan kayıtları MP4'e çevirir."""
    klasor = Path(klasor)
    if not ffmpeg or not klasor.is_dir():
        return []
    kayitlar: dict[str, list[tuple[int, Path]]] = {}
    for video in sorted(klasor.iterdir()):
        eslesme = _GECICI_AD.match(video.name)
        if eslesme and video.is_file():
            kayitlar.setdefault(eslesme.group(1), []).append((int(eslesme.group(2) or 1), video))
    kurtarilan = []
    for ad, liste in sorted(kayitlar.items()):
        tum_parcalar = [v for _, v in sorted(liste)]
        ses = klasor / f".{ad}{GECICI_SES}"
        if any(time.time() - f.stat().st_mtime < 3 for f in tum_parcalar):
            continue   # şu an yazılan (yeni başlamış) bir kayıt olabilir
        parcalar = [v for v in tum_parcalar if v.stat().st_size > 0]
        hedef = klasor / f"{ad}_kurtarildi.mp4"
        if not parcalar:
            ok, hata = False, "boş dosya"
        else:
            ses_var = ses.exists() and ses.stat().st_size > 0
            ok, hata = _birlestir(ffmpeg, parcalar, ses if ses_var else None, hedef)
            if not ok and ses_var:
                ok, hata = _birlestir(ffmpeg, parcalar, None, hedef)   # ses bozuksa en azından görüntü
            if not ok and len(parcalar) > 1:
                ok, hata = _birlestir(ffmpeg, parcalar[0], ses if ses_var else None, hedef)   # en az ilk parça
        if ok:
            log.info("Yarım kalan kayıt kurtarıldı: %s", hedef)
            kurtarilan.append(hedef)
            for f in (*tum_parcalar, ses):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            log.warning("Yarım kalan kayıt kurtarılamadı (%s): %s", ad, hata)
            if not parcalar:
                for f in (*tum_parcalar, ses):
                    try:
                        f.unlink(missing_ok=True)
                    except OSError:
                        pass
    return kurtarilan


class Kayitci:
    def __init__(self, genislik: int, yukseklik: int, fps: int, klasor: str | Path | None = None,
                 kodlayici: str = "auto", ffmpeg: str | None = None):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self.klasor = Path(klasor) if klasor else varsayilan_klasor()
        self.kodlayici_tercihi = kodlayici
        self.ffmpeg = ffmpeg
        self.hata_olunca = None          # kayıt yazılamazsa (disk doldu vb.) çağrılır: hata_olunca(mesaj)
        self._surec: subprocess.Popen | None = None
        self._kareler: queue.Queue = queue.Queue(maxsize=self._kuyruk_boyu())
        self._sesler: queue.Queue = queue.Queue(maxsize=2000)
        self._video_is = self._ses_is = None
        self._parca: dict | None = None          # şu an yazılan görüntü parçası: {"yol": Path, "kare": int}
        self._parcalar: list[Path] = []          # bu kaydın tüm görüntü parçaları (sırayla)
        self._kapananlar: list[threading.Thread] = []
        self._kayitta = False
        self._duraklatildi = False
        self._baslangic = 0.0
        self._duraklama_baslangic = 0.0
        self._toplam_duraklama = 0.0
        self.son_dosya: Path | None = None
        self.son_hata = ""
        self.atlanan_kare = 0
        self.atlanan_ses = 0
        self._ffmpeg_ciktisi: collections.deque = collections.deque(maxlen=50)
        self._kilit = threading.Lock()

    def _kuyruk_boyu(self) -> int:
        # Yaklaşık 1 saniyelik ham kare (1080p'de ~190 MB); kodlayıcı yetişemezse kare atlanır.
        return max(10, int(self.fps))

    @property
    def kayitta(self) -> bool:
        return self._kayitta

    @property
    def duraklatildi(self) -> bool:
        return self._kayitta and self._duraklatildi

    @property
    def sure(self) -> int:
        """Kaydedilen süre (saniye). Duraklatılan süre sayılmaz."""
        if not self._kayitta:
            return 0
        simdi = time.monotonic()
        duraklama = self._toplam_duraklama
        if self._duraklatildi:
            duraklama += simdi - self._duraklama_baslangic
        return max(0, int(simdi - self._baslangic - duraklama))

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
            self._ad = datetime.now().strftime("Kayit_%Y-%m-%d_%H-%M-%S")
            self._hedef = self.klasor / f"{self._ad}.mp4"
            self._gecici_video = parca_yolu(self.klasor, self._ad, 1)
            self._gecici_ses = self.klasor / f".{self._ad}{GECICI_SES}"
            self._kod = kodlayici_sec(ffmpeg, self.kodlayici_tercihi)
            try:
                self._ses_dosyasi = open(self._gecici_ses, "wb")
            except OSError as e:
                self.son_hata = f"Kayıt dosyası açılamadı: {e}"
                return False
            _gizle(self._gecici_ses)
            self._parcalar = []
            self._kapananlar = []
            self._ffmpeg_ciktisi.clear()
            self._hata_bildirildi = False
            if not self._parca_baslat():
                self._ses_dosyasi.close()
                self._gecici_ses.unlink(missing_ok=True)
                return False
            self._sesler = queue.Queue(maxsize=2000)
            self.atlanan_kare = self.atlanan_ses = 0
            self._ses_yazildi = False
            self._duraklatildi = False
            self._toplam_duraklama = 0.0
            self._kayitta = True
            self._baslangic = time.monotonic()
            self.son_hata = ""
            self._ses_is = threading.Thread(target=self._ses_dongu, name="kayit-ses", daemon=True)
            self._ses_is.start()
            log.info("Kayıt başladı: %s (%s)", self._hedef, self._kod)
            return True

    def _parca_baslat(self) -> bool:
        """Yeni bir görüntü parçası için FFmpeg'i başlatır (kilit tutulurken çağrılır)."""
        yol = parca_yolu(self.klasor, self._ad, len(self._parcalar) + 1)
        kod = self._kod
        komut = [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.genislik}x{self.yukseklik}",
                 "-framerate", str(self.fps), "-use_wallclock_as_timestamps", "1", "-i", "-",
                 "-fps_mode", "cfr", "-r", str(self.fps),
                 "-pix_fmt", "nv12" if kod != "mpeg4" else "yuv420p", "-c:v", kod,
                 *KODLAYICI_AYARLARI.get(kod, []),
                 "-g", str(max(1, int(self.fps) * 2)),   # 2 sn'de bir anahtar kare: çökmede en fazla 2 sn kaybolur
                 "-f", "matroska", "-flush_packets", "1", str(yol)]
        try:
            surec = subprocess.Popen(komut, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, creationflags=_PENCERESIZ)
        except Exception as e:
            self.son_hata = f"FFmpeg başlatılamadı: {e}"
            return False
        _gizle(yol)
        self._parcalar.append(yol)
        self._parca = {"yol": yol, "kare": 0}
        self._surec = surec
        self._kareler = queue.Queue(maxsize=self._kuyruk_boyu())
        # FFmpeg'in hata çıktısı sürekli okunur (okunmazsa boru dolup FFmpeg tıkanabilir)
        threading.Thread(target=self._ffmpeg_ciktisini_oku, args=(surec,), name="kayit-ffmpeg",
                         daemon=True).start()
        self._video_is = threading.Thread(target=self._video_dongu, args=(surec, self._kareler, self._parca),
                                          name="kayit-video", daemon=True)
        self._video_is.start()
        return True

    def duraklat(self) -> bool:
        """Kaydı duraklatır: görüntü parçası kapanır, ses yazılmaz. Bekletmez."""
        with self._kilit:
            if not self._kayitta or self._duraklatildi:
                return False
            self._duraklatildi = True
            self._duraklama_baslangic = time.monotonic()
            surec, video_is, kareler, parca = self._surec, self._video_is, self._kareler, self._parca
            self._surec = self._video_is = self._parca = None
        kareler.put(None)
        is_ = threading.Thread(target=self._parcayi_kapat, args=(surec, video_is, parca),
                               name="kayit-parca", daemon=True)
        self._kapananlar.append(is_)
        is_.start()
        log.info("Kayıt duraklatıldı")
        return True

    def devam_et(self) -> bool:
        """Duraklatılan kayda devam eder (yeni görüntü parçası başlar)."""
        with self._kilit:
            if not self._kayitta or not self._duraklatildi:
                return False
            if not self._parca_baslat():
                return False
            self._toplam_duraklama += time.monotonic() - self._duraklama_baslangic
            self._duraklatildi = False
        log.info("Kayda devam edildi (%d. parça)", len(self._parcalar))
        return True

    def kare_yaz(self, kare: np.ndarray) -> None:
        """Video hattından her karede çağrılır; asla beklemez (kuyruk doluysa kare atlanır)."""
        if not self._kayitta or self._duraklatildi:
            return
        try:
            self._kareler.put_nowait(kare)
        except queue.Full:
            self.atlanan_kare += 1

    def ses_yaz(self, blok: np.ndarray) -> None:
        """Mikserden her 10 ms'de çağrılır (ses iş parçacığı); asla beklemez."""
        if not self._kayitta or self._duraklatildi:
            return
        try:
            self._sesler.put_nowait(blok)
        except queue.Full:
            self.atlanan_ses += 1

    def _ffmpeg_ciktisini_oku(self, surec) -> None:
        try:
            for satir in surec.stderr:
                metin = satir.decode(errors="replace").rstrip()
                if metin:
                    self._ffmpeg_ciktisi.append(metin)
        except Exception:
            pass

    def _yazma_hatasi(self, mesaj: str) -> None:
        """Disk doldu, FFmpeg kapandı vb.: bir kez bildir; kayıt durdurulur, o ana kadarki kısım kaydedilir."""
        self.son_hata = mesaj
        log.warning(mesaj)
        if self._hata_bildirildi:
            return
        self._hata_bildirildi = True
        if self.hata_olunca is not None:
            try:
                self.hata_olunca(mesaj)
            except Exception:
                log.exception("Kayıt hata geri çağrısında hata")

    def _video_dongu(self, surec, kareler, parca) -> None:
        while True:
            kare = kareler.get()
            if kare is None:
                break
            try:
                surec.stdin.write(np.ascontiguousarray(kare).tobytes())
                parca["kare"] += 1
            except Exception as e:
                time.sleep(0.2)   # FFmpeg'in son satırları okunsun
                ayrinti = " ".join(list(self._ffmpeg_ciktisi)[-3:])
                self._yazma_hatasi(f"Kayıt görüntüsü yazılamadı: {e} {ayrinti}".strip())
                break

    def _parcayi_kapat(self, surec, video_is, parca) -> None:
        """Görüntü parçasını bitirir. Hiç kare yazılmadıysa (hemen duraklatıldıysa) parça silinir."""
        if video_is is not None:
            video_is.join(timeout=10)
        try:
            surec.stdin.close()
        except Exception:
            pass
        try:
            surec.wait(timeout=30)
        except subprocess.TimeoutExpired:
            surec.kill()
        if parca is not None and parca["kare"] == 0:
            try:
                parca["yol"].unlink(missing_ok=True)
            except OSError:
                pass

    def _ses_dongu(self) -> None:
        dosya = self._ses_dosyasi
        yazilabilir = True
        while True:
            blok = self._sesler.get()
            if blok is None:
                break
            if not yazilabilir:
                continue
            try:
                dosya.write((np.clip(blok, -1.0, 1.0) * 32767).astype("<i2").tobytes())
                self._ses_yazildi = True
            except OSError as e:
                yazilabilir = False
                self._yazma_hatasi(f"Kayıt sesi yazılamadı (disk dolu olabilir): {e}")

    def durdur(self, bitti=None) -> None:
        """Kaydı bitirir; birleştirme arka planda yapılır, bitince bitti(dosya_yolu|None, hata) çağrılır."""
        with self._kilit:
            if not self._kayitta:
                return
            self._kayitta = False
            self._duraklatildi = False
            surec, video_is, kareler, parca = self._surec, self._video_is, self._kareler, self._parca
            self._surec = self._video_is = self._parca = None
            ses_is, kapananlar = self._ses_is, list(self._kapananlar)
        if surec is not None:
            kareler.put(None)
        self._sesler.put(None)
        threading.Thread(target=self._bitir, args=(surec, video_is, parca, ses_is, kapananlar, bitti),
                         name="kayit-bitir", daemon=True).start()

    def _bitir(self, surec, video_is, parca, ses_is, kapananlar, bitti) -> None:
        hata = ""
        tamam = False
        try:
            for is_ in kapananlar:
                is_.join(timeout=45)
            if surec is not None:
                self._parcayi_kapat(surec, video_is, parca)
            ses_is.join(timeout=10)
            try:
                self._ses_dosyasi.close()
            except OSError:
                pass
            if self.atlanan_kare or self.atlanan_ses:
                log.warning("Kayıtta %d kare ve %d ses bloğu atlandı (bilgisayar yetişemedi)",
                            self.atlanan_kare, self.atlanan_ses)
            parcalar = [v for v in self._parcalar if v.exists() and v.stat().st_size > 0]
            if not parcalar:
                hata = self.son_hata or "Görüntü kaydedilemedi"
            else:
                tamam, ayrinti = _birlestir(self.ffmpeg, parcalar,
                                            self._gecici_ses if self._ses_yazildi else None, self._hedef)
                if not tamam and self._ses_yazildi:
                    log.warning("Ses birleştirilemedi: %s", ayrinti)
                    tamam, ayrinti = _birlestir(self.ffmpeg, parcalar, None, self._hedef)
                    hata = "Ses eklenemedi; sadece görüntü kaydedildi" if tamam else ""
                if not tamam:
                    hata = f"Kayıt dosyası oluşturulamadı: {ayrinti}"
                elif self.son_hata and not hata:
                    hata = self.son_hata   # yarıda kesildi ama o ana kadarki kısım kaydedildi
        except Exception as e:
            log.exception("Kayıt bitirilirken hata")
            hata = f"Kayıt bitirilemedi: {e}"
        finally:
            if tamam:   # başarısızsa geçici dosyalar kalır, bir sonraki açılışta yeniden denenir
                for f in (*self._parcalar, self._gecici_ses):
                    try:
                        f.unlink(missing_ok=True)
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
