import os
import sys
import subprocess
from pprint import pprint

def test_isql_direct():
    """Test koneksi langsung ke database Firebird menggunakan isql command line"""
    try:
        # Database path
        db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
        isql_path = r"C:\Program Files (x86)\Firebird\bin\isql.exe"
        
        if not os.path.exists(isql_path):
            print(f"Error: isql.exe not found at {isql_path}")
            return
            
        print(f"Testing connection to database: {db_path}")
        
        # Test query
        query = """
        SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT, 
               a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME, a.UPLOADDATETIME, 
               a.LASTUSER, a.LASTUPDATED, a.RECORDTAG, a.DRIVERNAME, a.DRIVERID, a.HARVESTINGDATE, a.PROCESSFLAG
        FROM FFBLOADINGCROP02 a WHERE ID <= 10;
        """
        
        # Create a temporary SQL file
        sql_file = "temp_query.sql"
        with open(sql_file, "w") as f:
            f.write(query)
        
        # Run ISQL directly from command line
        cmd = [
            isql_path,
            db_path,
            "-user", "SYSDBA",
            "-password", "masterkey",
            "-i", sql_file,
            "-page", "9999"
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        process = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Clean up the temp file
        if os.path.exists(sql_file):
            os.unlink(sql_file)
        
        # Process output
        if process.returncode != 0:
            print("Error running ISQL:")
            print(process.stderr)
            return
        
        print("\nISQL Query Results:")
        print("=" * 80)
        print(process.stdout)
        print("=" * 80)
        
        # Count rows and do some basic analysis
        stdout_lines = process.stdout.splitlines()
        data_lines = [line for line in stdout_lines if line.strip() and not line.startswith("=")]
        
        if len(data_lines) > 1:  # Assuming at least a header and one data line
            print(f"\nFound approximately {len(data_lines) - 1} rows of data")
            print("\nFirst few rows:")
            for i, line in enumerate(data_lines[:5]):
                print(f"{i}: {line}")
        else:
            print("No data rows found.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure the temporary file is deleted
        if os.path.exists(sql_file):
            os.unlink(sql_file)

if __name__ == "__main__":
    test_isql_direct() 