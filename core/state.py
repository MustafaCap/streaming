"""Uygulamanın tek merkezi durumu.

Arayüz, kısayollar, mini mod ve sistem tepsisi durumu kendi içinde tutmaz;
hepsi buradan okur ve değişikliklerden haberdar olur. Böylece "mini modda
kapattım ama ana pencere açık gösteriyor" gibi tutarsızlıklar olmaz.

Bu modül Qt'ye bağımlı değildir; testlerde doğrudan kullanılabilir.
Dinleyiciler herhangi bir iş parçacığından çağrılabilir, arayüz tarafı
(ui/) bunu Qt sinyaline çevirip ana iş parçacığına taşır.
"""

import threading
from dataclasses import dataclass, field, fields, replace
from typing import Callable


@dataclass(frozen=True)
class Durum:
    cikis_acik: bool = False          # sanal kameraya görüntü gidiyor mu
    sanal_kamera: str = "kapalı"      # kapalı | açık | yok (sürücü bulunamadı) | hata
    ekran_kaynagi: str = "kapalı"     # kapalı | çalışıyor | koptu
    yakalama_yontemi: str = ""        # dxcam | mss
    fps: float = 0.0
    kare_suresi_ms: float = 0.0
    son_hata: str = ""


Dinleyici = Callable[[Durum, Durum], None]  # (eski, yeni)


class DurumDeposu:
    def __init__(self):
        self._durum = Durum()
        self._kilit = threading.Lock()
        self._dinleyiciler: list[Dinleyici] = []

    @property
    def durum(self) -> Durum:
        return self._durum

    def dinle(self, fn: Dinleyici) -> None:
        self._dinleyiciler.append(fn)

    def guncelle(self, **degisiklikler) -> None:
        gecerli = {f.name for f in fields(Durum)}
        bilinmeyen = set(degisiklikler) - gecerli
        if bilinmeyen:
            raise KeyError(f"Bilinmeyen durum alanı: {bilinmeyen}")
        with self._kilit:
            eski = self._durum
            yeni = replace(eski, **degisiklikler)
            if yeni == eski:
                return
            self._durum = yeni
        for fn in list(self._dinleyiciler):
            fn(eski, yeni)
