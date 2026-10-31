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
QPushButton#buyuk[acik="true"] {{ border-color: {RENK['acik']}; color: {RENK['acik']}; }}
"""


def rozet_stili(durum: str) -> str:
    renk = {"açık": RENK["acik"], "çalışıyor": RENK["acik"],
            "yok": RENK["kapali"], "hata": RENK["kapali"], "koptu": RENK["kapali"]}.get(durum, RENK["yazi2"])
    return f"background: {renk}22; color: {renk}; border: 1px solid {renk};"
