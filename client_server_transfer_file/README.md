# Firebird Client-Server Query System

Sistem ini memungkinkan Anda untuk menjalankan query SQL ke beberapa database Firebird (.fdb) secara terpusat. Dengan arsitektur client-server, server dapat mengirim query ke beberapa client yang terhubung, dan setiap client akan menjalankan query pada database lokal mereka.

## Struktur Folder

```
client_server/
├── server/         # Aplikasi Server
│   └── server.py   # Implementasi Server
├── client/         # Aplikasi Client
│   └── client.py   # Implementasi Client
└── common/         # Modul yang digunakan bersama
    ├── db_utils.py # Utilitas untuk koneksi database
    └── network.py  # Utilitas komunikasi jaringan
```

## Fitur

### Server

- Mengelola koneksi dengan beberapa client
- Mengirim query SQL ke client yang dipilih atau semua client
- Menampilkan hasil query dari semua client
- Menyimpan dan memuat query dari file
- Menyimpan riwayat query yang dijalankan
- Antarmuka pengguna yang intuitif dengan tampilan tabel untuk hasil query

### Client

- Terhubung ke server dengan memasukkan alamat IP dan port
- Memilih file database Firebird lokal untuk digunakan
- Menerima dan menjalankan query SQL dari server
- Menampilkan riwayat query yang dijalankan
- Menampilkan hasil query terakhir

## Persyaratan

- Python 3.6+
- Firebird Database (1.5+, 2.x atau 3.0)
- Utilitas ISQL dari Firebird sudah terinstal

## Penggunaan

### Server

1. Jalankan aplikasi server
   ```
   python server/server.py
   ```

2. Klik "Server" -> "Start Server" untuk memulai server

3. Tunggu client terhubung ke server

4. Setelah client terhubung, masukkan query SQL di panel query

5. Pilih target client dari dropdown (atau "All Clients" untuk mengirim ke semua client)

6. Klik "Send Query" untuk mengirim query

7. Hasil query akan ditampilkan di panel hasil, dengan tab terpisah untuk setiap client

### Client

1. Jalankan aplikasi client
   ```
   python client/client.py
   ```

2. Pilih file database Firebird lokal dengan klik "Database" -> "Select Database"

3. Terhubung ke server dengan klik "Connection" -> "Connect to Server" dan masukkan alamat IP dan port server

4. Setelah terhubung, client akan menunggu query dari server

5. Saat menerima query, client akan menjalankannya di database lokal dan mengirim hasilnya kembali ke server

## Contoh Query

Berikut adalah beberapa contoh query SQL yang dapat dijalankan:

```sql
-- Mendapatkan daftar tabel
SELECT RDB$RELATION_NAME FROM RDB$RELATIONS 
WHERE RDB$SYSTEM_FLAG = 0 OR RDB$SYSTEM_FLAG IS NULL

-- Mendapatkan 10 baris pertama dari tabel EMP
SELECT FIRST 10 * FROM EMP

-- Mendapatkan jumlah pekerja dari tabel WORKERINFO
SELECT COUNT(*) AS TOTAL_WORKERS FROM WORKERINFO

-- Join antara dua tabel
SELECT w.EMPID, e.NAME, e.EMPTYPEID, e.DESIGNATIONID, w.JOBSTATUSID 
FROM WORKERINFO w JOIN EMP e ON w.EMPID = e.ID
```

## Keamanan

- Koneksi tidak dienkripsi, sebaiknya gunakan hanya di jaringan lokal
- Autentikasi database menggunakan kredensial default (SYSDBA/masterkey)
- Untuk keamanan database Firebird, disarankan untuk mengubah password default

## Troubleshooting

### Server tidak dapat dimulai
- Pastikan port tidak sedang digunakan oleh aplikasi lain
- Coba gunakan port berbeda (default: 5555)

### Client tidak dapat terhubung ke server
- Pastikan server telah dimulai
- Periksa apakah alamat IP dan port server benar
- Periksa apakah firewall tidak memblokir koneksi

### Query error
- Periksa sintaks SQL
- Pastikan tabel yang direferensikan ada di database
- Periksa apakah user database memiliki izin yang cukup 