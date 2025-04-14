PANDUAN KONFIGURASI FIREBIRD QUERY CLIENT
=======================================

File konfigurasi client_config.json berisi pengaturan koneksi untuk aplikasi ini.
Anda dapat mengubah file ini dengan editor teks apa pun (seperti Notepad).

FORMAT KONFIGURASI:
------------------

{
  "server_address": "localhost",  // Alamat server (localhost atau alamat IP)
  "server_port": 5555,            // Port server
  "auto_reconnect": true,         // Otomatis sambung kembali jika terputus
  "reconnect_interval": 5,        // Interval percobaan sambung ulang (detik)
  "client_id": "client_1A",       // ID client unik
  "display_name": "PG1A",         // Nama tampilan di server
  "database": {
    "path": "D:/Path/Ke/Database.FDB", // Jalur file database FDB
    "username": "SYSDBA",          // Username database (biasanya SYSDBA)
    "password": "masterkey"        // Password database
  },
  "isql_path": "C:/Program Files/Firebird/Firebird_3_0/bin/isql.exe"  // Lokasi isql.exe
}

CARA MENGUBAH KONFIGURASI:
------------------------

1. Buka file client_config.json dengan editor teks (Klik kanan > Edit with Notepad)
2. Ubah nilai parameter sesuai kebutuhan
3. Simpan file (Ctrl+S)
4. Restart aplikasi jika sedang berjalan

PARAMETER PENTING:
----------------

1. server_address:
   - Jika server berada di komputer yang sama: "localhost" atau "127.0.0.1"
   - Jika server berada di komputer lain: Masukkan alamat IP server

2. database/path:
   - Path lengkap ke file database Firebird (FDB)
   - Gunakan format path Windows dengan tanda \ atau /
   - Contoh: "C:\\Database\\MYDB.FDB" atau "C:/Database/MYDB.FDB"

3. database/username dan database/password:
   - Biasanya "SYSDBA" dan "masterkey" untuk instalasi default Firebird
   - Gunakan kredensial yang diberikan administrator database Anda

4. isql_path:
   - Path lengkap ke isql.exe (Interactive SQL Firebird)
   - Biasanya terletak di folder bin instalasi Firebird
   - Contoh: "C:/Program Files/Firebird/Firebird_3_0/bin/isql.exe"
   - Digunakan untuk eksekusi query langsung dan operasi database lainnya

CATATAN:
-------
- Pastikan aplikasi tidak sedang berjalan saat mengubah konfigurasi
- Backup file konfigurasi sebelum melakukan perubahan besar
- Jika terjadi error, coba kembalikan ke pengaturan asli