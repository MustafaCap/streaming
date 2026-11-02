"""Anlık tekrar: son 15 saniye (ayarlardan 5 dakikaya kadar) bellekte durur, Ctrl+Shift+B ile MP4 olarak kaydedilir.

  görüntü: video hattı her kareyi kare_yaz() ile verir -> kuyruk -> FFmpeg (stdin)
           FFmpeg sıkıştırılmış görüntüyü MPEG-TS olarak stdout'a yazar; diske hiçbir şey yazılmaz.
           TS paketleri anahtar karelerden (1 saniyede bir) parçalara bölünür, parçalar RAM'de
           tutulur. Süreyi aşan en eski parça atılır.
  ses    : mikser her 10 ms'lik bloğu ses_yaz() ile verir -> RAM'de 16 bit PCM halkası
  kaydet : seçilen parçalar ve ses geçici dosyaya yazılır, FFmpeg tek MP4'te birleştirir
           (görüntü yeniden kodlanmaz), geçici dosyalar silinir.

Kapalıyken FFmpeg çalışmaz ve hiç bellek kullanılmaz. Hiçbir ağ bağlantısı açılmaz.
Bellek: 1080p ekran görüntüsü için 2 dakika yaklaşık 50-150 MB görüntü + 23 MB ses.
"""

import collections
import logging
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from core.recorder import (KODLAYICI_AYARLARI, SES_HIZI, SES_KANALI, _PENCERESIZ, _gizle, ffmpeg_bul,
                           ffmpeg_girdi_bicimi, ffmpeg_karesi, kodlayici_sec, varsayilan_klasor)

log = logging.getLogger(__name__)

# 2.0.3: varsayılan 2 dk -> 15 sn (daha az bellek; oyun oynarken bilgisayarı yormasın)
VARSAYILAN_SURE = 15
EN_KISA, EN_UZUN = 15, 300
TS = 188
PAT_PID = 0


def sureyi_sinirla(sn) -> int:
    try:
        sn = int(sn)
    except (TypeError, ValueError):
        return VARSAYILAN_SURE
    return max(EN_KISA, min(EN_UZUN, sn))


def sure_etiketi(sn) -> str:
    """120 -> "Son 2 dk", 90 -> "Son 90 sn" (düğme ve bildirim metinleri için)."""
    sn = sureyi_sinirla(sn)
    return f"Son {sn // 60} dk" if sn % 60 == 0 else f"Son {sn} sn"


def dosya_adi(zaman: datetime | None = None) -> str:
    return (zaman or datetime.now()).strftime("Tekrar_%Y-%m-%d_%H-%M-%S.mp4")


def bos_hedef(klasor: Path, ad: str) -> Path:
    """Aynı saniyede ikinci tekrar kaydedilirse öncekinin üstüne yazılmasın: Tekrar_..~2.mp4"""
    hedef = Path(klasor) / ad
    sira = 2
    while hedef.exists():
        hedef = hedef.with_name(f"{Path(ad).stem}~{sira}{Path(ad).suffix}")
        sira += 1
    return hedef


def artik_dosyalari_sil(klasor, en_az_yas_sn: float = 120) -> int:
    """Kaydederken uygulama kapanırsa kalan gizli geçici dosyaları (.Tekrar_*.ts / .pcm) siler.
    Bunlar kurtarılamaz (tekrar zaten bellekteydi); sadece yer kaplarlar."""
    klasor = Path(klasor)
    if not klasor.is_dir():
        return 0
    silinen = 0
    simdi = time.time()
    for f in klasor.glob(".Tekrar_*"):
        if f.suffix not in (".ts", ".pcm") or not f.is_file():
            continue
        try:
            if simdi - f.stat().st_mtime >= en_az_yas_sn:
                f.unlink()
                silinen += 1
        except OSError:
            pass
    return silinen


def _pts(paket: bytes, bas: int) -> int | None:
    """PES başlığındaki PTS (90 kHz). bas: yük başlangıcı."""
    pes = paket[bas:]
    if len(pes) < 14 or pes[0:3] != b"\x00\x00\x01" or not (pes[7] & 0x80):
        return None
    p = pes[9:14]
    return (((p[0] >> 1) & 0x07) << 30) | (p[1] << 22) | ((p[2] >> 1) << 15) | (p[3] << 7) | (p[4] >> 1)


class TsParcalayici:
    """MPEG-TS akışını anahtar karede başlayan parçalara böler.

    parca_bitti(baslangic_pts, bytes) her yeni anahtar karede bir önceki parça için çağrılır.
    PAT/PMT paketleri (akışın başlığı) ayrıca saklanır; kayıtta her dosyanın başına eklenir.
    """

    def __init__(self, parca_bitti):
        self.parca_bitti = parca_bitti
        self.baslik = bytearray()       # ilk PAT + PMT
        self._pmt_pid = None
        self._video_pid = None
        self._artik = b""
        self._parca = None              # bytearray (ilk anahtar kareden önce None)
        self._parca_pts = None

    def besle(self, veri: bytes) -> None:
        veri = self._artik + veri
        n = len(veri) - len(veri) % TS
        self._artik = veri[n:]
        for i in range(0, n, TS):
            self._paket(veri[i:i + TS])

    def _paket(self, p: bytes) -> None:
        if p[0] != 0x47:
            return
        pid = ((p[1] & 0x1F) << 8) | p[2]
        pusi = bool(p[1] & 0x40)
        af = (p[3] >> 4) & 0x3
        bas = 4
        rai = False
        if af in (2, 3):
            uzunluk = p[4]
            if uzunluk > 0:
                rai = bool(p[5] & 0x40)
            bas = 5 + uzunluk
        if pid == PAT_PID:
            if self._pmt_pid is None and pusi and len(p) > bas + 13:
                tablo = p[bas + 1 + p[bas]:]   # pointer_field atla
                self._pmt_pid = ((tablo[10] & 0x1F) << 8) | tablo[11]
                self.baslik += p
            return
        if pid == self._pmt_pid:
            if len(self.baslik) == TS:
                self.baslik += p
            return
        if self._video_pid is None and pusi and p[bas:bas + 4] == b"\x00\x00\x01\xe0":
            self._video_pid = pid
        if pid != self._video_pid:
            return
        if pusi and rai:
            pts = _pts(p, bas)
            if self._parca is not None and self._parca_pts is not None:
                self.parca_bitti(self._parca_pts, bytes(self._parca))
            self._parca = bytearray()
            self._parca_pts = pts
        if self._parca is not None:
            self._parca += p


class AnlikTekrar:
    def __init__(self, genislik: int, yukseklik: int, fps: int, sure_sn: int = VARSAYILAN_SURE,
                 kodlayici: str = "auto", ffmpeg: str | None = None):
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, max(1, int(fps))
        self.sure_sn = sureyi_sinirla(sure_sn)
        self.kodlayici_tercihi = kodlayici
        self.ffmpeg = ffmpeg
        self.son_hata = ""
        self._kilit = threading.Lock()
        self._surec: subprocess.Popen | None = None
        self._acik = False
        self._kaydediliyor = False
        self._bosalt()

    def _bosalt(self) -> None:
        self._kareler: queue.Queue = queue.Queue(maxsize=max(4, self.fps // 2))
        self._parcalar: collections.deque = collections.deque()   # (duvar_saati, bytes)
        self._sesler: collections.deque = collections.deque()     # (duvar_saati, int16 bytes)
        self._kare_zamanlari: collections.deque = collections.deque(maxlen=self.fps * 20)
        self._yazilan = 0
        self._ilk_pts = None
        self._ts = TsParcalayici(self._parca_geldi)

    # ---- durum

    @property
    def acik(self) -> bool:
        return self._acik

    @property
    def kaydediliyor(self) -> bool:
        return self._kaydediliyor

    @property
    def bellek(self) -> int:
        """Kullanılan yaklaşık bellek (bayt)."""
        with self._kilit:
            return sum(len(b) for _, b in self._parcalar) + sum(len(b) for _, b in self._sesler)

    @property
    def tutulan_sure(self) -> float:
        with self._kilit:
            if not self._parcalar:
                return 0.0
            return max(0.0, time.monotonic() - self._parcalar[0][0])

    # ---- aç / kapat

    def baslat(self) -> bool:
        with self._kilit:
            if self._acik:
                return True
            ffmpeg = self.ffmpeg or ffmpeg_bul()
            if not ffmpeg:
                self.son_hata = "FFmpeg bulunamadı"
                return False
            self.ffmpeg = ffmpeg
            kod = kodlayici_sec(ffmpeg, self.kodlayici_tercihi)
            bicim = ffmpeg_girdi_bicimi(self.genislik, self.yukseklik)
            komut = [ffmpeg, "-hide_banner", "-loglevel", "error",
                     "-f", "rawvideo", "-pix_fmt", bicim, "-s", f"{self.genislik}x{self.yukseklik}",
                     "-framerate", str(self.fps), "-i", "-",
                     "-pix_fmt", "nv12" if kod != "mpeg4" else "yuv420p", "-c:v", kod,
                     *KODLAYICI_AYARLARI.get(kod, []),
                     "-g", str(self.fps), "-bf", "0",             # her saniye anahtar kare, B kare yok
                     "-bsf:v", "dump_extra=freq=keyframe",        # her parça tek başına çözülebilsin
                     "-f", "mpegts", "-flush_packets", "1", "-"]
            try:
                self._surec = subprocess.Popen(komut, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.DEVNULL, creationflags=_PENCERESIZ)
            except Exception as e:
                self.son_hata = f"FFmpeg başlatılamadı: {e}"
                return False
            self._bosalt()
            self._acik = True
            self.son_hata = ""
            surec, kareler = self._surec, self._kareler
        threading.Thread(target=self._yaz_dongu, args=(surec, kareler, bicim), name="tekrar-yaz", daemon=True).start()
        threading.Thread(target=self._oku_dongu, args=(surec,), name="tekrar-oku", daemon=True).start()
        log.info("Anlık tekrar açık (%d sn, %s)", self.sure_sn, kod)
        return True

    def durdur(self) -> None:
        """Kapatır ve belleği boşaltır."""
        with self._kilit:
            if not self._acik:
                return
            self._acik = False
            surec, kareler = self._surec, self._kareler
            self._surec = None
            self._parcalar.clear()
            self._sesler.clear()
        try:
            kareler.put_nowait(None)
        except queue.Full:
            pass
        if surec is not None:
            try:
                surec.stdin.close()
            except Exception:
                pass
            try:
                surec.wait(timeout=3)
            except Exception:
                surec.kill()
        log.info("Anlık tekrar kapandı")

    def sure_ayarla(self, sn) -> None:
        self.sure_sn = sureyi_sinirla(sn)
        self._kirp(time.monotonic())

    # ---- besleme (beklemez)

    def kare_yaz(self, kare: np.ndarray) -> None:
        if not self._acik:
            return
        try:
            self._kareler.put_nowait(kare)
        except queue.Full:
            pass   # kodlayıcı yetişemedi: kare atlanır

    def ses_yaz(self, blok: np.ndarray) -> None:
        if not self._acik:
            return
        veri = (np.clip(blok, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        simdi = time.monotonic()
        with self._kilit:
            self._sesler.append((simdi, veri))
            esik = simdi - self.sure_sn - 5
            while self._sesler and self._sesler[0][0] < esik:
                self._sesler.popleft()

    # ---- iş parçacıkları

    def _yaz_dongu(self, surec, kareler, bicim="rgb24") -> None:
        while True:
            kare = kareler.get()
            if kare is None:
                break
            try:
                surec.stdin.write(ffmpeg_karesi(kare, bicim))
            except Exception as e:
                if self._acik:
                    self.son_hata = f"Anlık tekrar durdu: {e}"
                    log.warning(self.son_hata)
                break
            with self._kilit:
                self._kare_zamanlari.append((self._yazilan, time.monotonic()))
                self._yazilan += 1

    def _oku_dongu(self, surec) -> None:
        try:
            while True:
                veri = surec.stdout.read1(65536) if hasattr(surec.stdout, "read1") else surec.stdout.read(65536)
                if not veri:
                    break
                self._ts.besle(veri)
        except Exception:
            log.exception("Anlık tekrar akışı okunamadı")

    def _kare_zamani(self, pts) -> float:
        """Parçanın ilk karesinin hatta yazıldığı an (ses bununla hizalanır)."""
        with self._kilit:
            if pts is None or not self._kare_zamanlari:
                return time.monotonic()
            if self._ilk_pts is None:
                self._ilk_pts = pts
            indeks = round((pts - self._ilk_pts) * self.fps / 90000)
            for i, t in self._kare_zamanlari:
                if i >= indeks:
                    return t
            return self._kare_zamanlari[-1][1]

    def _parca_geldi(self, pts, veri: bytes) -> None:
        t = self._kare_zamani(pts)
        with self._kilit:
            if not self._acik:
                return
            self._parcalar.append((t, veri))
        self._kirp(time.monotonic())

    def _kirp(self, simdi: float) -> None:
        with self._kilit:
            esik = simdi - self.sure_sn
            # ikinci parça da eşikten eskiyse ilk parça gereksiz
            while len(self._parcalar) > 1 and self._parcalar[1][0] <= esik:
                self._parcalar.popleft()

    # ---- kaydet

    def kaydet(self, klasor=None, bitti=None) -> bool:
        """Arka planda MP4 yazar; bitince bitti(dosya|None, hata) çağrılır. False: kaydedecek bir şey yok."""
        with self._kilit:
            if not self._acik:
                self.son_hata = "Anlık tekrar kapalı"
                return False
            if self._kaydediliyor:
                self.son_hata = "Önceki tekrar hâlâ kaydediliyor"
                return False
            if not self._parcalar:
                self.son_hata = "Henüz kaydedilecek görüntü yok"
                return False
            simdi = time.monotonic()
            esik = simdi - self.sure_sn
            parcalar = [p for p in self._parcalar]
            while len(parcalar) > 1 and parcalar[1][0] <= esik:
                parcalar.pop(0)
            baslangic = parcalar[0][0]
            sesler = [(t, b) for t, b in self._sesler if t >= baslangic]
            baslik = bytes(self._ts.baslik)
            self._kaydediliyor = True
        klasor = Path(klasor) if klasor else varsayilan_klasor()
        threading.Thread(target=self._kaydet, args=(klasor, baslik, parcalar, sesler, baslangic, bitti),
                         name="tekrar-kaydet", daemon=True).start()
        return True

    def _kaydet(self, klasor: Path, baslik: bytes, parcalar, sesler, baslangic: float, bitti) -> None:
        hedef = bos_hedef(klasor, dosya_adi())
        video = klasor / f".{hedef.stem}.ts"
        ses = klasor / f".{hedef.stem}.pcm"
        hata = ""
        try:
            klasor.mkdir(parents=True, exist_ok=True)
            with open(video, "wb") as f:
                f.write(baslik)
                for _, b in parcalar:
                    f.write(b)
            _gizle(video)
            ses_var = self._sesi_yaz(ses, sesler, baslangic)
            hata = self._birlestir(video, ses if ses_var else None, hedef)
            if hata and ses_var:
                log.warning("Tekrar sesi eklenemedi: %s", hata)
                hata = self._birlestir(video, None, hedef)
        except Exception as e:
            log.exception("Anlık tekrar kaydedilemedi")
            hata = str(e)
        finally:
            for f in (video, ses):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
            self._kaydediliyor = False
        dosya = hedef if not hata and hedef.exists() else None
        if dosya:
            log.info("Anlık tekrar kaydedildi: %s", dosya)
        if bitti is not None:
            try:
                bitti(dosya, hata)
            except Exception:
                log.exception("Tekrar bitti geri çağrısında hata")

    @staticmethod
    def _sesi_yaz(yol: Path, sesler, baslangic: float) -> bool:
        """Sesi parçanın başladığı andan itibaren yazar; ses gelmeyen aralıklar sessizlikle dolar."""
        if not sesler:
            return False
        ornek_bayt = 2 * SES_KANALI
        yazilan = 0
        with open(yol, "wb") as f:
            for t, b in sesler:
                ornek = len(b) // ornek_bayt
                beklenen = int((t - baslangic) * SES_HIZI) - ornek   # bu blok başlamalıydı
                bosluk = beklenen - yazilan
                if bosluk > SES_HIZI // 10:          # 100 ms'den uzun boşluk: sessizlik ekle
                    f.write(bytes(bosluk * ornek_bayt))
                    yazilan += bosluk
                f.write(b)
                yazilan += ornek
        _gizle(yol)
        return yazilan > 0

    def _birlestir(self, video: Path, ses: Path | None, hedef: Path) -> str:
        komut = [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "mpegts", "-i", str(video)]
        if ses is not None:
            komut += ["-f", "s16le", "-ar", str(SES_HIZI), "-ac", str(SES_KANALI), "-i", str(ses),
                      "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k"]
        else:
            komut += ["-map", "0:v"]
        komut += ["-c:v", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(hedef)]
        try:
            sonuc = subprocess.run(komut, capture_output=True, timeout=600, creationflags=_PENCERESIZ)
        except Exception as e:
            return str(e)
        if sonuc.returncode != 0 or not hedef.exists() or hedef.stat().st_size == 0:
            try:
                hedef.unlink(missing_ok=True)
            except OSError:
                pass
            return sonuc.stderr.decode(errors="replace").strip()[-300:] or "FFmpeg hata verdi"
        return ""
