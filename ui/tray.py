"""Sistem tepsisi: pencere kapatılınca uygulama saatin yanında çalışmaya devam eder."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ui.icons import uygulama_ikonu


class Tepsi(QSystemTrayIcon):
    def __init__(self, komutlar, hat, depo, pencereyi_goster, cikis):
        super().__init__(uygulama_ikonu(False))
        self.komutlar, self.hat = komutlar, hat
        self.setToolTip("Yayın Uygulaması")
        menu = QMenu()
        self.a_yayin = menu.addAction("Yayını başlat", lambda: komutlar.calistir("cikis.ac_kapat"))
        menu.addSeparator()
        self.a_mik = menu.addAction("Mikrofon", lambda: komutlar.calistir("ses.mikrofon"))
        self.a_sistem = menu.addAction("Bilgisayar sesi", lambda: komutlar.calistir("ses.sistem"))
        self.a_kamera = menu.addAction("Kamera", lambda: komutlar.calistir("kamera.ac_kapat"))
        for a in (self.a_mik, self.a_sistem, self.a_kamera):
            a.setCheckable(True)
        sahneler = menu.addMenu("Sahne")
        self.sahne_eylemleri: list[QAction] = []
        for i, s in enumerate(hat.sahneler.sahneler):
            a = sahneler.addAction(f"{i + 1}  {s.ad}", lambda n=i + 1: komutlar.calistir(f"sahne.sec:{n}"))
            a.setCheckable(True)
            self.sahne_eylemleri.append(a)
        menu.addSeparator()
        menu.addAction("Kayıt klasörünü aç", lambda: komutlar.calistir("kayit.klasor"))
        menu.addAction("Pencereyi göster", pencereyi_goster)
        menu.addAction("Mini mod", lambda: komutlar.calistir("pencere.mini"))
        menu.addAction("Çıkış", cikis)
        self._menu = menu  # çöp toplayıcı silmesin
        self.setContextMenu(menu)
        self.activated.connect(lambda neden: pencereyi_goster()
                               if neden in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self._canli = None

    def durumu_goster(self, d) -> None:
        self.a_yayin.setText("Yayını durdur" if d.cikis_acik else "Yayını başlat")
        self.a_mik.setChecked(not d.mikrofon_sessiz)
        self.a_mik.setText(f"Mikrofon: {'Kapalı' if d.mikrofon_sessiz else 'Açık'}")
        self.a_sistem.setChecked(not d.sistem_sessiz)
        self.a_sistem.setText(f"Bilgisayar sesi: {'Kapalı' if d.sistem_sessiz else 'Açık'}")
        self.a_kamera.setChecked(self.hat.kamera_istegi)
        self.a_kamera.setText(f"Kamera: {'Açık' if self.hat.kamera_istegi else 'Kapalı'}")
        for i, a in enumerate(self.sahne_eylemleri):
            a.setChecked(i == d.aktif_sahne)
        if self._canli != d.cikis_acik:
            self._canli = d.cikis_acik
            self.setIcon(uygulama_ikonu(d.cikis_acik))
            self.setToolTip("Yayın Uygulaması · " + ("Yayında" if d.cikis_acik else "Beklemede"))
