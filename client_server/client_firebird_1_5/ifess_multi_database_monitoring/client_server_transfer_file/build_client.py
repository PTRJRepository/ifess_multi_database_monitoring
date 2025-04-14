import os
import shutil
import sys
import subprocess
import json

def build_client():
    print("Memulai kompilasi Client Firebird Query...")
    
    # Salin client_config.json ke lokasi distribusi
    print("Menyalin file konfigurasi...")
    if os.path.exists("client/client_config.json"):
        # Salin ke folder root untuk distribusi
        try:
            # Baca file konfigurasi asli
            with open("client/client_config.json", 'r') as f:
                config = json.load(f)
            
            # Tambahkan isql_path jika belum ada
            if "isql_path" not in config:
                config["isql_path"] = "C:/Program Files/Firebird/Firebird_3_0/bin/isql.exe"
                print("Menambahkan default isql_path ke konfigurasi")
            
            # Tulis kembali file konfigurasi dengan parameter baru
            with open("client_config.json", 'w') as f:
                json.dump(config, f, indent=2)
                
            print("File konfigurasi disalin ke folder root dengan parameter isql_path")
        except Exception as e:
            print(f"ERROR: Gagal menyalin file konfigurasi ke folder root: {e}")
            return False
    else:
        print("ERROR: File client_config.json tidak ditemukan di folder client!")
        print("Lokasi yang dicari: " + os.path.abspath("client/client_config.json"))
        return False
    
    # Jalankan PyInstaller dengan opsi yang mengurangi kemungkinan false positive
    print("Menjalankan PyInstaller...")
    pyinstaller_command = [
        "python",
        "-m",
        "PyInstaller",
        "--name=FirebirdQueryClient",
        "--onefile",
        "--windowed",
        "--icon=NONE",
        # Tidak menyertakan client_config.json ke dalam executable
        # karena akan disediakan sebagai file terpisah
        "--add-data=common;common",
        # Opsi tambahan untuk mengurangi false positive
        "--noupx",  # Menonaktifkan kompresi UPX yang sering memicu antivirus
        "--clean",  # Membersihkan cache PyInstaller sebelum build
        "client/client.py"
    ]
    
    # Jalankan tanpa capture output agar terlihat secara real-time
    result = subprocess.run(pyinstaller_command)
    
    if result.returncode == 0:
        print("Kompilasi berhasil!")
        print(f"Executable dibuat di: {os.path.abspath('dist/FirebirdQueryClient.exe')}")
        
        # Salin client_config.json ke folder dist
        print("Menyalin file konfigurasi ke folder distribusi...")
        try:
            # Pastikan folder dist ada
            os.makedirs("dist", exist_ok=True)
            
            # Salin file konfigurasi
            shutil.copy("client_config.json", "dist/")
            
            # Verifikasi file telah disalin dengan benar
            if os.path.exists("dist/client_config.json"):
                print(f"File konfigurasi berhasil disalin ke: {os.path.abspath('dist/client_config.json')}")
            else:
                print("ERROR: File konfigurasi tidak ditemukan di folder dist setelah penyalinan")
                return False
        except Exception as e:
            print(f"ERROR: Gagal menyalin file konfigurasi ke folder dist: {e}")
            return False

        # Buat README_KONFIGURASI.txt
        with open("README_KONFIGURASI.txt", "w") as f:
            f.write("""PANDUAN KONFIGURASI FIREBIRD QUERY CLIENT
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
   - Gunakan format path Windows dengan tanda \\ atau /
   - Contoh: "C:\\\\Database\\\\MYDB.FDB" atau "C:/Database/MYDB.FDB"

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
- Jika terjadi error, coba kembalikan ke pengaturan asli""")
        
        # Salin README_KONFIGURASI.txt ke folder dist
        try:
            shutil.copy("README_KONFIGURASI.txt", "dist/")
        except Exception as e:
            print(f"WARNING: Gagal menyalin README_KONFIGURASI.txt: {e}")
        
        # Tambahkan readme tentang false positive ke folder dist
        with open("dist/README_ANTIVIRUS.txt", "w") as f:
            f.write("""CATATAN TENTANG PERINGATAN ANTIVIRUS
=================================

File executable yang dihasilkan dari PyInstaller mungkin dianggap sebagai ancaman
oleh beberapa antivirus. Ini adalah FALSE POSITIVE dan umum terjadi karena cara 
PyInstaller mengemas aplikasi.

Jika Anda mendapatkan peringatan, Anda dapat:
1. Mengizinkan aplikasi berjalan ("Allow")
2. Menambahkan file ke pengecualian antivirus Anda
3. Menambahkan folder instalasi ke pengecualian antivirus

Aplikasi ini TIDAK mengandung malware atau virus.
""")
        
        # Periksa sekali lagi apakah semua file yang dibutuhkan telah disiapkan
        required_files = ["FirebirdQueryClient.exe", "client_config.json", "README_KONFIGURASI.txt", "README_ANTIVIRUS.txt"]
        missing_files = []
        
        for file in required_files:
            if not os.path.exists(os.path.join("dist", file)):
                missing_files.append(file)
        
        if missing_files:
            print("\nPERINGATAN: Beberapa file tidak ditemukan di folder dist:")
            for file in missing_files:
                print(f"- {file}")
            print("\nHarap periksa folder dist dan tambahkan file yang hilang sebelum membuat installer.")
        else:
            print("\nSemua file telah disiapkan dengan baik di folder dist.")
            
        print("\nUntuk membuat installer profesional:")
        print("1. Instal NSIS dari https://nsis.sourceforge.io/Download")
        print("2. Jalankan 'install-nsis.bat' untuk membuat installer")
        print("3. Distribusikan 'FirebirdQueryClient_Setup.exe' ke pengguna")
        
        return True
    else:
        print("Kompilasi gagal!")
        return False

if __name__ == "__main__":
    success = build_client()
    if not success:
        print("\nTerjadi kesalahan selama proses build. Harap periksa pesan error di atas.")
        sys.exit(1) 