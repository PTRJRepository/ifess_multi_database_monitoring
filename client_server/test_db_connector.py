import os
import sys
import unittest
from pprint import pprint

# Tambahkan path ke direktori parent
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from common.db_utils import FirebirdConnector

class TestFirebirdConnector(unittest.TestCase):
    """Test kelas FirebirdConnector"""
    
    def setUp(self):
        """Set up test case - inisialisasi koneksi database"""
        # Database path yang akan diuji
        self.db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
        
        # Buat instance FirebirdConnector
        try:
            self.connector = FirebirdConnector(db_path=self.db_path, username='SYSDBA', password='masterkey')
            print(f"Connected to database: {self.db_path}")
        except Exception as e:
            self.fail(f"Setup failed: {e}")
    
    def test_connection(self):
        """Test koneksi ke database"""
        result = self.connector.test_connection()
        self.assertTrue(result, "Koneksi database gagal")
        print("Connection test passed!")
    
    def test_get_tables(self):
        """Test fungsi get_tables"""
        tables = self.connector.get_tables()
        self.assertIsInstance(tables, list, "get_tables harus mengembalikan list")
        print(f"Detected tables: {', '.join(tables[:10])}...")
        
        # Periksa tabel FFBLOADINGCROP02 ada dalam daftar
        self.assertIn("FFBLOADINGCROP02", tables, "FFBLOADINGCROP02 tidak ditemukan dalam daftar tabel")
    
    def test_ffbloadingcrop02_query(self):
        """Test query spesifik pada tabel FFBLOADINGCROP02"""
        query = """
        SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT, 
               a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME, a.UPLOADDATETIME, 
               a.LASTUSER, a.LASTUPDATED, a.RECORDTAG, a.DRIVERNAME, a.DRIVERID, a.HARVESTINGDATE, a.PROCESSFLAG
        FROM FFBLOADINGCROP02 a WHERE ID <= 10
        """
        
        # Jalankan query
        print(f"Executing query: {query}")
        result = self.connector.execute_query(query)
        
        self.assertIsInstance(result, list, "Result harus berupa list")
        self.assertGreaterEqual(len(result), 1, "Result set tidak boleh kosong")
        
        # Dapatkan result set pertama
        result_set = result[0]
        self.assertIn("headers", result_set, "Result set harus memiliki headers")
        self.assertIn("rows", result_set, "Result set harus memiliki rows")
        
        rows = result_set["rows"]
        print(f"Found {len(rows)} rows")
        
        # Periksa jumlah baris yang diharapkan
        self.assertEqual(len(rows), 10, "Query harus mengembalikan 10 baris data")
        
        # Periksa ID pada baris pertama = 1
        self.assertEqual(rows[0]["ID"], "1", "ID baris pertama harus 1")
        
        # Periksa data sampel lainnya
        expected_id10_transno = "10414634"
        actual_id10 = next((row for row in rows if row["ID"] == "10"), None)
        self.assertIsNotNone(actual_id10, "Row dengan ID 10 tidak ditemukan")
        self.assertEqual(actual_id10["TRANSNO"], expected_id10_transno, 
                         f"TRANSNO untuk ID 10 seharusnya {expected_id10_transno}")
        
        # Tampilkan struktur data untuk debugging
        print("\nData structure of first result row:")
        pprint(rows[0])
        
        # Verifkasi beberapa nilai pada data yang diharapkan
        expected_values = [
            {"ID": "1", "SCANUSERID": "188", "BUNCHES": "7", "TRANSNO": "10414593"},
            {"ID": "2", "SCANUSERID": "188", "BUNCHES": "4", "TRANSNO": "10414591"},
            {"ID": "7", "SCANUSERID": "188", "BUNCHES": "6", "TRANSNO": "10414600"},
            {"ID": "10", "SCANUSERID": "188", "BUNCHES": "11", "TRANSNO": "10414634"}
        ]
        
        for expected in expected_values:
            expected_id = expected["ID"]
            actual = next((row for row in rows if row["ID"] == expected_id), None)
            self.assertIsNotNone(actual, f"Row dengan ID {expected_id} tidak ditemukan")
            
            for key, value in expected.items():
                self.assertEqual(actual[key], value, 
                                f"Nilai {key} untuk ID {expected_id} seharusnya {value}, tetapi mendapat {actual[key]}")
        
        print("All data validations passed!")

def run_direct_test():
    """Run test secara langsung tanpa unittest framework"""
    db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
    
    try:
        print(f"Creating FirebirdConnector with database: {db_path}")
        connector = FirebirdConnector(db_path=db_path, username='SYSDBA', password='masterkey')
        
        print("Testing connection...")
        if connector.test_connection():
            print("Connection successful!")
        else:
            print("Connection failed!")
            return
        
        # Run the query
        query = """
        SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT, 
               a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME, a.UPLOADDATETIME, 
               a.LASTUSER, a.LASTUPDATED, a.RECORDTAG, a.DRIVERNAME, a.DRIVERID, a.HARVESTINGDATE, a.PROCESSFLAG
        FROM FFBLOADINGCROP02 a WHERE ID <= 10
        """
        
        print(f"Executing query: {query}")
        result = connector.execute_query(query)
        
        if not result or not result[0].get("rows"):
            print("No results found!")
            return
        
        rows = result[0]["rows"]
        print(f"Query returned {len(rows)} rows")
        
        # Display results in a formatted table
        headers = result[0]["headers"]
        
        # Determine column widths
        col_widths = {}
        for header in headers:
            col_widths[header] = max(len(header), max(len(str(row[header])) for row in rows))
        
        # Print headers
        header_line = ""
        for header in headers:
            header_line += f"{header:{col_widths[header]}} "
        print("\nQuery Results:")
        print("-" * len(header_line))
        print(header_line)
        print("-" * len(header_line))
        
        # Print rows
        for row in rows:
            row_line = ""
            for header in headers:
                row_line += f"{row[header]:{col_widths[header]}} "
            print(row_line)
        
        print("-" * len(header_line))
        print(f"Total: {len(rows)} rows")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run either unittest or direct test
    use_unittest = False
    
    if use_unittest:
        unittest.main()
    else:
        run_direct_test() 