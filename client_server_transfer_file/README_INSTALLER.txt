CARA MEMBUAT INSTALLER PROFESIONAL UNTUK FIREBIRD QUERY CLIENT
==========================================================

Firebird Query Client dapat diinstal seperti aplikasi Windows profesional
dengan kemampuan:
- Diinstal di folder Program Files
- Muncul di Windows Search
- Memiliki shortcut di Start Menu dan Desktop
- Dapat diuninstall dari Control Panel Windows

LANGKAH-LANGKAH PEMBUATAN INSTALLER:
-----------------------------------

1. PRASYARAT:
   - Instal NSIS (Nullsoft Scriptable Install System)
     Download dari: https://nsis.sourceforge.io/Download
   - Pastikan sudah mengkompilasi aplikasi dengan PyInstaller

2. CARA MEMBUAT INSTALLER:
   a. Jalankan build_client.bat untuk mengkompilasi aplikasi
   b. Jalankan install-nsis.bat untuk membuat installer

3. HASIL:
   - File installer: FirebirdQueryClient_Setup.exe
   - Ukuran installer sekitar 10-12 MB
   - Installer ini siap didistribusikan ke pengguna

4. CARA PENGGUNA MENGINSTAL:
   a. Jalankan FirebirdQueryClient_Setup.exe
   b. Ikuti wizard instalasi
   c. Aplikasi akan terinstal di Program Files
   d. Shortcut dibuat di Start Menu dan Desktop
   e. Dapat dijalankan dari Start Menu atau Windows Search

5. CARA PENGGUNA MENGUBAH KONFIGURASI:
   a. Buka Explorer dan arahkan ke:
      C:\Program Files\IFESS\Firebird Query Client\
   b. Edit file client_config.json dengan Notepad atau editor teks lainnya
   c. Simpan perubahan (mungkin perlu hak admin)
   d. Restart aplikasi

6. CARA PENGGUNA UNINSTALL:
   a. Buka Control Panel > Programs > Uninstall a program
   b. Cari "Firebird Query Client"
   c. Klik Uninstall dan ikuti petunjuk

CATATAN TAMBAHAN:
---------------
- Jika pengguna tidak memiliki hak admin, mereka mungkin tidak dapat
  mengubah file konfigurasi di Program Files. Dalam hal ini, Anda mungkin
  perlu menyesuaikan lokasi file konfigurasi ke folder yang dapat ditulis
  (seperti AppData).
- Jika terjadi masalah dengan antivirus yang mendeteksi false positive,
  pengguna dapat menambahkan pengecualian untuk folder instalasi. 