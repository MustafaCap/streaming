"""Tasarım kuralları: renkler tek yerde, simgeler çizilebiliyor, her pencere yakalamadan gizleniyor."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def uygulama():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _kontrast(a: str, b: str) -> float:
    def l(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    x, y = sorted((l(a), l(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def test_yazi_renkleri_zeminlerde_en_az_4_5_kontrast():
    from ui.theme import RENK
    for yazi in ("yazi", "yazi2", "soluk"):
        for zemin in ("zemin", "panel", "yuzen"):
            assert _kontrast(RENK[yazi], RENK[zemin]) >= 4.5, (yazi, zemin)


def test_renk_sadece_kayit_noktasi_ve_ses_cizgisinde():
    from ui.theme import RENK
    assert RENK["kayit"] == "#e5484d" and RENK["ses"] == "#10b981"
    import re
    renkli = []
    for ad, deger in RENK.items():
        r, g, b = (int(deger[i:i + 2], 16) for i in (1, 3, 5))
        if max(r, g, b) - min(r, g, b) > 24:
            renkli.append(ad)
    assert sorted(renkli) == ["kapat", "kayit", "ses"]
    assert re  # gri dışında renk yok


def test_simgeler_cizilir_kapali_hali_farkli(uygulama):
    from ui.icons import SIMGELER, simge_pixmap
    for ad in SIMGELER:
        pm = simge_pixmap(ad, "#e4e4e7", 18)
        assert not pm.isNull()
    acik = simge_pixmap("mikrofon", "#e4e4e7", 18).toImage()
    kapali = simge_pixmap("mikrofon", "#e4e4e7", 18, cizgili=True).toImage()
    assert acik != kapali


def test_gosterilen_her_pencere_yakalamadan_gizlenir(uygulama):
    from ui.gizlilik import PencereGizleyici
    gizlenen = []
    g = PencereGizleyici(gizle=gizlenen.append)
    uygulama.installEventFilter(g)
    try:
        w = QtWidgets.QWidget()
        w.show()
        menu = QtWidgets.QMenu()
        menu.addAction("deneme")
        menu.popup(w.pos())
        uygulama.processEvents()
        # (offscreen eklentisi açılır menünün tutamacını sonradan değiştirebiliyor; sayıya bak)
        assert int(w.winId()) in gizlenen and len(set(gizlenen)) >= 2
        cocuk = QtWidgets.QPushButton(w)
        cocuk.show()
        assert len([h for h in gizlenen if h == int(w.winId())]) >= 1
        menu.close()
        w.close()
    finally:
        uygulama.removeEventFilter(g)


def test_yeni_pencereler_de_yakalamadan_gizlenir(uygulama, tmp_path, monkeypatch):
    """Yardım, Ayarlar ve Hakkında pencereleri de (gösterildiği an) ekran yakalamaya girmez."""
    from core import paths
    from core.settings import Ayarlar
    from ui.gizlilik import PencereGizleyici
    from ui.hakkinda import HakkindaPenceresi
    from ui.settings_dialog import AyarlarPenceresi
    from ui.yardim import YardimPenceresi
    monkeypatch.setattr(paths, "ayar_dosyasi", lambda: tmp_path / "settings.json")
    gizlenen = []
    g = PencereGizleyici(gizle=gizlenen.append)
    uygulama.installEventFilter(g)
    try:
        for pencere in (YardimPenceresi("Sanal mikrofon bulunamadı"), AyarlarPenceresi(Ayarlar()),
                        HakkindaPenceresi()):
            pencere.show()
            uygulama.processEvents()
            assert int(pencere.winId()) in gizlenen, type(pencere).__name__
            pencere.close()
    finally:
        uygulama.removeEventFilter(g)
