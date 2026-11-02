"""Sistem tepsisi: pencere kapatılınca uygulama saatin yanında çalışmaya devam eder.

Menü: Ana pencereyi göster · Mini bar · mikrofon/sistem sesi/kamera · Sahne ▸ · Kaydı başlat ·
Son 2 dk'yı kaydet · Kayıt klasörü · Sanal çıkışı duraklat · (sorun varsa: sorun satırı) ·
Hakkında · Çıkış.
"""

from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ui.icons import uygulama_ikonu


class Tepsi(QSystemTrayIcon):
    def __init__(self, komutlar, hat, depo, pencereyi_goster, cikis, sorun_goster=None):
        super().__init__(uygulama_ikonu())
        self.komutlar, self.hat, self.depo = komutlar, hat, depo
        self._sorun_goster = sorun_goster
        self.setToolTip("RizeOn")
        menu = QMenu()
        menu.addAction("Ana pencereyi göster", pencereyi_goster)
        menu.addAction("Mini bar", lambda: komutlar.calistir("pencere.mini"))
        menu.addSeparator()
        self.a_mik = menu.addAction("Mikrofon", lambda: komutlar.calistir("ses.mikrofon"))
        self.a_sistem = menu.addAction("Sistem sesi", lambda: komutlar.calistir("ses.sistem"))
        self.a_kamera = menu.addAction("Kamera", lambda: komutlar.calistir("kamera.ac_kapat"))
        for a in (self.a_mik, self.a_sistem, self.a_kamera):
            a.setCheckable(True)
        self.sahneler = menu.addMenu("Sahne")
        self.sahneler.aboutToShow.connect(self._sahneleri_doldur)
        menu.addSeparator()
        self.a_kayit = menu.addAction("Kaydı başlat", lambda: komutlar.calistir("kayit.ac_kapat"))
        self.a_tekrar = menu.addAction("Son 15 sn'yi kaydet", lambda: komutlar.calistir("anlik_kayit.kaydet"))
        menu.addAction("Kayıt klasörünü aç", lambda: komutlar.calistir("kayit.klasor"))
        menu.addSeparator()
        self.a_cikis = menu.addAction("Sanal çıkışı duraklat", lambda: komutlar.calistir("cikis.ac_kapat"))
        self.a_cikis.setToolTip("Kamera ve mikrofon Zoom/Meet/Discord'a gönderilmez; tekrar basınca sürer")
        self.a_sorun = menu.addAction("", self._sorun)
        self.a_sorun.setVisible(False)
        menu.addSeparator()
        menu.addAction("Hakkında", self._hakkinda)
        menu.addAction("Çıkış", cikis)
        menu.aboutToShow.connect(lambda: self.durumu_goster(self.depo.durum))
        self._menu = menu  # çöp toplayıcı silmesin
        self.setContextMenu(menu)
        self.activated.connect(lambda neden: pencereyi_goster()
                               if neden in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)

    def _sahneleri_doldur(self) -> None:
        self.sahneler.clear()
        sy = self.hat.sahneler
        for i, s in enumerate(sy.sahneler):
            a = self.sahneler.addAction(s.ad, lambda n=i + 1: self.komutlar.calistir(f"sahne.sec:{n}"))
            a.setCheckable(True)
            a.setChecked(i == sy.indeks)

    def _sorun(self) -> None:
        if self._sorun_goster is not None:
            self._sorun_goster()

    def sorun_ayarla(self, metin: str) -> None:
        """Sanal kamera/mikrofon sorunu sürdükçe menüde görünür ('' = sorun yok)."""
        self.a_sorun.setText(f"{metin} · Nasıl düzeltilir?" if metin else "")
        self.a_sorun.setVisible(bool(metin))
        self.setToolTip("RizeOn" + (f" · {metin}" if metin else ""))

    @staticmethod
    def _hakkinda() -> None:
        from ui.hakkinda import hakkinda_goster
        hakkinda_goster()

    def durumu_goster(self, d) -> None:
        self.a_mik.setChecked(not d.mikrofon_sessiz)
        self.a_mik.setText(f"Mikrofon: {'kapalı' if d.mikrofon_sessiz else 'açık'}")
        self.a_sistem.setChecked(not d.sistem_sessiz)
        self.a_sistem.setText(f"Sistem sesi: {'kapalı' if d.sistem_sessiz else 'açık'}")
        sahnede = self.hat.kamera_sahnede
        self.a_kamera.setChecked(self.hat.kamera_gorunur_acik)
        self.a_kamera.setEnabled(sahnede)
        self.a_kamera.setText(f"Kamera: {'açık' if self.hat.kamera_gorunur_acik else 'kapalı'}" if sahnede
                              else "Kamera: bu sahnede yok")
        self.a_kayit.setText("Kaydı bitir" if d.kayit == "açık" else "Kaydı başlat")
        self.a_kayit.setEnabled(self.komutlar.var_mi("kayit.ac_kapat"))
        self.a_tekrar.setEnabled(self.komutlar.var_mi("anlik_kayit.kaydet"))
        tekrar = getattr(self.hat, "tekrar", None)
        if tekrar is not None:
            from core.anlik_tekrar import sure_etiketi
            etiket = sure_etiketi(tekrar.sure_sn)
            self.a_tekrar.setText(f"{etiket}'yı kaydet" if etiket.endswith("dk") else f"{etiket}'yi kaydet")
        self.a_cikis.setText("Sanal çıkışı duraklat" if self.hat.cikis_istegi else "Sanal çıkışı sürdür")
