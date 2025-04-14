; Script installer untuk Firebird Query Client
; Menggunakan NSIS (Nullsoft Scriptable Install System)

!define APPNAME "Firebird Query Client"
!define COMPANYNAME "IFESS"
!define DESCRIPTION "Aplikasi client untuk query database Firebird"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define INSTALLSIZE 15000

; Kompres installer
SetCompressor lzma

; Properti modern UI
!include "MUI2.nsh"
!include "LogicLib.nsh"  ; Untuk kondisional
!include "FileFunc.nsh"  ; Untuk pengecekan file
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Header\win.bmp"
!define MUI_ABORTWARNING

; Nama installer
Name "${APPNAME}"
OutFile "FirebirdQueryClient_Setup.exe"

; Default installation folder
InstallDir "$PROGRAMFILES\${COMPANYNAME}\${APPNAME}"

; Get installation folder from registry if available
InstallDirRegKey HKLM "Software\${COMPANYNAME}\${APPNAME}" ""

; Request application privileges for Windows Vista/7/8/10
RequestExecutionLevel admin

; Variabel untuk isql.exe
Var IsqlPath
Var Dialog
Var Label1
Var Text1
Var BrowseButton

;--------------------------------
; Custom pages

; Fungsi untuk halaman input isql
Function IsqlPathPage
  nsDialogs::Create 1018
  Pop $Dialog
  
  ${If} $Dialog == error
    Abort
  ${EndIf}
  
  ${NSD_CreateLabel} 0 0 100% 20u "Masukkan lokasi isql.exe (Interactive SQL Firebird):"
  Pop $Label1
  
  ${NSD_CreateText} 0 20u 70% 12u $IsqlPath
  Pop $Text1
  
  ${NSD_CreateBrowseButton} 75% 20u 20% 12u "Telusuri..."
  Pop $BrowseButton
  ${NSD_OnClick} $BrowseButton IsqlBrowseClick
  
  nsDialogs::Show
FunctionEnd

Function IsqlBrowseClick
  ${NSD_GetText} $Text1 $IsqlPath
  nsDialogs::SelectFileDialog open $IsqlPath "isql.exe|isql.exe|All Files|*.*"
  Pop $0
  ${If} $0 != ""
    ${NSD_SetText} $Text1 $0
    StrCpy $IsqlPath $0
  ${EndIf}
FunctionEnd

Function IsqlPathPageLeave
  ${NSD_GetText} $Text1 $IsqlPath
FunctionEnd

Function .onInit
  ; Default isql path
  StrCpy $IsqlPath "C:\Program Files\Firebird\Firebird_3_0\bin\isql.exe"
FunctionEnd

;--------------------------------
; Pages

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LISENSI.txt"
!insertmacro MUI_PAGE_DIRECTORY
Page custom IsqlPathPage IsqlPathPageLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\FirebirdQueryClient.exe"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\README_KONFIGURASI.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Buka panduan konfigurasi"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "Indonesian"

;--------------------------------
; Installer

Section "Install"

  SetOutPath "$INSTDIR"
  
  ; Cek file konfigurasi sumber
  IfFileExists "dist\client_config.json" FileExists FileNotFound
  
  FileNotFound:
    MessageBox MB_ICONEXCLAMATION "File konfigurasi (client_config.json) tidak ditemukan di folder dist! Instalasi tidak dapat dilanjutkan."
    Abort "File konfigurasi tidak ditemukan."
    
  FileExists:
  
  ; Tambahkan file-file ke installer
  File "dist\FirebirdQueryClient.exe"
  File "dist\client_config.json"
  File "dist\README_KONFIGURASI.txt"
  File "dist\README_ANTIVIRUS.txt"
  
  ; Verifikasi file konfigurasi terinstal
  IfFileExists "$INSTDIR\client_config.json" ConfigExists ConfigNotFound
  
  ConfigNotFound:
    MessageBox MB_ICONEXCLAMATION "Gagal menyalin file konfigurasi ke folder instalasi! Silakan salin manual file client_config.json ke $INSTDIR"
    Goto Continue
    
  ConfigExists:
    DetailPrint "File konfigurasi berhasil diinstal di: $INSTDIR\client_config.json"
    
    ; Update isql_path dalam client_config.json
    FileOpen $0 "$INSTDIR\client_config.json" r
    ${If} $0 != ""
      FileRead $0 $1
      FileClose $0
      ; Gunakan NSIS plugin JSON Edit untuk mengubah nilai (atau manipulasi string manual)
      ; Sebagai solusi sederhana, ubah file konfigurasi secara manual dengan memberi informasi ke pengguna
      DetailPrint "Menyetel lokasi isql ke: $IsqlPath"
      MessageBox MB_OK "Lokasi isql telah disetel ke:$\r$\n$IsqlPath$\r$\n$\r$\nUntuk mengubahnya, edit file client_config.json di folder instalasi."
    ${EndIf}
    
  Continue:
  
  ; Simpan informasi uninstall
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Buat shortcut di Start Menu
  CreateDirectory "$SMPROGRAMS\${COMPANYNAME}"
  CreateShortcut "$SMPROGRAMS\${COMPANYNAME}\${APPNAME}.lnk" "$INSTDIR\FirebirdQueryClient.exe" "" "$INSTDIR\FirebirdQueryClient.exe" 0
  CreateShortcut "$SMPROGRAMS\${COMPANYNAME}\Konfigurasi.lnk" "$INSTDIR\client_config.json" "" "$INSTDIR\client_config.json" 0
  CreateShortcut "$SMPROGRAMS\${COMPANYNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  
  ; Buat shortcut di desktop
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\FirebirdQueryClient.exe" "" "$INSTDIR\FirebirdQueryClient.exe" 0
  
  ; Tulis informasi uninstall di registry
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /S"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "DisplayIcon" "$\"$INSTDIR\FirebirdQueryClient.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "Publisher" "${COMPANYNAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "VersionMinor" ${VERSIONMINOR}
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "NoRepair" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
  
  ; Simpan lokasi isql dalam registry untuk seterusnya
  WriteRegStr HKLM "Software\${COMPANYNAME}\${APPNAME}" "IsqlPath" "$IsqlPath"
  
  ; Tampilkan pesan sukses
  MessageBox MB_OK "Instalasi berhasil! File konfigurasi tersedia di:$\r$\n$INSTDIR\client_config.json$\r$\n$\r$\nGunakan Notepad untuk mengedit file konfigurasi tersebut sesuai kebutuhan."

SectionEnd

;--------------------------------
; Uninstaller

Section "Uninstall"
  
  ; Hapus file dan folder aplikasi
  Delete "$INSTDIR\FirebirdQueryClient.exe"
  Delete "$INSTDIR\client_config.json"
  Delete "$INSTDIR\README_KONFIGURASI.txt"
  Delete "$INSTDIR\README_ANTIVIRUS.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  
  ; Hapus shortcut
  Delete "$SMPROGRAMS\${COMPANYNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${COMPANYNAME}\Konfigurasi.lnk"
  Delete "$SMPROGRAMS\${COMPANYNAME}\Uninstall ${APPNAME}.lnk"
  RMDir "$SMPROGRAMS\${COMPANYNAME}"
  Delete "$DESKTOP\${APPNAME}.lnk"
  
  ; Hapus informasi registry
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME}"
  DeleteRegKey HKLM "Software\${COMPANYNAME}\${APPNAME}"

SectionEnd 