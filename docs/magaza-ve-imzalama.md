# Microsoft Store ve SignPath için hazır metinler

Uygulamanın adı: **RizeOn**. Henüz kendi alan adı yok; web sitesi olarak GitHub sayfası kullanılıyor.

## 1. Microsoft Store (Partner Center) sayfası

Partner Center'da *Uygulamalar ve oyunlar → Yeni ürün → MSIX veya PWA uygulaması* yolunu izle. Alanlara şunları kopyala:

| Alan | Değer |
| --- | --- |
| Ürün adı (ayırt) | `RizeOn` |
| Kategori | Fotoğraf ve video (*Photo & video*) |
| Fiyat | Ücretsiz |
| Gizlilik politikası adresi | https://github.com/MustafaCap/streaming/blob/main/docs/gizlilik.md |
| Destek / web sitesi | https://github.com/MustafaCap/streaming |
| Telif | Copyright (C) 2026 Mustafa. GNU GPL sürüm 3. |
| Paket | Releases'teki `RizeOn-Store.msix` (kimlik değişkenleri girildikten sonra derlenmiş olanı) |

**Kısa açıklama (TR):** Meet, Zoom ve Discord'da sanal kamera ve sanal mikrofon olarak görünen, internete bağlanmayan ekran, kamera ve ses paylaşım uygulaması.

**Açıklama (TR):**

> RizeOn, ekranını, kameranı ve sesini tek bir görüntüde birleştirip görüntülü görüşme programlarına sanal kamera ve sanal mikrofon olarak verir.
>
> - Tek tuşla (F6) ekranın bir bölgesini seç ve sadece onu göster
> - Ekranın üstüne anında çizim yap (F7)
> - Kamerayı köşeye koy, taşı, arka planı bulanıklaştır
> - Mikrofon, bilgisayar sesi ve tek tek uygulamaların sesi için mikser
> - Bas-konuş, panik tuşu, bekleme görüntüsü
> - Bilgisayarına MP4 kayıt
>
> İnternete hiç bağlanmaz, hesap istemez, veri toplamaz. Özgür ve açık kaynaktır (GPLv3).
>
> **Gerekenler:** Sanal kamera için ücretsiz OBS Studio'nun (obsproject.com), sanal mikrofon için ücretsiz VB-Cable'ın (vb-audio.com) kurulu olması gerekir. Uygulama bunların kurulu olup olmadığını ana pencerede gösterir.

**Description (EN):**

> RizeOn combines your screen, camera and audio into one picture and hands it to video-call apps as a virtual camera and virtual microphone.
>
> - Pick a region of your screen with one key (F6) and show only that
> - Draw on top of your screen instantly (F7)
> - Camera overlay you can move, with background blur
> - Mixer for microphone, system audio and individual apps
> - Push-to-talk, panic key, standby image
> - Local MP4 recording
>
> It never connects to the internet, needs no account and collects no data. Free and open source (GPLv3).
>
> **Requirements:** the free OBS Studio (obsproject.com) for the virtual camera and the free VB-Cable (vb-audio.com) for the virtual microphone.

**Anahtar kelimeler:** sanal kamera, virtual camera, ekran paylaşımı, screen share, zoom, meet, discord, çizim

**Kısıtlı yetki gerekçesi (runFullTrust)** — Partner Center sorarsa:

> This is a desktop (Win32) app packaged with MSIX. It needs full trust to capture the screen (DXGI), register global hotkeys, capture per-application audio with WASAPI process loopback, and write frames to the OBS Virtual Camera driver's shared memory. It has no network access.

**Yaş derecelendirmesi (IARC anketi):** Şiddet, cinsellik, kumar yok. Kullanıcılar arası iletişim, konum paylaşımı ve satın alma yok. Sonuç büyük ihtimalle "3+" çıkar.

**Ekran görüntüleri:** En az 1 tane gerekiyor, en az 1366×768 boyutunda. Ana pencereyi, F6 bölge seçimini ve F7 çizimi gösteren 3 görüntü yeterli. Bunları senin çekmen gerekiyor.

**Risk:** Store denetçisi, OBS ve VB-Cable'ın ayrıca kurulması gerektiğine itiraz edebilir. Açıklamada bunu açıkça yazdık. İtiraz ederlerse cevabını birlikte yazarız.

## 2. SignPath Foundation başvurusu

Başvuru adresi: https://signpath.org/apply. Form şunları sorarsa:

| Soru | Cevap |
| --- | --- |
| Project name | `RizeOn` |
| Repository | https://github.com/MustafaCap/streaming |
| License | GPL-3.0 (all components open source; FFmpeg LGPL build, PySide6 LGPL) |
| Description | Offline Windows app that provides a virtual camera and virtual microphone for video calls (screen region sharing, on-screen drawing, camera overlay, audio mixer). No network access. |
| Build | GitHub Actions on `windows-latest` (`.github/workflows/uygulama.yml`): tests, PyInstaller (bootloader built from source), Inno Setup installer |
| Artifacts to sign | `RizeOn.exe` (app) and `RizeOn-Kurulum.exe` (Inno Setup installer) |
| Releases | https://github.com/MustafaCap/streaming/releases |
| Team | Mustafa (author, reviewer, approver) |
| Why signing | Edge/SmartScreen blocks the unsigned installer for users |

## 3. Kod imzalama politikası (SignPath kabul ederse README'ye eklenecek)

SignPath, proje sayfasında bu başlıkla bir bölüm istiyor. Kabul gelmeden eklenmez, çünkü "imzayı SignPath veriyor" cümlesi o zamana kadar doğru olmaz.

> ## Code signing policy
>
> Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).
>
> - Committers and reviewers: [Mustafa](https://github.com/MustafaCap)
> - Approvers: [Mustafa](https://github.com/MustafaCap)
>
> Privacy: this program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. See [docs/gizlilik.md](docs/gizlilik.md).
