import socket

import pytest

from core import network_guard


def test_dis_baglanti_ve_dns_engellenir():
    network_guard.kur()
    s = socket.socket()
    try:
        with pytest.raises(network_guard.AgEngellendi):
            s.connect(("93.184.216.34", 80))
        assert s.connect_ex(("8.8.8.8", 53)) != 0
    finally:
        s.close()
    with pytest.raises(network_guard.AgEngellendi):
        socket.getaddrinfo("example.com", 80)


def test_yerel_baglantiya_izin_verilir():
    network_guard.kur()
    sunucu = socket.socket()
    sunucu.bind(("127.0.0.1", 0))
    sunucu.listen(1)
    istemci = socket.socket()
    try:
        istemci.connect(sunucu.getsockname())  # hata vermemeli
    finally:
        istemci.close()
        sunucu.close()
