"""Komut sistemi.

Uygulamadaki her işlemin bir adı vardır: "cikis.ac_kapat", "sahne.sec:2" gibi.
Düğmeler, kısayollar (Aşama 4), mini mod ve sistem tepsisi doğrudan fonksiyon
çağırmaz, komutu adıyla çalıştırır. settings.json'daki kısayollar da komut
adlarına bağlanır.

Her komut çalıştığında dinleyicilere haber verilir; köşe bildirimleri
(Aşama 4) buna abone olacak.
"""

import logging
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Komut:
    ad: str            # ör. "cikis.ac_kapat"
    baslik: str        # kullanıcıya görünen ad, ör. "Yayını aç/kapat"
    calistir: Callable[[str | None], str | None]  # parametre alır, bildirim metni döndürebilir


class KomutYoneticisi:
    def __init__(self):
        self._komutlar: dict[str, Komut] = {}
        self._dinleyiciler: list[Callable[[str, str | None], None]] = []

    def kaydet(self, ad: str, baslik: str, fn: Callable[[str | None], str | None]) -> None:
        if ad in self._komutlar:
            raise ValueError(f"Komut zaten kayıtlı: {ad}")
        self._komutlar[ad] = Komut(ad, baslik, fn)

    def dinle(self, fn: Callable[[str, str | None], None]) -> None:
        """fn(komut_adi, bildirim_metni) her başarılı komuttan sonra çağrılır."""
        self._dinleyiciler.append(fn)

    def var_mi(self, ad: str) -> bool:
        return ad.split(":", 1)[0] in self._komutlar

    def liste(self) -> list[Komut]:
        return list(self._komutlar.values())

    def calistir(self, tam_ad: str) -> bool:
        """'sahne.sec:2' gibi ':' sonrası parametre olarak geçer. Hata uygulamayı çökertmez."""
        ad, _, parametre = tam_ad.partition(":")
        komut = self._komutlar.get(ad)
        if komut is None:
            log.warning("Bilinmeyen komut: %s", tam_ad)
            return False
        try:
            mesaj = komut.calistir(parametre or None)
        except Exception:
            log.exception("Komut çalışırken hata: %s", tam_ad)
            return False
        for fn in list(self._dinleyiciler):
            try:
                fn(tam_ad, mesaj)
            except Exception:
                log.exception("Komut dinleyicisi hata verdi")
        return True
