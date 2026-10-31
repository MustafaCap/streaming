; Yayın Uygulaması — Windows kurulum programı (Inno Setup 6)
;
; CI'da derlenir:  ISCC.exe /DSurum=1.3.0 kurulum\kurulum.iss
; Girdi : dist\YayinUygulamasi\  (PyInstaller çıktısı + ffmpeg + BENIOKU.md)
; Çıktı : Output\YayinUygulamasi-Kurulum.exe
;
; Ne yapar:
;  - Kurulum yerini sorar (varsayılan: Program Files\YayinUygulamasi)
;  - "Sadece benim için" seçilirse yönetici izni istemez (AppData\Local\Programs'a kurar)
;  - Başlat menüsüne ekler (Windows aramasında adıyla çıkar), isteğe bağlı masaüstü kısayolu
;  - Uygulama açıksa önce kapatılmasını ister (tek kopya mutex'i ile anlar)
;  - Denetim Masası / Ayarlar > Uygulamalar'dan kaldırılabilir
;  - Ayarlar ve kayıtlar (%APPDATA%, Videolar) kaldırırken silinmez

#ifndef Surum
  #define Surum "0.0.0"
#endif

#define UygulamaAdi "Yayın Uygulaması"
#define ExeAdi "YayinUygulamasi.exe"

[Setup]
; AppId sabit kalmalı: yeni sürüm eskisinin üstüne kurulsun, ikinci kopya olmasın
AppId={{7E3B2A91-5C4D-4F8E-9A16-2D8B0C5E4F71}
AppName={#UygulamaAdi}
AppVersion={#Surum}
AppVerName={#UygulamaAdi} {#Surum}
AppPublisher=Mustafa
AppPublisherURL=https://github.com/MustafaCap/streaming
; Klasör adı ASCII: bazı kütüphaneler Türkçe karakterli yolları sevmiyor
DefaultDirName={autopf}\YayinUygulamasi
DefaultGroupName={#UygulamaAdi}
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
SetupIconFile=uygulama.ico
UninstallDisplayIcon={app}\{#ExeAdi}
UninstallDisplayName={#UygulamaAdi}
OutputDir=..\Output
OutputBaseFilename=YayinUygulamasi-Kurulum
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Uygulama çalışıyorsa kurulum/kaldırma önce kapatmasını ister (core/tek_kopya.py ile aynı ad)
AppMutex=Local\YayinUygulamasi_TekKopya
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol ekle"; GroupDescription: "Kısayollar:"

[Files]
Source: "..\dist\YayinUygulamasi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Comment: "Ekran, kamera ve ses paylaşımı (sanal kamera + sanal mikrofon)"
Name: "{autodesktop}\{#UygulamaAdi}"; Filename: "{app}\{#ExeAdi}"; Tasks: masaustu

[Run]
Filename: "{app}\{#ExeAdi}"; Description: "{#UygulamaAdi}'nı şimdi aç"; Flags: nowait postinstall skipifsilent
