"""Video hattı: kaynak -> birleştirme -> çıkışlar.

Ayrı bir iş parçacığında sabit FPS ile döner:
  1) aktif sahne ekran istiyorsa ekranı yakala ve 1280x720'ye sığdır
  2) aktif sahne kamera istiyorsa webcam'in son karesini al
  3) sahneyi kur (scenes/), sahne değiştiyse yumuşak geçiş uygula
  4) sanal kameraya gönder, son kareyi önizleme için sakla

Arayüz bu iş parçacığını asla beklemez; sadece son_kare() ile en son kareyi alır.
Sanal kamerayı açıp kapatma istekleri de bu iş parçacığında işlenir, böylece
kamera başka bir iş parçacığından kapatılırken kare gönderilmez.
"""

import logging
import threading
import time

from capture.region import BolgeSecimi, uygula as bolge_uygula
from core import frames
from core.state import DurumDeposu
from outputs.virtualcam import SanalKameraYok
from scenes.scene_manager import KameraYerlesimi, Sahne, SahneYoneticisi, sahne_karesi

log = logging.getLogger(__name__)


class VideoHatti:
    def __init__(self, depo: DurumDeposu, kaynak, cikis, genislik=1280, yukseklik=720, fps=30,
                 imlec_goster: bool = True, kamera=None, sahneler: SahneYoneticisi | None = None,
                 kamera_yerlesimi: KameraYerlesimi | None = None, bekleme_metni: str = "Birazdan döneceğim",
                 kamera_acik: bool = True, bolge: BolgeSecimi | None = None, cizimler=None,
                 imlec_vurgusu: bool = False, bekleme_gorseli: str = ""):
        self.depo = depo
        self.kaynak = kaynak
        self.cikis = cikis
        self.kamera = kamera  # WebcamKaynagi ya da None
        self.bolge = bolge or BolgeSecimi()  # F6 kare seçme / yakınlaştırma / vurgulama
        self.cizimler = cizimler             # overlay.drawing.CizimDeposu ya da None
        self.imlec_vurgusu = imlec_vurgusu   # imlecin etrafında halka + tıklama dalgası
        self.bekleme_gorseli = bekleme_gorseli   # resim ya da kısa video
        from core.standby import BeklemeVideosu
        self._bekleme_videosu = BeklemeVideosu()
        self.panik = False                   # Panik tuşu: anında bekleme ekranı
        self.kayitci = None                  # core.recorder.Kayitci (yerel MP4 kayıt)
        # Ana pencerenin önizlemesi ekranda mı? Değilse ve yayın/kayıt da yoksa webcam'e
        # dokunulmaz (uygulama arka planda beklerken kamera ışığı yanmasın).
        self.onizleme_gorunur = True
        from core.logging_setup import SeyrekHata
        self._seyrek_hata = SeyrekHata(log)
        from overlay.cursor import ImlecVurgusu
        self._vurgu = ImlecVurgusu()
        self.sahneler = sahneler or SahneYoneticisi([Sahne("Sadece ekran", ekran=True)])
        self.kamera_yerlesimi = kamera_yerlesimi or KameraYerlesimi()
        self.bekleme_metni = bekleme_metni
        self.genislik, self.yukseklik, self.fps = genislik, yukseklik, fps
        self.imlec_goster = imlec_goster
        self._kamera_istegi = kamera_acik and kamera is not None
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
        if self.kamera is not None:
            self.kamera.durdur(bekle=True)
        self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı", ekran_kaynagi="kapalı", webcam="kapalı")

    def cikisi_ayarla(self, acik: bool) -> None:
        self._cikis_istegi = acik

    def kamerayi_ayarla(self, acik: bool) -> None:
        """Webcam'i aç/kapat (F10). Kapalıyken cihaz bırakılır, ışığı söner."""
        self._kamera_istegi = acik and self.kamera is not None

    @property
    def kamera_istegi(self) -> bool:
        return self._kamera_istegi

    def sahne_sec(self, indeks: int) -> bool:
        return self.sahneler.sec(indeks)

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
                log.warning("Sanal kamera açılamadı: %s", e)
                self._cikis_istegi = False
                self.depo.guncelle(cikis_acik=False, sanal_kamera="yok",
                                   son_hata=str(e) or "OBS Virtual Camera bulunamadı. OBS'yi kurup sanal kamerayı "
                                                      "bir kez başlat.")
            except Exception as e:
                log.exception("Sanal kamera açılamadı")
                self._cikis_istegi = False
                self.depo.guncelle(cikis_acik=False, sanal_kamera="hata", son_hata=f"Sanal kamera açılamadı: {e}")
        else:
            self.cikis.kapat()
            self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı")

    def _ekran_karesi(self):
        ham = self.kaynak.grab()
        if ham is None:
            self.depo.guncelle(ekran_kaynagi="koptu", yakalama_yontemi="")
            return None
        self.depo.guncelle(ekran_kaynagi="çalışıyor", yakalama_yontemi=self.kaynak.yontem)
        kare, donusum = bolge_uygula(ham, self.bolge.gorunum(), self.genislik, self.yukseklik,
                                     self.bolge.karartma_gucu)
        if self.cizimler is not None:
            from overlay.drawing import cizimleri_uygula
            kare = cizimleri_uygula(kare, self.cizimler, ham.shape[1], ham.shape[0], donusum)
        if self.imlec_goster or self.imlec_vurgusu:
            konum = getattr(self.kaynak, "imlec", lambda: None)()
            cikis_konumu = None
            if konum is not None:
                x, y = donusum(*konum)
                if -30 < x < self.genislik and -30 < y < self.yukseklik:
                    cikis_konumu = (x, y)
            if self.imlec_vurgusu:
                self._vurgu.guncelle(konum)
            if cikis_konumu is not None or (self.imlec_vurgusu and self._vurgu._dalgalar):
                if kare is ham:  # aynı boyuttaysa kopyalanmamıştır; yakalayıcının önbelleğini bozma
                    kare = kare.copy()
                if self.imlec_vurgusu:
                    olcek = donusum(1, 0)[0] - donusum(0, 0)[0]
                    self._vurgu.ciz(kare, cikis_konumu, donusum, max(0.3, olcek * ham.shape[0] / 1080))
                if self.imlec_goster and cikis_konumu is not None:
                    frames.imlec_ciz(kare, *cikis_konumu)
        return kare

    def _kamera_karesi(self, sahne: Sahne):
        """Webcam'i sadece gerektiğinde açık tutar; son karesini (ya da None) döndürür."""
        if self.kamera is None:
            return None
        kullaniliyor = (self._cikis_istegi or self.onizleme_gorunur
                        or (self.kayitci is not None and self.kayitci.kayitta))
        gerekli = self._kamera_istegi and sahne.kamera is not None and kullaniliyor
        if gerekli and not self.kamera.acik:
            self.kamera.baslat()
        elif not gerekli and self.kamera.acik:
            self.kamera.durdur()
        if not self._kamera_istegi:
            self.depo.guncelle(webcam="kapalı")
            return None
        if not gerekli:
            # açık ama şu an kullanılmıyor (bu sahnede yok ya da uygulama arka planda)
            self.depo.guncelle(webcam="açık" if kullaniliyor else "beklemede")
            return None
        kare = self.kamera.son_kare()
        if kare is not None:
            self.depo.guncelle(webcam="açık")
        elif self.kamera.son_hata:
            self.depo.guncelle(webcam="yok")
        return kare

    def _bekleme(self):
        from core.standby import video_mu
        if video_mu(self.bekleme_gorseli):
            kare = self._bekleme_videosu.kare(self.bekleme_gorseli, self.genislik, self.yukseklik)
            if kare is not None:
                return kare
            return frames.bilgi_karesi(self.genislik, self.yukseklik, self.bekleme_metni)
        if self._bekleme_videosu._cap is not None:
            self._bekleme_videosu.kapat()
        return frames.bekleme_karesi(self.genislik, self.yukseklik, self.bekleme_metni, self.bekleme_gorseli)

    def _kare_uret(self):
        if self.panik:
            # Panik: hiçbir kaynağa dokunmadan, geçiş beklemeden bekleme ekranı
            return self._bekleme()
        sahne = self.sahneler.aktif
        self.depo.guncelle(aktif_sahne=self.sahneler.indeks, sahne_adi=sahne.ad)
        ekran = self._ekran_karesi() if sahne.ekran else None
        kamera = self._kamera_karesi(sahne)
        kare = sahne_karesi(sahne, self.genislik, self.yukseklik, ekran, kamera,
                            self._kamera_istegi, self.kamera_yerlesimi, self.bekleme_metni,
                            bekleme=self._bekleme)
        with self._kilit:
            onceki = self._son_kare
        return self.sahneler.gecis_uygula(kare, onceki)

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
                if self.kayitci is not None and self.kayitci.kayitta:
                    self.kayitci.kare_yaz(kare)
                with self._kilit:
                    self._son_kare = kare
            except Exception:
                # Hiçbir hata hattı durdurmamalı; logla ve devam et (her karede değil, seyrek).
                self._seyrek_hata.yaz("Video hattında hata")
            is_suresi += time.perf_counter() - t0
            sayac += 1

            simdi = time.perf_counter()
            if simdi - rapor_zamani >= 1.0:
                self.depo.guncelle(fps=round(sayac / (simdi - rapor_zamani), 1),
                                   kare_suresi_ms=round(1000 * is_suresi / sayac, 1),
                                   kayit_suresi=self.kayitci.sure if self.kayitci is not None else 0)
                sayac, is_suresi, rapor_zamani = 0, 0.0, simdi

            sonraki += aralik
            bekle = sonraki - time.perf_counter()
            if bekle > 0:
                time.sleep(bekle)
            else:
                sonraki = time.perf_counter()  # geride kaldıysak yetişmeye çalışma, saati sıfırla
