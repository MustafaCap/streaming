"""Mini mod: ekran kenarında sürüklenebilir, her zaman üstte duran küçük çubuk.

Durum (CANLI/KAPALI/PANİK, kayıt süresi), Yayın, Kayıt, Mikrofon, Ses, Kamera, Kare,
Kalem, Panik ve ana pencereye dönüş.
Küçük kalsın diye düğmelerde sadece simge var; adı ve kısayolu fareyle üstüne
gelince görünür. Ekran yakalamaya girmez.
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
        ("cikis.ac_kapat", "📡", "Yayın"),
        ("kayit.ac_kapat", "⏺", "Kayıt"),
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
            QWidget#mini {{ background: #20242D; border-radius: 14px; }}
            QPushButton {{ background: {RENK['zemin']}; border: 1px solid {RENK['kenarlik']}; border-radius: 7px;
                           padding: 2px 4px; font-size: 14px; min-width: 28px; min-height: 24px; }}
            QPushButton:hover {{ border-color: {RENK['vurgu']}; }}
            QLabel#durum {{ font-size: 10px; font-weight: 700; background: transparent; padding: 0 2px; }}
        """)
        kap = QWidget(self, objectName="mini")
        self._kap = kap
        satir = QHBoxLayout(kap)
        satir.setContentsMargins(8, 5, 8, 5)
        satir.setSpacing(3)

        # Durum: yayın açık/kapalı, panik, kayıt — renkli ve yazılı (tek bakışta görünsün)
        durum_kutu = QVBoxLayout()
        durum_kutu.setSpacing(0)
        self.nokta = QLabel("●", objectName="durum")
        self.nokta.setToolTip("Yayın durumu")
        self.nokta.setAlignment(Qt.AlignCenter)
        self.durum_yazisi = QLabel("KAPALI", objectName="durum")
        self.durum_yazisi.setAlignment(Qt.AlignCenter)
        durum_kutu.addWidget(self.nokta)
        durum_kutu.addWidget(self.durum_yazisi)
        satir.addLayout(durum_kutu)
        satir.addSpacing(4)

        tuslar = (ayarlar.al("hotkeys", {}) if ayarlar is not None else {}) or {}
        self.dugmeler = {}
        # Küçük kalsın diye sadece simge; adı ve kısayol tuşu fareyle üstüne gelince görünür.
        for komut, simge, ad in self.DUGMELER:
            d = QPushButton(simge)
            d.setProperty("ad", f"{ad}" + (f" · {tus_metni(tuslar[komut])}" if tuslar.get(komut) else ""))
            d.setToolTip(d.property("ad"))
            d.setFocusPolicy(Qt.NoFocus)
            d.clicked.connect(lambda _=False, k=komut: komutlar.calistir(k))
            satir.addWidget(d)
            self.dugmeler[komut] = d

        satir.addSpacing(3)
        don = QPushButton("⤢")
        don.setToolTip("Ana pencereye dön (çubuğa çift tıklamak da olur)")
        don.setFocusPolicy(Qt.NoFocus)
        don.clicked.connect(self.ana_pencere_istendi.emit)
        satir.addWidget(don)

        dis = QHBoxLayout(self)
        dis.setContentsMargins(6, 6, 6, 6)   # gölge için yer
        dis.addWidget(kap)
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        golge = QGraphicsDropShadowEffect(kap)
        golge.setBlurRadius(12)
        golge.setOffset(0, 3)
        golge.setColor(QColor(0, 0, 0, 170))
        kap.setGraphicsEffect(golge)
        self._cerceve_rengi(RENK["kenarlik"])
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

    def _cerceve_rengi(self, renk: str) -> None:
        self._kap.setStyleSheet(f"QWidget#mini {{ background: #20242D; border: 2px solid {renk}; border-radius: 14px; }}")

    def durumu_goster(self, d) -> None:
        kayitta = getattr(d, "kayit", "kapalı") == "açık"
        if d.panik:
            renk, yazi = RENK["panik"], "PANİK"
        elif d.cikis_acik:
            renk, yazi = RENK["acik"], "CANLI"
        else:
            renk, yazi = RENK["yazi2"], "KAPALI"
        metin = f'<span style="color:{renk}">{yazi}</span>'
        if kayitta:
            sn = int(getattr(d, "kayit_suresi", 0) or 0)
            metin += f'<br><span style="color:{RENK["kapali"]}">REC {sn // 60:02d}:{sn % 60:02d}</span>'
        self.nokta.setStyleSheet(f"color: {renk}; font-size: 11px;")
        self.durum_yazisi.setText(metin)
        self._cerceve_rengi(RENK["kapali"] if kayitta and not d.panik else renk)
        acik = {
            "cikis.ac_kapat": d.cikis_acik,
            "kayit.ac_kapat": kayitta,
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
                d_.setToolTip(f"{d_.property('ad')}: {'Açık' if a else 'Kapalı'}")
                d_.setStyleSheet(f"color: {RENK['acik'] if a else RENK['kapali']};")
            else:
                renk = {"panik": RENK["panik"], "cikis.ac_kapat": RENK["acik"],
                        "kayit.ac_kapat": RENK["kapali"]}.get(komut, RENK["vurgu"]) if a else RENK["yazi"]
                d_.setStyleSheet(f"color: {renk}; border-color: {renk if a else 'transparent'};")
