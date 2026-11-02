"""Simgeler: ince çizgili SVG simgeler (dosya gerektirmez) ve uygulama simgesi.

Simge çizimleri Lucide simge setinin çizgi diliyle aynı (ISC lisansı, GPLv3 ile uyumlu):
24×24 alan, 1.75 kalınlık, yuvarlak uçlar. Renk çağıran tarafından verilir; arayüz tek renk
gri olduğu için simgeler de gridir. Kapalı durumda simgenin üstüne çapraz çizgi eklenir
(renk tek başına durum anlatmasın).
"""

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from ui.theme import RENK

CIZGI = 'fill="none" stroke="currentColor" stroke-width="{k}" stroke-linecap="round" stroke-linejoin="round"'

SIMGELER = {
    "mikrofon": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
                '<path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
    "ses": '<path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/>',
    "kamera": '<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 10.5"/>'
              '<rect x="2" y="6" width="14" height="12" rx="2"/>',
    "bolge": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
    "kalem": '<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "fosforlu": '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    "ok": '<path d="M7 17 17 7M8 7h9v9"/>',
    "kare": '<rect x="4" y="6" width="16" height="12" rx="1.5"/>',
    "yazi": '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "lazer": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1'
             'M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "silgi": '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/>'
             '<path d="M22 21H7"/>',
    "temizle": '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
    "foto": '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/>'
            '<circle cx="12" cy="13.5" r="3.5"/>',
    "kayit": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
    "duraklat": '<path d="M8 5v14M16 5v14" stroke-width="3"/>',
    "oynat": '<path d="M7 4.5l13 7.5-13 7.5Z" fill="currentColor" stroke="none"/>',
    "bitir": '<rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/>',
    "ileri": '<path d="M9 6l6 6-6 6" stroke-width="2"/>',
    "geri": '<path d="M15 6l-6 6 6 6" stroke-width="2"/>',
    "asagi": '<path d="m6 9 6 6 6-6" stroke-width="2"/>',
    "arti": '<path d="M12 5v14M5 12h14" stroke-width="2"/>',
    "kapat": '<path d="M6 6l12 12M18 6 6 18"/>',
    "ayarlar": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "kucult": '<path d="M5 12h14"/>',
    "buyut": '<rect x="4" y="4" width="16" height="16" rx="2"/>',
    "geri_yukle": '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2"/>',
    "goz": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><path d="M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/>',
    "goz_kapali": '<path d="M2 12s3-7 10-7c1.6 0 3 .4 4.2 1M22 12s-3 7-10 7c-1.6 0-3-.4-4.2-1M3 3l18 18"/>',
}

CAPRAZ = {"kamera": '<path d="M2 2l20 20"/>'}
VARSAYILAN_CAPRAZ = '<path d="M3 3l18 18"/>'


def svg(ad: str, renk: str, cizgili: bool = False, kalinlik: float = 1.75) -> bytes:
    govde = SIMGELER[ad] + ((CAPRAZ.get(ad, VARSAYILAN_CAPRAZ)) if cizgili else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="{renk}" '
            f'{CIZGI.format(k=kalinlik)}>{govde.replace("currentColor", renk)}</svg>').replace(
        'stroke="currentColor"', f'stroke="{renk}"').encode()


@lru_cache(maxsize=512)
def _pixmap(ad: str, renk: str, boyut: int, cizgili: bool, dpr: float) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer
    px = max(1, round(boyut * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    r = QSvgRenderer(QByteArray(svg(ad, renk, cizgili)))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def simge_pixmap(ad: str, renk: str | None = None, boyut: int = 18, cizgili: bool = False,
                 dpr: float = 2.0) -> QPixmap:
    return _pixmap(ad, renk or RENK["yazi"], boyut, cizgili, dpr)


def simge(ad: str, renk: str | None = None, boyut: int = 18, cizgili: bool = False) -> QIcon:
    """QIcon: simge('mikrofon'), kapalıyken simge('mikrofon', RENK['yazi2'], cizgili=True)."""
    icon = QIcon()
    for dpr in (1.0, 1.5, 2.0):
        icon.addPixmap(simge_pixmap(ad, renk, boyut, cizgili, dpr))
    return icon


def logo_pixmap(boyut: int = 64) -> QPixmap:
    """RizeOn logosu (koyu yuvarlak kare içinde "RO" ve köşe çerçevesi)."""
    return QPixmap(_logo(boyut))   # kopya: önbellekteki değişmesin


@lru_cache(maxsize=16)
def _logo(boyut: int) -> QPixmap:
    import base64
    from ui.logo_veri import PNG_BASE64
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(PNG_BASE64), "PNG")
    if boyut != pm.width():
        pm = pm.scaled(boyut, boyut, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pm


def uygulama_ikonu(canli: bool = False, boyut: int = 64) -> QIcon:
    """Pencere, görev çubuğu ve tepsi simgesi: RizeOn logosu.

    canli: eski sürümlerle uyum için duruyor; simge değişmez.
    """
    ikon = QIcon()
    for b in (16, 20, 24, 32, 48, 64, 128, 256):
        ikon.addPixmap(_logo(b))
    return ikon
