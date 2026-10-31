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

    def __init__(self, app, pencere, komutlar, depo, hat, ayarlar):
        super().__init__()
        self.app, self.pencere, self.komutlar, self.depo, self.ayarlar = app, pencere, komutlar, depo, ayarlar
        self._komut_sinyali.connect(self._komutu_calistir)
        self._bildirim_sinyali.connect(self._bildirim_goster)
        self._durum_sinyali.connect(self._durumu_goster)

        # komut adı -> tuş (bildirimlerde "Mikrofon kapandı · F8" yazmak için)
        self.tus_haritasi: dict[str, str] = {}
        for ayar in ("hotkeys", "pen_hotkeys"):
            for komut, tus in (ayarlar.al(ayar, {}) or {}).items():
                if tus:
                    self.tus_haritasi[komut] = tus_metni(tus)

        self.bildirim = Bildirim()
        komutlar.dinle(self._komut_bitti)

        self.kisayollar = KisayolYoneticisi(self._komut_sinyali.emit)

        self.tepsi = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            from ui.tray import Tepsi
            self.tepsi = Tepsi(komutlar, hat, depo, self.pencereyi_goster, self.cik)
            self.tepsi.show()
            depo.dinle(lambda eski, yeni: self._durum_sinyali.emit(yeni))
            self._durumu_goster(depo.durum)
        self.pencere.tepsiye_kucul = self.tepsi is not None and ayarlar.al("ui.minimize_to_tray", True)
        self.pencere.tepsiye_kuculdu = self._tepsiye_kuculdu
        self._ilk_kuculme = True

    def baslat(self) -> None:
        self.kisayollar.baslat()
        self.kisayollar.grup_ayarla("genel", gruplara_ayir(self.ayarlar.al("hotkeys", {}), self.komutlar))
        QTimer.singleShot(800, self._basarisizlari_bildir)

    def durdur(self) -> None:
        self.kisayollar.durdur()
        if self.tepsi is not None:
            self.tepsi.hide()

    # ---- komutlar ve bildirimler

    @Slot(str)
    def _komutu_calistir(self, ad: str) -> None:
        self.komutlar.calistir(ad)

    def _komut_bitti(self, ad: str, mesaj) -> None:
        if mesaj:
            self._bildirim_sinyali.emit(str(mesaj), self.tus_haritasi.get(ad, ""))

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

    # ---- pencere / tepsi

    def pencereyi_goster(self) -> None:
        self.pencere.showNormal()
        self.pencere.raise_()
        self.pencere.activateWindow()

    def _tepsiye_kuculdu(self) -> None:
        if self._ilk_kuculme and self.tepsi is not None:
            self._ilk_kuculme = False
            self.tepsi.showMessage("Yayın Uygulaması", "Arka planda çalışıyor. Kısayollar açık; "
                                   "kapatmak için simgeye sağ tıklayıp Çıkış'ı seç.",
                                   QSystemTrayIcon.Information, 3000)

    def cik(self) -> None:
        self.pencere.tepsiye_kucul = False
        self.pencere.close()
        self.app.quit()
