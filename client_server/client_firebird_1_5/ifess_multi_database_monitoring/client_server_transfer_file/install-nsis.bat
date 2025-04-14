@echo off
echo ================================================================
echo    Membuat Installer Firebird Query Client dengan NSIS
echo ================================================================
echo.

REM Periksa apakah NSIS sudah terinstal
if not exist "%PROGRAMFILES(X86)%\NSIS\makensis.exe" (
    echo NSIS tidak ditemukan. Silakan instal NSIS terlebih dahulu.
    echo Download NSIS dari: https://nsis.sourceforge.io/Download
    echo.
    pause
    exit /b 1
)

REM Periksa apakah dist sudah ada (hasil build PyInstaller)
if not exist "dist\FirebirdQueryClient.exe" (
    echo ERROR: File FirebirdQueryClient.exe tidak ditemukan.
    echo Silakan jalankan build_client.bat terlebih dahulu.
    echo.
    pause
    exit /b 1
)

REM Periksa apakah file konfigurasi ada
if not exist "dist\client_config.json" (
    echo ERROR: File konfigurasi client_config.json tidak ditemukan!
    echo File ini harus ada di folder dist untuk membuat installer yang berfungsi.
    echo.
    echo Pastikan build_client.py berjalan dengan benar dan menyalin file konfigurasi.
    echo.
    
    set /p answer="Apakah Anda ingin mencoba menyalin file konfigurasi secara manual? (y/n): "
    if /i "%answer%"=="y" (
        if exist "client\client_config.json" (
            echo Menyalin client_config.json dari folder client ke dist...
            copy "client\client_config.json" "dist\" 
            echo Salin berhasil.
        ) else if exist "client_config.json" (
            echo Menyalin client_config.json dari folder root ke dist...
            copy "client_config.json" "dist\"
            echo Salin berhasil.
        ) else (
            echo Tidak dapat menemukan file client_config.json.
            echo Installer tidak dapat dibuat.
            pause
            exit /b 1
        )
    ) else (
        echo Pembuatan installer dibatalkan.
        pause
        exit /b 1
    )
)

REM Verifikasi sekali lagi
if not exist "dist\client_config.json" (
    echo ERROR: File client_config.json masih tidak ditemukan di folder dist.
    echo Installer tidak dapat dibuat.
    pause
    exit /b 1
)

echo File yang akan dipaketkan dalam installer:
echo - dist\FirebirdQueryClient.exe
echo - dist\client_config.json
echo - dist\README_KONFIGURASI.txt
echo - dist\README_ANTIVIRUS.txt
echo.

echo Menjalankan kompiler NSIS...
"%PROGRAMFILES(X86)%\NSIS\makensis.exe" installer.nsi

echo.
if exist "FirebirdQueryClient_Setup.exe" (
    echo ================================================================
    echo Installer berhasil dibuat: FirebirdQueryClient_Setup.exe
    echo ================================================================
    echo.
    echo Installer ini akan menginstal Firebird Query Client dengan:
    echo - Lokasi instalasi di Program Files
    echo - File konfigurasi client_config.json di folder instalasi
    echo - Input lokasi isql.exe (Interactive SQL Firebird)
    echo - Shortcut di Start Menu dan Desktop
    echo - Shortcut khusus untuk file konfigurasi di Start Menu
    echo - Terintegrasi dengan Windows (dapat dicari di Windows Search)
    echo - Dapat di-uninstall dari Control Panel Windows
    echo.
) else (
    echo Terjadi kesalahan saat membuat installer.
    echo Silakan periksa log NSIS untuk detail.
)

pause 