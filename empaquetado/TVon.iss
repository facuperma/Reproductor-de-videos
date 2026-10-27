; Instalador de TVon (Inno Setup 6). Se compila con empaquetado\construir.py,
; que pasa /DVersion y /DOrigen (la carpeta generada por PyInstaller).

#ifndef Version
  #define Version "1.0.0"
#endif
#ifndef Origen
  #define Origen "..\compilado\dist\TVon"
#endif

[Setup]
AppId={{6B0F4C1E-7A2D-4E8B-9C35-5D1A7E2F9B40}
AppName=TVon
AppVersion={#Version}
AppVerName=TVon {#Version}
AppPublisher=facuperma
AppPublisherURL=https://github.com/facuperma/Reproductor-de-videos
DefaultDirName={autopf}\TVon
DefaultGroupName=TVon
DisableProgramGroupPage=yes
; Sin permisos de administrador: se instala para el usuario actual
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=TVon-Setup-{#Version}
SetupIconFile=..\organizador\icono.ico
UninstallDisplayIcon={app}\TVon.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TVon"; Filename: "{app}\TVon.exe"
Name: "{group}\Desinstalar TVon"; Filename: "{uninstallexe}"
Name: "{autodesktop}\TVon"; Filename: "{app}\TVon.exe"; Tasks: escritorio

[Run]
Filename: "{app}\TVon.exe"; Description: "Abrir TVon"; Flags: nowait postinstall skipifsilent
