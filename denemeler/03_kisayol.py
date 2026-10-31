"""Deneme 3: Global kısayollar (uygulama arka plandayken ve oyun açıkken).

Ne deniyoruz?
  - Win32 RegisterHotKey ile F tuşları oyun açıkken de yakalanıyor mu?
  - "Sadece kalem açıkken yakala" fikri: F7'ye basınca 1 tuşu kaydedilir,
    tekrar basınca kaydı silinir. Kayıt yokken 1 tuşu normal şekilde oyuna gitmeli.

Tuşlar:
  F6, F8      -> bip sesi + konsola yazı
  F7          -> "kalem modu" aç/kapat (1 tuşunu kaydeder / bırakır)
  1           -> sadece kalem modu açıkken yakalanır
  Ctrl+Shift+Q -> çıkış

Çalıştırma:
  python 03_kisayol.py
  Sonra bir oyunu aç ve tuşlara bas. Bip sesini duyuyorsan çalışıyor demektir.
  Oyun yönetici olarak çalışıyorsa, bu scripti de yönetici olarak açman gerekebilir;
  bunu da dene ve sonucu not et.
"""

import sys
import ctypes
import winsound
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]

WM_HOTKEY = 0x0312
MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0002, 0x0004, 0x4000
VK_F6, VK_F7, VK_F8, VK_1, VK_Q = 0x75, 0x76, 0x77, 0x31, 0x51

ID_F6, ID_F7, ID_F8, ID_1, ID_CIKIS = 1, 2, 3, 4, 99


def kaydet(kimlik, mod, vk, ad):
    if user32.RegisterHotKey(None, kimlik, mod | MOD_NOREPEAT, vk):
        print(f"  [+] {ad} kaydedildi")
        return True
    print(f"  [!] {ad} kaydedilemedi (başka bir uygulama kullanıyor olabilir)")
    return False


def main():
    # Türkçe karakterler her konsolda/yönlendirmede düzgün çıksın
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    print("Kısayollar kaydediliyor:")
    kaydet(ID_F6, 0, VK_F6, "F6")
    kaydet(ID_F7, 0, VK_F7, "F7 (kalem modu)")
    kaydet(ID_F8, 0, VK_F8, "F8")
    kaydet(ID_CIKIS, MOD_CONTROL | MOD_SHIFT, VK_Q, "Ctrl+Shift+Q (çıkış)")
    print("\nŞimdi bir oyun aç ve tuşlara bas. Çıkış: Ctrl+Shift+Q\n")

    kalem_acik = False
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message != WM_HOTKEY:
                continue
            kimlik = msg.wParam
            if kimlik == ID_CIKIS:
                break
            elif kimlik == ID_F6:
                print("F6 basıldı (kare seç)")
                winsound.Beep(800, 80)
            elif kimlik == ID_F8:
                print("F8 basıldı (mikrofon)")
                winsound.Beep(1000, 80)
            elif kimlik == ID_F7:
                kalem_acik = not kalem_acik
                if kalem_acik:
                    kaydet(ID_1, 0, VK_1, "1 tuşu")
                    print("Kalem AÇIK: 1 tuşu artık bu uygulamaya geliyor, oyuna gitmez.")
                    winsound.Beep(1200, 60); winsound.Beep(1500, 60)
                else:
                    user32.UnregisterHotKey(None, ID_1)
                    print("Kalem KAPALI: 1 tuşu tekrar normal şekilde oyuna gidiyor.")
                    winsound.Beep(1500, 60); winsound.Beep(1200, 60)
            elif kimlik == ID_1:
                print("1 basıldı (kalem türü: kalem)")
                winsound.Beep(600, 80)
    finally:
        for k in (ID_F6, ID_F7, ID_F8, ID_1, ID_CIKIS):
            user32.UnregisterHotKey(None, k)
        print("Kısayollar bırakıldı, çıkılıyor.")


if __name__ == "__main__":
    main()
