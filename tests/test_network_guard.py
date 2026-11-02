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


def test_yeni_moduller_internete_baglanmaz():
    """2.0.0'ın yeni parçaları (anlık tekrar, gürültü azaltma, yardım) ağ kullanmaz: içe aktarıp
    çalıştırırken bekçi açıkken hiçbir dış bağlantı denemesi olmaz."""
    import numpy as np

    network_guard.kur()
    denemeler = []
    eski = socket.socket.connect

    def izle(self, adres):
        denemeler.append(adres)
        return eski(self, adres)

    socket.socket.connect = izle
    try:
        from core.anlik_tekrar import AnlikTekrar
        from core.gurultu import GurultuAzaltici
        from ui import yardim
        t = AnlikTekrar(64, 48, 10)
        t.kare_yaz(np.zeros((48, 64, 3), np.uint8))
        GurultuAzaltici(True).isle(np.zeros(480, np.float32))
        metin = yardim.yardim_metni()
    finally:
        socket.socket.connect = eski
    assert denemeler == []
    assert "http://" not in metin and "https://" not in metin
