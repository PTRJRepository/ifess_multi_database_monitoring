"""
Script sederhana untuk menghubungkan ke database Firebird dan menjalankan query
"""
import os
import subprocess
import tempfile

def test_firebird_query():
    """Test query langsung ke database Firebird menggunakan ISQL command"""
    # Parameter koneksi
    db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
    isql_path = r"C:\Program Files (x86)\Firebird\bin\isql.exe"
    username = "SYSDBA"
    password = "masterkey"
    
    # Query yang akan dijalankan
    query = """
    SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT,
    a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME
    FROM FFBLOADINGCROP02 a 
    WHERE ID <= 10;
    """
    
    print(f"Database: {db_path}")
    print(f"ISQL path: {isql_path}")
    
    # Buat file temporary untuk query
    fd, query_file = tempfile.mkstemp(suffix='.sql')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(query)
        
        print(f"Query di-cache di file: {query_file}")
        print(f"Query: {query}")
        
        # Jalankan command ISQL
        command = [
            isql_path,
            "-user", username,
            "-password", password,
            db_path,
            "-i", query_file
        ]
        
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True)
        
        # Tampilkan hasil
        print("\nCommand Output:")
        print("=" * 80)
        print(result.stdout)
        
        if result.stderr:
            print("\nErrors:")
            print(result.stderr)
        
        print(f"Return code: {result.returncode}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Hapus file temporary
        if os.path.exists(query_file):
            os.unlink(query_file)

if __name__ == "__main__":
    test_firebird_query() 