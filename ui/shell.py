"""Uygulama kabuğu: kısayolları, köşe bildirimlerini ve sistem tepsisini ana pencereye bağlar.

Kısayollar ayrı bir iş parçacığında yakalanır; komutlar ise her zaman Qt'nin
ana iş parçacığında çalıştırılır (sinyal ile taşınır). Böylece ileride kare
seçme ve kalem gibi pencere açan komutlar güvenle çalışır.
"""

import logging

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QSystemTrayIcon

from core.hotkeys import KisayolYoneticisi, gruplara_ayir, tus_metni
from ui.toast import Bildirim

log = logging.getLogger(__name__)


class UygulamaKabugu(QObject):
    _komut_sinyali = Signal(str)
    _bildirim_sinyali = Signal(str, str, object)
    _durum_sinyali = Signal(object)

    def __init__(self, app, pencere, komutlar, depo, hat, ayarlar, cizimler=None, ses=None):
        super().__init__()
        self.app, self.pencere, self.komutlar, self.depo, self.ayarlar = app, pencere, komutlar, depo, ayarlar
        self.hat, self.ses = hat, ses
        self._katman = None   # kaynak eklerken açılan basit bölge seçici
        komutlar.kaydet("bolge.sec", "Bölge seç / tam ekrana dön", self._bolge_sec)
        komutlar.kaydet("kaynak.sec", "Ne gösterilsin: tüm ekran ya da bir pencere", self._kaynak_sec)
        komutlar.kaydet("kaynak.ekran", "Tüm ekranı yakala", self._ekrana_don)
        komutlar.kaydet("kaynak.monitor", "Bir monitörün tamamını göster", self._monitor_sec)
        self._pencere_koptu = False
        self._komut_sinyali.connect(self._komutu_calistir)
        self._bildirim_sinyali.connect(self._bildirim_goster)
        self._durum_sinyali.connect(self._durumu_goster)

        self._tus_haritasini_kur()

        self.bildirim = Bildirim()
        komutlar.dinle(self._komut_bitti)

        self.kisayollar = KisayolYoneticisi(self._komut_sinyali.emit)
        self.kalem = None
        if cizimler is not None:
            from ui.drawing_overlay import KalemDenetleyici
            self.kalem = KalemDenetleyici(komutlar, depo, hat, cizimler, self.kisayollar, ayarlar,
                                          bildir=lambda m: self.bildir(m))

        self.tepsi = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            from ui.tray import Tepsi
            self.tepsi = Tepsi(komutlar, hat, depo, self.pencereyi_goster, self.cikmayi_onayla)
            self.tepsi.show()
        self._son_hata = ""
        self.pencere.tepsiye_kucul = self.tepsi is not None and ayarlar.al("ui.minimize_to_tray", True)
        self.pencere.tepsiye_kuculdu = self._tepsiye_kuculdu
        self._ilk_kuculme = True

        from ui.mini_bar import MiniCubuk
        self.mini = MiniCubuk(komutlar, hat, ayarlar)
        self.mini.ana_pencere_istendi.connect(self.pencereyi_goster)
        self.pencere.mini_moda_gec = self.mini_moda_gec
        self.pencere.ayarlari_ac = self.ayarlari_ac
        self.pencere.uygulamadan_cik = self.cikmayi_onayla
        self.pencere.pencere_sec = self._kaynak_icin_pencere_sec
        self.pencere.bolge_sec = self._kaynak_icin_bolge_sec
        self.pencere.bas_konus_degisti = self._bas_konus_anahtari
        depo.dinle(lambda eski, yeni: self._durum_sinyali.emit(yeni))
        komutlar.kaydet("pencere.mini", "Mini moda geç", lambda _: self.mini_moda_gec())
        komutlar.kaydet("kayit.klasor", "Kayıt klasörünü aç", self._kayit_klasoru)
        komutlar.kaydet("pencere.goster", "Ana pencereyi göster", lambda _: self.pencereyi_goster())
        self._durumu_goster(depo.durum)

    def _tus_haritasini_kur(self) -> None:
        """komut adı -> tuş (bildirimlerde 'Mikrofon kapandı · F8' yazmak için)."""
        self.tus_haritasi: dict[str, str] = {}
        for ayar in ("hotkeys", "pen_hotkeys"):
            for komut, tus in (self.ayarlar.al(ayar, {}) or {}).items():
                if tus:
                    self.tus_haritasi[komut] = tus_metni(tus)

    def baslat(self) -> None:
        self.kisayollar.baslat()
        self.kisayollar.grup_ayarla("genel", gruplara_ayir(self.ayarlar.al("hotkeys", {}), self.komutlar))
        QTimer.singleShot(800, self._basarisizlari_bildir)

    def durdur(self) -> None:
        if self.kalem is not None and self.kalem.acik:
            self.kalem.kapat()
        self.kisayollar.durdur()
        self._izi_gizle()
        self.mini.hide()
        if self.tepsi is not None:
            self.tepsi.hide()

    # ---- komutlar ve bildirimler

    @Slot(str)
    def _komutu_calistir(self, ad: str) -> None:
        self.komutlar.calistir(ad)

    def komut_gonder(self, ad: str) -> None:
        """Herhangi bir iş parçacığından komut çalıştırmak için (Qt ana iş parçacığına taşınır)."""
        self._komut_sinyali.emit(ad)

    def _komut_bitti(self, ad: str, mesaj) -> None:
        if ad == "kayit.ac_kapat" and self.depo.durum.kayit == "açık":
            # Kayıt kısayolla (başka bir uygulamadayken) başladıysa mini çubuk açılsın: kayıt
            # sürüyor, süre ve durdur düğmesi görünsün. Ana penceredeki düğmeyle başladıysa dokunma.
            if not (self.pencere.isVisible() and self.pencere.isActiveWindow()) and not self.mini.isVisible():
                self.mini_moda_gec()
        if mesaj:
            self._bildirim_sinyali.emit(str(mesaj), self.tus_haritasi.get(ad, ""), None)

    def bildir(self, mesaj: str, tus: str = "", eylem=None) -> None:
        """Herhangi bir iş parçacığından bildirim göstermek için. eylem: ("Aç", fn)."""
        self._bildirim_sinyali.emit(mesaj, tus, eylem)

    @Slot(str, str, object)
    def _bildirim_goster(self, mesaj: str, tus: str, eylem=None) -> None:
        # Eylemli bildirimler (kayıt kaydedildi · Klasörde göster) ayar kapalı olsa da gösterilir
        if eylem is not None or self.ayarlar.al("ui.toasts", True):
            self.bildirim.goster(mesaj, tus, eylem=eylem)

    def _basarisizlari_bildir(self) -> None:
        if self.kisayollar.basarisiz:
            tuslar = ", ".join(b.split(":", 1)[1] for b in self.kisayollar.basarisiz)
            self.bildirim.goster(f"Kısayol alınamadı: {tuslar}", eylem=("Ayarlar", lambda: self.ayarlari_ac("kisayollar")))

    @Slot(object)
    def _durumu_goster(self, d) -> None:
        koptu = d.kaynak_turu == "pencere" and d.ekran_kaynagi == "koptu"
        if koptu and not self._pencere_koptu:
            # Tüm ekrana kendiliğinden dönülmez: yayında başka bir şey görünmesin
            self.bildirim.goster("Seçilen pencere kapandı · Göster menüsünden yenisini seç")
        self._pencere_koptu = koptu
        if d.son_hata and d.son_hata != self._son_hata:
            self.bildirim.goster(d.son_hata)
        self._son_hata = d.son_hata
        if self.tepsi is not None:
            self.tepsi.durumu_goster(d)
        if self.mini.isVisible():
            self.mini.durumu_goster(d)

    # ---- F6 kare seçme

    # ---- kaynak: tüm ekran ya da tek pencere

    def _kaynak_sec(self, _):
        from capture.window import PencereKaynagi
        from core.platform_win import yakalamadan_gizle
        from ui.pencere_secici import PencereSecici
        secici = PencereSecici(self.pencere if self.pencere.isVisible() else None, ekran_satiri=False)
        yakalamadan_gizle(int(secici.winId()))   # seçim penceresi karşı tarafa gitmesin
        if not secici.exec() or secici.secilen is None:
            return None
        if secici.secilen == "ekran":
            return self._ekrana_don(None)
        hwnd, baslik = secici.secilen
        self._tam_ekrana_hazirla()
        self.hat.kaynagi_degistir(PencereKaynagi(hwnd, baslik))
        self._pencere_koptu = False
        self.depo.guncelle(kaynak_turu="pencere", kaynak_adi=baslik)
        return f"Sadece bu pencere gösteriliyor: {baslik}"

    def _monitor_sec(self, param):
        try:
            monitor = max(0, int(param or 0))
        except ValueError:
            return None
        from capture.screen import EkranKaynagi
        if self.depo.durum.kaynak_turu == "ekran" and monitor == int(self.ayarlar.al("video.monitor", 0)) \
                and not self.hat.bolge.aktif:
            return None
        self._tam_ekrana_hazirla()
        self.ayarlar.ayarla("video.monitor", monitor)
        self.hat.kaynagi_degistir(EkranKaynagi(monitor, self.ayarlar.al("video.capture_backend", "dxcam")))
        self.depo.guncelle(kaynak_turu="ekran", kaynak_adi="")
        return f"Ekran {monitor + 1} gösteriliyor"

    def _ekrana_don(self, _):
        if self.depo.durum.kaynak_turu == "ekran":
            return "Tüm ekran zaten gösteriliyor"
        from capture.screen import EkranKaynagi
        self.hat.kaynagi_degistir(EkranKaynagi(self.ayarlar.al("video.monitor", 0),
                                               self.ayarlar.al("video.capture_backend", "dxcam")))
        self.depo.guncelle(kaynak_turu="ekran", kaynak_adi="")
        return f"Ekran {int(self.ayarlar.al('video.monitor', 0)) + 1} gösteriliyor"

    def _tam_ekrana_hazirla(self) -> None:
        """Pencereye geçerken bölge ve kalem kapanır (ikisi de monitörün üstünde çalışır)."""
        if self.kalem is not None:
            self.kalem.hepsini_kapat()
        elif self.hat.bolge.aktif:
            self.hat.bolge.temizle()
            self.depo.guncelle(bolge="")

    def _bolge_sec(self, _):
        if self.kalem is None:
            return None
        return self.kalem.bolge_ac_kapat()

    def _izi_gizle(self) -> None:
        if self.kalem is not None and self.kalem._iz is not None:
            self.kalem._iz.hide()

    def _kayit_klasoru(self, _):
        from ui.klasor import kayit_klasorunu_ac
        return None if kayit_klasorunu_ac(self.ayarlar) else "Kayıt klasörü açılamadı"

    # ---- pencere / tepsi

    def mini_moda_gec(self) -> None:
        self.hat.mini_gorunur = True
        self.pencere.hide()
        self.mini.durumu_goster(self.depo.durum)
        self.mini.goster()

    def ayarlari_ac(self, sekme: str | None = None) -> None:
        from ui.settings_dialog import AyarlarPenceresi
        ebeveyn = self.pencere if self.pencere.isVisible() else None
        AyarlarPenceresi(self.ayarlar, self.hat, self.ses, self._ayarlar_degisti, ebeveyn, sekme=sekme).exec()

    # ---- kaynak ekleme yardımcıları (Kaynaklar paneli)

    def _kaynak_icin_pencere_sec(self):
        from ui.pencere_secici import PencereSecici
        secici = PencereSecici(self.pencere if self.pencere.isVisible() else None, ekran_satiri=False)
        if not secici.exec() or not isinstance(secici.secilen, tuple):
            return None
        return secici.secilen

    def _kaynak_icin_bolge_sec(self, geri_cagri) -> None:
        """Ekran bölgesi kaynağı: kutu çizilir, (monitör, oranlar, piksel boyutu) geri verilir."""
        from capture.screen import monitor_dikdortgeni
        from ui.region_overlay import BolgeKatmani, ekrani_bul
        if self._katman is not None:
            self._katman.close()
        monitor = int(self.ayarlar.al("video.monitor", 0))
        dikdortgen = monitor_dikdortgeni(monitor)
        katman = BolgeKatmani(ekrani_bul(dikdortgen))

        def secildi(oran, _mod):
            w, h = (dikdortgen[2], dikdortgen[3]) if dikdortgen else (1920, 1080)
            geri_cagri(monitor, oran, (round(oran[2] * w), round(oran[3] * h)))

        katman.secildi.connect(secildi)
        katman.baslat()
        self._kaynak_katmani = katman   # çöp toplayıcı silmesin

    def _bas_konus_anahtari(self, acik: bool) -> bool:
        """Bas-konuş anahtarı: tuş seçilmemişse Ayarlar > Kısayollar açılır."""
        tus = (self.ayarlar.al("hotkeys", {}) or {}).get("bas_konus", "")
        if acik and not tus:
            self.bildirim.goster("Önce bas-konuş tuşunu seç")
            self.ayarlari_ac("kisayollar")
            tus = (self.ayarlar.al("hotkeys", {}) or {}).get("bas_konus", "")
            if not tus:
                return False
            self.ayarlar.ayarla("audio.ptt", True)
        self._bas_konusu_uygula()
        return True

    def bas_konus_kur(self, bas_konus, degisti) -> None:
        self.bas_konus, self._bas_konus_degisti = bas_konus, degisti
        self._bas_konusu_uygula()

    def _bas_konusu_uygula(self) -> None:
        bk = getattr(self, "bas_konus", None)
        if bk is None:
            return
        tus = (self.ayarlar.al("hotkeys", {}) or {}).get("bas_konus", "")
        if not self.ayarlar.al("audio.ptt", False):
            tus = ""    # anahtar kapalı: tuş ayarlı olsa da mikrofon hep açık
        if not bk.ayarla(tus):
            self.bildirim.goster(f"Bas-konuş tuşu geçersiz: {tus}")
        self._bas_konus_degisti(bk.basili)  # tuş yoksa mikrofon kapısı açılır

    def _ayarlar_degisti(self) -> None:
        self._tus_haritasini_kur()
        self._bas_konusu_uygula()
        if hasattr(self.pencere, "ayarlar_degisti"):
            self.pencere.ayarlar_degisti()
        self.kisayollar.grup_ayarla("genel", gruplara_ayir(self.ayarlar.al("hotkeys", {}), self.komutlar))
        if self.kalem is not None and self.kalem.acik:
            self.kalem._kalem_tuslari(True)
        self.pencere.tepsiye_kucul = self.tepsi is not None and self.ayarlar.al("ui.minimize_to_tray", True)
        self.app.setQuitOnLastWindowClosed(not self.pencere.tepsiye_kucul)
        QTimer.singleShot(800, self._basarisizlari_bildir)

    def pencereyi_goster(self) -> None:
        self.mini.hide()
        self.hat.mini_gorunur = False
        self.pencere.showNormal()
        self.pencere.raise_()
        self.pencere.activateWindow()

    def _tepsiye_kuculdu(self) -> None:
        d = self.depo.durum
        if d.kayit == "açık":
            # Kayıt sürüyor: görünür kalsın, mini bardan durdurulsun.
            self.mini_moda_gec()
            self.bildirim.goster("Kayıt sürüyor · mini bardan durdurabilirsin")
            return
        if self._ilk_kuculme:
            self._ilk_kuculme = False
            self.bildirim.goster("RizeOn tepside çalışıyor · kısayollar açık, kamera kapalı", sure_ms=4000)

    def cikmayi_onayla(self) -> None:
        """Tepsi menüsü / ayarlardaki Çıkış: kayıt sürüyorsa önce sorar."""
        d = self.depo.durum
        if d.kayit == "açık":
            from PySide6.QtWidgets import QMessageBox
            cevap = QMessageBox.question(
                self.pencere if self.pencere.isVisible() else None, "Çıkış",
                "Kayıt sürüyor. Uygulama tamamen kapatılsın mı?\nKayıt durdurulup kaydedilir.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if cevap != QMessageBox.Yes:
                return
        self.cik()

    def cik(self) -> None:
        self.pencere.tepsiye_kucul = False
        self.pencere.close()
        self.app.quit()
