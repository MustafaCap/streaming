; RizeOn — Windows kurulum programı (Inno Setup 6)
;
; CI'da derlenir:  ISCC.exe /DSurum=1.3.0 kurulum\kurulum.iss
; Girdi : dist\RizeOn\  (PyInstaller çıktısı + ffmpeg + BENIOKU.md + lisanslar)
;         build\kurulum_lisans.txt  (python kurulum\lisanslar.py dist\RizeOn üretir)
; Çıktı : Output\RizeOn-Kurulum.exe
;
; Ne yapar:
;  - Lisansı gösterir (GPLv3, Türkçe özetle)
;  - Kurulum yerini sorar (varsayılan: Program Files\RizeOn)
;  - "Sadece benim için" seçilirse yönetici izni istemez (AppData\Local\Programs'a kurar)
;  - Başlat menüsüne ekler (Windows aramasında adıyla çıkar), isteğe bağlı masaüstü kısayolu
;  - Uygulama açıksa önce kapatılmasını ister (tek kopya mutex'i ile anlar)
;  - Denetim Masası / Ayarlar > Uygulamalar'dan kaldırılabilir
;  - Ayarlar ve kayıtlar (%APPDATA%, Videolar) kaldırırken silinmez

#ifndef Surum
  #define Surum "0.0.0"
#endif

#define UygulamaAdi "RizeOn"
#define ExeAdi "RizeOn.exe"

[Setup]
; AppId sabit kalmalı: yeni sürüm eskisinin üstüne kurulsun, ikinci kopya olmasın
AppId={{7E3B2A91-5C4D-4F8E-9A16-2D8B0C5E4F71}
AppName={#UygulamaAdi}
AppVersion={#Surum}
AppVerName={#UygulamaAdi} {#Surum}
AppPublisher=Mustafa
AppPublisherURL=https://github.com/MustafaCap/streaming
; Kurulum exe'sinin Özellikler > Ayrıntılar bilgisi (exe'ninkiyle aynı: kurulum/surum_bilgisi.py)
VersionInfoVersion={#Surum}
VersionInfoCompany=Mustafa
VersionInfoDescription={#UygulamaAdi} kurulum programı
VersionInfoCopyright=Copyright (C) 2026 Mustafa. GNU GPL sürüm 3 ile lisanslıdır.
VersionInfoProductName={#UygulamaAdi}
VersionInfoProductVersion={#Surum}
; Klasör adı ASCII: bazı kütüphaneler Türkçe karakterli yolları sevmiyor
DefaultDirName={autopf}\RizeOn
DefaultGroupName={#UygulamaAdi}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
SetupIconFile=uygulama.ico
; Lisans sayfası: Türkçe özet + GPLv3 tam metni
LicenseFile=..\build\kurulum_lisans.txt
UninstallDisplayIcon={app}\{#ExeAdi}
UninstallDisplayName={#UygulamaAdi}
OutputDir=..\Output
OutputBaseFilename=RizeOn-Kurulum
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Uygulama çalışıyorsa kurulum/kaldırma önce kapatmasını ister (core/tek_kopya.py ile aynı ad;
; ikincisi uygulamanın eski adı "Yayın Uygulaması" zamanındaki sürümler için)
AppMutex=Local\RizeOn_TekKopya,Local\YayinUygulamasi_TekKopya
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol ekle"; GroupDescription: "Kısayollar:"

; Eski ad (Yayın Uygulaması, 1.5.x ve öncesi) ile kurulmuş dosyalar: aynı AppId olduğu için bu kurulum
; eskisinin üstüne gelir; eski exe ve kısayollar kalırsa iki uygulama varmış gibi görünür.
[InstallDelete]
Type: files; Name: "{app}\YayinUygulamasi.exe"
Type: files; Name: "{autoprograms}\Yayın Uygulaması.lnk"
Type: files; Name: "{autodesktop}\Yayın Uygulaması.lnk"

[Files]
Source: "..\dist\RizeOn\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Comment: "Ekran, kamera ve ses paylaşımı (sanal kamera + sanal mikrofon)"
Name: "{autodesktop}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Tasks: masaustu

[Run]
Filename: "{app}\{#ExeAdi}"; Description: "{#UygulamaAdi}'u şimdi aç"; Flags: nowait postinstall skipifsilent
