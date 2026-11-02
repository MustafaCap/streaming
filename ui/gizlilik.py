"""Uygulamanın kendi pencereleri karşı tarafa görünmez.

Her üst düzey pencere (ana pencere, mini bar, menüler, kalem barı, bildirimler, ayarlar,
açılır listeler, ipuçları, iletişim kutuları) ekranda görünür ama ekran yakalamaya girmez.
Tek tek her pencereye eklemek yerine uygulama genelinde bir olay süzgeci kullanılır: bir
pencere gösterildiği an yakalamadan gizlenir. Böylece ileride eklenen bir pencere de unutulmaz.
"""

from PySide6.QtCore import QEvent, QObject

from core.platform_win import yakalamadan_gizle


class PencereGizleyici(QObject):
    def __init__(self, gizle=yakalamadan_gizle):
        super().__init__()
        self._gizle = gizle
        self.gizlenenler = 0   # testler için

    def eventFilter(self, nesne, olay):
        if olay.type() == QEvent.Show and nesne.isWidgetType() and nesne.isWindow():
            try:
                self._gizle(int(nesne.winId()))
                self.gizlenenler += 1
            except Exception:
                pass
        return False


def kur(app) -> PencereGizleyici:
    """main() QApplication'ı kurunca bir kez çağırır."""
    g = PencereGizleyici()
    app.installEventFilter(g)
    app._pencere_gizleyici = g   # çöp toplayıcı silmesin
    return g
