"""Uygulama kabuğu: kısayolları, köşe bildirimlerini ve sistem tepsisini ana pencereye bağlar.

Kısayollar ayrı bir iş parçacığında yakalanır; komutlar ise her zaman Qt'nin
ana iş parçacığında çalıştırılır (sinyal ile taşınır). Böylece ileride kare
seçme ve kalem gibi pencere açan komutlar güvenle çalışır.
"""

import logging

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QSystemTrayIcon

from core.hotkeys import KisayolYoneticisi, gruplara_ayir, tus_metni
from ui.toast import Bildirim, bildirim_rengi

log = logging.getLogger(__name__)


class UygulamaKabugu(QObject):
    _komut_sinyali = Signal(str)
    _bildirim_sinyali = Signal(str, str)
    _durum_sinyali = Signal(object)

    def __init__(self, app, pencere, komutlar, depo, hat, ayarlar, cizimler=None, ses=None):
        super().__init__()
        self.app, self.pencere, self.komutlar, self.depo, self.ayarlar = app, pencere, komutlar, depo, ayarlar
        self.hat, self.ses = hat, ses
        self._katman = None
        self._iz = None   # yakınlaştırılan karenin ekrandaki yerini gösteren çerçeve
        komutlar.kaydet("bolge.sec", "Kare seç / tam ekrana dön", self._bolge_sec)
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
            self.kalem = KalemDenetleyici(komutlar, depo, hat, cizimler, self.kisayollar, ayarlar)

        self.tepsi = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            from ui.tray import Tepsi
            self.tepsi = Tepsi(komutlar, hat, depo, self.pencereyi_goster, self.cikmayi_onayla)
            self.tepsi.show()
        self.pencere.tepsiye_kucul = self.tepsi is not None and ayarlar.al("ui.minimize_to_tray", True)
        self.pencere.tepsiye_kuculdu = self._tepsiye_kuculdu
        self._ilk_kuculme = True

        from ui.mini_bar import MiniCubuk
        self.mini = MiniCubuk(komutlar, hat, ayarlar)
        self.mini.ana_pencere_istendi.connect(self.pencereyi_goster)
        self.pencere.mini_moda_gec = self.mini_moda_gec
        self.pencere.ayarlari_ac = self.ayarlari_ac
        self.pencere.uygulamadan_cik = self.cikmayi_onayla
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
            self._bildirim_sinyali.emit(str(mesaj), self.tus_haritasi.get(ad, ""))

    def bildir(self, mesaj: str, tus: str = "") -> None:
        """Herhangi bir iş parçacığından bildirim göstermek için."""
        self._bildirim_sinyali.emit(mesaj, tus)

    @Slot(str, str)
    def _bildirim_goster(self, mesaj: str, tus: str) -> None:
        if self.ayarlar.al("ui.toasts", True):
            self.bildirim.goster(mesaj, tus, bildirim_rengi(mesaj))

    def _basarisizlari_bildir(self) -> None:
        if self.kisayollar.basarisiz:
            tuslar = ", ".join(b.split(":", 1)[1] for b in self.kisayollar.basarisiz)
            self.bildirim.goster(f"Kısayol alınamadı: {tuslar}", "", bildirim_rengi("kapalı"))

    @Slot(object)
    def _durumu_goster(self, d) -> None:
        if self.tepsi is not None:
            self.tepsi.durumu_goster(d)
        if self.mini.isVisible():
            self.mini.durumu_goster(d)

    # ---- F6 kare seçme

    def _bolge_sec(self, _):
        from ui.region_overlay import BolgeKatmani, ekrani_bul
        if self._katman is not None:
            self._katman.close()
            return "Kare seçme iptal edildi"
        if self.hat.bolge.aktif:
            self.hat.bolge.temizle()
            self.depo.guncelle(bolge="")
            self._izi_gizle()
            return "Tam ekrana dönüldü"
        self._izi_gizle()
        ekran = ekrani_bul(getattr(self.hat.kaynak, "dikdortgen", None))
        self._katman = BolgeKatmani(ekran, self.hat.bolge.bolge)
        self._katman.secildi.connect(self._bolge_secildi)
        self._katman.destroyed.connect(self._katman_kapandi)
        self._katman.baslat()
        return None

    @Slot(tuple, str)
    def _bolge_secildi(self, bolge, mod) -> None:
        self.hat.bolge.sec(bolge, mod)
        self.depo.guncelle(bolge=mod)
        if mod == "yakinlastir":
            from ui.region_marker import YakinlastirmaIzi
            from ui.region_overlay import ekrani_bul
            if self._iz is None:
                self._iz = YakinlastirmaIzi()
            self._iz.goster(ekrani_bul(getattr(self.hat.kaynak, "dikdortgen", None)), self.hat.bolge.bolge or bolge)
        metin = "Kare yayında" if mod == "yakinlastir" else "Vurgulama açık"
        self._bildirim_goster(f"{metin} · tam ekran için tekrar", self.tus_haritasi.get("bolge.sec", ""))

    def _izi_gizle(self) -> None:
        if self._iz is not None:
            self._iz.hide()

    @Slot()
    def _katman_kapandi(self, *_):
        self._katman = None

    def _kayit_klasoru(self, _):
        from ui.klasor import kayit_klasorunu_ac
        return None if kayit_klasorunu_ac(self.ayarlar) else "Kayıt klasörü açılamadı"

    # ---- pencere / tepsi

    def mini_moda_gec(self) -> None:
        self.pencere.hide()
        self.mini.durumu_goster(self.depo.durum)
        self.mini.goster()

    def ayarlari_ac(self) -> None:
        from ui.settings_dialog import AyarlarPenceresi
        AyarlarPenceresi(self.ayarlar, self.hat, self.ses, self._ayarlar_degisti, self.pencere).exec()

    def bas_konus_kur(self, bas_konus, degisti) -> None:
        self.bas_konus, self._bas_konus_degisti = bas_konus, degisti
        self._bas_konusu_uygula()

    def _bas_konusu_uygula(self) -> None:
        bk = getattr(self, "bas_konus", None)
        if bk is None:
            return
        tus = (self.ayarlar.al("hotkeys", {}) or {}).get("bas_konus", "")
        if not bk.ayarla(tus):
            self.bildirim.goster(f"Bas-konuş tuşu geçersiz: {tus}", "", bildirim_rengi("kapalı"))
        self._bas_konus_degisti(bk.basili)  # tuş yoksa mikrofon kapısı açılır

    def _ayarlar_degisti(self) -> None:
        self._tus_haritasini_kur()
        if hasattr(self.pencere, "_bekleme_dugmesini_yaz"):
            self.pencere._bekleme_dugmesini_yaz()
        self._bas_konusu_uygula()
        self.kisayollar.grup_ayarla("genel", gruplara_ayir(self.ayarlar.al("hotkeys", {}), self.komutlar))
        if self.kalem is not None and self.kalem.acik:
            self.kalem._kalem_tuslari(True)
        self.pencere.tepsiye_kucul = self.tepsi is not None and self.ayarlar.al("ui.minimize_to_tray", True)
        self.app.setQuitOnLastWindowClosed(not self.pencere.tepsiye_kucul)
        QTimer.singleShot(800, self._basarisizlari_bildir)

    def pencereyi_goster(self) -> None:
        self.mini.hide()
        self.pencere.showNormal()
        self.pencere.raise_()
        self.pencere.activateWindow()

    def _tepsiye_kuculdu(self) -> None:
        d = self.depo.durum
        if d.cikis_acik or d.kayit == "açık":
            # Yayın/kayıt arka planda sürüyor (kamera da açık olabilir): görünür olsun, mini çubuktan durdurulsun.
            self.mini_moda_gec()
            ne = "Yayın" if d.cikis_acik else "Kayıt"
            self.bildirim.goster(f"{ne} sürüyor", "Mini çubuktan durdurabilirsin", bildirim_rengi("açık"))
            return
        if self._ilk_kuculme and self.tepsi is not None:
            self._ilk_kuculme = False
            self.tepsi.showMessage("RizeOn", "Arka planda çalışıyor. Kısayollar açık; "
                                   "kapatmak için simgeye sağ tıklayıp Çıkış'ı seç.",
                                   QSystemTrayIcon.Information, 3000)

    def cikmayi_onayla(self) -> None:
        """Çıkış düğmesi / tepsi menüsü: yayın veya kayıt açıksa önce sorar."""
        d = self.depo.durum
        if d.cikis_acik or d.kayit == "açık":
            from PySide6.QtWidgets import QMessageBox
            ne = "Yayın ve kayıt" if d.cikis_acik and d.kayit == "açık" else ("Yayın" if d.cikis_acik else "Kayıt")
            cevap = QMessageBox.question(
                self.pencere if self.pencere.isVisible() else None, "Çıkış",
                f"{ne} açık. Uygulama tamamen kapatılsın mı?"
                + ("\nKayıt durdurulup kaydedilir." if d.kayit == "açık" else ""),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if cevap != QMessageBox.Yes:
                return
        self.cik()

    def cik(self) -> None:
        self.pencere.tepsiye_kucul = False
        self.pencere.close()
        self.app.quit()
