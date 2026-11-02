"""Köşe bildirimleri: kısa, gri, sağ altta.

  "Mikrofon kapandı · Ctrl+Shift+M"         (kısa süre, tıklamalar alttaki pencereye geçer)
  "Son 2 dk kaydedildi · Aç"                (eylemli: tıklanabilir bağlantı, biraz daha uzun kalır)
  "Sanal mikrofon bulunamadı · Nasıl düzeltilir?"

Bildirim odak almaz ve ekran yakalamaya girmez (karşı taraf görmez, sadece sen görürsün).
Fare üstündeyken kaybolmaz.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from core.platform_win import yakalamadan_gizle
from ui.theme import ALFA, RENK, beyaz


class Bildirim(QWidget):
    SURE_MS = 1800
    EYLEMLI_SURE_MS = 5000

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.kart = QWidget(self)
        self.kart.setObjectName("kart")
        self.kart.setAttribute(Qt.WA_StyledBackground)
        self.kart.setStyleSheet(f"QWidget#kart {{ background: {RENK['yuzen']}; border: 1px solid "
                                f"{beyaz(ALFA['kenarlik_menu'])}; border-radius: 10px; }}")
        self.metin = QLabel()
        self.metin.setStyleSheet(f"color: {RENK['yazi']}; font-size: 13px;")
        self.ayrac = QLabel("·")
        self.ayrac.setStyleSheet(f"color: {RENK['soluk']};")
        self.tus = QLabel()
        self.tus.setStyleSheet(f"color: {RENK['soluk']}; font-size: 12px;")
        self.eylem = QPushButton(objectName="baglanti")
        self.eylem.setCursor(Qt.PointingHandCursor)
        self.eylem.setStyleSheet(f"QPushButton#baglanti {{ color: {RENK['yazi']}; font-size: 13px;"
                                 " text-decoration: underline; padding: 0 4px; }")
        self.eylem.clicked.connect(self._eyleme_basildi)
        satir = QHBoxLayout(self.kart)
        satir.setContentsMargins(14, 9, 12, 9)
        satir.setSpacing(6)
        satir.addWidget(self.metin)
        satir.addWidget(self.ayrac)
        satir.addWidget(self.tus)
        satir.addWidget(self.eylem)
        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(self.kart)
        self._eylem_fn = None

        self._zamanlayici = QTimer(self)
        self._zamanlayici.setSingleShot(True)
        self._zamanlayici.timeout.connect(self._sondur)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._anim_bitti)
        self._gizlenecek = False

    def goster(self, metin: str, tus: str = "", renk: str | None = None, eylem=None, sure_ms: int | None = None) -> None:
        """eylem: ("Aç", fn) — tıklanabilir bağlantı. renk: eski sürümle uyum için (kullanılmaz)."""
        self._eylem_fn = eylem[1] if eylem else None
        etkilesimli = eylem is not None
        if bool(self.windowFlags() & Qt.WindowTransparentForInput) == etkilesimli:
            self.hide()
            self.setWindowFlag(Qt.WindowTransparentForInput, not etkilesimli)
        self.metin.setText(metin)
        self.tus.setText(tus)
        self.tus.setVisible(bool(tus))
        self.eylem.setText(eylem[0] if eylem else "")
        self.eylem.setVisible(etkilesimli)
        self.ayrac.setVisible(bool(tus) or etkilesimli)
        self.adjustSize()
        ekran = QGuiApplication.primaryScreen().availableGeometry()
        self.move(ekran.right() - self.width() - 16, ekran.bottom() - self.height() - 16)
        self._anim.stop()
        self._gizlenecek = False
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        yakalamadan_gizle(int(self.winId()))   # (uygulama geneli süzgeç de yapar; testler için)
        self._zamanlayici.start(sure_ms or (self.EYLEMLI_SURE_MS if etkilesimli else self.SURE_MS))

    def _eyleme_basildi(self) -> None:
        fn, self._eylem_fn = self._eylem_fn, None
        self.hide()
        if fn is not None:
            fn()

    def enterEvent(self, e):
        self._zamanlayici.stop()
        self._anim.stop()
        self._gizlenecek = False
        self.setWindowOpacity(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._zamanlayici.start(1500)
        super().leaveEvent(e)

    def _sondur(self) -> None:
        self._gizlenecek = True
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _anim_bitti(self) -> None:
        if self._gizlenecek:
            self.hide()


def bildirim_rengi(mesaj: str) -> None:
    """Eski sürümle uyum: bildirimler artık tek renk gri."""
    return None
