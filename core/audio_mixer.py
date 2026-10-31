"""Ses mikseri: kaynakları (mikrofon, bilgisayar sesi) karıştırıp tek bir sese çevirir.

Bu dosya sadece numpy kullanır, cihazlarla konuşmaz; böylece testlerde
gerçek ses kartı olmadan denenebilir. Cihazları açıp kapatan kısım
core/audio_engine.py'de.

Akış:
  giriş cihazı -> Tampon.yaz()   (cihazın kendi iş parçacığında)
  CABLE Input  <- SesKaristirici.karistir(n)  (çıkış cihazının iş parçacığında)
"""

import threading

import numpy as np

ORNEKLEME = 48000
KANAL = 2


class Tampon:
    """Giriş geri çağrılarının yazdığı, çıkışın okuduğu iş parçacığı güvenli tampon.

    Ön tampon: çıkış, içeride en az ON_TAMPON kadar ses birikmeden okumaya başlamaz.
    Tampon boşalırsa (alt taşma) tekrar dolmasını bekler. Bu olmadan her 10 ms'de
    bir sessizlik boşluğu girer ve ses cızırtılı çıkar (Aşama 0, deneme 4'te bulundu).
    Çok dolarsa (iki cihazın saati biraz farklı işler) en eski ses atılır,
    böylece gecikme hiçbir zaman EN_FAZLA_SN'yi geçmez.
    """

    ON_TAMPON_SN = 0.04
    EN_FAZLA_SN = 0.25

    def __init__(self, giris_hizi: int = ORNEKLEME):
        self.giris_hizi = giris_hizi
        self._veri = np.zeros((0, KANAL), np.float32)
        self._kilit = threading.Lock()
        self._on_tampon = int(ORNEKLEME * self.ON_TAMPON_SN)
        self._en_fazla = int(ORNEKLEME * self.EN_FAZLA_SN)
        self._hazir = False
        self.alt_tasma = 0

    def temizle(self) -> None:
        with self._kilit:
            self._veri = np.zeros((0, KANAL), np.float32)
            self._hazir = False

    def yaz(self, blok: np.ndarray) -> None:
        """blok: (n, kanal) float32, -1..1 arası."""
        if blok.ndim == 1:
            blok = blok[:, None]
        if blok.shape[1] == 1:
            blok = np.repeat(blok, 2, axis=1)
        elif blok.shape[1] > 2:
            blok = blok[:, :2]
        if self.giris_hizi != ORNEKLEME and len(blok) > 1:
            # Basit doğrusal örnekleme hızı dönüştürme (ör. 44100 -> 48000)
            n_yeni = int(round(len(blok) * ORNEKLEME / self.giris_hizi))
            x_eski = np.arange(len(blok))
            x_yeni = np.linspace(0, len(blok) - 1, n_yeni)
            blok = np.stack([np.interp(x_yeni, x_eski, blok[:, k]) for k in range(2)], axis=1)
        blok = blok.astype(np.float32, copy=False)
        with self._kilit:
            self._veri = np.concatenate([self._veri, blok])[-self._en_fazla:]

    def oku(self, n: int) -> np.ndarray:
        with self._kilit:
            if not self._hazir:
                if len(self._veri) < self._on_tampon:
                    return np.zeros((n, KANAL), np.float32)
                self._hazir = True
            if len(self._veri) < n:  # alt taşma: tamponu yeniden doldurmayı bekle
                self.alt_tasma += 1
                self._hazir = False
                return np.zeros((n, KANAL), np.float32)
            parca, self._veri = self._veri[:n], self._veri[n:]
        return parca


class Kanal:
    """Mikserdeki bir satır: kaynak tamponu, seviye (kazanç), susturma ve seviye göstergesi."""

    def __init__(self, ad: str, kazanc: float = 1.0, sessiz: bool = False):
        self.ad = ad
        self.tampon = Tampon()
        self.kazanc = kazanc
        self.sessiz = sessiz
        self.bagli = False       # cihaz/kaynak şu an açık mı
        self.seviye = 0.0        # son bloğun tepe değeri (kazanç sonrası, 0..1+)
        self.carpan = 1.0        # otomatik ses kısma gibi geçici etkiler için
        self.kapi = True         # bas-konuş: tuş basılı değilken False (mikrofon susar)

    @property
    def kazanc(self) -> float:
        return self._kazanc

    @kazanc.setter
    def kazanc(self, deger: float) -> None:
        self._kazanc = float(min(2.0, max(0.0, deger)))


class SesKaristirici:
    """Kanalları toplar, sınırlar ve VB-Cable'a gidecek bloğu üretir.

    Ek özellikler:
      ana_sessiz : panik tuşu; hiçbir ses gitmez
      kisma_acik : otomatik ses kısma; mikrofonda konuşma varken bilgisayar sesi kısılır
    """

    KISMA_ESIK = 0.06          # bu tepe değerinin üstü "konuşuyor" sayılır
    KISMA_BIRAKMA_SN = 0.6     # konuşma bittikten bu kadar sonra ses geri açılmaya başlar

    def __init__(self):
        self.kanallar: dict[str, Kanal] = {}
        self.cikis_seviyesi = 0.0
        self.ana_sessiz = False
        self.kisma_acik = False
        self.kisma_seviyesi = 0.3
        self._kisma = 1.0
        self._sessizlik_sn = 99.0
        self.konusuyor = False
        self.kayit_dinleyici = None   # fn(blok): yerel kayıt sesi (VB-Cable'a gidenin aynısı)

    def kanal_ekle(self, anahtar: str, ad: str, kazanc: float = 1.0, sessiz: bool = False) -> Kanal:
        k = Kanal(ad, kazanc, sessiz)
        self.kanallar[anahtar] = k
        return k

    def _kisma_guncelle(self, n: int) -> None:
        mik = self.kanallar.get("mikrofon")
        self.konusuyor = mik is not None and mik.seviye > self.KISMA_ESIK
        self._sessizlik_sn = 0.0 if self.konusuyor else self._sessizlik_sn + n / ORNEKLEME
        hedef = self.kisma_seviyesi if (self.kisma_acik and self._sessizlik_sn < self.KISMA_BIRAKMA_SN) else 1.0
        adim = n / ORNEKLEME
        if hedef < self._kisma:
            self._kisma = max(hedef, self._kisma - adim / 0.08)   # ~80 ms'de kıs
        else:
            self._kisma = min(hedef, self._kisma + adim / 0.5)    # ~0,5 sn'de geri aç
        sistem = self.kanallar.get("sistem")
        if sistem is not None:
            sistem.carpan = self._kisma

    def karistir(self, n: int) -> np.ndarray:
        """n örneklik stereo float32 blok döndürür (çıkış geri çağrısında çalışır, hızlı olmalı)."""
        toplam = np.zeros((n, KANAL), np.float32)
        # mikrofon önce: ses kısma kararı ona göre verilir
        sirali = sorted(self.kanallar.items(), key=lambda kv: kv[0] != "mikrofon")
        for anahtar, k in sirali:
            blok = k.tampon.oku(n)  # sessizken de oku ki tampon dolup eski ses birikmesin
            if k.sessiz or not k.bagli or not k.kapi:
                k.seviye = 0.0
            else:
                carpan = k.kazanc * k.carpan
                if carpan != 1.0:
                    blok = blok * carpan
                k.seviye = float(np.abs(blok).max()) if n else 0.0
                toplam += blok
            if anahtar == "mikrofon":
                self._kisma_guncelle(n)
        if self.ana_sessiz:
            self.cikis_seviyesi = 0.0
            toplam = np.zeros((n, KANAL), np.float32)
        else:
            tepe = float(np.abs(toplam).max()) if n else 0.0
            if tepe > 1.0:
                np.clip(toplam, -1.0, 1.0, out=toplam)  # basit sınırlayıcı: patlama yerine kırpma
            self.cikis_seviyesi = min(tepe, 1.0)
        dinleyici = self.kayit_dinleyici
        if dinleyici is not None:
            try:
                dinleyici(toplam)
            except Exception:
                pass
        return toplam

    def seviyeler(self) -> dict[str, float]:
        """Arayüzdeki seviye çubukları için: {'mikrofon': 0.3, 'sistem': 0.1, 'cikis': 0.35}"""
        d = {a: k.seviye for a, k in self.kanallar.items()}
        d["cikis"] = self.cikis_seviyesi
        return d

    def sifirla(self) -> None:
        for k in self.kanallar.values():
            k.tampon.temizle()
            k.seviye = 0.0
        self.cikis_seviyesi = 0.0


def db(seviye: float) -> float:
    """0..1 tepe değerini desibele çevirir (gösterge için). 0 -> -60 dB."""
    return max(-60.0, 20.0 * float(np.log10(max(seviye, 1e-6))))
