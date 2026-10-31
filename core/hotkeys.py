"""Global kısayollar (uygulama arka plandayken ve tam ekran oyunda da çalışır).

Windows'un RegisterHotKey özelliği kullanılır (Aşama 0, deneme 3'te oyun açıkken,
yönetici izni olmadan çalıştığı doğrulandı). Klavye kancası (keyboard/pynput)
kullanmıyoruz: hem antivirüsler sevmiyor hem de tuşları oyundan çalabiliyor.

Kısayollar settings.json'daki "hotkeys" bölümünden okunur: {"komut adı": "tuş"}.
Tuşlar gruplara ayrılır; ör. "kalem" grubu (1-6, Ctrl+Z, Del) sadece kalem
açıkken kaydedilir, kalem kapalıyken bu tuşlar normal şekilde oyuna gider.

RegisterHotKey, kaydı yapan iş parçacığının mesaj kuyruğuna haber verir;
bu yüzden kendi mesaj döngüsü olan ayrı bir iş parçacığı çalıştırıyoruz.
Kayıt değişiklikleri de o iş parçacığına mesajla iletilir.
"""

import logging
import queue
import sys
import threading

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT, WM_APP = 0x0312, 0x0012, 0x8000

_DEGISTIRICILER = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
                   "shift": MOD_SHIFT, "win": MOD_WIN}
_OZEL_TUSLAR = {
    "del": 0x2E, "delete": 0x2E, "ins": 0x2D, "insert": 0x2D, "enter": 0x0D, "esc": 0x1B,
    "escape": 0x1B, "space": 0x20, "tab": 0x09, "backspace": 0x08, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "printscreen": 0x2C, "scrolllock": 0x91,
}


class GecersizTus(ValueError):
    pass


def tus_coz(metin: str) -> tuple[int, int]:
    """'Ctrl+Shift+R' -> (MOD_CONTROL|MOD_SHIFT, 0x52). Geçersizse GecersizTus."""
    if not metin or not metin.strip():
        raise GecersizTus("Boş tuş")
    parcalar = [p.strip() for p in metin.replace(" ", "").split("+")]
    if any(not p for p in parcalar):
        raise GecersizTus(f"Geçersiz tuş: {metin}")
    mod = 0
    for p in parcalar[:-1]:
        if p.lower() not in _DEGISTIRICILER:
            raise GecersizTus(f"Bilinmeyen değiştirici: {p}")
        mod |= _DEGISTIRICILER[p.lower()]
    tus = parcalar[-1]
    k = tus.lower()
    if len(tus) == 1 and tus.isalnum() and tus.isascii():
        return mod, ord(tus.upper())
    if k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return mod, 0x70 + int(k[1:]) - 1
    if k.startswith("num") and k[3:].isdigit() and len(k) == 4:
        return mod, 0x60 + int(k[3:])
    if k in _OZEL_TUSLAR:
        return mod, _OZEL_TUSLAR[k]
    raise GecersizTus(f"Bilinmeyen tuş: {tus}")


def tus_metni(metin: str) -> str:
    """Bildirimlerde göstermek için düzgün yazım: 'ctrl+1' -> 'Ctrl+1'."""
    parcalar = [p.strip() for p in metin.split("+") if p.strip()]
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in parcalar)


class KisayolYoneticisi:
    """gruplar: {"genel": {"F8": "ses.mikrofon", ...}, "kalem": {...}} biçiminde tuş -> komut.

    basildi(komut_adi) kısayolun iş parçacığından çağrılır; arayüz bunu Qt ana
    iş parçacığına taşımalıdır.
    """

    def __init__(self, basildi):
        self.basildi = basildi
        self._islemler: queue.Queue = queue.Queue()
        self._is: threading.Thread | None = None
        self._tid = 0
        self._hazir = threading.Event()
        self._kayitli: dict[int, tuple[str, str, str]] = {}  # id -> (grup, tuş, komut)
        self._sonraki_id = 1
        self.basarisiz: list[str] = []  # başka program kullandığı için alınamayan tuşlar
        self._kilit = threading.Lock()

    @property
    def destekleniyor(self) -> bool:
        return sys.platform == "win32"

    def baslat(self) -> None:
        if not self.destekleniyor or self._is is not None:
            return
        self._is = threading.Thread(target=self._dongu, name="kisayollar", daemon=True)
        self._is.start()
        self._hazir.wait(2)

    def durdur(self) -> None:
        if self._is is None:
            return
        import ctypes
        ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._is.join(timeout=2)
        self._is = None

    def grup_ayarla(self, grup: str, tuslar: dict[str, str]) -> None:
        """Bir grubun kısayollarını (yeniden) kaydeder. Boş sözlük = grubu kaldır."""
        self._gonder(("grup", grup, dict(tuslar)))

    def grubu_kaldir(self, grup: str) -> None:
        self._gonder(("grup", grup, {}))

    def _gonder(self, islem) -> None:
        if not self.destekleniyor or self._is is None:
            return
        import ctypes
        self._islemler.put(islem)
        ctypes.windll.user32.PostThreadMessageW(self._tid, WM_APP, 0, 0)

    # ---------------- kısayol iş parçacığı

    def _dongu(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                        wintypes.UINT, wintypes.UINT]
        self._tid = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # bu iş parçacığına mesaj kuyruğu açtır
        self._hazir.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    kayit = self._kayitli.get(int(msg.wParam))
                    if kayit:
                        try:
                            self.basildi(kayit[2])
                        except Exception:
                            log.exception("Kısayol işlenirken hata")
                elif msg.message == WM_APP:
                    self._islemleri_yap(user32)
        finally:
            for kimlik in list(self._kayitli):
                user32.UnregisterHotKey(None, kimlik)
            self._kayitli.clear()

    def _islemleri_yap(self, user32) -> None:
        while True:
            try:
                tur, grup, tuslar = self._islemler.get_nowait()
            except queue.Empty:
                return
            if tur != "grup":
                continue
            for kimlik, (g, _, _) in list(self._kayitli.items()):
                if g == grup:
                    user32.UnregisterHotKey(None, kimlik)
                    del self._kayitli[kimlik]
            basarisiz = [b for b in self.basarisiz if not b.startswith(f"{grup}:")]
            for tus, komut in tuslar.items():
                try:
                    mod, vk = tus_coz(tus)
                except GecersizTus as e:
                    log.warning("%s (%s)", e, komut)
                    basarisiz.append(f"{grup}:{tus}")
                    continue
                kimlik = self._sonraki_id
                self._sonraki_id += 1
                if user32.RegisterHotKey(None, kimlik, mod | MOD_NOREPEAT, vk):
                    self._kayitli[kimlik] = (grup, tus, komut)
                else:
                    log.warning("Kısayol alınamadı (başka bir program kullanıyor olabilir): %s", tus)
                    basarisiz.append(f"{grup}:{tus}")
            with self._kilit:
                self.basarisiz = basarisiz


VARSAYILAN_KISAYOLLAR = {
    "bolge.sec": "F6",
    "kalem.ac_kapat": "F7",
    "ses.mikrofon": "F8",
    "ses.sistem": "F9",
    "kamera.ac_kapat": "F10",
    "anlik_kayit.kaydet": "F11",
    "panik": "F12",
    "sahne.sec:1": "Ctrl+1",
    "sahne.sec:2": "Ctrl+2",
    "sahne.sec:3": "Ctrl+3",
    "sahne.sec:4": "Ctrl+4",
    "kayit.ac_kapat": "Ctrl+Shift+R",
}


def gruplara_ayir(ayar: dict, komutlar) -> dict[str, str]:
    """settings.json'daki {komut: tuş} -> {tuş: komut}; olmayan komutlar ve boş tuşlar atlanır.

    Aynı tuş iki komuta verilmişse ilki geçerli olur (uyarı loglanır).
    """
    sonuc: dict[str, str] = {}
    for komut, tus in ayar.items():
        if not tus or not isinstance(tus, str):
            continue
        if komutlar is not None and not komutlar.var_mi(komut):
            continue
        anahtar = tus_metni(tus)
        if anahtar in sonuc:
            log.warning("%s tuşu hem %s hem %s için ayarlı; ilki kullanılacak", anahtar, sonuc[anahtar], komut)
            continue
        sonuc[anahtar] = komut
    return sonuc
