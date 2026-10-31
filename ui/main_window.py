"""Ana pencere (brifteki tasarım).

  üst   : uygulama adı, durum rozetleri (sanal kamera, sanal mikrofon, kayıt), Mini mod, Ayarlar
  sol   : Sahneler (Ctrl+1..4) ve Kaynaklar (ekran, webcam, mikrofon, bilgisayar sesi)
  orta  : 16:9 önizleme = karşı tarafın gördüğü (ses kapalı / kalem açık uyarılarıyla)
  sağ   : ses mikseri
  alt   : büyük kontrol düğmeleri; her birinde adı, Açık/Kapalı ve kısayol tuşu

Pencere hiçbir durumu kendi tutmaz; her şey DurumDeposu'ndan okunur, her işlem
komut adıyla çalıştırılır (kısayol, mini mod ve tepsi ile aynı yol).
"""

import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from core.commands import KomutYoneticisi
from core.hotkeys import tus_metni
from core.platform_win import yakalamadan_gizle
from core.state import Durum, DurumDeposu
from ui.theme import QSS, RENK, rozet_stili

log = logging.getLogger(__name__)


class _DurumKoprusu(QObject):
    """Video/ses iş parçacıklarından gelen durum değişikliklerini Qt ana iş parçacığına taşır."""
    degisti = Signal(object)


class KontrolDugmesi(QPushButton):
    """Büyük kontrol düğmesi: üstte ad, ortada Açık/Kapalı, altta kısayol."""

    def __init__(self, ad: str, kisayol: str, renk_acik: str = RENK["acik"], cizgili: bool = False):
        super().__init__(objectName="kontrol")
        self.ad, self.kisayol, self.renk_acik, self.cizgili = ad, kisayol, renk_acik, cizgili
        self.setCheckable(True)
        self.setMinimumSize(104, 74)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._durum = None

    def goster(self, acik: bool, metin_acik: str = "Açık", metin_kapali: str = "Kapalı") -> None:
        if self._durum == (acik, metin_acik, metin_kapali):
            return
        self._durum = (acik, metin_acik, metin_kapali)
        self.setChecked(acik)
        # Renk tek başına durum anlatmasın: yazı + kapalıyken üstü çizili ad
        durum = metin_acik if acik else metin_kapali
        ad = self.ad if acik or not self.cizgili else "".join(c + "\u0336" for c in self.ad)
        self.setText(f"{ad}\n{durum}\n{self.kisayol or ' '}")
        renk = self.renk_acik if acik else RENK["yazi2"]
        self.setStyleSheet(f"QPushButton#kontrol {{ color: {renk}; }}"
                           + (f"QPushButton#kontrol {{ border-color: {renk}; }}" if acik else ""))


class AnaPencere(QMainWindow):
    def __init__(self, depo: DurumDeposu, komutlar: KomutYoneticisi, hat, onizleme_fps: int = 15,
                 ses=None, mikser=None, ayarlar=None):
        super().__init__()
        self.depo, self.komutlar, self.hat, self.ayarlar = depo, komutlar, hat, ayarlar
        self.tepsiye_kucul = False       # UygulamaKabugu ayarlar
        self.tepsiye_kuculdu = None      # ilk küçülmede bilgi vermek için geri çağrı
        self.mini_moda_gec = None        # UygulamaKabugu ayarlar
        self.ayarlari_ac = None
        self.setWindowTitle("Yayın Uygulaması")
        self.setStyleSheet(QSS)
        self.resize(1320, 800)
        self.setMinimumSize(1000, 640)

        # ---------------- üst çubuk
        self.rozet_kamera = QLabel(objectName="rozet")
        self.rozet_mikrofon = QLabel(objectName="rozet")
        self.rozet_kayit = QLabel(objectName="rozet")
        mini = QPushButton("▭  Mini mod", objectName="sahne")
        mini.clicked.connect(lambda: self.mini_moda_gec and self.mini_moda_gec())
        ayar = QPushButton("⚙  Ayarlar", objectName="sahne")
        ayar.clicked.connect(lambda: self.ayarlari_ac and self.ayarlari_ac())
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Yayın Uygulaması", objectName="baslik"))
        ust.addSpacing(12)
        for r in (self.rozet_kamera, self.rozet_mikrofon, self.rozet_kayit):
            ust.addWidget(r)
        self.rozet_mikrofon.setVisible(ses is not None)
        ust.addStretch()
        ust.addWidget(mini)
        ust.addWidget(ayar)

        # ---------------- sol: sahneler + kaynaklar
        sol = QFrame(objectName="panel")
        sol.setFixedWidth(240)
        sol_kutu = QVBoxLayout(sol)
        sol_kutu.setContentsMargins(12, 12, 12, 12)
        sol_kutu.setSpacing(6)
        sol_kutu.addWidget(self._bolum_basligi("Sahneler"))
        self.sahne_dugmeleri = []
        for i, sahne in enumerate(hat.sahneler.sahneler):
            tus = self._tus(f"sahne.sec:{i + 1}")
            d = QPushButton(f"{sahne.ad}" + (f"   ·  {tus}" if tus else ""), objectName="liste")
            d.setCheckable(True)
            d.clicked.connect(lambda _=False, n=i + 1: self._calistir(f"sahne.sec:{n}"))
            sol_kutu.addWidget(d)
            self.sahne_dugmeleri.append(d)
        sol_kutu.addSpacing(12)
        sol_kutu.addWidget(self._bolum_basligi("Kaynaklar"))
        self.kaynaklar = {}
        for anahtar, ad in (("ekran", "Ekran"), ("webcam", "Webcam"), ("mikrofon", "Mikrofon"),
                            ("sistem", "Bilgisayar sesi")):
            nokta, metin = QLabel("●"), QLabel(objectName="ikincil")
            metin.setWordWrap(True)
            satir = QGridLayout()
            satir.setHorizontalSpacing(8)
            satir.setVerticalSpacing(0)
            baslik = QLabel(ad)
            baslik.setStyleSheet("background: transparent;")
            nokta.setStyleSheet("background: transparent;")
            satir.addWidget(nokta, 0, 0)
            satir.addWidget(baslik, 0, 1)
            satir.addWidget(metin, 1, 1)
            satir.setColumnStretch(1, 1)
            sol_kutu.addLayout(satir)
            self.kaynaklar[anahtar] = (nokta, metin)
        sol_kutu.addStretch()

        # ---------------- orta: önizleme
        self.onizleme = QLabel(objectName="onizleme")
        self.onizleme.setAlignment(Qt.AlignCenter)
        self.onizleme.setMinimumSize(480, 270)
        self.onizleme.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ses_uyarisi = self._etiket(RENK["kapali"])
        self.kalem_etiketi = self._etiket(RENK["vurgu"], "✎ Kalem açık" + self._tus_eki("kalem.ac_kapat"))
        self.bolge_etiketi = self._etiket(RENK["vurgu"])
        self.panik_etiketi = self._etiket(RENK["panik"], "⚠ Panik: bekleme ekranı" + self._tus_eki("panik"))

        orta = QHBoxLayout()
        orta.setSpacing(12)
        orta.addWidget(sol)
        orta.addWidget(self.onizleme, 1)
        self.mikser_paneli = None
        if ses is not None and mikser is not None:
            from ui.mixer_panel import MikserPaneli
            self.mikser_paneli = MikserPaneli(depo, komutlar, ses, mikser, ayarlar)
            orta.addWidget(self.mikser_paneli)

        # ---------------- alt: kontrol düğmeleri
        self.kontroller: dict[str, KontrolDugmesi] = {}
        alt = QHBoxLayout()
        alt.setSpacing(8)
        tanimlar = [
            ("cikis.ac_kapat", "Yayın", RENK["acik"]),
            ("ses.mikrofon", "Mikrofon", RENK["acik"]),
            ("ses.sistem", "Bilgisayar sesi", RENK["acik"]),
            ("kamera.ac_kapat", "Kamera", RENK["acik"]),
            ("bolge.sec", "Kare seç", RENK["vurgu"]),
            ("kalem.ac_kapat", "Kalem", RENK["vurgu"]),
            ("panik", "Panik", RENK["panik"]),
            ("kayit.ac_kapat", "Kayıt", RENK["kapali"]),
        ]
        for komut, ad, renk in tanimlar:
            d = KontrolDugmesi(ad, self._tus(komut), renk,
                               cizgili=komut in ("ses.mikrofon", "ses.sistem", "kamera.ac_kapat"))
            d.clicked.connect(lambda _=False, k=komut: self._calistir(k))
            alt.addWidget(d)
            self.kontroller[komut] = d
        self.bilgi = QLabel(objectName="ikincil")
        self.hata = QLabel(objectName="hata")
        self.hata.setWordWrap(True)
        bilgi_satiri = QHBoxLayout()
        bilgi_satiri.addWidget(self.bilgi)
        bilgi_satiri.addStretch()
        bilgi_satiri.addWidget(self.hata, 1)
        alt_kutu = QVBoxLayout()
        alt_kutu.addLayout(alt)
        alt_kutu.addLayout(bilgi_satiri)
        alt_panel = QFrame(objectName="panel")
        alt_panel.setLayout(alt_kutu)

        kok = QVBoxLayout()
        kok.setContentsMargins(16, 12, 16, 16)
        kok.setSpacing(12)
        kok.addLayout(ust)
        kok.addLayout(orta, 1)
        kok.addWidget(alt_panel)
        govde = QWidget()
        govde.setLayout(kok)
        self.setCentralWidget(govde)

        # ---------------- durum bağlantısı (iş parçacığı güvenli)
        self._kopru = _DurumKoprusu()
        self._kopru.degisti.connect(self._durumu_goster)
        depo.dinle(lambda eski, yeni: self._kopru.degisti.emit(yeni))
        self._durumu_goster(depo.durum)

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._onizlemeyi_guncelle)
        self._zamanlayici.start(max(1, 1000 // onizleme_fps))

    # ---------------- yardımcılar

    def _tus(self, komut: str) -> str:
        if self.ayarlar is None:
            return ""
        tus = (self.ayarlar.al("hotkeys", {}) or {}).get(komut, "")
        return tus_metni(tus) if tus else ""

    def _tus_eki(self, komut: str) -> str:
        t = self._tus(komut)
        return f" · {t}" if t else ""

    @staticmethod
    def _bolum_basligi(metin: str) -> QLabel:
        e = QLabel(metin.upper(), objectName="ikincil")
        e.setStyleSheet(f"color: {RENK['yazi2']}; font-size: 11px; font-weight: 600; letter-spacing: 1px;"
                        " background: transparent;")
        return e

    def _etiket(self, renk: str, metin: str = "") -> QLabel:
        e = QLabel(metin, self.onizleme)
        e.setStyleSheet(f"background: {renk}; color: white; border-radius: 6px; padding: 3px 8px;"
                        " font-weight: 600; font-size: 12px;")
        e.adjustSize()
        e.hide()
        return e

    def _calistir(self, komut: str) -> None:
        self.komutlar.calistir(komut)
        self._durumu_goster(self.depo.durum)  # düğme hemen doğru görünsün

    def showEvent(self, olay):
        super().showEvent(olay)
        # Önizleme kendini yakalamasın (sonsuz ayna) ve karşı tarafa gitmesin.
        yakalamadan_gizle(int(self.winId()))

    def resizeEvent(self, olay):
        super().resizeEvent(olay)
        self._etiketleri_yerlestir()

    def _etiketleri_yerlestir(self) -> None:
        x = 10
        for e in (self.ses_uyarisi, self.panik_etiketi):
            if e.isVisible():
                e.move(x, 10)
                x += e.width() + 8
        y = 10
        for e in (self.kalem_etiketi, self.bolge_etiketi):
            if e.isVisible():
                e.move(self.onizleme.width() - e.width() - 10, y)
                y += e.height() + 6

    # ---------------- durum

    def _durumu_goster(self, d: Durum) -> None:
        self.rozet_kamera.setText(f"Sanal kamera: {d.sanal_kamera.capitalize()}")
        self.rozet_kamera.setStyleSheet(rozet_stili(d.sanal_kamera))
        self.rozet_mikrofon.setText(f"Sanal mikrofon: {d.sanal_mikrofon.capitalize()}")
        self.rozet_mikrofon.setStyleSheet(rozet_stili(d.sanal_mikrofon))
        kayit = getattr(d, "kayit", "kapalı")
        self.rozet_kayit.setText("● Kayıt" if kayit == "açık" else "Kayıt: Kapalı")
        self.rozet_kayit.setStyleSheet(rozet_stili("hata" if kayit == "açık" else "kapalı"))

        secili = self.hat.sahneler.indeks
        for i, dugme in enumerate(self.sahne_dugmeleri):
            dugme.setChecked(i == secili)

        def kaynak(anahtar, durum, aciklama):
            nokta, metin = self.kaynaklar[anahtar]
            renk = {"çalışıyor": RENK["acik"], "açık": RENK["acik"], "koptu": RENK["kapali"],
                    "yok": RENK["kapali"], "hata": RENK["kapali"]}.get(durum, RENK["yazi2"])
            nokta.setStyleSheet(f"color: {renk}; background: transparent;")
            metin.setText(aciklama)

        kaynak("ekran", d.ekran_kaynagi, d.ekran_kaynagi.capitalize()
               + (f" ({d.yakalama_yontemi})" if d.yakalama_yontemi else ""))
        kaynak("webcam", d.webcam, {"açık": "Açık", "kapalı": "Kapalı", "yok": "Bulunamadı"}.get(d.webcam, d.webcam))
        if d.mikrofon_sessiz:
            kaynak("mikrofon", "kapalı", "Susturuldu")
        else:
            kaynak("mikrofon", d.mikrofon, d.mikrofon_adi or d.mikrofon.capitalize())
        if d.sistem_sessiz:
            kaynak("sistem", "kapalı", "Susturuldu")
        else:
            kaynak("sistem", d.sistem_sesi, d.sistem_kaynagi or d.sistem_sesi.capitalize())

        panik = getattr(d, "panik", False)
        durumlar = {
            "cikis.ac_kapat": (d.cikis_acik, "Yayında", "Kapalı"),
            "ses.mikrofon": (not d.mikrofon_sessiz, "Açık", "Kapalı"),
            "ses.sistem": (not d.sistem_sessiz, "Açık", "Kapalı"),
            "kamera.ac_kapat": (self.hat.kamera_istegi, "Açık", "Kapalı"),
            "bolge.sec": (bool(d.bolge), "Vurgu" if d.bolge == "vurgula" else "Kare", "Tam ekran"),
            "kalem.ac_kapat": (d.kalem_acik, "Açık", "Kapalı"),
            "panik": (panik, "AÇIK", "Kapalı"),
            "kayit.ac_kapat": (kayit == "açık", "Kayıtta", "Kapalı"),
        }
        for komut, dugme in self.kontroller.items():
            dugme.setEnabled(self.komutlar.var_mi(komut))
            dugme.goster(*durumlar[komut])

        if self.mikser_paneli is not None:
            self.mikser_paneli.durumu_goster(d)
            uyarilar = [ad for ad, sessiz in (("Mikrofon", d.mikrofon_sessiz), ("Bilgisayar sesi", d.sistem_sessiz))
                        if sessiz]
            self.ses_uyarisi.setText("🔇 " + " ve ".join(uyarilar) + " kapalı")
            self.ses_uyarisi.adjustSize()
            self.ses_uyarisi.setVisible(bool(uyarilar))
        self.kalem_etiketi.setVisible(d.kalem_acik)
        self.bolge_etiketi.setText(("◎ Vurgulama" if d.bolge == "vurgula" else "⛶ Kare yayında")
                                   + self._tus_eki("bolge.sec"))
        self.bolge_etiketi.adjustSize()
        self.bolge_etiketi.setVisible(bool(d.bolge))
        self.panik_etiketi.setVisible(panik)
        self._etiketleri_yerlestir()

        self.bilgi.setText(f"{d.fps:.0f} FPS  ·  kare başına {d.kare_suresi_ms:.1f} ms  ·  Sahne: {d.sahne_adi}"
                           + ("  ·  Meet/Zoom/Discord'da kamera: 'OBS Virtual Camera', mikrofon: 'CABLE Output'"
                              if d.cikis_acik else ""))
        self.hata.setText(d.son_hata)

    def _onizlemeyi_guncelle(self) -> None:
        if not self.isVisible() or self.isMinimized():
            return  # görünmüyorken boşuna işlemci harcama
        kare = self.hat.son_kare()
        h, w = kare.shape[:2]
        resim = QImage(kare.data, w, h, 3 * w, QImage.Format_RGB888)
        hedef = self.onizleme.size()
        self.onizleme.setPixmap(QPixmap.fromImage(resim).scaled(
            hedef, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, olay):
        if self.tepsiye_kucul:
            # Kapat düğmesi uygulamayı kapatmaz; saatin yanına (sistem tepsisine) küçülür.
            olay.ignore()
            self.hide()
            if self.tepsiye_kuculdu is not None:
                self.tepsiye_kuculdu()
            return
        self._zamanlayici.stop()
        super().closeEvent(olay)
