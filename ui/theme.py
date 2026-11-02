"""Tasarım kuralları: renkler, yazı ve ölçüler tek yerde (saf PySide6 + QSS).

Arayüz tek renk gri. Renk sadece anlam taşıdığı iki yerde var:
  - kayıt kırmızısı : yalnızca kayıt sürerken küçük nokta (duraklatınca gri olur)
  - ses yeşili      : yalnızca canlı ses seviyesi çizgileri (VU)
Kapalı durumlar (mikrofon/kamera kapalı) kırmızı değil: sönük gri zemin + çapraz çizgili simge.
Çizim renkleri (beyaz, kırmızı, sarı, mavi) kullanıcının içeriğidir, bu kurala girmez.

Gri tonlar #141417 / #1a1a1e zemin üzerinde en az 4.5:1 kontrast verir; daha soluk gri kullanma.
"""

from PySide6.QtGui import QColor

RENK = {
    "zemin": "#141417",       # ana pencere
    "panel": "#1a1a1e",       # sahneler, kaynaklar, mikser, anahtarlar, kontrol barı
    "yuzen": "#1f1f23",       # mini bar, kalem barı, açılır menüler, bildirimler
    "onizleme": "#1c1c20",    # önizleme boşken
    "iz": "#26262b",          # sürgü ve seviye çizgisinin boş kısmı
    "yazi": "#e4e4e7",        # ana yazı
    "yazi2": "#a1a1aa",       # başlıklar, etiketler
    "soluk": "#8b8b94",       # açıklamalar, kısayol ipuçları
    "nokta": "#71717a",       # tutma yeri noktaları, duraklatılmış kayıt noktası (yazı değil)
    "dugme": "#d4d4d8",       # başlık çubuğundaki yazılı düğmeler, sürgü tutamağı
    "beyaz": "#ffffff",       # seçili / üzerine gelinen yazı
    "kayit": "#e5484d",       # YALNIZCA kayıt sürerken küçük nokta
    "ses": "#10b981",         # YALNIZCA canlı ses seviyesi çizgileri
    "kapat": "#c42b1c",       # pencere kapat düğmesi üzerine gelince (Windows standardı)
}
# Eski adlar (yeni arayüze geçmemiş kod için; hepsi gri)
RENK.update({"vurgu": RENK["yazi"], "acik": RENK["yazi"], "kapali": RENK["yazi2"], "panik": RENK["yazi"],
             "kenarlik": "#2a2a2f"})

# Saydam beyaz katmanlar (alfa 0..1): kenarlık, üzerine gelme, seçili
ALFA = {
    "kenarlik_ince": 0.06,
    "kenarlik": 0.08,
    "kenarlik_menu": 0.10,
    "uzerine": 0.07,
    "seçili": 0.10,
    "kapali": 0.07,
    "grup": 0.05,
}

YAZI_TIPI = '"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
YAZI_AILESI = ["Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI"]
GOVDE_PX, KUCUK_PX, EN_KUCUK_PX = 13, 12, 11

YARICAP = {"pencere": 8, "panel": 12, "karo": 8, "menu": 10}
KARO = (76, 60)               # kontrol barı karosu (genişlik, yükseklik)
DUGME = 36                    # simge düğmesi (tıklanabilir alan en az 36 px)


def beyaz(alfa: float) -> str:
    """QSS için saydam beyaz: 'rgba(255, 255, 255, a)' (Qt'de a 0..255)."""
    return f"rgba(255, 255, 255, {round(alfa * 255)})"


def saydam(renk: str, alfa: float) -> str:
    """'#RRGGBB' -> 'rgba(r, g, b, a)'. (Qt'de 8 haneli hex #AARRGGBB demektir, karışmasın.)"""
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {round(alfa * 255)})"


def qrenk(ad: str, alfa: float | None = None) -> QColor:
    """Boyama için QColor: qrenk('panel') ya da qrenk('beyaz', 0.08)."""
    c = QColor(RENK[ad])
    if alfa is not None:
        c.setAlphaF(alfa)
    return c


def yazi_tipi(px: int = GOVDE_PX, kalin: bool = False):
    from PySide6.QtGui import QFont
    f = QFont()
    f.setFamilies(YAZI_AILESI)
    f.setPixelSize(px)
    if kalin:
        f.setWeight(QFont.DemiBold)
    return f


_K = beyaz(ALFA["kenarlik"])
_KI = beyaz(ALFA["kenarlik_ince"])
_KM = beyaz(ALFA["kenarlik_menu"])
_U = beyaz(ALFA["uzerine"])
_S = beyaz(ALFA["seçili"])

QSS = f"""
QWidget {{ background: transparent; color: {RENK['yazi']}; font-family: {YAZI_TIPI}; font-size: {GOVDE_PX}px; }}
QMainWindow, QDialog, QWidget#kok {{ background: {RENK['zemin']}; }}
QFrame#panel {{ background: {RENK['panel']}; border: 1px solid {_KI}; border-radius: {YARICAP['panel']}px; }}
QFrame#kontrolBari {{ background: {RENK['panel']}; border: 1px solid {_KI}; border-radius: {YARICAP['panel']}px; }}
QFrame#ayrac {{ background: {_K}; border: none; }}
QFrame#kayitGrubu {{ background: {beyaz(ALFA['grup'])}; border: none; border-radius: {YARICAP['karo']}px; }}

QLabel {{ background: transparent; }}
QLabel#baslik {{ color: {RENK['yazi2']}; font-size: {KUCUK_PX}px; }}
QLabel#ikincil {{ color: {RENK['yazi2']}; font-size: {KUCUK_PX}px; }}
QLabel#soluk {{ color: {RENK['soluk']}; font-size: {EN_KUCUK_PX}px; }}
QLabel#hata {{ color: {RENK['yazi']}; font-size: {KUCUK_PX}px; }}
QLabel#onizleme {{ background: {RENK['onizleme']}; border-radius: {YARICAP['pencere']}px; }}
QLabel#cip {{ background: {RENK['yuzen']}; color: {RENK['yazi']}; border: 1px solid {_K};
              border-radius: 11px; padding: 2px 10px; font-size: {KUCUK_PX}px; }}

QPushButton {{ background: transparent; border: none; border-radius: 14px; color: {RENK['dugme']};
              padding: 0 12px; min-height: 28px; font-size: {KUCUK_PX}px; }}
QPushButton:hover {{ background: {_U}; color: {RENK['beyaz']}; }}
QPushButton:checked {{ background: {_S}; color: {RENK['beyaz']}; }}
QPushButton:disabled {{ color: {RENK['soluk']}; }}
QPushButton:focus {{ outline: none; }}
QPushButton#cerceveli {{ border: 1px solid {_K}; border-radius: 16px; min-height: 30px; color: {RENK['yazi']}; }}
QPushButton#baglanti {{ color: {RENK['yazi2']}; border-radius: 11px; min-height: 22px; padding: 0 8px;
                       font-size: {EN_KUCUK_PX}px; }}
QPushButton#baglanti:hover {{ color: {RENK['beyaz']}; }}
QPushButton#dialog {{ border: 1px solid {_K}; border-radius: 8px; min-height: 32px; padding: 0 16px; color: {RENK['yazi']}; }}
QPushButton#dialog:default {{ background: {_S}; }}

QToolTip {{ background: {RENK['yuzen']}; color: {RENK['yazi']}; border: 1px solid {_KM};
            border-radius: 6px; padding: 4px 8px; font-size: {KUCUK_PX}px; }}

QMenu {{ background: {RENK['yuzen']}; border: 1px solid {_KM}; border-radius: {YARICAP['menu']}px; padding: 4px; }}
QMenu::item {{ background: transparent; color: {RENK['yazi']}; padding: 0 12px; min-height: 36px;
               border-radius: 6px; }}
QMenu::item:selected {{ background: {_U}; color: {RENK['beyaz']}; }}
QMenu::item:disabled {{ color: {RENK['soluk']}; }}
QMenu::item:checked {{ background: {_S}; }}
QMenu::indicator {{ width: 0; height: 0; }}
QMenu::separator {{ height: 1px; background: {_K}; margin: 4px 6px; }}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QKeySequenceEdit, QPlainTextEdit {{
    background: {RENK['panel']}; border: 1px solid {_K}; border-radius: 6px; padding: 4px 8px; min-height: 26px;
    selection-background-color: {beyaz(0.2)}; }}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: {beyaz(0.16)}; }}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border-color: {beyaz(0.3)}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {RENK['yuzen']}; border: 1px solid {_KM}; outline: none;
                               selection-background-color: {_U}; padding: 4px; }}

QSlider {{ min-height: 20px; }}
QSlider::groove:horizontal {{ height: 4px; background: {RENK['iz']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {RENK['nokta']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {RENK['dugme']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {RENK['beyaz']}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {beyaz(0.14)}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {beyaz(0.14)}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: 1px solid {_KI}; border-radius: {YARICAP['karo']}px; top: -1px; background: {RENK['panel']}; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {RENK['yazi2']}; border-radius: 6px; }}
QTabBar::tab:hover {{ background: {_U}; color: {RENK['beyaz']}; }}
QTabBar::tab:selected {{ background: {_S}; color: {RENK['beyaz']}; }}

QTableWidget, QListWidget {{ background: {RENK['panel']}; gridline-color: {_KI}; border: 1px solid {_KI};
                             border-radius: 6px; outline: none; }}
QListWidget::item {{ min-height: 36px; padding: 0 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {_U}; }}
QListWidget::item:selected {{ background: {_S}; color: {RENK['beyaz']}; }}
QTableWidget::item:selected {{ background: {_S}; color: {RENK['beyaz']}; }}
QHeaderView::section {{ background: {RENK['zemin']}; color: {RENK['yazi2']}; border: none; padding: 6px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {beyaz(0.3)}; background: transparent; }}
QCheckBox::indicator:checked {{ background: {RENK['dugme']}; border-color: {RENK['dugme']}; }}
QRadioButton {{ spacing: 8px; }}
"""


def rozet_stili(durum: str) -> str:
    """Eski ana pencere için (2. aşamada kalkar)."""
    return f"background: {RENK['yuzen']}; color: {RENK['yazi']}; border: 1px solid {beyaz(ALFA['kenarlik'])};"
