import threading
import time

from core import cpu_dagilimi


def test_is_parcacigi_adiyla_cpu_yazilir():
    olcer = cpu_dagilimi.CpuDagilimi()
    bitis = threading.Event()

    def mesgul():
        while not bitis.is_set():
            sum(range(1000))

    t = threading.Thread(target=mesgul, name="mesgul-is", daemon=True)
    t.start()
    time.sleep(0.5)
    toplam, oran = olcer.ornek()   # iş parçacığı çalışırken ölç
    bitis.set()
    t.join()
    assert oran.get("mesgul-is", 0) > 0 and toplam >= oran["mesgul-is"]
    satir = cpu_dagilimi.metin(toplam, oran, 0.5)
    assert satir.startswith("CPU dağılımı") and "mesgul-is" in satir
