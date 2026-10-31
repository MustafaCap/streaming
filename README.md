# Yayın Uygulaması

Windows 11 için çevrimdışı çalışan, Meet/Zoom/Discord'da sanal kamera ve sanal mikrofon olarak görünen ekran, kamera ve ses paylaşım uygulaması. Öne çıkan özellikler: tek tuşla ekranın bir bölgesini seçip göstermek ve ekrana anında çizim yapmak.

## Durum

- **Aşama 0 (bitti):** riskli parçalar küçük denemelerle doğrulandı, bkz. [denemeler/](denemeler/README.md).
- **Aşama 1 (şu an):** ekran yakalanıp sanal kameraya gönderiliyor; önizlemeli basit pencere.

## Hazır .exe ile deneme (Python gerekmez)

1. Bir kere **OBS Studio** kur (https://obsproject.com/), aç, "Sanal Kamerayı Başlat"a bas ve kapat. Uygulama OBS'nin sanal kamera sürücüsünü kullanır; OBS'nin açık olması gerekmez.
2. [Releases sayfasından](https://github.com/MustafaCap/streaming/releases/tag/asama-1) `YayinUygulamasi.zip`'i indir, bir klasöre çıkar.
3. `YayinUygulamasi\YayinUygulamasi.exe`'yi çalıştır ("Windows bilgisayarınızı korudu" çıkarsa: Ek bilgi > Yine de çalıştır).
4. **Yayını başlat**'a bas. Zoom/Meet/Discord'da (veya Windows Kamera uygulamasında) kamera olarak **OBS Virtual Camera**'yı seç.

Ayarlar `%APPDATA%\YayinUygulamasi\settings.json`, loglar `%APPDATA%\YayinUygulamasi\logs\` klasöründe. Bir sorun olursa `uygulama.log` dosyasını gönder.

## Geliştirici kurulumu

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py          # uygulamayı çalıştır
python -m pytest -q     # testler
```

## Klasör yapısı

```
main.py              başlangıç noktası (ağ kilidi, log, ayarlar, pencere)
config/              varsayılan ayarlar (kullanıcı ayarları %APPDATA%'da)
core/                ayarlar, merkezi durum, komutlar, video hattı, ağ kilidi, Windows yardımcıları
capture/             ekran yakalama (dxcam, yedek mss)
outputs/             sanal kamera çıkışı
ui/                  arayüz ve tema
tests/               birim testleri (pytest)
denemeler/           Aşama 0 risk denemeleri
```

## İlkeler

- **Çevrimdışı:** `core/network_guard.py` dış ağ bağlantılarını ve DNS sorgularını engeller.
- **Önce kararlılık:** kaynak koparsa (monitör, sürücü) uygulama çökmez; durum rozetinde görünür ve yeniden denenir.
