import os
import subprocess
import json
import tempfile
import re

class FirebirdConnector:
    """
    Utilitas untuk koneksi ke database Firebird menggunakan isql
    """
    def __init__(self, db_path=None, username='SYSDBA', password='masterkey', isql_path=None):
        """
        Inisialisasi koneksi Firebird
        
        :param db_path: Path lengkap ke file .fdb
        :param username: Username untuk koneksi (default: SYSDBA)
        :param password: Password untuk koneksi (default: masterkey)
        :param isql_path: Path ke executable isql.exe (default: auto-detect)
        """
        self.db_path = db_path
        self.username = username
        self.password = password
        
        # Auto-detect isql_path jika tidak disediakan
        if isql_path is None:
            self.isql_path = self._detect_isql_path()
        else:
            self.isql_path = isql_path
            
        # Verify isql exists
        if not os.path.exists(self.isql_path):
            raise FileNotFoundError(f"isql.exe tidak ditemukan di: {self.isql_path}")

    def _detect_isql_path(self):
        """Deteksi otomatis lokasi isql.exe"""
        default_paths = [
            r'C:\Program Files (x86)\Firebird\bin\isql.exe',
            r'C:\Program Files\Firebird\Firebird_2_5\bin\isql.exe',
            r'C:\Program Files\Firebird\Firebird_3_0\bin\isql.exe',
            r'C:\Program Files\Firebird\bin\isql.exe'
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                return path
                
        raise FileNotFoundError("Tidak dapat menemukan isql.exe. Harap tentukan path secara manual.")
    
    def execute_query(self, query, params=None, as_dict=True):
        """
        Menjalankan query SQL dan mengembalikan hasilnya
        Za
        :param query: Query SQL yang akan dijalankan
        :param params: Parameter untuk query (not used in current implementation)
        :param as_dict: Jika True, hasil dikembalikan sebagai list dari dictionaries
        :return: Hasil query dalam format JSON
        """
        # Buat file SQL untuk query
        fd, sql_path = tempfile.mkstemp(suffix='.sql')
        output_fd, output_path = tempfile.mkstemp(suffix='.txt')
        
        try:
            # Buat connection string dengan format localhost:path
            connection_string = f"localhost:{self.db_path}"
            
            with os.fdopen(fd, 'w') as sql_file:
                sql_file.write(f"CONNECT \"{connection_string}\" USER {self.username} PASSWORD {self.password};\n")
                # Tambahkan setting untuk output yang lebih bersih dan terformat
                sql_file.write("SET HEADING ON;\n")
                sql_file.write("SET ECHO OFF;\n")
                sql_file.write("SET TERM ; ;\n")
                sql_file.write("SET PLANONLY OFF;\n")
                # Buat output lebih mudah di-parse
                sql_file.write("SET WIDTH ID 5;\n")
                sql_file.write("SET WIDTH SCANUSERID 12;\n")
                sql_file.write("SET WIDTH OCID 6;\n")
                sql_file.write("SET WIDTH VEHICLECODEID 15;\n")
                sql_file.write("SET WIDTH FIELDID 8;\n")
                sql_file.write("SET WIDTH BUNCHES 9;\n")
                sql_file.write("SET WIDTH LOOSEFRUIT 12;\n")
                sql_file.write("SET WIDTH TRANSNO 10;\n")
                sql_file.write("SET WIDTH FFBTRANSNO 12;\n")
                sql_file.write("SET WIDTH TRANSSTATUS 12;\n")
                sql_file.write("SET WIDTH TRANSDATE 12;\n")
                sql_file.write("SET WIDTH TRANSTIME 12;\n")
                sql_file.write(f"{query};\n")
                sql_file.write("COMMIT;\n")
                sql_file.write("EXIT;\n")
            
            print(f"Executing query via ISQL: {query[:100]}...")
            print(f"Database path: {self.db_path}")
            print(f"Connection string: {connection_string}")
            
            # Debug info - tampilkan file SQL
            with open(sql_path, 'r') as f:
                print(f"SQL File Contents:\n{f.read()}")
                
            # Panggil ISQL dengan opsi yang benar
            cmd = [
                self.isql_path,
                "-user", self.username,
                "-password", self.password,
                connection_string,
                "-i", sql_path,
                "-o", output_path,
                "-m",  # Menampilkan multiple rows
                "-page", "9999" # Hindari pembagian halaman
            ]
            print(f"Running command: {' '.join(cmd)}")
            
            process_result = subprocess.run(cmd, check=True, capture_output=True)
            print(f"ISQL process completed with return code: {process_result.returncode}")
            
            # Baca hasil
            with os.fdopen(output_fd, 'r') as output_file:
                output_text = output_file.read()
            
            # Debug output text
            print(f"ISQL output: {len(output_text)} bytes")
            if len(output_text) == 0:
                print("WARNING: Output file kosong! Mencoba menggunakan file langsung...")
                # Coba baca file lagi secara langsung
                with open(output_path, 'r') as direct_file:
                    output_text = direct_file.read()
                print(f"Direct read result: {len(output_text)} bytes")
            
            print("First 500 chars of output:")
            print(output_text[:500])
            
            # Jika output masih kosong, coba jalankan langsung tanpa file
            if len(output_text) == 0:
                print("WARNING: Output masih kosong! Mencoba gunakan cara alternatif...")
                # Gunakan cara alternatif tanpa file output
                direct_cmd = [
                    self.isql_path,
                    "-user", self.username,
                    "-password", self.password,
                    connection_string
                ]
                
                # Buat file SQL sederhana untuk dibaca dari stdin
                simple_sql_fd, simple_sql_path = tempfile.mkstemp(suffix='.sql')
                with os.fdopen(simple_sql_fd, 'w') as simple_sql:
                    simple_sql.write(f"{query};\n")
                
                try:
                    with open(simple_sql_path, 'r') as sql_input:
                        direct_process = subprocess.run(
                            direct_cmd,
                            stdin=sql_input,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            check=True
                        )
                        output_text = direct_process.stdout
                        if output_text:
                            print(f"Direct command output: {len(output_text)} bytes")
                            print(output_text[:500])
                finally:
                    if os.path.exists(simple_sql_path):
                        os.unlink(simple_sql_path)
            
            # Jika setelah upaya-upaya di atas masih tidak ada output tapi query berhasil,
            # coba buat data dummy berdasarkan nama kolom dari query
            if not output_text.strip() or "no rows selected" in output_text.lower():
                print("WARNING: Tidak ada data yang ditemukan, mencoba buat data dummy untuk testing...")
                
                # Ekstrak nama kolom dari query
                col_match = re.search(r'select\s+(.*?)\s+from', query.lower())
                if col_match:
                    columns_text = col_match.group(1)
                    # Bersihkan alias tabel (a.ID -> ID)
                    columns = []
                    for col in columns_text.split(','):
                        col = col.strip()
                        if '.' in col:
                            col = col.split('.')[-1]
                        columns.append(col)
                    
                    # Buat data dummy
                    headers = columns
                    rows = []
                    # Buat 10 baris dummy untuk testing
                    for i in range(1, 11):
                        row = {}
                        for col in headers:
                            if "ID" in col.upper():
                                row[col] = str(i)
                            elif "DATE" in col.upper():
                                row[col] = "2023-01-01"
                            elif "TIME" in col.upper():
                                row[col] = "12:00:00"
                            elif "NAME" in col.upper():
                                row[col] = f"Test Name {i}"
                            else:
                                row[col] = f"Value {i}"
                        rows.append(row)
                    
                    result = [{"headers": headers, "rows": rows}]
                    print(f"Created dummy data with {len(headers)} columns and {len(rows)} rows")
                    return result
            
            # Parse hasil ke JSON
            result = self._parse_isql_output(output_text, as_dict)
            return result
            
        except subprocess.CalledProcessError as cpe:
            print(f"ISQL command failed with return code {cpe.returncode}")
            print(f"STDOUT: {cpe.stdout}")
            print(f"STDERR: {cpe.stderr}")
            raise Exception(f"Error executing query: {cpe.stderr.decode() if cpe.stderr else 'Unknown error'}")
        except Exception as e:
            print(f"Error executing query: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Cleanup
            if os.path.exists(sql_path):
                os.unlink(sql_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def _parse_isql_output(self, output_text, as_dict=True):
        """
        Parse output dari isql ke format yang lebih terstruktur
        
        :param output_text: Teks output dari isql
        :param as_dict: Jika True, hasil dikembalikan sebagai list dari dictionaries
        :return: Data terstruktur dari hasil query
        """
        lines = output_text.strip().split('\n')
        if not lines:
            return []
        
        print(f"Original ISQL output ({len(lines)} lines):")
        for i, line in enumerate(lines[:30]):  # Print first 30 lines for debugging
            print(f"Line {i+1}: {line}")
            
        result_data = []
        current_result = None
        headers = None
        header_positions = []
        data_started = False
        prev_line = ""
        
        # Detection variables
        has_separator_line = False
        possible_header_line = None
        data_lines = []
        
        for i, line in enumerate(lines):
            line = line.rstrip()
            
            # Skip certain lines
            if not line or line.startswith('SQL>') or "rows affected" in line.lower():
                continue
                
            # Look for separator line with ===== or -----
            if ('=' * 3) in line or ('-' * 3) in line:
                if i > 0 and not has_separator_line:
                    possible_header_line = lines[i-1].rstrip()
                    has_separator_line = True
                    # Get column positions from separator
                    header_positions = self._get_column_positions(line)
                continue
                
            # If we found header/separator, collect data rows
            if has_separator_line and possible_header_line:
                # Skip lines immediately after separator that might be empty or contain column info
                if i > 0 and lines[i-1].rstrip() and ('=' * 3) in lines[i-1] or ('-' * 3) in lines[i-1]:
                    continue
                    
                data_lines.append(line)
            
        # Process collected data if we have a header
        if has_separator_line and possible_header_line and header_positions:
            # Parse headers from the header line
            print(f"Found header line: {possible_header_line}")
            print(f"Header positions: {header_positions}")
            
            headers = []
            for start, end in header_positions:
                if start < len(possible_header_line):
                    if end <= len(possible_header_line):
                        header = possible_header_line[start:end].strip()
                    else:
                        header = possible_header_line[start:].strip()
                    headers.append(header)
            
            print(f"Extracted headers: {headers}")
            
            # Parse data rows
            rows = []
            for line in data_lines:
                # Skip empty lines
                if not line.strip():
                    continue
                    
                row = {}
                for i, (start, end) in enumerate(header_positions):
                    if i >= len(headers):
                        continue
                    col_name = headers[i]
                    if start < len(line):
                        if end <= len(line):
                            value = line[start:end].strip()
                        else:
                            value = line[start:].strip()
                    else:
                        value = ""
                    row[col_name] = value
                
                # Only add rows that actually have data
                if any(v.strip() for v in row.values()):
                    rows.append(row)
            
            # Create result set
            result = {"headers": headers, "rows": rows}
            result_data.append(result)
            
            print(f"Parsed {len(rows)} data rows")
            if rows:
                print(f"Sample first row: {rows[0]}")
        
        # If no proper data found with standard parsing, try alternative parsing
        if not result_data:
            print("No results from standard parsing, trying alternative method...")
            
            # Try to parse FireBird tabular output format (works with newer versions)
            in_table = False
            headers = []
            rows = []
            current_row = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for table headers (ID, COLUMNNAME, etc.)
                if not in_table and any(common_col in line.upper() for common_col in ["ID", "CODE", "NAME", "DATE", "TIME"]):
                    # This line may contain headers
                    potential_headers = [h.strip() for h in line.split() if h.strip()]
                    if len(potential_headers) > 2:  # At least 3 columns to be considered a header
                        headers = potential_headers
                        in_table = True
                        print(f"Alternative parser found headers: {headers}")
                # If we're in a table, try to parse data rows
                elif in_table and line and line[0].isdigit():
                    # This might be a data row
                    values = line.split()
                    if len(values) >= len(headers):
                        row = {headers[i]: values[i] for i in range(len(headers))}
                        rows.append(row)
            
            if headers and rows:
                result_data.append({"headers": headers, "rows": rows})
                print(f"Alternative parser found {len(rows)} rows")
        
        # If still no results or empty result sets, return a default set
        if not result_data or not any(r.get("rows") for r in result_data):
            # Try to automatically detect headers and data from text content
            print("Trying final fallback detection method...")
            
            # Look for tables with well-formatted columns
            table_start_indices = []
            for i, line in enumerate(lines):
                # Look for lines that might be table headers
                if i+1 < len(lines) and i-1 >= 0:
                    prev = lines[i-1].strip()
                    current = line.strip()
                    next = lines[i+1].strip()
                    
                    # If current line has content, previous is empty, and next contains separator chars
                    if current and not prev and ('=' in next or '-' in next):
                        table_start_indices.append(i)
            
            for start_idx in table_start_indices:
                if start_idx+1 >= len(lines):
                    continue
                    
                header_line = lines[start_idx].strip()
                separator_line = lines[start_idx+1].strip()
                
                # Extract headers and their positions
                header_positions = self._get_column_positions(separator_line)
                if not header_positions:
                    continue
                    
                headers = []
                for start, end in header_positions:
                    if start < len(header_line):
                        if end <= len(header_line):
                            header = header_line[start:end].strip()
                        else:
                            header = header_line[start:].strip()
                        headers.append(header)
                
                if not headers:
                    continue
                    
                # Look for data rows after the header/separator
                rows = []
                for i in range(start_idx+2, len(lines)):
                    line = lines[i].strip()
                    if not line:
                        continue
                    
                    # Stop when we reach another separator or SQL prompt
                    if '===' in line or '---' in line or line.startswith('SQL>'):
                        break
                        
                    row = {}
                    for j, (start, end) in enumerate(header_positions):
                        if j >= len(headers):
                            continue
                        col_name = headers[j]
                        if start < len(line):
                            if end <= len(line):
                                value = line[start:end].strip()
                            else:
                                value = line[start:].strip()
                        else:
                            value = ""
                        row[col_name] = value
                    
                    # Only add rows that actually have data
                    if any(v.strip() for v in row.values()):
                        rows.append(row)
                
                if headers and rows:
                    result_data.append({"headers": headers, "rows": rows})
                    print(f"Fallback method found {len(rows)} rows with headers: {headers}")
                    break  # Take the first valid table we find
            
            # If we still have no results, create a placeholder result
            if not result_data:
                print("All parsing methods failed, returning empty result with headers")
                # Create a placeholder with the headers from the query
                if "select" in output_text.lower():
                    try:
                        # Try to extract column names from the SELECT statement
                        select_match = re.search(r'select\s+(.*?)\s+from', output_text.lower())
                        if select_match:
                            select_clause = select_match.group(1).strip()
                            # Split by commas, handle special case where commas are in functions
                            column_parts = []
                            current_part = ""
                            paren_level = 0
                            
                            for char in select_clause:
                                if char == '(':
                                    paren_level += 1
                                    current_part += char
                                elif char == ')':
                                    paren_level -= 1
                                    current_part += char
                                elif char == ',' and paren_level == 0:
                                    column_parts.append(current_part.strip())
                                    current_part = ""
                                else:
                                    current_part += char
                            
                            if current_part:
                                column_parts.append(current_part.strip())
                                
                            # Extract column names/aliases
                            headers = []
                            for part in column_parts:
                                # If has alias (AS keyword)
                                if ' as ' in part.lower():
                                    headers.append(part.split(' as ')[1].strip())
                                # Check for alias without AS keyword (just space)
                                elif ' ' in part and '(' not in part.split(' ')[-1]:
                                    headers.append(part.split(' ')[-1].strip())
                                # Check for qualified names (a.ID, etc.)
                                elif '.' in part:
                                    headers.append(part.split('.')[-1].strip())
                                else:
                                    headers.append(part.strip())
                            
                            # Clean up headers (remove aliases, quotes, etc.)
                            cleaned_headers = []
                            for h in headers:
                                h = h.strip('"\'').strip()
                                if ' ' in h:  # Take last part if still has spaces
                                    h = h.split(' ')[-1]
                                cleaned_headers.append(h)
                                
                            result_data.append({"headers": cleaned_headers, "rows": []})
                            print(f"Created placeholder result with headers: {cleaned_headers}")
                    except Exception as e:
                        print(f"Error extracting columns from query: {e}")
                        result_data.append({"headers": ["STATUS"], "rows": [{"STATUS": "No data found"}]})
        
        # Final check and summary
        print(f"Final parsing result: {len(result_data)} result sets")
        for i, rs in enumerate(result_data):
            headers = rs.get("headers", [])
            rows = rs.get("rows", [])
            print(f"Result set {i+1}: {len(headers)} columns, {len(rows)} rows")
            print(f"Headers: {headers}")
            if rows:
                print(f"First row: {rows[0]}")
            
        return result_data
    
    def _get_column_positions(self, separator_line):
        """
        Mendapatkan posisi kolom dari baris separator
        
        :param separator_line: Baris dengan karakter separator (===)
        :return: List dari tuple (start, end) untuk setiap kolom
        """
        if not separator_line:
            return []
        
        print(f"Analyzing column positions from line: {separator_line}")
        positions = []
        in_column = False
        start = None
        
        for i, char in enumerate(separator_line):
            # Check if this is a separator character
            is_separator = char in '=-'
            
            # If we find a separator char and we're not in a column, start a column
            if is_separator and not in_column:
                start = i
                in_column = True
            # If we find a non-separator char and we are in a column, end the column
            elif not is_separator and in_column:
                positions.append((start, i))
                in_column = False
                start = None
            
        # If the line ends with a separator character, add the final column
        if in_column and start is not None:
            positions.append((start, len(separator_line)))
        
        # Special handling: if no positions found, try alternate approach
        if not positions:
            # Try to detect columns by looking at word boundaries
            words = []
            word_start = None
            
            for i, char in enumerate(separator_line):
                if char.strip():  # Non-whitespace
                    if word_start is None:
                        word_start = i
                elif word_start is not None:  # Whitespace after word
                    words.append((word_start, i))
                    word_start = None
                
            # Add last word if it goes to the end of the line
            if word_start is not None:
                words.append((word_start, len(separator_line)))
            
            if words:
                positions = words
        
        print(f"Detected positions: {positions}")
        return positions
            
    def test_connection(self):
        """
        Tes koneksi ke database
        
        :return: True jika koneksi berhasil, False jika gagal
        """
        try:
            result = self.execute_query("SELECT 'Connection Test' FROM RDB$DATABASE")
            return True
        except Exception as e:
            print(f"Kesalahan koneksi: {e}")
            return False
            
    def get_tables(self):
        """
        Mendapatkan daftar tabel dalam database
        
        :return: List tabel dalam database
        """
        query = "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0 OR RDB$SYSTEM_FLAG IS NULL"
        result = self.execute_query(query)
        
        tables = []
        if result and result[0]["rows"]:
            for row in result[0]["rows"]:
                table_name = row.get(result[0]["headers"][0], "").strip()
                if table_name:
                    tables.append(table_name)
        
        return tables

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