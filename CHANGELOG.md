# Değişiklikler

Her sürüm [Releases](https://github.com/MustafaCap/streaming/releases) sayfasında `v<sürüm>` adıyla kalıcı olarak durur (1.5.0'dan itibaren). `uygulama` sürümü her zaman en son paketi gösterir.

## 1.5.1 — 2026-10-31

- Antivirüslerin yanlış alarm verme ihtimali azaltıldı:
  - Exe'nin başındaki PyInstaller önyükleyicisi artık hazır gelen yerine kaynak koddan derleniyor. Hazır olanı zararlı programlar da kullandığı için antivirüslere takılabiliyordu.
  - Exe ve kurulum programının *Özellikler → Ayrıntılar* sekmesinde artık ürün adı, sürüm, üretici ve lisans bilgisi var.
- Her derlemede paketlenmiş exe pencere açmadan bir kez çalıştırılıyor. Böylece eksik bir parça varsa sürüm yayınlanmadan fark ediliyor.
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
