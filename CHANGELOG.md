# Değişiklikler

Her sürüm [Releases](https://github.com/MustafaCap/streaming/releases) sayfasında `v<sürüm>` adıyla kalıcı olarak durur (1.5.0'dan itibaren). `uygulama` sürümü her zaman en son paketi gösterir.

## 3.1.0 — 2026-11-11

- **Toplantıda paylaş:** Zoom, Meet ve Teams sanal kameraya düşük çözünürlük ayırdığı için ekran bölgesi, kalem ve yazılar toplantıda bulanık görünüyordu. Yeni "Toplantıda paylaş" düğmesi (ana pencerenin üstünde ve tepsi menüsünde) RizeOn görüntüsünü çerçevesiz ayrı bir pencerede açar. Toplantıda **Ekranı paylaş > Pencere > "RizeOn Toplantı"** seçilince görüntü ekran paylaşımı kalitesinde, net gider. Yüzün istersen aynı anda sanal kameradan gitmeye devam eder.
  - Sürükleyerek taşınır, kenarlarından boyutlandırılır (oran korunur). Çift tık 1280×720 ile 1920×1080 arasında geçer; sağ tık menüsünden boyut seçilir ya da kapatılır. Esc de kapatır.
  - Simge durumuna küçültülmez (küçültülen pencereyi toplantı uygulaması donmuş görür). Başka pencerelerin arkasında kalabilir.
  - Birden fazla monitör varsa yakalanmayan monitörde açılır. Tek monitörde yakalanan ekranın üstünde açık bırakılırsa görüntü kendi içine yansır; toplantı uygulamasını önüne alman yeterli.
  - İstersen Ayarlar > Kısayollar'dan bir kısayol atanabilir ("toplanti.pencere").

## 2.0.6 — 2026-11-03

- **İşlemci teşhisi:** uygulama 30 saniyede bir log dosyasına (`%APPDATA%\RizeOn\logs\uygulama.log`) işlemcinin nereye gittiğini yazar: video hattı, ses, webcam, anlık tekrar, FFmpeg ayrı ayrı, Görev Yöneticisi gibi tüm çekirdeklere oranla. Satır "CPU dağılımı" ile başlar. Hiçbir yere gönderilmez.

## 2.0.5 — 2026-11-03

- **Daha az işlemci kullanımı.** Ölçümde (aynı bilgisayarda, 30 FPS, sanal kamera + anlık tekrar açık) görüntü hattı: masaüstü dururken bir çekirdeğin %51'i yerine %2'si, ekran sürekli değişirken (oyun, video) %52 yerine %23'ü, ekran + köşede kamera varken %52 yerine %18'i.
  - Ekran ve fare yerinde duruyorsa kare baştan kurulmaz; bir önceki kare aynen kullanılır.
  - Ekranı 720p'ye küçültme 4-5 kat hızlı (görüntü göz ile ayırt edilemeyecek kadar aynı).
  - Sanal kamera, anlık tekrar ve kayıt aynı kareyi ayrı ayrı çevirmiyor; NV12'ye bir kez çevrilir. FFmpeg'e de NV12 gider, donanım kodlayıcı (QSV, NVENC) için FFmpeg ayrıca çevirmez.
  - Önizleme görüntü değişmediyse yeniden çizilmez.
  - Pencere yakalamada renk çevirme ~10 kat hızlı.
- Kayıt ve yayın kalitesi, kodlayıcı ayarları değişmedi.

## 2.0.4 — 2026-11-03

- Microsoft Store paketi (`RizeOn-Store.msix`) artık Partner Center'daki gerçek RizeOn kimliğiyle derleniyor, Store'a yüklenebiliyor. Paket Türkçe ve İngilizce mağaza sayfasını destekliyor.

## 2.0.3 — 2026-11-02

- **Anlık tekrar varsayılanı 15 saniye** (önceden 2 dakika): bellekte çok daha az yer tutar. Düğme "Son 15 sn'yi kaydet" olur; süre Ayarlar > Genel'den 15 sn ile 5 dk arasında seçilir. Süreyi hiç değiştirmemiş olanlarda da 15 sn'ye geçer.
- **Zoom'da ses-görüntü uyumu:** sanal mikrofonun ses tamponu en fazla 0,25 sn yerine 0,12 sn tutar; ses görüntünün gerisinde daha az kalır.
- **Uzun kayıtlarda ses kayması giderildi:** ses, görüntüyle aynı saate göre yazılır. Bilgisayar yetişemeyip ses atlarsa boşluk sessizlikle doldurulur, ses önde giderse fazlası atılır.
- **Kayıt ve anlık tekrar daha hafif:** FFmpeg'e kareler RGB yerine YUV olarak gider (yarı yarıya daha az veri) ve gereksiz bir kopya kaldırıldı.

## 2.0.2 — 2026-11-02

- **Kayıt:** kaydı durdurup dosya hazırlanırken hemen yeni kayıt başlatılırsa iki kayıt birbirine karışabiliyordu (yeni kaydın sesi kesilebiliyor, eski kayıt "kaydedilemedi" diyebiliyordu). Artık önceki dosya hazır olana kadar yeni kayıt başlamaz ve "birkaç saniye sonra tekrar dene" der.
- **Kayıt ve anlık tekrar:** aynı saniyede iki dosya oluşursa ikincisi birincinin üstüne yazmaz, adının sonuna ~2 eklenir.
- **Anlık tekrar:** kaydederken uygulama kapanırsa Kayıtlar klasöründe kalan gizli geçici dosyalar bir sonraki açılışta silinir.
- Okunamayan bir kaynak (ör. bozuk ayar) log dosyasına saniyede 30 kez aynı hatayı yazmıyor; ilk seferinde ayrıntılı, sonra arada bir özetle yazılır.
- Güvenlik denetimi: indirme sayfasına dosya koyan GitHub eylemi sabit bir sürüme bağlandı (paketlerin değiştirilemeden yayımlanması için).

## 2.0.1 — 2026-11-02

- **Kamera:** aktif sahnede kamera kaynağı yoksa mini bardaki, ana penceredeki ve tepsideki Kamera düğmesi kapalı görünür ve basılamaz (kısayol da "Bu sahnede kamera yok" der). Böylece kamera seni çekmiyorken "açık" görünmez.
- **Kalemdeki yazı aracı:** yazılan yazı tutulup sürüklenerek taşınır (Ctrl+Z / sağ tık eski yerine döndürür, sürüklerken Esc iptal eder). Yazı kutusu açıkken dışarı tıklamak artık yeni kutu açmaz: boşsa kutu kapanır, yazı varsa kaydedilir.
- **Fare tuşları kısayol olabilir:** orta tuş ve yan tuşlar (Fare3, Fare4, Fare5), Ctrl/Alt/Shift ile birlikte de. Ayarlar > Kısayollar'da hücreye çift tıklayıp fare tuşuna basman yeterli. Bas-konuş için de çalışır.
- İlk açılışta **Gelişmiş görünüm** açık gelir (eski kurulumlarda da bir kez açılır; kapatırsan hatırlanır).
- **Çıkış** düğmesi Ayarlar'dan ana pencerenin en altına, CPU / GPU / FPS yazısının yanına taşındı.

## 2.0.0 — 2026-11-02

- Arayüz baştan tasarlandı: tek renk gri tema, yeni logo, çerçevesiz ana pencere ve başlık çubuğu (Gelişmiş, Kayıt klasörü, Son 2 dk'yı kaydet, Mini bar, Ayarlar). Pencere daraldıkça sütunlar alt alta geçer; sade görünümde pencere daha küçük olabilir.
- **Yayın düğmesi kalktı.** Sanal kamera ve sanal mikrofon uygulama açılınca arka planda kendiliğinden başlar; tepsi menüsünden *Sanal çıkışı duraklat* ile durdurulur.
- **Kayıt artık kamerayı kendiliğinden kapatmıyor.** Önizlemede ne görüyorsan o kaydedilir ("Kayıtta kamera da açık olsun" ayarı kalktı).
- Gelişmiş görünümde sahneler ve kaynaklar: her sahneye ekran, pencere, ekran bölgesi, kamera, resim, yazı gibi kaynaklar eklenir, sabit yerlerde durur, göz simgesiyle gizlenir. Kontrol barındaki **Göster** menüsünden tüm ekran, monitör, pencere ya da bölge seçilir.
- Ses mikserinde **Sesim / Dengeli / Oyun** modları. Mikrofon seçimi Ayarlar > Ses'e taşındı. Alt satırda CPU, GPU ve FPS görünür.
- Bölge seçimi ve kalem tek katmanda birleşti: bölgede **Yakınlaştır / Vurgula**, yeni kalem barı (silgi, 3 kalınlık, yeni renkler, geri al, temizle). Kalem barı sürüklenebilir.
- Yeni mini bar: kayıt yokken araçlarla açılır, kayıt başlayınca kendiliğinden küçülür.
- **Anlık tekrar:** son 2 dakika bellekte tutulur, Ctrl+Shift+B ile `Tekrar_….mp4` olarak kaydedilir. Diske sürekli yazmaz. Süre 30 sn – 5 dk arası ayarlanır, kapatılabilir (kapalıyken bellek kullanmaz).
- **Ekran görüntüsü:** Ctrl+Shift+G ya da mini bardaki düğme, karşı tarafın gördüğü görüntüyü çizimlerle birlikte `Goruntu_….png` olarak kaydeder.
- **Gürültü azaltma (RNNoise):** klavye, fan ve uğultu sesini bastırır. Kütüphane kaynak koddan derlenip pakete konur.
- Köşe bildirimleri yenilendi: "Son 2 dk kaydedildi · Aç", "Ekran görüntüsü kaydedildi", "Kayıt kaydedildi · Klasörde göster". Sanal kamera ya da mikrofon bulunamazsa "… bulunamadı · Nasıl düzeltilir?" çıkar, tıklayınca yardım açılır; sorun sürdükçe tepsi menüsünde de görünür.
- **Kısayollar Ctrl+Shift'e taşındı** (F tuşları oyunlarla ve Fn tuşlarıyla çakışıyordu): Bölge Ctrl+Shift+S, Kalem Ctrl+Shift+D, Mikrofon Ctrl+Shift+M, Sistem sesi Ctrl+Shift+A, Kamera Ctrl+Shift+C, Son 2 dk Ctrl+Shift+B, Panik Ctrl+Shift+P, Sahneler Ctrl+Shift+1…9, Kaydı duraklat Ctrl+Shift+K. Yeni: Ekran görüntüsü Ctrl+Shift+G, Çizimleri sil Ctrl+Shift+X, kalemde 7 = silgi, Esc = kalemi kapat. Eski sürümden gelirken sadece hiç değiştirmediğin tuşlar taşınır; yeni tuş başka bir işte kullanılıyorsa boş bırakılır.
- Alınamayan kısayollar bildirilir ve Ayarlar > Kısayollar'da ⚠ ile işaretlenir.
- Ayarlara yeni seçenekler: anlık tekrar süresi ve aç/kapa, ekran görüntüsü klasörü, mikrofon seçimi, ses modlarını sıfırla, Çıkış düğmesi.
- Ayarlar, Hakkında ve yardım dahil uygulamanın bütün pencereleri ekran yakalamaya girmez.

## 1.7.0 — 2026-10-31

- Kayıt duraklatılıp devam ettirilebiliyor. Kayıt sürerken **Duraklat** düğmesi çıkıyor (mini çubukta ⏸, kısayol Ctrl+Alt+D). Duraklatılan süre videoya girmiyor ve kayıt süresine sayılmıyor. Duraklatılmışken uygulama çökerse kayıt yine kurtarılıyor.
- Tüm ekran yerine tek bir pencere gösterilebiliyor. **Göster** düğmesinden (mini çubukta 🗔) açık pencerelerden biri seçiliyor. Yayında ve kayıtta sadece o pencere görünüyor, üstüne başka pencere gelse bile. Yayın ya da kayıt sürerken de değiştirilebiliyor.
- Ana pencere sadeleşti. Varsayılan görünümde önizleme ve temel düğmeler var: Yayın, Kayıt, Göster, Kamera, Mikrofon, Bilgisayar sesi. Sahneler, ses mikseri, kare seçme, kalem, panik ve bekleme ekranı **☰ Gelişmiş** düğmesiyle açılıyor. Uygulama son seçimi hatırlıyor.
- Kayıtlar düğmesi sağ alta taşındı.

## 1.6.0 — 2026-10-31

- Uygulamanın adı artık **RizeOn**. Pencere, tepsi, Hakkında, exe (`RizeOn.exe`), kurulum programı (`RizeOn-Kurulum.exe`), zip ve Store paketi yeni adla geliyor.
- Eski sürümün üstüne kurulur. Kurulum programı eski `YayinUygulamasi.exe`'yi ve "Yayın Uygulaması" kısayollarını siler. Uygulama eski adla açıksa önce kapatılmasını ister.
- Ayarlar, loglar ve bekleme görüntüleri ilk açılışta `%APPDATA%\YayinUygulamasi`'ndan `%APPDATA%\RizeOn`'a taşınır. Ayarlardaki eski klasör yolları da düzeltilir.
- Yeni kayıtlar `Videolar\RizeOn` klasörüne yazılır. Eski kayıtlar `Videolar\YayinUygulamasi`'nda kalır.

## 1.5.1 — 2026-10-31

- Antivirüslerin yanlış alarm verme ihtimali azaltıldı:
  - Exe'nin başındaki PyInstaller önyükleyicisi artık hazır gelen yerine kaynak koddan derleniyor. Hazır olanı zararlı programlar da kullandığı için antivirüslere takılabiliyordu.
  - Exe ve kurulum programının *Özellikler → Ayrıntılar* sekmesinde artık ürün adı, sürüm, üretici ve lisans bilgisi var.
- Her derlemede paketlenmiş exe pencere açmadan bir kez çalıştırılıyor. Böylece eksik bir parça varsa sürüm yayınlanmadan fark ediliyor.
- Microsoft Store için MSIX paketi (`YayinUygulamasi-Store.msix`) her derlemede hazırlanıyor. Gizlilik politikası (`docs/gizlilik.md`) ve mağaza / SignPath başvuru metinleri (`docs/magaza-ve-imzalama.md`) eklendi.
- README'ye, Edge indirmeyi durdurduğunda ya da Windows "bilgisayarınızı korudu" dediğinde ne yapılacağı ve dosyanın SHA-256 ile nasıl denetleneceği eklendi.

## 1.5.0 — 2026-10-31

- Pencere kapatıldıktan ya da uygulamadan çıkıldıktan sonra kameranın açık kalması düzeltildi:
  - Kamera hızlıca kapatılıp açıldığında eski bağlantı artık arkada kalmıyor.
  - Kamera okunurken hata olursa kamera bırakılıyor.
  - Çıkış'ta bir şey takılırsa uygulama 15 saniye içinde zorla kapanıyor.
- Yayın ya da kayıt sürerken pencere kapatılırsa mini çubuk açılıyor. Böylece yayının sürdüğü görülüyor ve oradan durdurulabiliyor.
- Ana pencereye "Çıkış" düğmesi eklendi. Uygulamayı tamamen kapatıyor. Yayın ya da kayıt açıksa önce soruyor.
- Kayıt çökmeye dayanıklı hale geldi:
  - Uygulama çökerse ya da elektrik giderse yarım kalan kayıt bir sonraki açılışta `..._kurtarildi.mp4` olarak kurtarılıyor.
  - Disk dolarsa kayıt durduruluyor ve kullanıcıya söyleniyor. O ana kadarki kısım kaydediliyor.
  - Ses dosyasındaki 4 GB sınırı kalktı.
- Hatalar artık kaybolmuyor:
  - Arka plan hataları ve yerel çökmeler log'a yazılıyor (`logs\cokme.log`).
  - Açılışta bir hata olursa bunu söyleyen bir pencere çıkıyor.
  - Aynı hata log'u doldurmuyor.
- `settings.json`'a elle yanlış türde bir değer yazılırsa o ayar varsayılana dönüyor. Ayar dosyası kilitliyse uygulama çökmüyor.
- Bağımlılık sürümleri sabitlendi. Her sürüm için kalıcı bir Release ve SHA-256 dosya özetleri yayınlanıyor.

## 1.4.0 — 2026-10-31

- Uygulama özgür ve açık kaynak oldu: GNU GPL sürüm 3.
- Kurulum programı ilk sayfada lisansı gösteriyor.
- "Hakkında" penceresi eklendi (tepsi menüsü ve Ayarlar).
- Kullanılan kütüphanelerin lisansları paketteki `lisanslar` klasörüne konuyor.
- Sanal kamera artık kendi kodumuzla OBS Virtual Camera sürücüsüne yazılıyor. pyvirtualcam GPLv2 lisanslı olduğu ve GPLv3 ile uyumsuz olduğu için çıkarıldı.

## 1.3.0 — 2026-10-31

- Windows kurulum programı (`YayinUygulamasi-Kurulum.exe`):
  - Kurulum yerini soruyor.
  - Başlat menüsüne ekliyor, böylece uygulama Windows aramasında çıkıyor.
  - İsteğe bağlı masaüstü kısayolu oluşturuyor.
  - Ayarlar > Uygulamalar'dan kaldırılabiliyor.

## 1.2.0 — 2026-10-31

- Uygulama tek kopya çalışıyor. Tekrar açılınca çalışan pencere öne geliyor.
- Pencere gizliyken (yayın ya da kayıt da yoksa) kamera kapalı tutuluyor.
- Ctrl+Shift+R yayın kapalıyken kamerasız kayıt başlatıyor ve mini çubuğu açıyor.
- Mini çubuk küçüldü.

## 1.1.0 — 2026-10-31

- Yayın ya da kayıt durunca mikrofonun bir daha açılmaması düzeltildi.
- Yankı giderildi: bilgisayar sesi artık uygulama uygulama yakalanıyor ve Zoom/Discord hariç tutuluyor.
- Panik tuşu Ctrl+Alt+P oldu. F12'yi Windows ayırdığı için çalışmıyordu.
- Yakınlaştırılan kare ekranda ince bir çerçeveyle gösteriliyor.
- Kamera önizlemede sürüklenerek taşınabiliyor.
- Kayıtlar düğmesi eklendi.
- Bekleme ekranına resim ya da video konabiliyor.
- Mini çubukta Yayın ve Kayıt düğmeleri var.

## 1.0.0 — 2026-10-31

- İlk tam sürüm:
  - Ekran ve kamera, OBS Virtual Camera üzerinden sanal kamera olarak gidiyor.
  - Mikrofon ve bilgisayar sesi VB-Cable üzerinden sanal mikrofon olarak gidiyor.
  - Sahneler ve kare seçme (F6).
  - Ekrana çizim (F7).
  - Kısayollar, mini mod, ayarlar.
  - Panik, bas-konuş ve ses kısma.
  - Yerel MP4 kaydı.
  - Arka plan bulanıklaştırma.
