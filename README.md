# RizeOn

*(1.6.0'dan önceki adı: Yayın Uygulaması. Eski sürümün üstüne kurulur; ayarların ve bekleme görüntülerin yeni klasöre kendiliğinden taşınır.)*

Windows 10/11 için **internete hiç bağlanmayan**, Meet/Zoom/Discord'da **sanal kamera** ve **sanal mikrofon** olarak görünen ekran, kamera ve ses paylaşım uygulaması. Öne çıkanlar: tek tuşla ekranın bir bölgesini seçip göstermek (Ctrl+Shift+S), ekrana anında çizim yapmak (Ctrl+Shift+D) ve son 2 dakikayı tek tuşla kaydetmek (Ctrl+Shift+B).

## Kurulum (bir kere)

1. **OBS Studio** kur (https://obsproject.com/), aç, *Sanal Kamerayı Başlat*'a bir kez bas ve kapat. Uygulama OBS'nin sanal kamera sürücüsünü kullanır; OBS'nin açık olması gerekmez.
2. **VB-Cable** kur (https://vb-audio.com/Cable/ → zip'i çıkar → `VBCABLE_Setup_x64.exe`'ye sağ tık → *Yönetici olarak çalıştır* → *Install Driver*), sonra bilgisayarı yeniden başlat.
3. Windows ses ayarlarında **varsayılan giriş = gerçek mikrofonun**, **varsayılan çıkış = gerçek hoparlör/kulaklık** olsun. CABLE'ı Windows'ta varsayılan yapma; sadece Zoom/Discord içinde seçilir. CABLE Output için *Bu cihazı dinle*'yi açma (geri besleme gürültüsü yapar).
4. [Releases → uygulama](https://github.com/MustafaCap/streaming/releases/tag/uygulama) sayfasından (ya da [Releases](https://github.com/MustafaCap/streaming/releases)'teki sürüm numaralı `v…` sayfalarından) **`RizeOn-Kurulum.exe`**'yi indir ve çalıştır. Yeni sürümü kurmak için aynısını yap, eskisinin üstüne kurulur. Kurulum yerini sorar, Başlat menüsüne ekler (Windows aramasına "RizeOn" yazınca çıkar) ve istersen masaüstüne kısayol koyar. "Windows bilgisayarınızı korudu" çıkarsa: *Ek bilgi → Yine de çalıştır* (kurulum programı imzalı değil). Kaldırmak için: *Ayarlar → Uygulamalar → RizeOn → Kaldır* (ayarların ve kayıtların silinmez).
   - Kurmadan denemek istersen aynı sayfadaki `RizeOn.zip`'i bir klasöre çıkarıp `RizeOn\RizeOn.exe`'yi çalıştırabilirsin (`D:\streaming\guncelle.bat` bunu indirir).

### İndirirken ya da açarken Windows uyarı verirse

Kurulum programı henüz **kod imzalı değil** ve az indirildiği için Microsoft'un "tanınmış dosyalar" listesinde yok. Bu yüzden Windows ve Edge, virüs bulmasalar da tanımadıkları her .exe için uyarı gösterir.

1. **Edge indirmeyi durdurursa** ("… yaygın olarak indirilmiyor"): İndirilenler listesinde dosyanın üstüne gel, **⋯** → **Sakla** (*Keep*) → **Daha fazla göster** (*Show more*) → **Yine de sakla** (*Keep anyway*).
2. **Açınca "Windows bilgisayarınızı korudu" çıkarsa:** **Ek bilgi** → **Yine de çalıştır**.
3. **Dosyanın gerçekten bu depodan geldiğini denetlemek için:** PowerShell'de `Get-FileHash .\RizeOn-Kurulum.exe` yaz. Çıkan özet, aynı Releases sayfasındaki `SHA256SUMS.txt` dosyasındaki satırla aynı olmalı.

Uyarı **"virüs algılandı"** ya da **"cihazınıza zarar verebilir"** diyorsa geçme; bize bildir. Bu, Windows Defender'ın yanlış alarmı olabilir. Dosyayı Microsoft'a inceleme için göndermemiz gerekir.

## Kullanım

1. Uygulamayı aç. Sanal kamera ve sanal mikrofon arka planda **kendiliğinden başlar**; ayrı bir Yayın düğmesi yok. Duraklatmak için tepsi simgesine sağ tık → *Sanal çıkışı duraklat*.
2. Zoom / Meet / Discord'da: kamera **OBS Virtual Camera**, mikrofon **CABLE Output (VB-Audio Virtual Cable)**.
3. Ana pencere ilk açılışta Gelişmiş görünümle açılır: solda sahneler ve kaynaklar, ortada önizleme ve altta kontrol barı (Mikrofon, Sistem sesi, Kamera, Göster, Bölge, Kalem, Kayıt), sağda ses mikseri ve ses anahtarları. Başlık çubuğundaki **☰ Gelişmiş** ile sade görünüme geçilir. Aktif sahnede kamera kaynağı yoksa Kamera düğmesi kapalı görünür ve basılamaz. Pencere daraldıkça sütunlar alt alta geçer. Uygulama son seçimi hatırlar.
4. Ne gösterileceğini **Göster** menüsünden seç: tüm ekran, bir monitör, bir pencere ya da ekranın bir bölgesi.
5. Pencereyi kapatınca uygulama saatin yanındaki tepside çalışmaya devam eder; kısayollar açık kalır. Uygulama tek kopya çalışır: exe'yi tekrar açarsan çalışan pencere öne gelir. Pencere ve mini bar kapalıyken (kayıt da yoksa) kamera kapalı tutulur. Kayıt sürerken pencereyi kapatırsan mini bar açılır. Tamamen kapatmak için tepsi menüsü ya da ana pencerenin en altındaki *Çıkış* (kayıt açıksa önce sorar).

### Kısayollar (hepsi Ayarlar > Kısayollar'dan değiştirilebilir)

2.0.0'da kısayollar oyunlar ve dizüstü Fn tuşlarıyla çakışmasın diye **Ctrl+Shift**'e taşındı. Eski sürümden gelirken sadece hiç değiştirmediğin tuşlar taşınır; yeni tuş başka bir işte kullanılıyorsa o kısayol boş bırakılır.

| Tuş | İşlev |
| --- | --- |
| Ctrl+Shift+S | Bölge seç: kutu çiz, **Yakınlaştır** ya da **Vurgula**; **Enter** tamam, **Esc** vazgeç. Tekrar basınca tam ekrana döner |
| Ctrl+Shift+D | Kalemi aç/kapat |
| 1–7 | Kalem türü: kalem, fosforlu, ok, kare, yazı, lazer, silgi (sadece kalem açıkken) |
| Ctrl+Z / Del / Esc | Geri al / hepsini sil / kalemi kapat (sadece kalem açıkken; sağ tık da geri alır) |
| Ctrl+Shift+X | Çizimleri sil (kalem kapalıyken de) |
| Ctrl+Shift+M / A / C | Mikrofon / sistem sesi / kamera aç-kapat |
| Ctrl+Shift+B | Son 2 dakikayı MP4 olarak kaydet (anlık tekrar) |
| Ctrl+Shift+G | Ekran görüntüsü (çizimler dahil, PNG) |
| Ctrl+Shift+P | Panik: anında bekleme ekranı, ses kesilir; tekrar basınca geri döner |
| Ctrl+Shift+1 … 9 | Sahne seç |
| Ctrl+Shift+R | Yerel MP4 kaydı başlat/durdur. Başka bir uygulamadayken basarsan mini bar açılır |
| Ctrl+Shift+K | Kaydı duraklat / devam et. Duraklatılan süre videoya girmez |
| (ayarlanabilir) | Ne gösterilsin: tüm ekran ya da bir pencere |
| (ayarlanabilir) | Bas-konuş: basılıyken mikrofon açık (Gelişmiş görünümde *Bas-konuş* anahtarı açık olmalı) |

Kısayollara farenin orta tuşu ve yan tuşları da atanabilir (Fare3, Fare4, Fare5; Ctrl/Alt/Shift ile de): Ayarlar > Kısayollar'da hücreye çift tıklayıp fare tuşuna bas. Fare tıkı açık uygulamaya da gider. Kalem açıkken yazı aracında var olan yazıyı tutup sürükleyerek yerini değiştirebilirsin; boş yazı kutusu dışarı tıklayınca ya da Esc ile kapanır.

Kısayola basınca sağ altta kısa bir bildirim çıkar ("Mikrofon kapandı · Ctrl+Shift+M"). Başka bir program aynı tuşu kullanıyorsa uygulama bunu söyler ve Ayarlar > Kısayollar'da o tuşun yanında ⚠ görünür.

### Özellikler

- **Sahneler ve kaynaklar** (Gelişmiş görünüm): her sahnede ekran, pencere, ekran bölgesi, kamera, resim, yazı, imleç vurgusu gibi kaynaklar sabit yerlerde durur; göz simgesiyle gizlenir. Sahne adına çift tıklayıp değiştirebilirsin. Kamerayı **önizlemede fareyle sürükleyerek** istediğin yere koyabilirsin (boyut, ayna, **arka plan bulanıklaştırma** Ayarlar > Kamera).
- **Ses mikseri**: mikrofon ve sistem sesi ayrı seviyeler; **Sesim / Dengeli / Oyun** modları tek tıkla seviyeleri ayarlar (kendi ayarını moda kaydedebilirsin; Ayarlar > Ses'ten sıfırlanır). Mikrofon seçimi Ayarlar > Ses'te. Sistem sesinde Zoom/Discord/Teams ve uygulamanın kendi sesi **hiç alınmaz**, böylece yankı oluşmaz. (Meet tarayıcıda çalıştığı için yankı olursa kulaklık kullan ya da Ayarlar > Ses'te `msedge.exe`'yi hariç listesine ekle.)
- **Gürültü azaltma** (RNNoise): klavye, fan ve uğultu sesini bastırır. Gelişmiş görünümdeki *Gürültü azaltma* anahtarıyla açılır.
- **Otomatik ses kısma** (konuşunca oyun sesi kısılır) ve **bas-konuş**.
- **Bölge**: ekranın bir kısmını animasyonla yakınlaştır ya da vurgula (geri kalan kararır). Yakınlaştırınca seçilen yer ekranında ince bir çerçeveyle gösterilir (sadece sen görürsün).
- **Kalem**: kalem, fosforlu, ok, kare, yazı (Türkçe), lazer, silgi; 4 renk, 3 kalınlık. Çizimler yayına ayrıca eklenir, tam ekran oyunda katman görünmese bile karşı taraf görür.
- **Anlık tekrar**: son 2 dakika bellekte tutulur, **Ctrl+Shift+B** (ya da başlık çubuğundaki düğme) `Tekrar_….mp4` olarak kaydeder. Diske sürekli yazılmaz. Süre (30 sn – 5 dk) ve aç/kapa Ayarlar > Genel'de; kapalıyken hiç bellek kullanmaz.
- **Ekran görüntüsü**: **Ctrl+Shift+G** ya da mini bardaki düğme karşı tarafın gördüğü görüntüyü (çizimler dahil) `Goruntu_….png` olarak kaydeder. Klasör Ayarlar > Genel'de.
- **Mini bar**: her zaman üstte duran küçük bar (başlık çubuğunda *Mini bar*). Kayıt yokken araçlarla açılır, kayıt başlayınca kendiliğinden küçülür (süre, duraklat).
- **Bekleme ekranı**: yazı, resim ya da sessiz döngüde oynayan kısa video (MP4/GIF…).
- **Yerel kayıt**: `Videolar\RizeOn\` klasörüne MP4; ekran kartına göre NVIDIA/Intel/AMD donanım kodlayıcısı. Kayıt kamerayı kendiliğinden kapatmaz; gördüğün neyse o kaydedilir. Kayıt bitince köşede *Klasörde göster* çıkar. Uygulama çökerse ya da elektrik giderse kayıt bir sonraki açılışta `..._kurtarildi.mp4` olarak kurtarılır. Disk dolarsa kayıt durur, o ana kadarki kısım kaydedilir.
- **Sanal çıkış uyarıları**: OBS Virtual Camera ya da VB-Cable bulunamazsa köşede "Sanal mikrofon bulunamadı · Nasıl düzeltilir?" çıkar; tıklayınca adım adım yardım açılır. Sorun sürdükçe tepsi menüsünde de görünür.
- Uygulamanın **bütün pencereleri** (ana pencere, menüler, ayarlar, kalem barı, bölge seçimi, bildirimler, mini bar) **ekran yakalamaya girmez**; karşı taraf görmez.
- Bir kaynak koparsa (kamera çıkarılır, mikrofon değişir) uygulama çökmez; birkaç saniyede bir yeniden denenir.

### Bildirimler hakkında

Windows'ta başka bir uygulamanın bildirimini ekran yakalamadan çıkarmanın resmi bir yolu yok. Görüşmeye başlamadan önce **Rahatsız Etme'yi (Win+N)** açman önerilir.

## Sorun giderme

| Sorun | Çözüm |
| --- | --- |
| "Sanal kamera bulunamadı" | OBS kurulu değil ya da sanal kamerası hiç başlatılmamış (Kurulum 1). Bildirimdeki *Nasıl düzeltilir?* adımları gösterir. |
| "Sanal mikrofon bulunamadı" | VB-Cable kurulu değil ya da bilgisayar yeniden başlatılmadı (Kurulum 2). |
| Karşı taraf sadece gürültü duyuyor | Windows varsayılan girişi CABLE olmuş; gerçek mikrofona çevir (Kurulum 3). |
| Ses kısık | Mikserde Mikrofon kaydırıcısını %100'ün üstüne çıkar. |
| Yankı var | Hoparlörden çıkan sesi mikrofon da duyuyor olabilir: kulaklık kullan. Meet gibi tarayıcıdan katılıyorsan tarayıcıyı (`msedge.exe`) Ayarlar > Ses'te hariç listesine ekle. |
| Kısayol çalışmıyor | Başka bir program kullanıyor olabilir; Ayarlar > Kısayollar'dan değiştir. Tek başına F12 kullanılamaz (Windows'a ayrılmış). Oyun yönetici olarak çalışıyorsa uygulamayı da yönetici olarak aç. |
| Zoom "kamera başka uygulamada" diyor | Birkaç saniye bekle ya da Zoom'da kamerayı kapatıp aç. |
| "OBS sanal kamerası başka bir programda açık" | OBS Studio açık ve kendi sanal kamerası çalışıyor; OBS'de *Sanal Kamerayı Durdur*'a bas ya da OBS'yi kapat. |
| Kamera "yok" görünüyor | Windows *Ayarlar → Gizlilik ve güvenlik → Kamera*'da masaüstü uygulamalarının kameraya erişimi açık olmalı. Ayarlar > Kamera'dan kamera numarasını da dene. |
| Uygulama açılmıyor | Bir hata penceresi çıkar ve log klasörünü açmayı önerir; `uygulama.log` ve `cokme.log` dosyalarını gönder. |

Ayarlar `%APPDATA%\RizeOn\settings.json` (elle bozulan bir değer varsayılana döner), loglar `%APPDATA%\RizeOn\logs\` klasöründe (`uygulama.log`, yerel çökmeler için `cokme.log`). Bir sorun olursa bu dosyaları ve sürüm numarasını (*Hakkında*) gönder.

## Geliştirici kurulumu

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py          # uygulamayı çalıştır
python -m pytest -q     # testler
```

Yerel kayıt için `ffmpeg\ffmpeg.exe` (LGPL derlemesi) gerekir; paketlenmiş sürümde hazır gelir, geliştirirken PATH'teki ffmpeg de kullanılır (paketlenmiş sürümde kullanılmaz). Bağımlılık sürümleri `requirements*.txt`'te sabittir; güncellerken CI'da testlerin geçtiğini gör. `main` dalına her birleşmede GitHub Actions Windows'ta testleri çalıştırır, PyInstaller ile paketler ve [uygulama](https://github.com/MustafaCap/streaming/releases/tag/uygulama) sürümünü günceller. `core/surum.py`'deki sürüm numarası ilk kez görüldüğünde ayrıca kalıcı bir `v<sürüm>` sürümü açılır; notu [CHANGELOG.md](CHANGELOG.md)'den gelir (yeni sürüm numarası verirken oraya not ekle, yoksa test kırılır). Her Release'te `SHA256SUMS.txt` dosya özetleri bulunur; paketteki `ffmpeg\KAYNAK.txt` kullanılan FFmpeg'in adını ve özetini yazar. Aynı adımda `kurulum/kurulum.iss` Inno Setup ile `RizeOn-Kurulum.exe`'ye çevrilir. Paket tek bir .exe yerine klasördür (`--onedir`): tek .exe her açılışta 100+ MB'ı geçici klasöre açtığı için yavaş başlar ve antivirüslere daha çok takılır. Aynı nedenle CI, PyInstaller önyükleyicisini kaynaktan derler (hazır önyükleyiciye antivirüsler daha çok takılıyor). Exe'ye `kurulum/surum_bilgisi.py` ile sürüm bilgisi yazar ve paketlenmiş exe'yi `RizeOn.exe --duman-testi sonuc.txt` ile pencere açmadan bir kez çalıştırır.

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
kurulum/             Windows kurulum programı (Inno Setup betiği), uygulama simgesi,
                     lisans toplama betiği ve Türkçe lisans özeti
tests/               birim testleri (pytest)
denemeler/           Aşama 0 risk denemeleri
```

## Lisans

RizeOn **özgür ve açık kaynak** bir yazılımdır: **GNU GPL sürüm 3** ile dağıtılır (tam metin: [LICENSE](LICENSE)). Telif hakkı © 2026 Mustafa.

Kısaca: ücretsiz kullanabilir, kopyalayabilir, paylaşabilirsin. Değiştirip dağıtan kişi, değiştirdiği hali de GPLv3 ile ve kaynak koduyla birlikte dağıtmak zorundadır. Program hiçbir garanti olmadan sunulur. Kurulum programı lisansı ilk sayfada gösterir; uygulamada *Ayarlar → Hakkında* ya da tepsi menüsü → *Hakkında*'dan da görülür.

### Kullanılan parçalar

Paketin içindeki `lisanslar` klasöründe her parçanın kendi lisans metni ve `UCUNCU_PARTI_LISANSLAR.txt` listesi var (CI'da `kurulum/lisanslar.py` toplar).

| Parça | Lisans |
| --- | --- |
| PySide6 / Qt | LGPLv3 |
| OpenCV (opencv-python) | Apache 2.0 (içindeki FFmpeg LGPLv2.1) |
| FFmpeg (BtbN LGPL derlemesi, `ffmpeg\`) | LGPLv2.1+ |
| RNNoise (gürültü azaltma, `rnnoise\`, kaynak koddan derlenir) | BSD-3 |
| numpy | BSD-3 |
| Pillow | MIT-CMU (HPND) |
| psutil | BSD-3 |
| mss, dxcam, comtypes, PyAudioWPatch (PortAudio) | MIT |
| MediaPipe Selfie Segmentation modeli (`models\`) | Apache 2.0 |
| Python çalışma zamanı | PSF |

Sanal kamera çıkışı kendi kodumuzdur (`outputs/obs_kamera.py`): görüntüyü OBS'nin sanal kamera sürücüsünün okuduğu paylaşılan belleğe yazar. Önceden kullanılan pyvirtualcam sadece GPLv2 lisanslı olduğu ve GPLv3 ile aynı pakette dağıtılamadığı için çıkarıldı.

OBS Virtual Camera ve VB-Cable pakete konmaz, kullanıcı ayrıca kurar. QFluentWidgets bilerek kullanılmadı.
