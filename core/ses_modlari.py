""""Önde olan" ses modları: Sesim, Dengeli, Oyun.

Her mod mikrofon ve sistem/oyun sesi için bir yüzde çiftidir. Sürgü elle değişince hiçbir mod
seçili görünmez ve "<son mod>'e kaydet" bağlantısı çıkar; basılırsa yeni değerler o moda yazılır
(ayarlarda saklanır). Ayarlar'daki "Ses modlarını varsayılana döndür" ilk değerlere döner.

Bu modül Qt'ye bağlı değildir.
"""

MODLAR = ("sesim", "dengeli", "oyun")
ETIKETLER = {"sesim": "Sesim", "dengeli": "Dengeli", "oyun": "Oyun"}
KAYDET_ETIKETI = {"sesim": "Sesim'e kaydet", "dengeli": "Dengeli'ye kaydet", "oyun": "Oyun'a kaydet"}
VARSAYILAN = {"sesim": [100, 45], "dengeli": [80, 80], "oyun": [70, 100]}
IPUCU = {"sesim": "Sesin önde, oyun/sistem sesi kısık",
         "dengeli": "İkisi aynı seviyede",
         "oyun": "Oyun sesi önde"}


def _yuzde(v) -> int | None:
    try:
        return max(0, min(200, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def modlar(ayarlar) -> dict[str, list[int]]:
    """Ayarlardaki modlar; eksik/bozuk olan varsayılandan tamamlanır."""
    kayitli = ayarlar.al("audio.modes", {}) if ayarlar is not None else {}
    sonuc = {}
    for ad in MODLAR:
        deger = kayitli.get(ad) if isinstance(kayitli, dict) else None
        if isinstance(deger, (list, tuple)) and len(deger) == 2 and None not in map(_yuzde, deger):
            sonuc[ad] = [_yuzde(deger[0]), _yuzde(deger[1])]
        else:
            sonuc[ad] = list(VARSAYILAN[ad])
    return sonuc


def eslesen(mik: int, sis: int, tum: dict[str, list[int]]) -> str:
    """Sürgüler bir modla aynıysa o modun adı, değilse ''."""
    for ad in MODLAR:
        if tum[ad] == [mik, sis]:
            return ad
    return ""


def son_mod(ayarlar) -> str:
    ad = ayarlar.al("audio.last_mode", "dengeli") if ayarlar is not None else "dengeli"
    return ad if ad in MODLAR else "dengeli"


def uygula(ayarlar, mikser, ad: str) -> tuple[int, int]:
    mik, sis = modlar(ayarlar)[ad]
    mikser.kanallar["mikrofon"].kazanc = mik / 100.0
    mikser.kanallar["sistem"].kazanc = sis / 100.0
    if ayarlar is not None:
        ayarlar.veri.setdefault("audio", {})["last_mode"] = ad
        ayarlar.veri["audio"]["mic_gain"] = mik / 100.0
        ayarlar.ayarla("audio.system_gain", sis / 100.0)
    return mik, sis


def kaydet(ayarlar, ad: str, mik: int, sis: int) -> None:
    tum = modlar(ayarlar)
    tum[ad] = [int(mik), int(sis)]
    ayarlar.veri.setdefault("audio", {})["last_mode"] = ad
    ayarlar.ayarla("audio.modes", tum)


def varsayilana_don(ayarlar) -> None:
    ayarlar.ayarla("audio.modes", {ad: list(v) for ad, v in VARSAYILAN.items()})
