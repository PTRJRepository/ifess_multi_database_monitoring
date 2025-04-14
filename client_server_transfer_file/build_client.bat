@echo off
echo ================================================================
echo    Kompilasi Aplikasi Client Firebird Query
echo ================================================================
echo.

python build_client.py
echo.

if exist "dist" (
    echo Package executable berhasil dibuat di folder 'dist'
    echo.
    echo File yang siap digunakan:
    echo - FirebirdQueryClient.exe (Aplikasi utama)
    echo - client_config.json (File konfigurasi yang dapat diubah)
    echo - README_KONFIGURASI.txt (Panduan konfigurasi)
    echo.
    echo Anda memiliki dua opsi distribusi:
    echo.
    echo 1. DISTRIBUSI MANUAL:
    echo    Distribusikan folder 'dist' langsung ke pengguna
    echo.
    echo 2. INSTALLER PROFESIONAL [DIREKOMENDASIKAN]:
    echo    Untuk membuat installer yang dapat diinstal di Program Files,
    echo    muncul di Start Menu, dan dapat di-uninstall dari Control Panel:
    echo    a. Instal NSIS dari: https://nsis.sourceforge.io/Download
    echo    b. Jalankan install-nsis.bat
    echo    c. Distribusikan FirebirdQueryClient_Setup.exe yang dihasilkan
    echo.
)
pause 