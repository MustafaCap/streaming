"""Mini mod: ekran kenarında sürüklenebilir, her zaman üstte duran küçük çubuk.

Durum noktası, Mikrofon, Ses, Kamera, Kare, Kalem, Panik ve ana pencereye dönüş.
Her düğmenin altında kısayol tuşu yazar. Ekran yakalamaya girmez.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.hotkeys import tus_metni
from core.platform_win import yakalamadan_gizle
from ui.theme import QSS, RENK


class MiniCubuk(QWidget):
    ana_pencere_istendi = Signal()

    DUGMELER = [  # komut, simge, ad
        ("ses.mikrofon", "🎙", "Mik"),
        ("ses.sistem", "🔊", "Ses"),
        ("kamera.ac_kapat", "📷", "Kamera"),
        ("bolge.sec", "⛶", "Kare"),
        ("kalem.ac_kapat", "✎", "Kalem"),
        ("panik", "⚠", "Panik"),
    ]

    def __init__(self, komutlar, hat, ayarlar):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.komutlar, self.hat, self.ayarlar = komutlar, hat, ayarlar
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(QSS + f"""
            QWidget#mini {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']}; border-radius: 12px; }}
            QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
                           padding: 4px 6px; font-size: 16px; min-width: 44px; }}
            QPushButton:hover {{ border-color: {RENK['kenarlik']}; }}
            QLabel#tus {{ color: {RENK['yazi2']}; font-size: 10px; background: transparent; }}
        """)
        kap = QWidget(self, objectName="mini")
        satir = QHBoxLayout(kap)
        satir.setContentsMargins(10, 6, 10, 6)
        satir.setSpacing(2)

        self.nokta = QLabel("●")
        self.nokta.setToolTip("Yayın durumu")
        self.nokta.setStyleSheet("font-size: 16px; background: transparent;")
        satir.addWidget(self.nokta)
        satir.addSpacing(6)

        tuslar = (ayarlar.al("hotkeys", {}) if ayarlar is not None else {}) or {}
        self.dugmeler = {}
        for komut, simge, ad in self.DUGMELER:
            kutu = QVBoxLayout()
            kutu.setSpacing(0)
            d = QPushButton(simge)
            d.setToolTip(ad)
            d.setFocusPolicy(Qt.NoFocus)
            d.clicked.connect(lambda _=False, k=komut: komutlar.calistir(k))
            tus = QLabel(tus_metni(tuslar[komut]) if tuslar.get(komut) else ad, objectName="tus")
            tus.setAlignment(Qt.AlignCenter)
            kutu.addWidget(d)
            kutu.addWidget(tus)
            satir.addLayout(kutu)
            self.dugmeler[komut] = d

        satir.addSpacing(6)
        don = QPushButton("⤢")
        don.setToolTip("Ana pencereye dön")
        don.setFocusPolicy(Qt.NoFocus)
        don.clicked.connect(self.ana_pencere_istendi.emit)
        kutu = QVBoxLayout()
        kutu.setSpacing(0)
        kutu.addWidget(don)
        e = QLabel("Pencere", objectName="tus")
        e.setAlignment(Qt.AlignCenter)
        kutu.addWidget(e)
        satir.addLayout(kutu)

        dis = QHBoxLayout(self)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.addWidget(kap)
        self.adjustSize()
        self._surukle: QPoint | None = None
        self._konumu_yukle()

    def _konumu_yukle(self) -> None:
        g = QGuiApplication.primaryScreen().availableGeometry()
        konum = self.ayarlar.al("ui.mini_pos", None) if self.ayarlar is not None else None
        if isinstance(konum, list) and len(konum) == 2:
            nokta = QPoint(int(konum[0]), int(konum[1]))
            if any(e.availableGeometry().contains(nokta) for e in QGuiApplication.screens()):
                self.move(nokta)
                return
        self.move(g.x() + (g.width() - self.width()) // 2, g.bottom() - self.height() - 60)

    def goster(self) -> None:
        self.show()
        yakalamadan_gizle(int(self.winId()))
        self.raise_()

    # ---- sürükleme

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._surukle = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._surukle is not None:
            self.move(e.globalPosition().toPoint() - self._surukle)

    def mouseReleaseEvent(self, e):
        if self._surukle is not None and self.ayarlar is not None:
            self.ayarlar.ayarla("ui.mini_pos", [self.x(), self.y()])
            self.ayarlar.kaydet()
        self._surukle = None

    def mouseDoubleClickEvent(self, e):
        self.ana_pencere_istendi.emit()

    # ---- durum

    def durumu_goster(self, d) -> None:
        self.nokta.setStyleSheet(f"font-size: 16px; background: transparent; color: "
                                 f"{RENK['panik'] if d.panik else (RENK['acik'] if d.cikis_acik else RENK['yazi2'])};")
        acik = {
            "ses.mikrofon": not d.mikrofon_sessiz,
            "ses.sistem": not d.sistem_sessiz,
            "kamera.ac_kapat": self.hat.kamera_istegi,
            "bolge.sec": bool(d.bolge),
            "kalem.ac_kapat": d.kalem_acik,
            "panik": d.panik,
        }
        for komut, d_ in self.dugmeler.items():
            a = acik[komut]
            d_.setEnabled(self.komutlar.var_mi(komut))
            if komut in ("ses.mikrofon", "ses.sistem", "kamera.ac_kapat"):
                # renk tek başına anlatmasın: kapalıyken simgenin yanında ✕
                simge = next(s for k, s, _ in self.DUGMELER if k == komut)
                d_.setText(simge if a else f"{simge}✕")
                d_.setToolTip(f"{d_.toolTip().split(':')[0]}: {'Açık' if a else 'Kapalı'}")
                d_.setStyleSheet(f"color: {RENK['acik'] if a else RENK['kapali']};")
            else:
                renk = (RENK["panik"] if komut == "panik" else RENK["vurgu"]) if a else RENK["yazi"]
                d_.setStyleSheet(f"color: {renk}; border-color: {renk if a else 'transparent'};")
