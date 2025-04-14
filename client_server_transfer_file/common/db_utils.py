import os
import sys
import platform
import json
from datetime import datetime

class FirebirdConnector:
    """
    Kelas untuk menangani koneksi ke database Firebird.
    Untuk client, hanya digunakan untuk file transfer tanpa koneksi database asli.
    """
    
    def __init__(self, db_path=None, username="SYSDBA", password="masterkey"):
        """
        Inisialisasi objek FirebirdConnector
        
        Parameters:
            db_path (str): Path ke file database .fdb
            username (str): Username database (default: SYSDBA)
            password (str): Password database (default: masterkey)
        """
        self.db_path = db_path
        self.username = username
        self.password = password
        self.db_info = {}
        
        # Periksa apakah file database ada
        if db_path and os.path.exists(db_path):
            self.update_db_info()
    
    def update_db_info(self):
        """Update info dasar tentang file database"""
        if not self.db_path:
            return
            
        try:
            # Dapatkan info file
            filename = os.path.basename(self.db_path)
            file_size = os.path.getsize(self.db_path)
            file_mod_time = os.path.getmtime(self.db_path)
            
            self.db_info = {
                "filename": filename,
                "file_size": file_size,
                "last_modified": datetime.fromtimestamp(file_mod_time).isoformat(),
                "path": self.db_path
            }
        except Exception as e:
            print(f"Error updating DB info: {e}")
            self.db_info = {}
    
    def test_connection(self):
        """
        Dummy method untuk kompatibilitas.
        Client tidak perlu melakukan koneksi database sebenarnya.
        """
        # Hanya periksa keberadaan file
        if not self.db_path:
            return False
        return os.path.exists(self.db_path)
    
    def get_tables(self):
        """
        Dummy method untuk kompatibilitas.
        Client tidak perlu mendapatkan daftar tabel.
        """
            return []
        
    def execute_query(self, query):
        """
        Dummy method untuk kompatibilitas.
        Client tidak menjalankan query.
        
        Raises:
            ValueError: Selalu diangkat karena client tidak boleh menjalankan query
        """
        raise ValueError("Query execution is not available on client side")
    
    def get_database_file_info(self):
        """
        Dapatkan informasi file database
        
        Returns:
            dict: Info file database
        """
        if not self.db_path:
            return {
                "exists": False,
                "path": None,
                "filename": None,
                "size": 0,
                "error": "Database path not set"
            }
        
        try:
            exists = os.path.exists(self.db_path)
            filename = os.path.basename(self.db_path)
            
            if exists:
                size = os.path.getsize(self.db_path)
                modified = os.path.getmtime(self.db_path)
                modified_str = datetime.fromtimestamp(modified).isoformat()
            else:
                size = 0
                modified_str = None
            
            return {
                "exists": exists,
                "path": self.db_path,
                "filename": filename,
                "size": size,
                "modified": modified_str
            }
        except Exception as e:
            return {
                "exists": False,
                "path": self.db_path,
                "filename": os.path.basename(self.db_path) if self.db_path else None,
                "size": 0,
                "error": str(e)
            }
    
    def read_database_chunk(self, offset, chunk_size):
        """
        Baca chunk dari file database untuk transfer
        
        Parameters:
            offset (int): Offset byte untuk mulai membaca
            chunk_size (int): Ukuran chunk dalam byte
        
        Returns:
            tuple: (data, is_last) di mana data adalah chunk binary dan is_last adalah boolean
        """
        if not self.db_path or not os.path.exists(self.db_path):
            return None, False
        
        try:
            with open(self.db_path, 'rb') as f:
                f.seek(offset)
                data = f.read(chunk_size)
                
                # Periksa apakah ini chunk terakhir
                current_pos = f.tell()
                file_size = os.path.getsize(self.db_path)
                is_last = current_pos >= file_size
                
                return data, is_last
        except Exception as e:
            print(f"Error reading database chunk: {e}")
            return None, False

    def get_example_query(self, table_name=None):
        """Mendapatkan contoh query untuk testing"""
        if not table_name:
            # Coba dapatkan tabel pertama dari database
            tables = self.get_tables()
            if tables:
                table_name = tables[0]
            else:
                # Default table jika tidak ada tabel
                table_name = "FFBLOADINGCROP02"
        
        # Buat query SELECT * FROM table LIMIT 100
        query = f"SELECT * FROM {table_name}"
        
        print(f"Generated example query: {query}")
        return query 