"""Video hattı: kaynak -> birleştirme -> çıkışlar.

Ayrı bir iş parçacığında sabit FPS ile döner:
  1) aktif sahne ekran istiyorsa ekranı yakala ve 1280x720'ye sığdır
  2) aktif sahne kamera istiyorsa webcam'in son karesini al
  3) sahneyi kur (scenes/), sahne değiştiyse yumuşak geçiş uygula
  4) sanal kameraya gönder, son kareyi önizleme için sakla

Arayüz bu iş parçacığını asla beklemez; sadece son_kare() ile en son kareyi alır.
Sanal kamerayı açıp kapatma istekleri de bu iş parçacığında işlenir, böylece
kamera başka bir iş parçacığından kapatılırken kare gönderilmez.

2.0.0'dan itibaren sanal kamera arka planda hep açık: uygulama açılınca başlar. Sürücü
yoksa ya da çalışırken koparsa birkaç saniyede bir yeniden denenir; durum DurumDeposu'na
yazılır, arayüz bildirim gösterir.
"""

import logging
import threading
import time

import numpy as np

from capture.region import BolgeSecimi, uygula as bolge_uygula
from core import frames
from core.state import DurumDeposu
from outputs.virtualcam import SanalKameraYok
from scenes.kaynaklar import EkKaynaklar
from scenes.scene_manager import KameraYerlesimi, Sahne, SahneYoneticisi, sahne_karesi

log = logging.getLogger(__name__)


class VideoHatti:
    CIKIS_YENIDEN_DENEME_SN = 5.0

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
        self.imlec_vurgusu = imlec_vurgusu   # eski genel ayar; 2.0.0'da sahnedeki "İmleç vurgusu" kaynağı
        self.bekleme_gorseli = bekleme_gorseli   # resim ya da kısa video
        from core.standby import BeklemeVideosu
        self._bekleme_videosu = BeklemeVideosu()
        self.panik = False                   # Panik tuşu: anında bekleme ekranı
        self.kayitci = None                  # core.recorder.Kayitci (yerel MP4 kayıt)
        self.tekrar = None                   # core.anlik_tekrar.AnlikTekrar (son 2 dk bellekte)
        # Ana pencere (simge durumunda olsa da) ya da mini bar açık mı? İkisi de kapalıysa (uygulama
        # tepside) ve kayıt yoksa webcam'e dokunulmaz: arka planda beklerken kamera ışığı yanmasın.
        self.onizleme_gorunur = True
        self.mini_gorunur = False
        self.ek = EkKaynaklar(genislik, yukseklik, fps)
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
        self._cikis_sonraki_deneme = 0.0
        self._bekleyen_kaynak = None         # kaynagi_degistir() ile gelen, sonraki karede geçilecek kaynak
        self._ekran_onbellek = None          # (ham kare, imza, çıkış karesi): ekran değişmediyse yeniden kullanılır
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
        with self._kilit:
            bekleyen, self._bekleyen_kaynak = self._bekleyen_kaynak, None
        if bekleyen is not None:
            bekleyen.kapat()
        if self.kamera is not None:
            self.kamera.durdur(bekle=True)
        self.ek.kapat()
        self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı", ekran_kaynagi="kapalı", webcam="kapalı")

    def kaynagi_degistir(self, yeni) -> None:
        """Ekran ya da pencere kaynağına geç. Geçiş video hattının kendi iş parçacığında, bir
        sonraki karede yapılır; eski kaynak orada kapatılır (yakalama ortasında kapanmasın)."""
        with self._kilit:
            onceki, self._bekleyen_kaynak = self._bekleyen_kaynak, yeni
        if onceki is not None:
            onceki.kapat()

    def _bekleyen_kaynaga_gec(self) -> None:
        with self._kilit:
            yeni, self._bekleyen_kaynak = self._bekleyen_kaynak, None
        if yeni is None:
            return
        eski, self.kaynak = self.kaynak, yeni
        try:
            eski.kapat()
        except Exception:
            log.exception("Eski görüntü kaynağı kapatılamadı")

    def cikisi_ayarla(self, acik: bool) -> None:
        self._cikis_istegi = acik
        self._cikis_sonraki_deneme = 0.0   # hemen dene

    def kamerayi_ayarla(self, acik: bool) -> None:
        """Webcam'i aç/kapat (F10). Kapalıyken cihaz bırakılır, ışığı söner."""
        self._kamera_istegi = acik and self.kamera is not None

    @property
    def kamera_istegi(self) -> bool:
        return self._kamera_istegi

    @property
    def kamera_sahnede(self) -> bool:
        """Aktif sahnede görünür bir kamera kaynağı var mı (yoksa Kamera düğmeleri devre dışı)."""
        try:
            return self.sahneler.aktif.kamera_var
        except Exception:
            return False

    @property
    def kamera_gorunur_acik(self) -> bool:
        """Kullanıcıya "kamera açık" gösterilecek mi: açık istenmiş VE bu sahnede kamera var."""
        return self._kamera_istegi and self.kamera_sahnede

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
            if time.monotonic() < self._cikis_sonraki_deneme:
                return   # açılamadı; birkaç saniye sonra yeniden denenir (OBS sonradan kurulabilir)
            try:
                self.cikis.ac()
                self.depo.guncelle(cikis_acik=True, sanal_kamera="açık", son_hata="")
            except SanalKameraYok as e:
                if self.depo.durum.sanal_kamera != "yok":
                    log.warning("Sanal kamera açılamadı: %s", e)
                self._cikis_sonraki_deneme = time.monotonic() + self.CIKIS_YENIDEN_DENEME_SN
                self.depo.guncelle(cikis_acik=False, sanal_kamera="yok",
                                   son_hata=str(e) or "OBS Virtual Camera bulunamadı. OBS'yi kurup sanal kamerayı "
                                                      "bir kez başlat.")
            except Exception as e:
                if self.depo.durum.sanal_kamera != "hata":
                    log.exception("Sanal kamera açılamadı")
                self._cikis_sonraki_deneme = time.monotonic() + self.CIKIS_YENIDEN_DENEME_SN
                self.depo.guncelle(cikis_acik=False, sanal_kamera="hata", son_hata=f"Sanal kamera açılamadı: {e}")
        else:
            self.cikis.kapat()
            self.depo.guncelle(cikis_acik=False, sanal_kamera="kapalı")

    def _gonder(self, kare) -> None:
        """Sanal kameraya gönder; çalışırken koparsa kapat, durumu yaz, sonra yeniden dene."""
        try:
            self.cikis.gonder(kare)
        except Exception as e:
            log.warning("Sanal kamera koptu: %s", e)
            try:
                self.cikis.kapat()
            except Exception:
                pass
            self._cikis_sonraki_deneme = time.monotonic() + self.CIKIS_YENIDEN_DENEME_SN
            self.depo.guncelle(cikis_acik=False, sanal_kamera="koptu", son_hata=f"Sanal kamera koptu: {e}")

    @property
    def kamera_kullaniliyor(self) -> bool:
        """Görüntü birine gösteriliyor mu: pencere ya da mini bar açık, ya da kayıt sürüyor."""
        return (self.onizleme_gorunur or self.mini_gorunur
                or (self.kayitci is not None and self.kayitci.kayitta))

    def _ekran_karesi(self, sahne: Sahne | None = None):
        """Ana ekranın çıkış boyutundaki karesi (salt okunur; üstüne yazılmaz) ya da None.

        Ekran değişmediyse (dxcam aynı kareyi verir), fare yerinde duruyorsa, çizim ve F6
        animasyonu yoksa bir önceki kare olduğu gibi döner: küçültme, imleç çizme ve kopyalama
        her karede baştan yapılmaz. Masaüstü dururken işlemcinin çoğu buradan kazanılır."""
        if self._bekleyen_kaynak is not None:
            self._bekleyen_kaynaga_gec()
        ham = self.kaynak.grab()
        if ham is None:
            self.depo.guncelle(ekran_kaynagi="koptu", yakalama_yontemi="")
            self._ekran_onbellek = None
            return None
        self.depo.guncelle(ekran_kaynagi="çalışıyor", yakalama_yontemi=self.kaynak.yontem)
        gorunum = self.bolge.gorunum()
        kalem = self.cizimler is not None and (sahne is None or sahne.kalem)
        cizim_imzasi = None
        if kalem:
            cizim_imzasi = self.cizimler.surum
            if not self.cizimler.bos and self.cizimler.anlik()[1]:
                cizim_imzasi = object()   # lazer izi her karede soluyor: önbellek kullanılmaz
        vurgu = self.imlec_vurgusu or (sahne is not None and sahne.imlec_vurgusu)
        imlec_iste = self.imlec_goster or vurgu
        konum = getattr(self.kaynak, "imlec", lambda: None)() if imlec_iste else None
        if vurgu:
            self._vurgu.guncelle(konum)
        dalga = vurgu and bool(self._vurgu._dalgalar)
        imza = (gorunum, self.bolge.karartma_gucu, cizim_imzasi, konum, vurgu, self.imlec_goster,
                self.genislik, self.yukseklik)
        onceki = self._ekran_onbellek
        if onceki is not None and onceki[0] is ham and onceki[1] == imza and not dalga:
            return onceki[2]

        kare, donusum = bolge_uygula(ham, gorunum, self.genislik, self.yukseklik, self.bolge.karartma_gucu)
        if kalem:
            from overlay.drawing import cizimleri_uygula
            kare = cizimleri_uygula(kare, self.cizimler, ham.shape[1], ham.shape[0], donusum)
        if imlec_iste:
            cikis_konumu = None
            if konum is not None:
                x, y = donusum(*konum)
                if -30 < x < self.genislik and -30 < y < self.yukseklik:
                    cikis_konumu = (x, y)
            if cikis_konumu is not None or dalga:
                if not kare.flags.writeable or np.may_share_memory(kare, ham):  # yakalayıcının karesini bozma
                    kare = kare.copy()
                if vurgu:
                    olcek = donusum(1, 0)[0] - donusum(0, 0)[0]
                    self._vurgu.ciz(kare, cikis_konumu, donusum, max(0.3, olcek * ham.shape[0] / 1080))
                if self.imlec_goster and cikis_konumu is not None:
                    frames.imlec_ciz(kare, *cikis_konumu)
        if kare.base is not None or kare is ham:
            kare = kare.view()   # yakalayıcının dizisini (ya da görünümünü) salt okunur yapmadan paylaş
        kare.setflags(write=False)
        # ham da tutulur: silinip aynı adrese yeni kare gelirse "aynı kare" sanılmasın
        self._ekran_onbellek = (ham, imza, kare)
        return kare

    def _kamera_karesi(self, sahne: Sahne):
        """Webcam'i sadece gerektiğinde açık tutar; son karesini (ya da None) döndürür."""
        if self.kamera is None:
            return None
        kullaniliyor = self.kamera_kullaniliyor
        gerekli = self._kamera_istegi and sahne.kamera is not None and kullaniliyor
        if gerekli and not self.kamera.acik:
            self.kamera.baslat()
        elif not gerekli and self.kamera.acik:
            self.kamera.durdur()
        if not self._kamera_istegi:
            self.depo.guncelle(webcam="kapalı")
            return None
        if not gerekli:
            # açık istendi ama şu an kullanılmıyor (bu sahnede yok ya da uygulama arka planda): cihaz kapalı
            self.depo.guncelle(webcam="beklemede")
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
        ekran = self._ekran_karesi(sahne) if sahne.ekran else None
        kamera = self._kamera_karesi(sahne)
        ek = self.ek.kareler(sahne, self._kamera_istegi, self.kamera_kullaniliyor)
        kare = sahne_karesi(sahne, self.genislik, self.yukseklik, ekran, kamera,
                            self._kamera_istegi, self.kamera_yerlesimi, self.bekleme_metni,
                            bekleme=self._bekleme, ek=ek)
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
                    self._gonder(kare)
                if self.kayitci is not None and self.kayitci.kayitta:
                    self.kayitci.kare_yaz(kare)
                if self.tekrar is not None and self.tekrar.acik:
                    self.tekrar.kare_yaz(kare)
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
