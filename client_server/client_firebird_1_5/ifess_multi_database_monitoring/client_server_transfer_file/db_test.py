import os
import sys
import fdb  # pip install fdb

def test_db_connection():
    """Test koneksi langsung ke database Firebird menggunakan fdb library"""
    try:
        # Database path
        db_path = r"D:\Gawean Rebinmas\Monitoring Database\ifess\PTRJ_P1A_08042025\PTRJ_P1A.FDB"
        
        print(f"Connecting to database: {db_path}")
        # Buat koneksi
        conn = fdb.connect(
            dsn=db_path,
            user='SYSDBA',
            password='masterkey'
        )
        
        print("Connected successfully!")
        
        # Buat cursor
        cursor = conn.cursor()
        
        # Execute query
        query = """
        SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT, 
               a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME, a.UPLOADDATETIME, 
               a.LASTUSER, a.LASTUPDATED, a.RECORDTAG, a.DRIVERNAME, a.DRIVERID, a.HARVESTINGDATE, a.PROCESSFLAG
        FROM FFBLOADINGCROP02 a WHERE ID <= 10
        """
        
        print(f"Executing query:\n{query}")
        cursor.execute(query)
        
        # Fetch column names
        column_names = [desc[0] for desc in cursor.description]
        print(f"Column names: {column_names}")
        
        # Fetch results
        rows = cursor.fetchall()
        print(f"Query returned {len(rows)} rows")
        
        if not rows:
            print("No rows returned")
            cursor.close()
            conn.close()
            return
        
        # Format and display results
        # Determine column widths
        col_widths = {}
        for i, col_name in enumerate(column_names):
            # Calculate max width for column (header width or max data width)
            col_widths[i] = max(len(col_name), 
                                max(len(str(row[i])) for row in rows))
        
        # Create header line
        header = ""
        separator = ""
        for i, col_name in enumerate(column_names):
            header += f"{col_name:{col_widths[i]}} | "
            separator += "-" * col_widths[i] + "-+-"
        
        # Print header
        print("\nResults:")
        print(separator)
        print(header)
        print(separator)
        
        # Print rows
        for row in rows:
            row_str = ""
            for i, value in enumerate(row):
                row_str += f"{str(value):{col_widths[i]}} | "
            print(row_str)
        
        print(separator)
        print(f"Total: {len(rows)} rows")
        
        # Close connections
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_db_connection() 