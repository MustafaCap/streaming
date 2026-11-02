"""Sağ sütun: ses mikseri ve (Gelişmiş'te) özellik anahtarları.

Ses mikseri: Mikrofon ve Sistem / oyun için ad + yüzde, ince yeşil canlı seviye çizgisi ve gri
sürgü. Sistem sesinin altında hangi uygulamaların hariç olduğu ve "Düzenle" (Ayarlar > Ses).
"Önde olan": Sesim / Dengeli / Oyun modları (core/ses_modlari.py).

Anahtarlar: Gürültü azaltma, Otomatik kısma, Bas-konuş, Kamera arka planı (bulanıklaştırma).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from core import ses_modlari
from core.state import Durum
from ui.bilesenler import Anahtar, SecimGrubu, SesCizgisi
from ui.theme import RENK

SURGU_UST = 200   # 1.7.0'daki gibi sesi iki katına kadar yükseltebilir


def haric_metni(ayarlar) -> str:
    """'Zoom ve Discord hariç' gibi kısa açıklama (Ayarlar > Ses'teki listeden)."""
    if ayarlar is None:
        return ""
    mod = ayarlar.al("audio.system_mode", "auto")
    dahil = ayarlar.al("audio.include_app", "")
    if mod == "app" and dahil:
        return f"Sadece {dahil.removesuffix('.exe')}"
    if mod == "all":
        return "Tüm sesler"
    adlar = []
    for a in ayarlar.al("audio.exclude_apps", []) or []:
        ad = str(a).removesuffix(".exe").removesuffix(".EXE")
        ad = {"ms-teams": "Teams"}.get(ad, ad)
        if ad not in adlar:
            adlar.append(ad)
    if not adlar:
        return "Tüm sesler"
    if len(adlar) <= 2:
        return " ve ".join(adlar) + " hariç"
    return f"{adlar[0]}, {adlar[1]} +{len(adlar) - 2} hariç"


class _Kanal(QWidget):
    degisti = Signal()        # kullanıcı sürgüyü oynattı
    birakildi = Signal()

    def __init__(self, baslik: str, kanal, parent=None):
        super().__init__(parent)
        self.kanal = kanal
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(0, 0, 0, 0)
        kutu.setSpacing(8)
        ust = QHBoxLayout()
        self.baslik = QLabel(baslik)
        self.yuzde = QLabel(objectName="ikincil")
        ust.addWidget(self.baslik)
        ust.addStretch()
        ust.addWidget(self.yuzde)
        kutu.addLayout(ust)
        self.alt_satir = QHBoxLayout()
        self.alt_satir.setContentsMargins(0, -4, 0, 0)
        self.bilgi = QLabel(objectName="soluk")
        self.bilgi.setWordWrap(True)
        self.alt_satir.addWidget(self.bilgi, 1)
        kutu.addLayout(self.alt_satir)
        self.cizgi = SesCizgisi()
        kutu.addWidget(self.cizgi)
        self.surgu = QSlider(Qt.Horizontal)
        self.surgu.setRange(0, SURGU_UST)
        self.surgu.setAccessibleName(f"{baslik} ses seviyesi")
        self.surgu.setCursor(Qt.PointingHandCursor)
        self.surgu.setPageStep(10)
        kutu.addWidget(self.surgu)
        self._yaz(self.deger())
        self.surgu.setValue(self.deger())
        self.surgu.valueChanged.connect(self._surgu_degisti)
        self.surgu.sliderReleased.connect(self.birakildi.emit)
        self._programdan = False

    def deger(self) -> int:
        return round(self.kanal.kazanc * 100)

    def _yaz(self, v: int) -> None:
        self.yuzde.setText(f"{v}%")

    def ayarla(self, v: int) -> None:
        self._programdan = True
        self.surgu.setValue(v)
        self._programdan = False
        self._yaz(v)

    def _surgu_degisti(self, v: int) -> None:
        self.kanal.kazanc = v / 100.0
        self._yaz(v)
        if not self._programdan:
            self.degisti.emit()
            if not self.surgu.isSliderDown():
                self.birakildi.emit()   # klavyeyle ya da tekerlekle değişti

    def bilgi_yaz(self, metin: str) -> None:
        self.bilgi.setText(metin)
        self.bilgi.setVisible(bool(metin))


class MikserPaneli(QFrame):
    def __init__(self, depo, komutlar, ses, mikser, ayarlar, duzenle=None, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.depo, self.ses, self.mikser, self.ayarlar = depo, ses, mikser, ayarlar
        self._duzenle = duzenle
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(14, 14, 14, 14)
        kutu.setSpacing(18)
        kutu.addWidget(QLabel("Ses mikseri", objectName="baslik"))

        self.mik = _Kanal("Mikrofon", mikser.kanallar["mikrofon"])
        self.sistem = _Kanal("Sistem / oyun", mikser.kanallar["sistem"])
        self.duzenle_dugmesi = QPushButton("Düzenle", objectName="baglanti")
        self.duzenle_dugmesi.setToolTip("Hangi uygulamaların sesi alınmasın")
        self.duzenle_dugmesi.setCursor(Qt.PointingHandCursor)
        self.duzenle_dugmesi.setStyleSheet("text-decoration: underline;")
        self.duzenle_dugmesi.clicked.connect(lambda: self._duzenle and self._duzenle())
        self.sistem.alt_satir.addWidget(self.duzenle_dugmesi, 0, Qt.AlignRight)
        kutu.addWidget(self.mik)
        kutu.addWidget(self.sistem)

        # ---- Önde olan
        mod_kutu = QVBoxLayout()
        mod_kutu.setSpacing(8)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Önde olan", objectName="ikincil"))
        ust.addStretch()
        self.kaydet_dugmesi = QPushButton(objectName="baglanti")
        self.kaydet_dugmesi.setCursor(Qt.PointingHandCursor)
        self.kaydet_dugmesi.setStyleSheet(f"text-decoration: underline; font-size: 12px; color: {RENK['yazi']};")
        self.kaydet_dugmesi.clicked.connect(self._moda_kaydet)
        ust.addWidget(self.kaydet_dugmesi)
        mod_kutu.addLayout(ust)
        self.modlar = SecimGrubu([ses_modlari.ETIKETLER[m] for m in ses_modlari.MODLAR],
                                 [ses_modlari.IPUCU[m] for m in ses_modlari.MODLAR], ad="Önde olan")
        self.modlar.secildi.connect(self._mod_secildi)
        mod_kutu.addWidget(self.modlar)
        kutu.addLayout(mod_kutu)

        for k in (self.mik, self.sistem):
            k.degisti.connect(self._elle_degisti)
            k.birakildi.connect(self._kazanclari_kaydet)
        self.modlari_yenile()
        self.haric_yenile()

        self._zamanlayici = QTimer(self)
        self._zamanlayici.timeout.connect(self._seviyeleri_guncelle)
        self._zamanlayici.start(50)

    # ---- modlar

    def modlari_yenile(self) -> None:
        """Sürgüleri kanallara eşitler ve seçili modu bulur (ayarlar değişince de çağrılır)."""
        self.mik.ayarla(self.mik.deger())
        self.sistem.ayarla(self.sistem.deger())
        ad = ses_modlari.eslesen(self.mik.deger(), self.sistem.deger(), ses_modlari.modlar(self.ayarlar))
        self.modlar.sec(ses_modlari.MODLAR.index(ad) if ad else -1)
        son = ses_modlari.son_mod(self.ayarlar)
        self.kaydet_dugmesi.setText(ses_modlari.KAYDET_ETIKETI[son])
        self.kaydet_dugmesi.setToolTip(f"Şimdiki seviyeler {ses_modlari.ETIKETLER[son]} modunun yeni değeri olsun")
        self.kaydet_dugmesi.setVisible(not ad)

    def _mod_secildi(self, n: int) -> None:
        ad = ses_modlari.MODLAR[n]
        mik, sis = ses_modlari.uygula(self.ayarlar, self.mikser, ad)
        self.mik.ayarla(mik)
        self.sistem.ayarla(sis)
        self.modlari_yenile()

    def _elle_degisti(self) -> None:
        self.modlari_yenile()

    def _kazanclari_kaydet(self) -> None:
        if self.ayarlar is not None:
            self.ayarlar.veri.setdefault("audio", {})["mic_gain"] = self.mik.kanal.kazanc
            self.ayarlar.ayarla("audio.system_gain", self.sistem.kanal.kazanc)

    def _moda_kaydet(self) -> None:
        if self.ayarlar is None:
            return
        ses_modlari.kaydet(self.ayarlar, ses_modlari.son_mod(self.ayarlar), self.mik.deger(), self.sistem.deger())
        self._kazanclari_kaydet()
        self.modlari_yenile()

    def haric_yenile(self) -> None:
        self.sistem.bilgi.setText(haric_metni(self.ayarlar))
        if self.ayarlar is not None:
            self.sistem.bilgi.setToolTip(", ".join(self.ayarlar.al("audio.exclude_apps", []) or []))
        self.sistem.bilgi.setVisible(True)

    # ---- canlı

    def _seviyeleri_guncelle(self) -> None:
        if not self.isVisible():
            return
        s = self.mikser.seviyeler()
        d = self.depo.durum
        self.mik.cizgi.ayarla(0.0 if d.mikrofon_sessiz else s.get("mikrofon", 0.0))
        self.sistem.cizgi.ayarla(0.0 if d.sistem_sessiz else s.get("sistem", 0.0))

    def durumu_goster(self, d: Durum) -> None:
        if d.mikrofon == "yok":
            self.mik.bilgi_yaz(d.ses_hatasi or "Mikrofon bulunamadı")
        elif d.bas_konus:
            self.mik.bilgi_yaz("Konuşuyor" if d.konusuyor else "Bas-konuş: konuşmak için tuşu basılı tut")
        else:
            self.mik.bilgi_yaz("")
        if d.sistem_sesi == "yok":
            self.sistem.bilgi.setText(d.ses_hatasi or "Sistem sesi alınamıyor")
        else:
            self.sistem.bilgi.setText(haric_metni(self.ayarlar))


class _AnahtarSatiri(QWidget):
    def __init__(self, baslik: str, aciklama: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(52)
        kutu = QHBoxLayout(self)
        kutu.setContentsMargins(0, 0, 0, 0)
        kutu.setSpacing(12)
        yazi = QVBoxLayout()
        yazi.setSpacing(0)
        self.baslik = QLabel(baslik)
        self.aciklama = QLabel(aciklama, objectName="soluk")
        self.aciklama.setWordWrap(True)
        yazi.addWidget(self.baslik)
        yazi.addWidget(self.aciklama)
        kutu.addLayout(yazi, 1)
        self.anahtar = Anahtar(baslik)
        self.anahtar.setToolTip(aciklama)
        kutu.addWidget(self.anahtar)


class AnahtarPaneli(QFrame):
    """Gürültü azaltma · Otomatik kısma · Bas-konuş · Kamera arka planı."""

    def __init__(self, ayarlar, mikser, hat, gurultu=None, bas_konus_degisti=None, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.ayarlar, self.mikser, self.hat = ayarlar, mikser, hat
        self.gurultu = gurultu                       # core.gurultu.GurultuAzaltici ya da None
        self._bas_konus_degisti = bas_konus_degisti  # fn(acik) -> bool (tuş yoksa False)
        kutu = QVBoxLayout(self)
        kutu.setContentsMargins(14, 6, 14, 6)
        kutu.setSpacing(0)
        self.satirlar: dict[str, _AnahtarSatiri] = {}
        for anahtar, baslik, aciklama in (
                ("gurultu", "Gürültü azaltma", "Klavye ve fan sesini bastırır"),
                ("kisma", "Otomatik kısma", "Konuşunca oyun sesi kısılır"),
                ("bas_konus", "Bas-konuş", "Tuşa basılıyken mikrofon açık"),
                ("bulanik", "Kamera arka planı", "Arkadaki odayı bulanıklaştırır")):
            satir = _AnahtarSatiri(baslik, aciklama)
            satir.anahtar.toggled.connect(lambda acik, a=anahtar: self._degisti(a, acik))
            kutu.addWidget(satir)
            self.satirlar[anahtar] = satir
        self.yenile()

    def yenile(self) -> None:
        """Anahtarları ayarlara göre gösterir (Ayarlar penceresi kapanınca da çağrılır)."""
        a = self.ayarlar
        durumlar = {
            "gurultu": bool(a.al("audio.noise_suppression", False)) if a else False,
            "kisma": bool(getattr(self.mikser, "kisma_acik", False)),
            "bas_konus": bool(a.al("audio.ptt", False)) if a else False,
            "bulanik": bool(getattr(self.hat.kamera, "bulaniklastir", False)) if self.hat.kamera else False,
        }
        for ad, acik in durumlar.items():
            s = self.satirlar[ad].anahtar
            s.blockSignals(True)
            s.setChecked(acik)
            s.blockSignals(False)
        gurultu_var = self.gurultu is not None and getattr(self.gurultu, "kullanilabilir", False)
        g = self.satirlar["gurultu"]
        g.anahtar.setEnabled(gurultu_var)
        g.aciklama.setText("Klavye ve fan sesini bastırır" if gurultu_var else
                           "Bu kurulumda yok (rnnoise)")
        b = self.satirlar["bulanik"]
        b.anahtar.setEnabled(self.hat.kamera is not None)

    def _degisti(self, ad: str, acik: bool) -> None:
        a = self.ayarlar
        if ad == "gurultu":
            if self.gurultu is not None:
                self.gurultu.acik = acik
            if a:
                a.ayarla("audio.noise_suppression", acik)
        elif ad == "kisma":
            self.mikser.kisma_acik = acik
            if a:
                a.ayarla("audio.ducking", acik)
        elif ad == "bas_konus":
            if a:
                a.ayarla("audio.ptt", acik)
            if self._bas_konus_degisti is not None and not self._bas_konus_degisti(acik):
                # tuş seçilmemiş: anahtar kapalı kalır (Ayarlar > Kısayollar açılır)
                if a:
                    a.ayarla("audio.ptt", False)
                self.yenile()
        elif ad == "bulanik":
            if self.hat.kamera is not None:
                self.hat.kamera.bulaniklastir = acik
            if a:
                a.ayarla("camera.blur", acik)
