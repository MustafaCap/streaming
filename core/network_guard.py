"""Ağ kilidi: uygulama hiçbir dış ağ bağlantısı açamaz.

Briefin "çevrimdışı" ilkesini sadece söz olarak değil kodla garanti eder.
Bir kütüphane gizlice internete bağlanmaya çalışırsa bağlantı engellenir ve
loga yazılır. Sadece bu bilgisayarın kendisine (127.0.0.1 / ::1) izin verilir.
"""

import ipaddress
import logging
import socket

log = logging.getLogger(__name__)

_kurulu = False


class AgEngellendi(ConnectionError):
    pass


def _yerel_mi(adres) -> bool:
    if not isinstance(adres, tuple) or not adres:
        return True  # AF_UNIX gibi dosya tabanlı soketler
    host = adres[0]
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # alan adı: dışarı çıkmak demek


def kur() -> None:
    global _kurulu
    if _kurulu:
        return
    asil_connect = socket.socket.connect
    asil_connect_ex = socket.socket.connect_ex

    def connect(self, adres):
        if not _yerel_mi(adres):
            log.error("Ağ bağlantısı engellendi: %s", adres)
            raise AgEngellendi(f"Bu uygulama çevrimdışı çalışır; {adres} adresine bağlantı engellendi.")
        return asil_connect(self, adres)

    def connect_ex(self, adres):
        if not _yerel_mi(adres):
            log.error("Ağ bağlantısı engellendi: %s", adres)
            return 13  # EACCES
        return asil_connect_ex(self, adres)

    asil_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        # DNS sorgusu da dışarıya bilgi sızdırır; sadece yerel adlara izin ver.
        if host not in (None, "", "localhost") and not _yerel_mi((host,)):
            log.error("DNS sorgusu engellendi: %s", host)
            raise AgEngellendi(f"Bu uygulama çevrimdışı çalışır; '{host}' adı çözülmedi.")
        return asil_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.getaddrinfo = getaddrinfo
    socket.socket.connect_ex = connect_ex
    _kurulu = True
