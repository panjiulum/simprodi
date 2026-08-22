; installer.iss — Script Inno Setup.
; Dijalankan otomatis oleh .github/workflows/build-exe.yml (ISCC.exe sudah
; terpasang bawaan di runner "windows-latest" GitHub Actions) SETELAH
; PyInstaller menghasilkan dist/SIMPRODI.exe.
;
; Bisa juga dijalankan manual di Windows (perlu Inno Setup 6 terpasang,
; unduh gratis di https://jrsoftware.org/isinfo.php):
;   1. pyinstaller SIMPRODI.spec
;   2. buka installer.iss di Inno Setup Compiler, klik Compile
;   Hasil: Output/SIMPRODI_Setup.exe

#define MyAppName "SIMPRODI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Program Studi"
#define MyAppExeName "SIMPRODI.exe"

[Setup]
AppId={{B6C1F9A2-6E3D-4C9E-9C1A-3F2E9D8B7A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Data pengguna (database, backup, dokumen) tersimpan di
; ~/SistemSkripsi — sepenuhnya terpisah dari folder instalasi, jadi aman
; di-uninstall/upgrade kapan saja tanpa risiko kehilangan data.
OutputDir=Output
OutputBaseFilename=SIMPRODI_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan {#MyAppName} sekarang"; Flags: nowait postinstall skipifsilent
