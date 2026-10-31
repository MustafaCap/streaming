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

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
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
        from core.surum import SURUM
        self.setWindowTitle(f"Yayın Uygulaması {SURUM}")
        self.setStyleSheet(QSS)
        self.resize(1320, 800)
        self.setMinimumSize(1000, 640)

        # ---------------- üst çubuk
        self.rozet_kamera = QLabel(objectName="rozet")
        self.rozet_mikrofon = QLabel(objectName="rozet")
        self.rozet_kayit = QLabel(objectName="rozet")
        mini = QPushButton("▭  Mini mod", objectName="sahne")
        mini.setToolTip("Ana pencereyi gizle, her zaman üstte duran küçük çubuğa geç")
        mini.setStyleSheet(f"QPushButton {{ border-color: {RENK['vurgu']}; color: {RENK['vurgu']}; font-weight: 600; }}")
        mini.clicked.connect(lambda: self.mini_moda_gec and self.mini_moda_gec())
        ayar = QPushButton("⚙  Ayarlar", objectName="sahne")
        ayar.clicked.connect(lambda: self.ayarlari_ac and self.ayarlari_ac())
        kayitlar = QPushButton("📁  Kayıtlar", objectName="sahne")
        kayitlar.setToolTip("Kayıt klasörünü aç")
        kayitlar.clicked.connect(self.kayit_klasorunu_ac)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Yayın Uygulaması", objectName="baslik"))
        ust.addSpacing(12)
        for r in (self.rozet_kamera, self.rozet_mikrofon, self.rozet_kayit):
            ust.addWidget(r)
        self.rozet_mikrofon.setVisible(ses is not None)
        ust.addStretch()
        ust.addWidget(kayitlar)
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
        self.bekleme_dugmesi = QPushButton(objectName="liste")
        self.bekleme_dugmesi.setToolTip("Bekleme ekranında (ve panikte) gösterilecek resim ya da kısa video")
        self.bekleme_dugmesi.clicked.connect(self._bekleme_menusu)
        sol_kutu.addSpacing(4)
        sol_kutu.addWidget(self.bekleme_dugmesi)
        self._bekleme_dugmesini_yaz()
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
        self.onizleme.setMouseTracking(True)
        self.onizleme.installEventFilter(self)
        self.onizleme.setToolTip("Köşedeki kamerayı fareyle sürükleyerek taşıyabilirsin")
        self._kamera_surukle = None   # (fare ile kutu merkezi arasındaki fark) sürüklerken
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

    # ---------------- bekleme ekranı

    def _bekleme_dugmesini_yaz(self) -> None:
        from pathlib import Path

        from core.standby import video_mu
        yol = getattr(self.hat, "bekleme_gorseli", "") or ""
        tur = "Video" if video_mu(yol) else ("Resim" if yol else "Yazı")
        ad = f" ({Path(yol).name})" if yol and not video_mu(yol) else ""
        self.bekleme_dugmesi.setText(f"🖼  Bekleme ekranı: {tur}{ad}  ▾")

    def _bekleme_menusu(self) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(QSS)
        menu.addAction("Resim ya da kısa video seç…", self._bekleme_sec)
        kaldir = menu.addAction("Sadece yazı kullan", lambda: self._bekleme_uygula(""))
        kaldir.setEnabled(bool(getattr(self.hat, "bekleme_gorseli", "")))
        menu.addAction("Bekleme sahnesine geç", lambda: self._calistir(f"sahne.sec:{self._bekleme_sahnesi()}"))
        menu.exec(self.bekleme_dugmesi.mapToGlobal(self.bekleme_dugmesi.rect().bottomLeft()))

    def _bekleme_sahnesi(self) -> int:
        for i, s in enumerate(self.hat.sahneler.sahneler):
            if s.bekleme:
                return i + 1
        return len(self.hat.sahneler.sahneler)

    def _bekleme_sec(self) -> None:
        from ui.bekleme_secici import dosya_sec
        yol = dosya_sec(self)
        if yol:
            self._bekleme_uygula(yol)

    def _bekleme_uygula(self, yol: str) -> None:
        if self.ayarlar is not None:
            from ui.bekleme_secici import uygula
            uygula(self.ayarlar, self.hat, yol)
        else:
            self.hat.bekleme_gorseli = yol
        self._bekleme_dugmesini_yaz()

    def kayit_klasorunu_ac(self) -> None:
        from ui.klasor import kayit_klasorunu_ac
        kayit_klasorunu_ac(self.ayarlar)

    # ---------------- önizlemede kamerayı sürükleme

    def _cikis_noktasi(self, nokta):
        """Önizlemedeki fare noktası -> çıkış karesinde piksel (resmin dışındaysa None)."""
        pm = self.onizleme.pixmap()
        if pm is None or pm.isNull():
            return None
        pw, ph = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
        ox, oy = (self.onizleme.width() - pw) / 2, (self.onizleme.height() - ph) / 2
        x, y = (nokta.x() - ox) / pw, (nokta.y() - oy) / ph
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return None
        return x * self.hat.genislik, y * self.hat.yukseklik

    def _kamera_gorunuyor(self) -> bool:
        sahne = self.hat.sahneler.aktif
        return sahne.kamera == "corner" and self.hat.kamera_istegi and not self.hat.panik

    def _kamera_ustunde(self, nokta) -> bool:
        p = self._cikis_noktasi(nokta)
        if p is None or not self._kamera_gorunuyor():
            return False
        x, y, w, h = self.hat.kamera_yerlesimi.dikdortgen(self.hat.genislik, self.hat.yukseklik)
        return x <= p[0] <= x + w and y <= p[1] <= y + h

    def eventFilter(self, nesne, olay):
        if nesne is not self.onizleme:
            return super().eventFilter(nesne, olay)
        tur = olay.type()
        if tur == QEvent.MouseButtonPress and olay.button() == Qt.LeftButton and self._kamera_ustunde(olay.position()):
            p = self._cikis_noktasi(olay.position())
            x, y, w, h = self.hat.kamera_yerlesimi.dikdortgen(self.hat.genislik, self.hat.yukseklik)
            self._kamera_surukle = (p[0] - (x + w / 2), p[1] - (y + h / 2))
            self.onizleme.setCursor(Qt.ClosedHandCursor)
            return True
        if tur == QEvent.MouseMove:
            if self._kamera_surukle is not None:
                p = self._cikis_noktasi(olay.position())
                if p is not None:
                    from dataclasses import replace
                    dx, dy = self._kamera_surukle
                    W, H = self.hat.genislik, self.hat.yukseklik
                    x, y, w, h = self.hat.kamera_yerlesimi.dikdortgen(W, H)
                    # kutu çıkışın dışına taşmasın
                    cx = min(max(p[0] - dx, w / 2), W - w / 2) / W
                    cy = min(max(p[1] - dy, h / 2), H - h / 2) / H
                    self.hat.kamera_yerlesimi = replace(self.hat.kamera_yerlesimi, konum=(cx, cy))
                return True
            self.onizleme.setCursor(Qt.OpenHandCursor if self._kamera_ustunde(olay.position()) else Qt.ArrowCursor)
        if tur == QEvent.MouseButtonRelease and self._kamera_surukle is not None:
            self._kamera_surukle = None
            self.onizleme.setCursor(Qt.OpenHandCursor)
            konum = self.hat.kamera_yerlesimi.konum
            if self.ayarlar is not None and konum is not None:
                self.ayarlar.ayarla("camera.position", [round(konum[0], 4), round(konum[1], 4)])
            return True
        return super().eventFilter(nesne, olay)

    def _calistir(self, komut: str) -> None:
        self.komutlar.calistir(komut)
        self._durumu_goster(self.depo.durum)  # düğme hemen doğru görünsün

    def showEvent(self, olay):
        super().showEvent(olay)
        self.hat.onizleme_gorunur = True
        # Önizleme kendini yakalamasın (sonsuz ayna) ve karşı tarafa gitmesin.
        yakalamadan_gizle(int(self.winId()))

    def hideEvent(self, olay):
        super().hideEvent(olay)
        self.hat.onizleme_gorunur = False   # arka planda kamera boşuna açık kalmasın

    def changeEvent(self, olay):
        super().changeEvent(olay)
        if olay.type() == QEvent.WindowStateChange:
            self.hat.onizleme_gorunur = self.isVisible() and not self.isMinimized()

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
        sure = f"{d.kayit_suresi // 60:02d}:{d.kayit_suresi % 60:02d}"
        self.rozet_kayit.setText(f"● Kayıt {sure}" if kayit == "açık" else
                                 ("Kayıt: Hata" if kayit == "hata" else "Kayıt: Kapalı"))
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
        kaynak("webcam", d.webcam, {"açık": "Açık", "kapalı": "Kapalı", "yok": "Bulunamadı", "beklemede": "Beklemede (pencere gizli, kamera kapalı)"}.get(d.webcam, d.webcam))
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
