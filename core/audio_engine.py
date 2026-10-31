"""Ses motoru: ses cihazlarını açar, mikserle bağlar, koparsa yeniden bağlanır.

  Mikrofon (seçilen cihaz, MME)                 ┐
  Bilgisayar sesi (Process Loopback ya da       ├─> SesKaristirici ─> "CABLE Input" (VB-Cable)
               hoparlör loopback)               ┘                     = Zoom'da "CABLE Output" mikrofonu

Aşama 0'dan çıkan dersler:
  - Windows'un varsayılan mikrofonuna güvenme: o CABLE ise kendi sesimizi geri
    alırız (gürültü). Mikrofonu kendimiz seçeriz, CABLE'ı asla mikrofon yapmayız.
  - Bilgisayar sesinde Zoom/Discord'u hariç tutarız ki karşı taraf yankı duymasın.

Denetçi iş parçacığı saniyede bir her şeyin çalıştığını kontrol eder; bir cihaz
çıkarılırsa uygulama çökmez, o kaynak "yok" görünür ve yeniden bağlanmaya çalışılır.
"""

import logging
import threading
import time

import numpy as np

from core.audio_mixer import KANAL, ORNEKLEME, SesKaristirici
from core.state import DurumDeposu

log = logging.getLogger(__name__)

BLOK = 480  # 10 ms
KABLO_ADI = "CABLE Input"
VARSAYILAN_HARIC = ["Zoom.exe", "Discord.exe", "ms-teams.exe", "Teams.exe", "Skype.exe"]


def _kablo_mu(ad: str) -> bool:
    return "cable" in ad.lower()


class _Akis:
    """Bir PyAudio akışı + son geri çağrı zamanı (cihaz koptu mu anlamak için)."""

    def __init__(self):
        self.akis = None
        self.son = 0.0

    @property
    def acik(self) -> bool:
        return self.akis is not None

    def saglikli(self, zaman_asimi: float = 1.5) -> bool:
        if self.akis is None:
            return False
        try:
            if not self.akis.is_active():
                return False
        except Exception:
            return False
        return time.monotonic() - self.son < zaman_asimi

    def kapat(self) -> None:
        if self.akis is not None:
            try:
                self.akis.stop_stream()
                self.akis.close()
            except Exception:
                pass
        self.akis = None


class SesMotoru:
    def __init__(self, depo: DurumDeposu, karistirici: SesKaristirici, mikrofon_adi: str = "",
                 sistem_modu: str = "auto", haric_uygulamalar=None, dahil_uygulama: str = ""):
        """sistem_modu:
             "auto"  : haric_uygulamalar'dan çalışan ilki hariç tüm bilgisayar sesi (yankı olmaz)
             "all"   : hoparlörden çıkan her şey (eski yöntem, Windows 10 eski sürümler için)
             "app"   : sadece dahil_uygulama'nın sesi (ör. bir oyun)
        """
        self.depo = depo
        self.mikser = karistirici
        self.mikrofon_adi = mikrofon_adi
        self.sistem_modu = sistem_modu if sistem_modu in ("auto", "all", "app") else "auto"
        self.haric_uygulamalar = list(haric_uygulamalar if haric_uygulamalar is not None else VARSAYILAN_HARIC)
        self.dahil_uygulama = dahil_uygulama

        self._pa = None
        self._kablo = _Akis()
        self._mik = _Akis()
        self._hoparlor = _Akis()        # "all" modu
        self._surec = None              # SurecSesi ("auto"/"app" modu)
        self._surec_hedef = None        # (pid, haric)
        self._surec_kontrol = 0.0
        self._mik_denendi = False       # mikrofon yoksa sürekli yeniden başlatıp sesi kesmeyelim
        self._yeniden_baslat = threading.Event()
        self._istek = False
        self._calis = threading.Event()
        self._is: threading.Thread | None = None
        self._cihaz_listesi: list[str] = []
        self._kilit = threading.Lock()

    # ---------------- dışarıdan

    def baslat(self) -> None:
        if self._is is not None:
            return
        self._calis.set()
        self._is = threading.Thread(target=self._denetci, name="ses-denetci", daemon=True)
        self._is.start()

    def durdur(self) -> None:
        self._istek = False
        self._calis.clear()
        if self._is is not None:
            self._is.join(timeout=5)
            self._is = None
        self._hepsini_kapat()
        self.depo.guncelle(sanal_mikrofon="kapalı")

    def ac(self, acik: bool) -> None:
        """Sesi VB-Cable'a göndermeye başla/durdur (Yayını başlat düğmesiyle birlikte)."""
        self._istek = acik

    @property
    def istek(self) -> bool:
        return self._istek

    def mikrofon_sec(self, ad: str) -> None:
        self.mikrofon_adi = ad
        self._mik_denendi = False
        self._yeniden_baslat.set()

    def sistem_ayarla(self, modu: str, dahil_uygulama: str | None = None) -> None:
        self.sistem_modu = modu if modu in ("auto", "all", "app") else "auto"
        if dahil_uygulama is not None:
            self.dahil_uygulama = dahil_uygulama
        self._yeniden_baslat.set()

    def yenile(self) -> None:
        """Cihaz listesini yeniden tara (yeni takılan mikrofon için)."""
        self._mik_denendi = False
        self._yeniden_baslat.set()

    def mikrofonlar(self) -> list[str]:
        """Seçilebilir mikrofonlar (CABLE hariç). Liste denetçi tarafından güncellenir."""
        with self._kilit:
            return list(self._cihaz_listesi)

    # ---------------- denetçi iş parçacığı

    def _denetci(self) -> None:
        while self._calis.is_set():
            try:
                if self._yeniden_baslat.is_set():
                    # cihaz/ayar değişti: her şeyi kapat, cihaz listesini baştan oku
                    self._yeniden_baslat.clear()
                    self._hepsini_kapat()
                if self._istek:
                    self._calistir()
                elif self._kablo.acik or self._mik.acik or self._surec or self._hoparlor.acik:
                    self._hepsini_kapat()
                    self.depo.guncelle(sanal_mikrofon="kapalı")
                elif self._pa is None:
                    self._pa_hazirla()  # kapalıyken de mikrofon listesini doldur
            except Exception:
                log.exception("Ses denetçisinde hata")
                self._hepsini_kapat()
            self._yeniden_baslat.wait(1.0)

    def _pa_hazirla(self) -> None:
        if self._pa is not None:
            return
        import pyaudiowpatch as pyaudio
        self._pa = pyaudio.PyAudio()
        liste = [d["name"] for d in self._mme_cihazlari(giris=True)
                 if not _kablo_mu(d["name"]) and "mapper" not in d["name"].lower()
                 and "eşleyici" not in d["name"].lower()]
        with self._kilit:
            self._cihaz_listesi = liste

    def _mme_cihazlari(self, giris: bool):
        p = self._pa
        sonuc = []
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            host = p.get_host_api_info_by_index(d["hostApi"])["name"]
            kanal = d["maxInputChannels"] if giris else d["maxOutputChannels"]
            if host == "MME" and kanal > 0:
                sonuc.append(d)
        return sonuc

    def _calistir(self) -> None:
        # Kopan akış varsa hepsini kapatıp Windows'un cihaz listesini baştan oku
        if (self._kablo.acik and not self._kablo.saglikli()) or (self._mik.acik and not self._mik.saglikli()):
            log.warning("Ses cihazı koptu; yeniden bağlanılıyor")
            self._mik_denendi = False
            self._hepsini_kapat()
        # Hoparlör sessizken Windows hiç veri vermeyebilir; sadece akışın kendisi durduysa kopmuş say.
        if self._hoparlor.acik and not self._hoparlor.saglikli(zaman_asimi=float("inf")):
            self._hoparlor.kapat()
            self._sistem_durumu("yok", "Hoparlör sesi koptu")
        if self._surec is not None and not self._surec.calisiyor:
            self._surec.durdur()
            self._surec, self._surec_hedef = None, None

        self._pa_hazirla()
        if not self._kablo.acik:
            if not self._kabloyu_ac():
                self._hepsini_kapat()
                time.sleep(4.0)  # VB-Cable kurulana kadar çok sık deneme
                return
        if not self._mik.acik and not self._mik_denendi:
            self._mikrofonu_ac()
        self._sistem_sesini_ayarla()

    def _kabloyu_ac(self) -> bool:
        import pyaudiowpatch as pyaudio
        kablo = next((d for d in self._mme_cihazlari(giris=False) if KABLO_ADI.lower() in d["name"].lower()), None)
        if kablo is None:
            self.depo.guncelle(sanal_mikrofon="yok",
                               ses_hatasi="VB-Cable bulunamadı. vb-audio.com/Cable'dan kurup bilgisayarı yeniden başlat.")
            return False

        def geri_cagri(in_data, frames, t, status):
            self._kablo.son = time.monotonic()
            try:
                return (self.mikser.karistir(frames).tobytes(), pyaudio.paContinue)
            except Exception:
                return (np.zeros((frames, KANAL), np.float32).tobytes(), pyaudio.paContinue)

        try:
            self._kablo.son = time.monotonic()
            self._kablo.akis = self._pa.open(format=pyaudio.paFloat32, channels=KANAL, rate=ORNEKLEME,
                                             output=True, output_device_index=kablo["index"],
                                             frames_per_buffer=BLOK, stream_callback=geri_cagri)
        except Exception as e:
            log.warning("CABLE Input açılamadı: %s", e)
            self.depo.guncelle(sanal_mikrofon="hata", ses_hatasi=f"VB-Cable açılamadı: {e}")
            return False
        log.info("Ses çıkışı: %s", kablo["name"])
        self.depo.guncelle(sanal_mikrofon="açık", ses_hatasi="")
        return True

    def _mikrofon_cihazi(self):
        cihazlar = [d for d in self._mme_cihazlari(giris=True)
                    if not _kablo_mu(d["name"]) and "mapper" not in d["name"].lower()
                    and "eşleyici" not in d["name"].lower()]
        if self.mikrofon_adi:
            if _kablo_mu(self.mikrofon_adi):
                return None, "CABLE mikrofon olarak seçilemez (kendi sesini geri alır). Gerçek mikrofonu seç."
            for d in cihazlar:
                if d["name"] == self.mikrofon_adi or d["name"].startswith(self.mikrofon_adi[:31]):
                    return d, ""
            return None, f"'{self.mikrofon_adi}' bulunamadı"
        # Seçim yoksa Windows varsayılanı; ama CABLE ise kullanma
        try:
            varsayilan = self._pa.get_default_input_device_info()
            if not _kablo_mu(varsayilan["name"]):
                for d in cihazlar:
                    if d["name"] == varsayilan["name"]:
                        return d, ""
        except Exception:
            pass
        if cihazlar:
            return cihazlar[0], ""
        return None, "Mikrofon bulunamadı"

    def _mikrofonu_ac(self) -> None:
        import pyaudiowpatch as pyaudio
        self._mik_denendi = True
        kanal = self.mikser.kanallar["mikrofon"]
        d, hata = self._mikrofon_cihazi()
        if d is None:
            kanal.bagli = False
            self.depo.guncelle(mikrofon="yok", mikrofon_adi="", ses_hatasi=hata)
            return

        def geri_cagri(in_data, frames, t, status):
            self._mik.son = time.monotonic()
            kanal.tampon.yaz(np.frombuffer(in_data, np.float32))
            return (None, pyaudio.paContinue)

        try:
            kanal.tampon.giris_hizi = ORNEKLEME
            kanal.tampon.temizle()
            self._mik.son = time.monotonic()
            self._mik.akis = self._pa.open(format=pyaudio.paFloat32, channels=1, rate=ORNEKLEME, input=True,
                                           input_device_index=d["index"], frames_per_buffer=BLOK,
                                           stream_callback=geri_cagri)
        except Exception as e:
            log.warning("Mikrofon açılamadı: %s", e)
            kanal.bagli = False
            self.depo.guncelle(mikrofon="yok", mikrofon_adi="", ses_hatasi=f"Mikrofon açılamadı: {e}")
            return
        kanal.bagli = True
        log.info("Mikrofon: %s", d["name"])
        self.depo.guncelle(mikrofon="açık", mikrofon_adi=d["name"])

    # ---- bilgisayar sesi

    def _sistem_durumu(self, durum: str, aciklama: str) -> None:
        self.depo.guncelle(sistem_sesi=durum, sistem_kaynagi=aciklama)

    def _istenen_surec_hedefi(self):
        """(pid, haric, açıklama) ya da None."""
        from capture.app_audio import kendi_pid, surec_bul
        if self.sistem_modu == "app":
            if not self.dahil_uygulama:
                return None, "Uygulama seçilmedi"
            pid = surec_bul(self.dahil_uygulama)
            if pid is None:
                return None, f"{self.dahil_uygulama} çalışmıyor"
            return (pid, False), f"Sadece {self.dahil_uygulama}"
        for ad in self.haric_uygulamalar:
            pid = surec_bul(ad)
            if pid is not None:
                return (pid, True), f"Tüm sesler ({ad} hariç)"
        return (kendi_pid(), True), "Tüm bilgisayar sesi"

    def _sistem_sesini_ayarla(self) -> None:
        kanal = self.mikser.kanallar["sistem"]
        if self.sistem_modu == "all":
            if self._surec is not None:
                self._surec.durdur()
                self._surec, self._surec_hedef = None, None
            if not self._hoparlor.acik:
                self._hoparlor_loopback_ac()
            return
        if self._hoparlor.acik:
            self._hoparlor.kapat()

        simdi = time.monotonic()
        if self._surec is not None and simdi - self._surec_kontrol < 3.0:
            return
        self._surec_kontrol = simdi
        hedef, aciklama = self._istenen_surec_hedefi()
        if hedef == self._surec_hedef and self._surec is not None:
            return
        if self._surec is not None:
            self._surec.durdur()
            self._surec, self._surec_hedef = None, None
        if hedef is None:
            kanal.bagli = False
            self._sistem_durumu("yok", aciklama)
            return

        from capture.app_audio import SurecSesi
        kanal.tampon.giris_hizi = ORNEKLEME
        kanal.tampon.temizle()
        surec = SurecSesi(hedef[0], hedef[1], kanal.tampon.yaz)
        if surec.baslat():
            self._surec, self._surec_hedef = surec, hedef
            kanal.bagli = True
            self._sistem_durumu("açık", aciklama)
        else:
            # Eski Windows sürümü vb.: hoparlör loopback'e geç
            log.warning("%s; hoparlör loopback kullanılacak", surec.hata)
            self.sistem_modu = "all"
            self._hoparlor_loopback_ac()

    def _hoparlor_loopback_ac(self) -> None:
        import pyaudiowpatch as pyaudio
        kanal = self.mikser.kanallar["sistem"]
        try:
            lb = self._pa.get_default_wasapi_loopback()
        except Exception as e:
            kanal.bagli = False
            self._sistem_durumu("yok", f"Hoparlör bulunamadı: {e}")
            return
        if _kablo_mu(lb["name"]):
            kanal.bagli = False
            self._sistem_durumu("yok", "Windows'ta varsayılan hoparlör CABLE olmuş; gerçek hoparlörü seç")
            return
        kanal_sayisi = lb["maxInputChannels"]

        def geri_cagri(in_data, frames, t, status):
            self._hoparlor.son = time.monotonic()
            kanal.tampon.yaz(np.frombuffer(in_data, np.float32).reshape(-1, kanal_sayisi))
            return (None, pyaudio.paContinue)

        try:
            kanal.tampon.giris_hizi = int(lb["defaultSampleRate"])
            kanal.tampon.temizle()
            self._hoparlor.son = time.monotonic()
            self._hoparlor.akis = self._pa.open(format=pyaudio.paFloat32, channels=kanal_sayisi,
                                                rate=int(lb["defaultSampleRate"]), input=True,
                                                input_device_index=lb["index"], frames_per_buffer=BLOK,
                                                stream_callback=geri_cagri)
        except Exception as e:
            kanal.bagli = False
            self._sistem_durumu("yok", f"Hoparlör sesi açılamadı: {e}")
            return
        kanal.bagli = True
        self._sistem_durumu("açık", "Hoparlörden çıkan tüm ses")

    def _hepsini_kapat(self) -> None:
        for a in (self._kablo, self._mik, self._hoparlor):
            a.kapat()
        if self._surec is not None:
            self._surec.durdur()
        self._surec, self._surec_hedef = None, None
        for k in self.mikser.kanallar.values():
            k.bagli = False
        self.mikser.sifirla()
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        self.depo.guncelle(mikrofon="kapalı", sistem_sesi="kapalı", mikrofon_adi="", sistem_kaynagi="")
