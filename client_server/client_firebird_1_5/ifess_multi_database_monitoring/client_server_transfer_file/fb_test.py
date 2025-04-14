"""
Test koneksi ke database Firebird menggunakan format versi lama (localhost:)
"""
import os
import subprocess
import tempfile

def test_firebird_connection():
    """Test koneksi ke database Firebird dengan format localhost:path"""
    # Parameter koneksi
    db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
    isql_path = r"C:\Program Files (x86)\Firebird\bin\isql.exe"
    username = "SYSDBA"
    password = "masterkey"
    
    # Buat connection string dengan format localhost:path
    connection_string = f"localhost:{db_path}"
    
    # Query sederhana
    query = """
    SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT,
    a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME
    FROM FFBLOADINGCROP02 a 
    WHERE ID <= 10;
    """
    
    # Buat file SQL
    sql_file = "test_query.sql"
    with open(sql_file, "w") as f:
        f.write(query)
        f.write("\n")
        f.write("COMMIT;\n")
        f.write("EXIT;\n")
    
    # Output file
    output_file = "test_result.txt"
    
    try:
        print(f"Connection string: {connection_string}")
        print(f"Query:\n{query}")
        
        # Jalankan ISQL dengan format yang sama persis seperti show_workers.bat
        command = [
            isql_path,
            "-user", username,
            "-password", password,
            connection_string,
            "-i", sql_file,
            "-o", output_file
        ]
        
        print(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True)
        
        # Cek hasil eksekusi
        if result.returncode != 0:
            print(f"Error running command: {result.returncode}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")
            if result.stdout:
                print(f"STDOUT: {result.stdout}")
        else:
            print("Command executed successfully!")
        
        # Baca file output
        if os.path.exists(output_file):
            print("\nQuery Results:")
            print("=" * 80)
            with open(output_file, "r") as f:
                content = f.read()
                print(content)
            print("=" * 80)
        else:
            print(f"Output file {output_file} not found!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if os.path.exists(sql_file):
            os.unlink(sql_file)
        if os.path.exists(output_file):
            os.unlink(output_file)

if __name__ == "__main__":
    test_firebird_connection() 