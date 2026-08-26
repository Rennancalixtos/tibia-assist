; installer.nsi - instalador do EasyF (NSIS)
;
; Empacota a pasta onedir ja gerada pelo build.bat/PyInstaller (EasyF.exe +
; _internal\) - nao compila nada Python aqui. Cria atalho na Area de
; Trabalho e no Menu Iniciar, registra um desinstalador (Painel de
; Controle > Programas).
;
; Compilar localmente (depois de rodar build.bat):
;   makensis /DAPP_DIR="dist\EasyF" /DEXE_NAME="EasyF.exe" installer.nsi
;
; O nome real do .exe vem do EasyF.spec - o workflow de release
; (.github/workflows/release.yml) descobre isso automaticamente e passa pro
; makensis, sem precisar hardcodar aqui. Os defines abaixo so servem de
; fallback pra compilar manualmente sem passar /D.

!ifndef APP_DIR
  !define APP_DIR "dist\EasyF"
!endif
!ifndef EXE_NAME
  !define EXE_NAME "EasyF.exe"
!endif

!include "MUI2.nsh"

Name "EasyF"
OutFile "dist\EasyF-Setup.exe"
InstallDir "$LOCALAPPDATA\EasyF"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "PortugueseBR"

Section "Instalar"
  SetOutPath "$INSTDIR"
  File /r "${APP_DIR}\*.*"

  CreateShortCut "$DESKTOP\EasyF.lnk" "$INSTDIR\${EXE_NAME}"

  CreateDirectory "$SMPROGRAMS\EasyF"
  CreateShortCut "$SMPROGRAMS\EasyF\EasyF.lnk" "$INSTDIR\${EXE_NAME}"
  CreateShortCut "$SMPROGRAMS\EasyF\Desinstalar.lnk" "$INSTDIR\Uninstall.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF" "DisplayName" "EasyF"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF" "NoRepair" 1
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"

  Delete "$DESKTOP\EasyF.lnk"
  Delete "$SMPROGRAMS\EasyF\EasyF.lnk"
  Delete "$SMPROGRAMS\EasyF\Desinstalar.lnk"
  RMDir "$SMPROGRAMS\EasyF"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\EasyF"
  ; Nao remove %APPDATA%\EasyF (config/licenca do usuario) de proposito -
  ; uma reinstalacao nao deve perder a sessao/calibracao de ninguem.
SectionEnd
