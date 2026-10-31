# Yayın Uygulaması

Windows 10/11 için **internete hiç bağlanmayan**, Meet/Zoom/Discord'da **sanal kamera** ve **sanal mikrofon** olarak görünen ekran, kamera ve ses paylaşım uygulaması. Öne çıkanlar: tek tuşla ekranın bir bölgesini seçip göstermek (F6) ve ekrana anında çizim yapmak (F7).

## Kurulum (bir kere)

1. **OBS Studio** kur (https://obsproject.com/), aç, *Sanal Kamerayı Başlat*'a bir kez bas ve kapat. Uygulama OBS'nin sanal kamera sürücüsünü kullanır; OBS'nin açık olması gerekmez.
2. **VB-Cable** kur (https://vb-audio.com/Cable/ → zip'i çıkar → `VBCABLE_Setup_x64.exe`'ye sağ tık → *Yönetici olarak çalıştır* → *Install Driver*), sonra bilgisayarı yeniden başlat.
3. Windows ses ayarlarında **varsayılan giriş = gerçek mikrofonun**, **varsayılan çıkış = gerçek hoparlör/kulaklık** olsun. CABLE'ı Windows'ta varsayılan yapma; sadece Zoom/Discord içinde seçilir. CABLE Output için *Bu cihazı dinle*'yi açma (geri besleme gürültüsü yapar).
4. [Releases → uygulama](https://github.com/MustafaCap/streaming/releases/tag/uygulama) sayfasından `YayinUygulamasi.zip`'i indir (ya da `D:\streaming\guncelle.bat`), bir klasöre çıkar, `YayinUygulamasi\YayinUygulamasi.exe`'yi çalıştır. "Windows bilgisayarınızı korudu" çıkarsa: *Ek bilgi → Yine de çalıştır*.

## Kullanım

1. **Yayın** düğmesine bas (görüntü ve ses birlikte başlar).
2. Zoom / Meet / Discord'da: kamera **OBS Virtual Camera**, mikrofon **CABLE Output (VB-Audio Virtual Cable)**.
3. Pencereyi kapatınca uygulama saatin yanındaki tepside çalışmaya devam eder; kısayollar açık kalır. Tamamen kapatmak için tepsi simgesine sağ tık → *Çıkış*.

### Kısayollar (hepsi Ayarlar > Kısayollar'dan değiştirilebilir)

| Tuş | İşlev |
| --- | --- |
| F6 | Kare seç (fareyle çiz; **Enter** yakınlaştır, **V** vurgula, **Esc** iptal); tekrar F6 tam ekrana döner |
| F7 | Kalemi aç/kapat |
| 1–6 | Kalem türü: kalem, fosforlu, ok, kare, yazı, lazer (sadece kalem açıkken) |
| Ctrl+Z / Del | Son çizimi geri al / hepsini sil (sadece kalem açıkken; sağ tık da geri alır) |
| F8 / F9 / F10 | Mikrofon / bilgisayar sesi / kamera aç-kapat |
| F12 | Panik: anında bekleme ekranı, ses kesilir; tekrar basınca geri döner |
| Ctrl+1 … Ctrl+4 | Sahne: Ekran + Kamera, Sadece ekran, Sadece kamera, Bekleme |
| Ctrl+Shift+R | Yerel MP4 kaydı başlat/durdur |
| (ayarlanabilir) | Bas-konuş: basılıyken mikrofon açık |

Kısayola basınca sağ altta kısa bir bildirim çıkar ("Mikrofon kapandı · F8"). Başka bir program aynı tuşu kullanıyorsa uygulama bunu söyler.

### Özellikler

- **Sahneler** ve 0,3 sn yumuşak geçiş; webcam köşede (köşe, boyut, ayna, **arka plan bulanıklaştırma** Ayarlar > Kamera).
- **Ses mikseri**: mikrofon ve bilgisayar sesi ayrı seviyeler (%0–200), seviye göstergeleri, mikrofon seçimi. Bilgisayar sesinde Zoom/Discord/Teams **otomatik hariç tutulur**, böylece karşı taraf kendi sesini yankı olarak duymaz. (Meet tarayıcıda çalıştığı için yankı olursa kulaklık kullan ya da Ayarlar > Ses'te `msedge.exe`'yi hariç listesine ekle.)
- **Otomatik ses kısma** (konuşunca oyun sesi kısılır) ve **bas-konuş** (Ayarlar).
- **Kare seçme**: animasyonlu yakınlaştırma ya da vurgulama (geri kalan kararır).
- **Kalem**: kalem, fosforlu, ok, kare, yazı (Türkçe), lazer; 4 renk. Çizimler yayına ayrıca eklenir, tam ekran oyunda katman görünmese bile karşı taraf görür.
- **Mini mod**: her zaman üstte duran küçük çubuk (sağ üstteki *Mini mod*).
- **Bekleme ekranı**: yazı ya da görsel (Ayarlar > Genel).
- **İmleç vurgulama**: halka + tıklama dalgası (Ayarlar > Genel).
- **Yerel kayıt**: `Videolar\YayinUygulamasi\` klasörüne MP4; ekran kartına göre NVIDIA/Intel/AMD donanım kodlayıcısı.
- Uygulamanın kendi pencereleri (önizleme, kalem çubuğu, kare seçme, bildirimler, mini mod) **ekran yakalamaya girmez**; karşı taraf görmez.
- Bir kaynak koparsa (kamera çıkarılır, mikrofon değişir) uygulama çökmez; o kaynak kırmızı görünür ve birkaç saniyede bir yeniden denenir.

### Bildirimler hakkında

Windows'ta başka bir uygulamanın bildirimini ekran yakalamadan çıkarmanın resmi bir yolu yok. Yayın ilk başladığında uygulama **Rahatsız Etme'yi açmayı (Win+N)** hatırlatır (Ayarlar'dan kapatılabilir).

## Sorun giderme

| Sorun | Çözüm |
| --- | --- |
| "Sanal kamera: Yok" | OBS kurulu değil ya da sanal kamerası hiç başlatılmamış (Kurulum 1). |
| "Sanal mikrofon: Yok" | VB-Cable kurulu değil ya da bilgisayar yeniden başlatılmadı (Kurulum 2). |
| Karşı taraf sadece gürültü duyuyor | Windows varsayılan girişi CABLE olmuş; gerçek mikrofona çevir (Kurulum 3). |
| Ses kısık | Mikserde Mikrofon kaydırıcısını %100'ün üstüne çıkar. |
| Kısayol çalışmıyor | Başka bir program kullanıyor olabilir; Ayarlar > Kısayollar'dan değiştir. Oyun yönetici olarak çalışıyorsa uygulamayı da yönetici olarak aç. |
| Zoom "kamera başka uygulamada" diyor | Birkaç saniye bekle ya da Zoom'da kamerayı kapatıp aç. |

Ayarlar `%APPDATA%\YayinUygulamasi\settings.json`, loglar `%APPDATA%\YayinUygulamasi\logs\uygulama.log`. Bir sorun olursa bu log dosyasını gönder.

## Geliştirici kurulumu

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py          # uygulamayı çalıştır
python -m pytest -q     # testler
```

Yerel kayıt için `ffmpeg\ffmpeg.exe` (LGPL derlemesi) gerekir; paketlenmiş sürümde hazır gelir, geliştirirken PATH'teki ffmpeg de kullanılır. `main` dalına her birleşmede GitHub Actions Windows'ta testleri çalıştırır, PyInstaller ile paketler ve [uygulama](https://github.com/MustafaCap/streaming/releases/tag/uygulama) sürümünü günceller. Paket tek bir .exe yerine klasördür (`--onedir`): tek .exe her açılışta 100+ MB'ı geçici klasöre açtığı için yavaş başlar ve antivirüslere daha çok takılır.

## Klasör yapısı

```
main.py              başlangıç: ağ kilidi, log, ayarlar, bileşenleri bağlar
config/              varsayılan ayarlar ve kısayollar (kullanıcı ayarları %APPDATA%'da)
core/                merkezi durum, komutlar, video hattı, ses mikseri ve motoru, kısayollar,
                     kayıt (FFmpeg), ağ kilidi, Windows yardımcıları
capture/             ekran (dxcam, yedek mss), webcam, uygulama sesi (Process Loopback),
                     kare seçme/yakınlaştırma, arka plan bulanıklaştırma
overlay/             çizimler ve imleç vurgusu (çıkış karesine çizim)
scenes/              sahneler ve geçişler
outputs/             sanal kamera çıkışı
ui/                  ana pencere, mikser, mini mod, ayarlar, kare seçme ve kalem katmanları,
                     bildirimler, sistem tepsisi
models/              arka plan bulanıklaştırma modeli (Apache 2.0)
tests/               birim testleri (pytest)
denemeler/           Aşama 0 risk denemeleri
```

## Lisanslar

Kullanılan kütüphaneler ücretli dağıtıma uygun lisanslıdır: PySide6 (LGPL), OpenCV, numpy, Pillow, psutil, mss, dxcam, pyvirtualcam, PyAudioWPatch, comtypes (MIT/BSD/Apache), FFmpeg LGPL derlemesi (`ffmpeg\LICENSE.txt`), MediaPipe Selfie Segmentation modeli (Apache 2.0, `models\`). QFluentWidgets (GPL) bilerek kullanılmadı. OBS Virtual Camera ve VB-Cable kullanıcı tarafından ayrıca kurulur.
