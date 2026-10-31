# Aşama 0 — Risk denemeleri

Bu klasördeki her dosya tek bir riskli konuyu dener. Asıl uygulama değiller; amaç, bir şey çalışmazsa bunu kod yazmaya başlamadan öğrenmek. Her denemeden sonra sonucu [SONUCLAR.md](SONUCLAR.md) dosyasına yaz.

## En kolay yol: hazır .exe

Python kurmak istemiyorsan [Releases sayfasından](https://github.com/MustafaCap/streaming/releases/tag/asama-0) `Asama0-Denemeler.zip`'i indir, bir klasöre çıkar ve içindeki `BENIOKU.txt`'yi izle. Sadece OBS ve VB-Cable kurulu olmalı. Zip, GitHub'da her değişiklikte otomatik olarak yeniden derlenir.

## 1. Kurulum (Python ile, bir kere)

1. **Python 3.11 veya 3.12** kur: https://www.python.org/downloads/ (kurulumda "Add python.exe to PATH" kutusunu işaretle). 3.13 kullanma; bazı kütüphaneler henüz hazır olmayabilir.
2. **OBS Studio** kur: https://obsproject.com/ (sanal kamera sürücüsü için). Kurduktan sonra OBS'yi bir kere aç, "Sanal Kamerayı Başlat"a bas, kapat. Bu, sürücünün kaydolmasını sağlar.
3. **VB-Cable** kur: https://vb-audio.com/Cable/ (zip'i aç, `VBCABLE_Setup_x64.exe`'ye sağ tık > Yönetici olarak çalıştır, sonra bilgisayarı yeniden başlat).
4. **Windows ses ayarı:** Ayarlar > Sistem > Ses'te varsayılan çıkış gerçek hoparlörün/kulaklığın olmalı, "CABLE Input" OLMAMALI.
5. Projeyi indir ve sanal ortamı kur. PowerShell'de:

```powershell
git clone https://github.com/MustafaCap/streaming.git
cd streaming
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r denemeler\requirements.txt
cd denemeler
```

> PowerShell "script çalıştırma devre dışı" derse bir kere şunu çalıştır: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 2. Denemeler

### Deneme 1 — Ekran → sanal kamera

```powershell
python 01_ekran_sanal_kamera.py
```

Zoom'da (veya https://webcamtests.com gibi bir sitede ya da Windows Kamera uygulamasında) kamera olarak **OBS Virtual Camera**'yı seç. Ekranını görmelisin.

Not et: konsoldaki FPS ve "kare başına iş" süresi, Görev Yöneticisi'ndeki işlemci kullanımı. Sonra `--mss` ile de dene ve farkı not et.

**Siyah ekran:** iki ekran kartlı laptoplarda olur. Ayarlar > Sistem > Ekran > Grafik'te `.venv\Scripts\python.exe` dosyasını ekleyip "Güç tasarrufu" seç ve tekrar dene.

### Deneme 2 — Kendi penceremizi yakalamadan gizleme

```powershell
python 02_yakalamadan_gizle.py
```

Script kendi kendini test eder ve konsola `BAŞARILI` ya da `BAŞARISIZ` yazar. İstersen aynı anda Deneme 1'i de çalıştır: pembe pencere senin ekranında görünür, Zoom önizlemesinde görünmemeli.

### Deneme 3 — Global kısayollar

```powershell
python 03_kisayol.py
```

Bir oyun aç (önce pencereli/kenarlıksız modda, sonra tam ekran). F6 ve F8'e bas, bip sesini duymalısın. Sonra:

1. Kalem kapalıyken oyunda `1`'e bas: oyun bunu almalı (ör. silah değiştirmeli).
2. F7'ye bas (kalem açılır), `1`'e bas: bip sesi gelmeli ve oyun almamalı.
3. Tekrar F7, `1` yine oyuna gitmeli.

Çalışmazsa PowerShell'i **yönetici olarak** açıp tekrar dene ve iki sonucu da not et. Çıkış: `Ctrl+Shift+Q`.

### Deneme 4 — Mikrofon + bilgisayar sesi → VB-Cable

```powershell
python 04_sistem_sesi_vbcable.py --liste    # önce cihazları gör
python 04_sistem_sesi_vbcable.py
```

Konsolda iki seviye çubuğu oynamalı. Discord'da (veya Windows Ses Kaydedici'de) mikrofon olarak **CABLE Output**'u seç. Konuşurken bir yandan YouTube aç; kayıtta ikisi de duyulmalı.

**Yankı testi:** bir arkadaşınla Discord/Zoom görüşmesi yap, mikrofon olarak CABLE Output seçili olsun, kulaklık TAKMADAN hoparlörden dinle. Arkadaşın kendi sesini yankı olarak duyacak. Bu beklenen sonuç; neden Deneme 5'e ihtiyacımız olduğunu gösteriyor.

### Deneme 5 — Sadece tek uygulamanın sesi (en deneysel olan)

```powershell
python 05_uygulama_sesi.py --surec msedge.exe
python 05_uygulama_sesi.py --surec msedge.exe --haric
```

Edge'de YouTube videosu, aynı anda Spotify'da müzik çal. İlk komutun oluşturduğu `kayit_msedge.wav`'da sadece video sesi, ikincisinin oluşturduğu `kayit_msedge_haric.wav`'da sadece müzik olmalı.

Hata verirse konsol çıktısının **tamamını** kopyalayıp bana gönder. Bu dosya Windows'un ses arayüzünü doğrudan çağırdığı için ilk denemede bir düzeltme gerekebilir.

## 3. Bitince

[SONUCLAR.md](SONUCLAR.md)'yi doldur ve bana gönder (ya da sonuçları sohbete yaz). Ona göre 1. aşamanın planını kesinleştireceğiz.
