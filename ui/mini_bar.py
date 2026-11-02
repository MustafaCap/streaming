"""Mini bar: her zaman üstte duran, sürüklenebilir küçük bar. Ekran yakalamaya girmez.

  kayıtta (küçük)   : tutma yeri · kırmızı nokta + süre · duraklat · genişlet ›
  duraklatıldı      : gri nokta, soluk süre, ▶
  genişletilmiş     : tutma yeri · Mikrofon · Sistem sesi · Kamera · Bölge · Kalem · Ekran görüntüsü |
                      kayıt grubu (nokta + süre · duraklat · bitir) ya da Kayıt · küçült ‹

Kayıt yokken genişletilmiş açılır; kayıt başlayınca kendiliğinden küçülür. Kapalı mikrofon ve
kamera sönük gri zemin + çapraz çizgili simgeyle görünür. Aktif sahnede kamera kaynağı yoksa
Kamera düğmesi kapalı görünür ve basılamaz. Panik ve "Son 2 dk" barda yok
(kısayolları var). Sağ tık: ana pencere, kaydı bitir. Tutma yerine çift tık: ana pencere.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QMenu, QWidget

from core.hotkeys import tus_metni
from core.platform_win import yakalamadan_gizle
from ui.bilesenler import KayitGrubu, SimgeDugme, TutmaYeri
from ui.theme import ALFA, RENK, beyaz


def _ayrac() -> QWidget:
    a = QWidget()
    a.setFixedSize(13, 20)
    a.setObjectName("miniAyrac")
    a.setStyleSheet(f"QWidget#miniAyrac {{ border-left: 1px solid {beyaz(ALFA['kenarlik'])}; margin-left: 6px; }}")
    return a


class MiniCubuk(QWidget):
    ana_pencere_istendi = Signal()

    ARACLAR = [  # komut, simge, açıkken ad, kapalıyken ad
        ("ses.mikrofon", "mikrofon", "Mikrofon açık, kapat", "Mikrofon kapalı, aç"),
        ("ses.sistem", "ses", "Sistem sesi açık, kapat", "Sistem sesi kapalı, aç"),
        ("kamera.ac_kapat", "kamera", "Kamera açık, kapat", "Kamera kapalı, aç"),
        ("bolge.sec", "bolge", "Bölge seç", "Bölge seç"),
        ("kalem.ac_kapat", "kalem", "Kalem", "Kalem"),
        ("ekran.goruntusu", "foto", "Ekran görüntüsü al", "Ekran görüntüsü al"),
    ]

    def __init__(self, komutlar, hat, ayarlar):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.komutlar, self.hat, self.ayarlar = komutlar, hat, ayarlar
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAccessibleName("RizeOn mini bar")
        self.genis = True
        self._kayitta = False
        self._son = None

        kap = QWidget(self, objectName="mini")
        kap.setAttribute(Qt.WA_StyledBackground)
        self._kap = kap
        satir = QHBoxLayout(kap)
        satir.setContentsMargins(4, 0, 4, 0)
        satir.setSpacing(2)
        self.tutma = TutmaYeri(dikey_bosluk=4)
        self.tutma.birakildi.connect(self._konumu_kaydet)
        self.tutma.cift_tiklandi.connect(self.ana_pencere_istendi.emit)
        self.tutma.setToolTip("Taşı · çift tıkla: ana pencere")
        satir.addWidget(self.tutma)

        self.dugmeler: dict[str, SimgeDugme] = {}
        self._araclar = QWidget()
        arac_satiri = QHBoxLayout(self._araclar)
        arac_satiri.setContentsMargins(0, 0, 0, 0)
        arac_satiri.setSpacing(2)
        for komut, simge, ad, _ in self.ARACLAR:
            d = SimgeDugme(simge, ad, self._tus(komut))
            d.clicked.connect(lambda _=False, k=komut: self._calistir(k))
            arac_satiri.addWidget(d)
            self.dugmeler[komut] = d
        arac_satiri.addWidget(_ayrac())
        satir.addWidget(self._araclar)

        self.kayit = SimgeDugme("kayit", "Kaydı başlat", self._tus("kayit.ac_kapat"))
        self.kayit.clicked.connect(lambda: self._calistir("kayit.ac_kapat"))
        satir.addWidget(self.kayit)
        self.dugmeler["kayit.ac_kapat"] = self.kayit
        self.kayit_grubu = KayitGrubu(dugme_boyu=32, bitir=True, zemin=False,
                                      tus_duraklat=self._tus("kayit.duraklat"), tus_bitir=self._tus("kayit.ac_kapat"))
        self.kayit_grubu.duraklat_basildi.connect(lambda: self._calistir("kayit.duraklat"))
        self.kayit_grubu.bitir_basildi.connect(lambda: self._calistir("kayit.ac_kapat"))
        satir.addWidget(self.kayit_grubu)
        self.dugmeler["kayit.duraklat"] = self.kayit_grubu.duraklat

        self.ac_kapa = SimgeDugme("geri", "Küçült", boyut=32, simge_boyu=14, renk=RENK["soluk"])
        self.ac_kapa.clicked.connect(lambda: self.genislet(not self.genis))
        satir.addWidget(self.ac_kapa)

        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(kap)
        self._yerlesim()
        self._konumu_yukle()

    def _tus(self, komut: str) -> str:
        tuslar = (self.ayarlar.al("hotkeys", {}) if self.ayarlar is not None else {}) or {}
        return tus_metni(tuslar[komut]) if tuslar.get(komut) else ""

    def _calistir(self, komut: str) -> None:
        if self.komutlar.var_mi(komut):
            self.komutlar.calistir(komut)

    # ---- düzen

    def genislet(self, genis: bool) -> None:
        self.genis = genis
        self._yerlesim()

    def _yerlesim(self) -> None:
        genis, kayitta = self.genis, self._kayitta
        yukseklik = 44 if genis else 40
        self._kap.setFixedHeight(yukseklik)
        self._kap.setStyleSheet(f"QWidget#mini {{ background: {RENK['yuzen']}; border: 1px solid "
                                f"{beyaz(ALFA['kenarlik'])}; border-radius: {yukseklik // 2}px; }}")
        self._araclar.setVisible(genis)
        self.kayit.setVisible(genis and not kayitta)
        self.kayit_grubu.setVisible(kayitta)
        if self.kayit_grubu.bitir is not None:
            self.kayit_grubu.bitir.setVisible(genis)
        boy = 36 if genis else 32
        for d in (self.kayit_grubu.duraklat, self.kayit_grubu.bitir):
            if d is not None:
                d.setFixedSize(boy, boy)
        # Kayıt yokken küçük bar boş kalırdı: küçültme sadece kayıtta var
        self.ac_kapa.setVisible(kayitta or not genis)
        self.ac_kapa.setFixedSize(boy, boy)
        self.ac_kapa.durum(simge_adi="geri" if genis else "ileri")
        self.ac_kapa.ad_ayarla("Küçült" if genis else "Genişlet")
        self.adjustSize()
        if self.isVisible():
            # sağa doğru büyüsün/küçülsün ama ekrandan taşmasın
            g = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
            x = min(self.x(), g.right() - self.width())
            self.move(max(g.x(), x), self.y())

    def _konumu_yukle(self) -> None:
        g = QGuiApplication.primaryScreen().availableGeometry()
        konum = self.ayarlar.al("ui.mini_pos", None) if self.ayarlar is not None else None
        if isinstance(konum, list) and len(konum) == 2:
            nokta = QPoint(int(konum[0]), int(konum[1]))
            if any(e.availableGeometry().contains(nokta) for e in QGuiApplication.screens()):
                self.move(nokta)
                return
        self.move(g.x() + (g.width() - self.width()) // 2, g.bottom() - self.height() - 60)

    def _konumu_kaydet(self) -> None:
        if self.ayarlar is not None:
            self.ayarlar.ayarla("ui.mini_pos", [self.x(), self.y()])

    def goster(self) -> None:
        # Kayıt yokken genişletilmiş, kayıttayken küçük açılır
        self.genis = not self._kayitta
        self._yerlesim()
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        self.hat.mini_gorunur = True     # mini bar açıkken kamera çalışır

    def hideEvent(self, e):
        super().hideEvent(e)
        self.hat.mini_gorunur = False

    # ---- sağ tık

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction("Ana pencereyi göster", self.ana_pencere_istendi.emit)
        if self._kayitta:
            menu.addAction("Kaydı bitir", lambda: self._calistir("kayit.ac_kapat"))
        menu.addAction("Genişlet" if not self.genis else "Küçült", lambda: self.genislet(not self.genis))
        menu.exec(e.globalPos())

    # ---- durum

    def durumu_goster(self, d) -> None:
        kayitta = getattr(d, "kayit", "kapalı") == "açık"
        if kayitta != self._kayitta:
            self._kayitta = kayitta
            if kayitta:
                self.genis = False         # kayıt başlayınca kendiliğinden küçülür
            self._yerlesim()
        if kayitta:
            self.kayit_grubu.guncelle(d.kayit_suresi, d.kayit_duraklatildi, self._tus("kayit.duraklat"))
        kamera = self.hat.kamera_gorunur_acik
        kamera_sahnede = self.hat.kamera_sahnede
        durumlar = {
            "ses.mikrofon": (d.mikrofon_sessiz, False),
            "ses.sistem": (d.sistem_sessiz, False),
            "kamera.ac_kapat": (not kamera, False),
            "bolge.sec": (False, bool(d.bolge)),
            "kalem.ac_kapat": (False, d.kalem_acik),
            "ekran.goruntusu": (False, False),
        }
        for komut, simge, ad_acik, ad_kapali in self.ARACLAR:
            kapali, secili = durumlar[komut]
            dugme = self.dugmeler[komut]
            dugme.durum(kapali=kapali, secili=secili)
            kullanilabilir = self.komutlar.var_mi(komut)
            if komut == "kamera.ac_kapat" and not kamera_sahnede:
                # Sahnede kamera yokken "açık" görünmesin, basılamasın (seni çekiyor sanılmasın)
                kullanilabilir = False
                dugme.ad_ayarla("Bu sahnede kamera yok")
            else:
                dugme.ad_ayarla(ad_kapali if kapali else ad_acik, self._tus(komut))
            dugme.setEnabled(kullanilabilir)
        self.kayit.setEnabled(self.komutlar.var_mi("kayit.ac_kapat"))
