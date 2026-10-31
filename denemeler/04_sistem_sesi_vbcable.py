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

Durdurmak için: Ctrl+C
"""

import argparse
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

ORNEKLEME = 48000
BLOK = 480  # 10 ms
KANAL = 2


class Tampon:
    """Giriş geri çağrılarının yazdığı, çıkışın okuduğu basit iş parçacığı güvenli tampon."""

    def __init__(self, en_fazla_sn=0.5):
        self.veri = np.zeros((0, KANAL), np.float32)
        self.kilit = threading.Lock()
        self.en_fazla = int(ORNEKLEME * en_fazla_sn)
        self.seviye = 0.0

    def yaz(self, blok: np.ndarray):
        if blok.shape[1] == 1:
            blok = np.repeat(blok, 2, axis=1)
        elif blok.shape[1] > 2:
            blok = blok[:, :2]
        self.seviye = float(np.abs(blok).max()) if len(blok) else 0.0
        with self.kilit:
            self.veri = np.concatenate([self.veri, blok])[-self.en_fazla:]

    def oku(self, n: int) -> np.ndarray:
        with self.kilit:
            parca, self.veri = self.veri[:n], self.veri[n:]
        if len(parca) < n:  # yeterli veri yoksa sessizlikle doldur (loopback sessizken veri vermez)
            parca = np.concatenate([parca, np.zeros((n - len(parca), KANAL), np.float32)])
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--mik", type=float, default=1.0, help="mikrofon seviyesi")
    ap.add_argument("--sistem", type=float, default=0.7, help="bilgisayar sesi seviyesi")
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

    # Bilgisayar sesi: varsayılan hoparlörün loopback'i (WASAPI)
    loopback = p.get_default_wasapi_loopback()
    if "CABLE" in loopback["name"]:
        print("[HATA] Varsayılan hoparlörün VB-Cable olarak ayarlanmış. Bu sonsuz döngü yaratır;")
        print("       Windows ses ayarlarından varsayılan çıkışı gerçek hoparlör/kulaklık yap.")
        return

    mik_tampon, sistem_tampon = Tampon(), Tampon()

    def loopback_cb(in_data, frames, t, status):
        blok = np.frombuffer(in_data, np.float32).reshape(-1, loopback["maxInputChannels"])
        sistem_tampon.yaz(blok)
        return (None, pyaudio.paContinue)

    def mik_cb(in_data, frames, t, status):
        mik_tampon.yaz(np.frombuffer(in_data, np.float32).reshape(-1, 1))
        return (None, pyaudio.paContinue)

    def cikis_cb(in_data, frames, t, status):
        karisim = mik_tampon.oku(frames) * args.mik + sistem_tampon.oku(frames) * args.sistem
        np.clip(karisim, -1.0, 1.0, out=karisim)  # basit sınırlayıcı
        return (karisim.astype(np.float32).tobytes(), pyaudio.paContinue)

    akislar = []
    try:
        akislar.append(p.open(format=pyaudio.paFloat32, channels=loopback["maxInputChannels"],
                              rate=int(loopback["defaultSampleRate"]), input=True,
                              input_device_index=loopback["index"], frames_per_buffer=BLOK,
                              stream_callback=loopback_cb))
        if int(loopback["defaultSampleRate"]) != ORNEKLEME:
            print(f"[NOT] Hoparlör {int(loopback['defaultSampleRate'])} Hz; bu denemede dönüştürme yok, "
                  "ses tiz/kalın çıkabilir. Windows ses ayarından 48000 Hz yapabilirsin.")
        if args.mik > 0:
            akislar.append(p.open(format=pyaudio.paFloat32, channels=1, rate=ORNEKLEME, input=True,
                                  frames_per_buffer=BLOK, stream_callback=mik_cb))  # varsayılan mikrofon (MME)
        akislar.append(p.open(format=pyaudio.paFloat32, channels=KANAL, rate=ORNEKLEME, output=True,
                              output_device_index=kablo["index"], frames_per_buffer=BLOK,
                              stream_callback=cikis_cb))
    except Exception as e:
        print(f"[HATA] Ses akışı açılamadı: {e}")
        return

    print(f"Bilgisayar sesi: {loopback['name']}")
    print(f"Çıkış          : {kablo['name']}")
    print("Zoom/Discord'da mikrofon olarak 'CABLE Output' seç. Durdurmak için Ctrl+C.\n")
    try:
        while True:
            print(f"\rMik [{cubuk(mik_tampon.seviye)}]  Sistem [{cubuk(sistem_tampon.seviye)}]", end="")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDurduruldu.")
    finally:
        for a in akislar:
            a.stop_stream(); a.close()
        p.terminate()


if __name__ == "__main__":
    main()
