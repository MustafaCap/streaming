"""Brifteki renkler ve koyu tema (saf PySide6 + QSS, QFluentWidgets yok)."""

RENK = {
    "zemin": "#121419",
    "panel": "#1A1D24",
    "kenarlik": "#2A2F3A",
    "yazi": "#E8EAF0",
    "yazi2": "#A3A9B8",
    "vurgu": "#4C9BFF",
    "acik": "#3DD68C",
    "kapali": "#F2555A",
    "panik": "#F5A524",
}

def saydam(renk: str, alfa: float) -> str:
    """'#RRGGBB' -> 'rgba(r, g, b, a)'. (Qt'de 8 haneli hex #AARRGGBB demektir, karışmasın.)"""
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {round(alfa * 255)})"


QSS = f"""
QWidget {{ background: {RENK['zemin']}; color: {RENK['yazi']};
          font-family: "Inter", "Segoe UI", sans-serif; font-size: 14px; }}
QFrame#panel {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']}; border-radius: 10px; }}
QLabel#ikincil {{ color: {RENK['yazi2']}; font-size: 12px; background: transparent; }}
QLabel#baslik {{ font-size: 18px; font-weight: 600; background: transparent; }}
QLabel#hata {{ color: {RENK['kapali']}; background: transparent; }}
QLabel#onizleme {{ background: #000; border: 1px solid {RENK['kenarlik']}; border-radius: 6px; }}
QLabel#rozet {{ border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
QPushButton#buyuk {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']};
                    border-radius: 10px; padding: 14px 28px; font-size: 16px; font-weight: 600; }}
QPushButton#buyuk:hover {{ border-color: {RENK['vurgu']}; }}
QPushButton#sahne {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']};
                    border-radius: 8px; padding: 8px 14px; }}
QPushButton#sahne:hover {{ border-color: {RENK['vurgu']}; }}
QPushButton#sahne:checked {{ border-color: {RENK['vurgu']}; color: {RENK['vurgu']}; background: {saydam(RENK['vurgu'], 0.12)}; }}
QPushButton#kontrol {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']};
                      border-radius: 10px; padding: 6px 8px; font-size: 13px; font-weight: 600; }}
QPushButton#kontrol:hover {{ background: {RENK['kenarlik']}; }}
QPushButton#kontrol:disabled {{ color: #5A6070; }}
QPushButton#liste {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
                    padding: 8px 10px; text-align: left; }}
QPushButton#liste:hover {{ background: {RENK['kenarlik']}; }}
QPushButton#liste:checked {{ border-color: {RENK['vurgu']}; color: {RENK['vurgu']}; background: {saydam(RENK['vurgu'], 0.12)}; }}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {{ background: {RENK['panel']}; border: 1px solid {RENK['kenarlik']};
           border-radius: 6px; padding: 4px 8px; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {RENK['vurgu']}; }}
QTabWidget::pane {{ border: 1px solid {RENK['kenarlik']}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {RENK['yazi2']}; }}
QTabBar::tab:selected {{ color: {RENK['yazi']}; border-bottom: 2px solid {RENK['vurgu']}; }}
QTableWidget {{ background: {RENK['panel']}; gridline-color: {RENK['kenarlik']}; border: none; }}
QHeaderView::section {{ background: {RENK['zemin']}; color: {RENK['yazi2']}; border: none; padding: 6px; }}
QCheckBox {{ background: transparent; }}
QPushButton#buyuk[acik="true"] {{ border-color: {RENK['acik']}; color: {RENK['acik']}; }}
"""


def rozet_stili(durum: str) -> str:
    renk = {"açık": RENK["acik"], "çalışıyor": RENK["acik"],
            "yok": RENK["kapali"], "hata": RENK["kapali"], "koptu": RENK["kapali"]}.get(durum, RENK["yazi2"])
    return f"background: {saydam(renk, 0.13)}; color: {renk}; border: 1px solid {renk};"
