"""Deneme 4: Mikrofon + bilgisayar sesini karıştırıp VB-Cable'a gönder.

Ne deniyoruz?
  - WASAPI loopback ile bilgisayar sesi (oyun, YouTube) yakalanıyor mu?
  - Mikrofonla karıştırılıp "CABLE Input"a verilince Zoom/Discord'da
    "CABLE Output" mikrofonu seçildiğinde karşı taraf ikisini de duyuyor mu?
  - YANKI SORUNU: Zoom'daki karşı tarafın sesi de hoparlörden çıktığı için
    loopback onu da yakalar ve geri gönderir. Bunu kendi kulağınla gör.
    (Çözümü 05 numaralı denemede deniyoruz.)

Çalıştırma:
  python 04_sistem_sesi_vbcable.py --liste      # ses cihazlarını listele
  python 04_sistem_sesi_vbcable.py              # varsayılan mikrofon + varsayılan hoparlör sesi
  python 04_sistem_sesi_vbcable.py --mik 0.8 --sistem 0.5   # seviyeler (0.0 - 2.0)
  python 04_sistem_sesi_vbcable.py --mik 0      # sadece bilgisayar sesi
  python 04_sistem_sesi_vbcable.py --sistem 0   # sadece mikrofon
  python 04_sistem_sesi_vbcable.py --ton        # VB-Cable'a temiz test tonu (sorun nerede?)

  Her çalıştırmada CABLE'a gönderilen sesin ilk 20 saniyesi gonderilen_ses.wav'a yazılır.

Durdurmak için: Ctrl+C
"""

import sys
import argparse
import threading
import time
import wave

import numpy as np
import pyaudiowpatch as pyaudio

ORNEKLEME = 48000
BLOK = 480  # 10 ms
KANAL = 2


class Tampon:
    """Giriş geri çağrılarının yazdığı, çıkışın okuduğu iş parçacığı güvenli tampon.

    Ön tampon: çıkış, içeride en az ON_TAMPON kadar ses birikmeden okumaya başlamaz.
    Tampon boşalırsa (alt taşma) tekrar dolmasını bekler. Bu olmadan her 10 ms'de
    bir sessizlik boşluğu girer ve ses cızırtılı/gürültülü çıkar.
    """

    ON_TAMPON = int(ORNEKLEME * 0.04)  # 40 ms

    def __init__(self, giris_hizi=ORNEKLEME, en_fazla_sn=0.3):
        self.veri = np.zeros((0, KANAL), np.float32)
        self.kilit = threading.Lock()
        self.en_fazla = int(ORNEKLEME * en_fazla_sn)
        self.giris_hizi = giris_hizi
        self.seviye = 0.0
        self.hazir = False
        self.alt_tasma = 0

    def yaz(self, blok: np.ndarray):
        if blok.shape[1] == 1:
            blok = np.repeat(blok, 2, axis=1)
        elif blok.shape[1] > 2:
            blok = blok[:, :2]
        if self.giris_hizi != ORNEKLEME and len(blok) > 1:
            # Basit doğrusal örnekleme hızı dönüştürme (ör. 44100 -> 48000)
            n_yeni = int(round(len(blok) * ORNEKLEME / self.giris_hizi))
            x_eski = np.arange(len(blok))
            x_yeni = np.linspace(0, len(blok) - 1, n_yeni)
            blok = np.stack([np.interp(x_yeni, x_eski, blok[:, k]) for k in range(2)], axis=1).astype(np.float32)
        self.seviye = float(np.abs(blok).max()) if len(blok) else 0.0
        with self.kilit:
            self.veri = np.concatenate([self.veri, blok])[-self.en_fazla:]

    def oku(self, n: int) -> np.ndarray:
        with self.kilit:
            if not self.hazir:
                if len(self.veri) < self.ON_TAMPON:
                    return np.zeros((n, KANAL), np.float32)
                self.hazir = True
            if len(self.veri) < n:  # alt taşma: tamponu yeniden doldurmayı bekle
                self.alt_tasma += 1
                self.hazir = False
                return np.zeros((n, KANAL), np.float32)
            parca, self.veri = self.veri[:n], self.veri[n:]
        return parca


def cihaz_bul(p, isim_parcasi, giris: bool, host_api_adi="MME"):
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        host = p.get_host_api_info_by_index(d["hostApi"])["name"]
        kanal = d["maxInputChannels"] if giris else d["maxOutputChannels"]
        if host == host_api_adi and kanal > 0 and isim_parcasi.lower() in d["name"].lower():
            return d
    return None


def cihazlari_listele(p):
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        host = p.get_host_api_info_by_index(d["hostApi"])["name"]
        print(f"[{i:2}] {host:22} giriş:{d['maxInputChannels']} çıkış:{d['maxOutputChannels']} "
              f"{int(d['defaultSampleRate'])} Hz  {d['name']}")


def cubuk(seviye):
    n = int(min(seviye, 1.0) * 30)
    return "#" * n + "-" * (30 - n)


def main():
    # Türkçe karakterler her konsolda/yönlendirmede düzgün çıksın
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--mik", type=float, default=1.0, help="mikrofon seviyesi (0 = kapalı)")
    ap.add_argument("--sistem", type=float, default=0.7, help="bilgisayar sesi seviyesi (0 = kapalı)")
    ap.add_argument("--ton", action="store_true",
                    help="mikrofon/sistem yerine temiz bir 440 Hz test tonu gönder (VB-Cable'ı tek başına test eder)")
    ap.add_argument("--kayit", type=int, default=20,
                    help="CABLE'a gönderilen sesin ilk kaç saniyesi gonderilen_ses.wav'a yazılsın (0 = yazma)")
    args = ap.parse_args()

    p = pyaudio.PyAudio()
    if args.liste:
        cihazlari_listele(p)
        return

    # Çıkış: VB-Cable (MME, çünkü MME örnekleme hızını kendisi dönüştürür)
    kablo = cihaz_bul(p, "CABLE Input", giris=False)
    if kablo is None:
        print("[HATA] 'CABLE Input' bulunamadı. VB-Cable kurulu mu? (--liste ile kontrol et)")
        return

    loopback = None
    if not args.ton and args.sistem > 0:
        # Bilgisayar sesi: varsayılan hoparlörün loopback'i (WASAPI)
        loopback = p.get_default_wasapi_loopback()
        if "CABLE" in loopback["name"]:
            print("[HATA] Varsayılan hoparlörün VB-Cable olarak ayarlanmış. Bu sonsuz döngü yaratır;")
            print("       Windows ses ayarlarından varsayılan çıkışı gerçek hoparlör/kulaklık yap.")
            return

    mik_tampon = Tampon()
    sistem_tampon = Tampon(giris_hizi=int(loopback["defaultSampleRate"]) if loopback else ORNEKLEME)
    kayit_parcalari, kayit_sinir = [], args.kayit * ORNEKLEME
    kayit_sayac = [0]
    ton_faz = [0]

    def loopback_cb(in_data, frames, t, status):
        blok = np.frombuffer(in_data, np.float32).reshape(-1, loopback["maxInputChannels"])
        sistem_tampon.yaz(blok)
        return (None, pyaudio.paContinue)

    def mik_cb(in_data, frames, t, status):
        mik_tampon.yaz(np.frombuffer(in_data, np.float32).reshape(-1, 1))
        return (None, pyaudio.paContinue)

    def cikis_cb(in_data, frames, t, status):
        if args.ton:
            n = np.arange(ton_faz[0], ton_faz[0] + frames)
            ton_faz[0] += frames
            tek = (0.2 * np.sin(2 * np.pi * 440 * n / ORNEKLEME)).astype(np.float32)
            karisim = np.stack([tek, tek], axis=1)
        else:
            karisim = np.zeros((frames, KANAL), np.float32)
            if args.mik > 0:
                karisim += mik_tampon.oku(frames) * args.mik
            if loopback is not None:
                karisim += sistem_tampon.oku(frames) * args.sistem
            np.clip(karisim, -1.0, 1.0, out=karisim)  # basit sınırlayıcı
        if kayit_sayac[0] < kayit_sinir:
            kayit_parcalari.append(karisim.copy())
            kayit_sayac[0] += frames
        return (karisim.astype(np.float32).tobytes(), pyaudio.paContinue)

    akislar = []
    try:
        if loopback is not None:
            akislar.append(p.open(format=pyaudio.paFloat32, channels=loopback["maxInputChannels"],
                                  rate=int(loopback["defaultSampleRate"]), input=True,
                                  input_device_index=loopback["index"], frames_per_buffer=BLOK,
                                  stream_callback=loopback_cb))
        if not args.ton and args.mik > 0:
            akislar.append(p.open(format=pyaudio.paFloat32, channels=1, rate=ORNEKLEME, input=True,
                                  frames_per_buffer=BLOK, stream_callback=mik_cb))  # varsayılan mikrofon (MME)
        akislar.append(p.open(format=pyaudio.paFloat32, channels=KANAL, rate=ORNEKLEME, output=True,
                              output_device_index=kablo["index"], frames_per_buffer=BLOK,
                              stream_callback=cikis_cb))
    except Exception as e:
        print(f"[HATA] Ses akışı açılamadı: {e}")
        return

    if args.ton:
        print("TEST TONU modu: CABLE'a temiz bir 'biiip' (440 Hz) gönderiliyor.")
    else:
        print(f"Mikrofon       : {'kapalı' if args.mik <= 0 else 'varsayılan mikrofon'}")
        print(f"Bilgisayar sesi: {loopback['name'] + ' (' + str(int(loopback['defaultSampleRate'])) + ' Hz)' if loopback else 'kapalı'}")
    print(f"Çıkış          : {kablo['name']}")
    print("Dinlemek için: Windows Ses Kaydedici'de mikrofonu 'CABLE Output' seçip kayıt al.")
    print("UYARI: CABLE Output için 'Bu cihazı dinle'yi AÇMA; hoparlörden çıkan ses tekrar")
    print("       yakalanır ve kulak tırmalayan bir geri besleme (feedback) gürültüsü oluşur.")
    print("Durdurmak için Ctrl+C.\n")
    try:
        while True:
            print(f"\rMik [{cubuk(mik_tampon.seviye)}]  Sistem [{cubuk(sistem_tampon.seviye)}]  "
                  f"boşluk: mik {mik_tampon.alt_tasma} / sistem {sistem_tampon.alt_tasma}   ", end="")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDurduruldu.")
    finally:
        for a in akislar:
            a.stop_stream(); a.close()
        p.terminate()
        if kayit_parcalari:
            veri = (np.concatenate(kayit_parcalari) * 32767).astype(np.int16)
            with wave.open("gonderilen_ses.wav", "wb") as w:
                w.setnchannels(KANAL); w.setsampwidth(2); w.setframerate(ORNEKLEME)
                w.writeframes(veri.tobytes())
            print(f"CABLE'a gönderilen sesin ilk {len(veri) / ORNEKLEME:.0f} saniyesi: gonderilen_ses.wav")
            print("Bu dosya temizse sorun bizde değil, VB-Cable/Windows ayarındadır.")


if __name__ == "__main__":
    main()
