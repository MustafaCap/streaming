"""Video hattı: kaynak -> birleştirme -> çıkışlar.

Ayrı bir iş parçacığında sabit FPS ile döner:
  1) ekranı yakala (kaynak koparsa bilgi ekranı göster)
  2) 1280x720'ye sığdır (ileride: sahneler, kamera, çizimler burada eklenecek)
  3) sanal kameraya gönder
  4) son kareyi önizleme için sakla

Arayüz bu iş parçacığını asla beklemez; sadece son_kare() ile en son kareyi alır.
Sanal kamerayı açıp kapatma istekleri de bu iş parçacığında işlenir, böylece
kamera başka bir iş parçacığından kapatılırken kare gönderilmez.
"""

import logging
import threading
import time

from core import frames
from core.state import DurumDeposu
from outputs.virtualcam import SanalKameraYok

log = logging.getLogger(__name__)


class VideoHatti:
    def __init__(self, depo: DurumDeposu, kaynak, cikis, genislik=1280, yukseklik=720, fps=30):
        self.depo = depo
        self.kaynak = kaynak
        self.cikis = cikis
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self._son_kare = frames.siyah_kare(genislik, yukseklik)
        self._kilit = threading.Lock()
        self._cikis_istegi = False
        self._calisiyor = threading.Event()
        self._is_parcacigi: threading.Thread | None = None

    # ---- dışarıdan çağrılanlar (herhangi bir iş parçacığı) ----

    def baslat(self) -> None:
        if self._is_parcacigi is not None:
            return
        self._calisiyor.set()
        self._is_parcacigi = threading.Thread(target=self._dongu, name="video-hatti", daemon=True)
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self._calisiyor.clear()
        if self._is_parcacigi is not None:
            self._is_parcacigi.join(timeout=3)
            self._is_parcacigi = None
        self.cikis.kapat()
        self.kaynak.kapat()
        self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı", ekran_kaynagi="kapalı")

    def cikisi_ayarla(self, acik: bool) -> None:
        self._cikis_istegi = acik

    @property
    def cikis_istegi(self) -> bool:
        """Kullanıcının son isteği (henüz işlenmemiş olabilir); hızlı çift tıklamada doğru yönü verir."""
        return self._cikis_istegi

    def son_kare(self):
        with self._kilit:
            return self._son_kare

    # ---- video iş parçacığı ----

    def _cikis_istegini_isle(self) -> None:
        istek = self._cikis_istegi
        if istek == self.cikis.acik:
            return
        if istek:
            try:
                self.cikis.ac()
                self.depo.guncelle(cikis_acik=True, sanal_kamera="açık", son_hata="")
            except SanalKameraYok as e:
                log.warning("Sanal kamera bulunamadı: %s", e)
                self._cikis_istegi = False
                self.depo.guncelle(cikis_acik=False, sanal_kamera="yok",
                                   son_hata="OBS Virtual Camera bulunamadı. OBS'yi kurup sanal kamerayı bir kez başlat.")
            except Exception as e:
                log.exception("Sanal kamera açılamadı")
                self._cikis_istegi = False
                self.depo.guncelle(cikis_acik=False, sanal_kamera="hata", son_hata=f"Sanal kamera açılamadı: {e}")
        else:
            self.cikis.kapat()
            self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı")

    def _kare_uret(self):
        ham = self.kaynak.grab()
        if ham is None:
            self.depo.guncelle(ekran_kaynagi="koptu", yakalama_yontemi="")
            return frames.bilgi_karesi(self.genislik, self.yukseklik, "Ekran yakalanamiyor")
        self.depo.guncelle(ekran_kaynagi="çalışıyor", yakalama_yontemi=self.kaynak.yontem)
        return frames.sigdir(ham, self.genislik, self.yukseklik)

    def _dongu(self) -> None:
        aralik = 1.0 / self.fps
        sonraki = time.perf_counter()
        sayac, is_suresi, rapor_zamani = 0, 0.0, time.perf_counter()
        while self._calisiyor.is_set():
            t0 = time.perf_counter()
            try:
                self._cikis_istegini_isle()
                kare = self._kare_uret()
                if self.cikis.acik:
                    self.cikis.gonder(kare)
                with self._kilit:
                    self._son_kare = kare
            except Exception:
                # Hiçbir hata hattı durdurmamalı; logla ve devam et.
                log.exception("Video hattında hata")
            is_suresi += time.perf_counter() - t0
            sayac += 1

            simdi = time.perf_counter()
            if simdi - rapor_zamani >= 1.0:
                self.depo.guncelle(fps=round(sayac / (simdi - rapor_zamani), 1),
                                   kare_suresi_ms=round(1000 * is_suresi / sayac, 1))
                sayac, is_suresi, rapor_zamani = 0, 0.0, simdi

            sonraki += aralik
            bekle = sonraki - time.perf_counter()
            if bekle > 0:
                time.sleep(bekle)
            else:
                sonraki = time.perf_counter()  # geride kaldıysak yetişmeye çalışma, saati sıfırla
