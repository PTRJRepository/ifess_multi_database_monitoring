import os
import sys
import socket
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import datetime

# Tambahkan path untuk mengimpor dari direktori common
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from common.network import NetworkMessage, send_message, receive_message, DEFAULT_PORT

class FirebirdClient:
    """Representasi dari client yang terhubung"""
    def __init__(self, client_id, display_name, socket, address):
        self.client_id = client_id
        self.display_name = display_name
        self.socket = socket
        self.address = address
        self.last_seen = time.time()
        self.is_connected = True
        self.db_info = {}
        self.tables = []

class ServerApp:
    """Aplikasi server untuk mengelola koneksi client dan mengirim query SQL"""
    def __init__(self, host='0.0.0.0', port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # client_id -> FirebirdClient
        self.lock = threading.Lock()
        self.running = False
        self.accept_thread = None
        self.heartbeat_thread = None
        self.query_history = []
        
        # Inisialisasi UI
        self.init_ui()
    
    def init_ui(self):
        """Inisialisasi antarmuka pengguna"""
        self.root = tk.Tk()
        self.root.title("Firebird Query Server")
        self.root.geometry("1000x800")
        
        # Menu bar
        menubar = tk.Menu(self.root)
        server_menu = tk.Menu(menubar, tearoff=0)
        server_menu.add_command(label="Start Server", command=self.start_server)
        server_menu.add_command(label="Stop Server", command=self.stop_server)
        server_menu.add_separator()
        server_menu.add_command(label="Exit", command=self.exit_app)
        menubar.add_cascade(label="Server", menu=server_menu)
        
        query_menu = tk.Menu(menubar, tearoff=0)
        query_menu.add_command(label="Send Query", command=self.send_query_ui)
        query_menu.add_command(label="Load Query from File", command=self.load_query)
        query_menu.add_command(label="Save Query", command=self.save_query)
        query_menu.add_separator()
        query_menu.add_command(label="Query History", command=self.show_history)
        menubar.add_cascade(label="Query", menu=query_menu)
        
        self.root.config(menu=menubar)
        
        # Paned window untuk membagi UI
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Panel kiri untuk daftar client
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Status server
        status_frame = ttk.LabelFrame(left_frame, text="Server Status")
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.server_status = ttk.Label(status_frame, text="Server: Stopped")
        self.server_status.pack(pady=5)
        
        # Daftar client
        clients_frame = ttk.LabelFrame(left_frame, text="Connected Clients")
        clients_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.client_tree = ttk.Treeview(clients_frame, columns=("ID", "Name", "IP", "Status"), show="headings")
        self.client_tree.heading("ID", text="ID")
        self.client_tree.heading("Name", text="Name")
        self.client_tree.heading("IP", text="IP Address")
        self.client_tree.heading("Status", text="Status")
        self.client_tree.column("ID", width=50)
        self.client_tree.column("Name", width=150)
        self.client_tree.column("IP", width=120)
        self.client_tree.column("Status", width=80)
        self.client_tree.pack(fill=tk.BOTH, expand=True)
        
        # Client context menu
        self.client_menu = tk.Menu(self.client_tree, tearoff=0)
        self.client_menu.add_command(label="Refresh Tables", command=self.refresh_client_tables)
        self.client_menu.add_command(label="Disconnect Client", command=self.disconnect_client)
        self.client_menu.add_command(label="Rename Client", command=self.rename_client)
        
        self.client_tree.bind("<Button-3>", self.show_client_menu)
        self.client_tree.bind("<Double-1>", self.show_client_details)
        
        # Panel kanan untuk query dan hasil
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=3)
        
        # Query editor
        query_frame = ttk.LabelFrame(right_frame, text="SQL Query")
        query_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.query_text = scrolledtext.ScrolledText(query_frame, height=10)
        self.query_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Target selection
        target_frame = ttk.Frame(right_frame)
        target_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(target_frame, text="Target: ").pack(side=tk.LEFT)
        self.target_var = tk.StringVar(value="All Clients")
        self.target_dropdown = ttk.Combobox(target_frame, textvariable=self.target_var)
        self.target_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.update_target_dropdown()
        
        # Send query button
        self.send_button = ttk.Button(target_frame, text="Send Query", command=self.send_query)
        self.send_button.pack(side=tk.RIGHT, padx=5)
        
        # Results
        results_frame = ttk.LabelFrame(right_frame, text="Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.results_notebook = ttk.Notebook(results_frame)
        self.results_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Log frame
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=5)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
        
        # Konfigurasi closing event
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        
        # Update UI setiap 1 detik
        self.update_ui()
    
    def update_ui(self):
        """Update UI secara periodik"""
        self.update_client_list()
        self.root.after(1000, self.update_ui)
    
    def update_client_list(self):
        """Update daftar client di UI"""
        # Clear treeview
        for item in self.client_tree.get_children():
            self.client_tree.delete(item)
        
        # Tambahkan client yang terhubung
        with self.lock:
            for client_id, client in self.clients.items():
                status = "Connected" if client.is_connected else "Disconnected"
                self.client_tree.insert("", tk.END, values=(
                    client_id, 
                    client.display_name, 
                    f"{client.address[0]}:{client.address[1]}", 
                    status
                ))
        
        # Update dropdown target
        self.update_target_dropdown()
    
    def update_target_dropdown(self):
        """Update dropdown untuk pilihan target client"""
        values = ["All Clients"]
        with self.lock:
            for client_id, client in self.clients.items():
                if client.is_connected:
                    values.append(f"{client.display_name} ({client_id})")
        
        self.target_dropdown['values'] = values
    
    def log(self, message):
        """Tambahkan pesan ke log"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        print(log_message, end="")
    
    def start_server(self):
        """Mulai server socket untuk menerima koneksi"""
        if self.running:
            messagebox.showinfo("Server", "Server sudah berjalan")
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.log(f"Server berjalan di {self.host}:{self.port}")
            self.server_status.config(text=f"Server: Running on port {self.port}")
            
            # Mulai thread untuk menerima koneksi
            self.accept_thread = threading.Thread(target=self.accept_connections)
            self.accept_thread.daemon = True
            self.accept_thread.start()
            
            # Mulai thread untuk heartbeat
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_clients)
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()
            
        except Exception as e:
            self.log(f"Error memulai server: {e}")
            messagebox.showerror("Server Error", f"Tidak dapat memulai server: {e}")
    
    def stop_server(self):
        """Hentikan server"""
        if not self.running:
            messagebox.showinfo("Server", "Server sudah berhenti")
            return
        
        self.running = False
        
        # Tutup semua koneksi client
        with self.lock:
            for client_id, client in self.clients.items():
                try:
                    client.socket.close()
                except:
                    pass
            self.clients.clear()
        
        # Tutup server socket
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None
        
        self.log("Server dihentikan")
        self.server_status.config(text="Server: Stopped")
        self.update_client_list()
    
    def accept_connections(self):
        """Thread untuk menerima koneksi dari client"""
        try:
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.settimeout(5.0)  # Set timeout
                    
                    # Buat thread untuk handle client
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log(f"Error saat menerima koneksi: {e}")
                    break
        except Exception as e:
            if self.running:
                self.log(f"Error di thread accept_connections: {e}")
    
    def handle_client(self, client_socket, client_address):
        """Handle komunikasi dengan client"""
        client_id = None
        
        try:
            # Tingkatkan timeout untuk registrasi
            client_socket.settimeout(15.0)
            
            # Terima pesan registrasi
            message = receive_message(client_socket)
            
            if not message or message.msg_type != NetworkMessage.TYPE_REGISTER:
                self.log(f"Registrasi gagal dari {client_address}")
                client_socket.close()
                return
            
            # Extract informasi registrasi
            client_id = message.client_id or f"client_{int(time.time())}"
            client_info = message.data
            display_name = client_info.get('display_name', f"Client {client_id}")
            db_info = client_info.get('db_info', {})
            
            # Buat objek client
            client = FirebirdClient(client_id, display_name, client_socket, client_address)
            client.db_info = db_info
            
            # Simpan client
            with self.lock:
                self.clients[client_id] = client
            
            self.log(f"Client {display_name} ({client_id}) terhubung dari {client_address[0]}:{client_address[1]}")
            
            # Minta daftar tabel dari client
            try:
                tables_message = NetworkMessage(NetworkMessage.TYPE_QUERY, {
                    'query': "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0 OR RDB$SYSTEM_FLAG IS NULL",
                    'description': 'get_tables'
                }, client_id)
                
                success = send_message(client_socket, tables_message)
                if not success:
                    self.log(f"Gagal mengirim permintaan tabel ke {display_name}")
            except Exception as e:
                self.log(f"Error saat meminta tabel dari {display_name}: {e}")
            
            # Loop utama untuk client ini
            while self.running and client.is_connected:
                try:
                    # Set timeout untuk socket
                    client_socket.settimeout(10.0)  # Tingkatkan timeout
                    
                    # Terima pesan dari client
                    print(f"[SERVER] Menunggu pesan dari client {display_name}...")
                    message = receive_message(client_socket)
                    
                    if not message:
                        print(f"[SERVER] Koneksi terputus dari {display_name}")
                        self.log(f"Koneksi terputus dari {display_name}")
                        break
                    
                    # Reset timeout
                    client.last_seen = time.time()
                    
                    # Proses pesan berdasarkan tipe
                    print(f"[SERVER] Menerima pesan tipe {message.msg_type} dari {display_name}")
                    self.log(f"Menerima pesan tipe {message.msg_type} dari {display_name}")
                    
                    # Proses pesan
                    if message.msg_type == NetworkMessage.TYPE_PONG:
                        # Heartbeat response, tidak perlu diproses lebih lanjut
                        pass
                    elif message.msg_type == NetworkMessage.TYPE_RESULT:
                        # Detail debug untuk hasil query
                        result_data = message.data
                        query = result_data.get('query', 'Unknown query')
                        description = result_data.get('description', '')
                        result = result_data.get('result', [])
                        
                        print("="*50)
                        print(f"[SERVER] Menerima hasil query dari {display_name}:")
                        print(f"Query: {query[:100]}...")
                        print(f"Description: {description}")
                        print(f"Result sets: {len(result)}")
                        
                        for i, rs in enumerate(result):
                            headers = rs.get('headers', [])
                            rows = rs.get('rows', [])
                            print(f"Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
                            print(f"  Headers: {headers}")
                            if rows and len(rows) > 0:
                                print(f"  First row keys: {list(rows[0].keys()) if isinstance(rows[0], dict) else 'not a dict'}")
                                print(f"  First row data: {str(rows[0])[:200]}...")
                        print("="*50)
                        
                        self.log(f"Menerima hasil query dari {display_name}: {len(result)} result sets")
                        
                        # Hasil query
                        self.process_query_result(client, message.data)
                    elif message.msg_type == NetworkMessage.TYPE_ERROR:
                        # Error dari client
                        error = message.data.get('error', 'Unknown error')
                        self.log(f"Error dari {client.display_name}: {error}")
                except socket.timeout:
                    # Log timeout tapi jangan langsung putuskan koneksi
                    self.log(f"Timeout saat berkomunikasi dengan {display_name}, menunggu heartbeat...")
                    continue
                except ConnectionError as ce:
                    print(f"[SERVER] Connection error dengan {display_name}: {ce}")
                    self.log(f"Connection error dengan {display_name}: {ce}")
                    break
                except Exception as e:
                    print(f"[SERVER] Error saat berkomunikasi dengan {client.display_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    self.log(f"Error saat berkomunikasi dengan {client.display_name}: {e}")
                    break
            
            # Client disconnected
            with self.lock:
                if client_id in self.clients:
                    self.clients[client_id].is_connected = False
            
            self.log(f"Client {display_name} terputus")
            
        except Exception as e:
            print(f"[SERVER] Error dalam handle_client: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"Error dalam handle_client: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            
            # Update client list di UI
            self.update_client_list()
    
    def heartbeat_clients(self):
        """Thread untuk ping client secara berkala"""
        while self.running:
            try:
                with self.lock:
                    # Copy client list untuk iterasi
                    clients_copy = list(self.clients.items())
                
                # Check setiap client
                for client_id, client in clients_copy:
                    if not client.is_connected:
                        continue
                    
                    try:
                        # Jika terlalu lama tidak ada respon, anggap client terputus
                        if time.time() - client.last_seen > 30:  # Tingkatkan timeout ke 30 detik
                            self.log(f"Client {client.display_name} timeout")
                            client.is_connected = False
                            try:
                                client.socket.close()
                            except:
                                pass
                            continue
                        
                        # Kirim ping
                        ping_message = NetworkMessage(NetworkMessage.TYPE_PING, {}, client_id)
                        if not send_message(client.socket, ping_message):
                            self.log(f"Gagal mengirim ping ke {client.display_name}")
                            client.is_connected = False
                            try:
                                client.socket.close()
                            except:
                                pass
                    except Exception as e:
                        self.log(f"Error saat ping client {client.display_name}: {e}")
                        client.is_connected = False
                        try:
                            client.socket.close()
                        except:
                            pass
                
                # Update client list di UI
                self.update_client_list()
                
            except Exception as e:
                self.log(f"Error in heartbeat thread: {e}")
            
            # Sleep selama 5 detik
            time.sleep(5)
    
    def process_query_result(self, client, result_data):
        """Proses hasil query dari client"""
        query = result_data.get('query', '')
        description = result_data.get('description', '')
        result = result_data.get('result', [])
        error = result_data.get('error')
        
        # Debug info detail
        print("="*50)
        print(f"[SERVER] PROCESS_QUERY_RESULT dari {client.display_name}")
        print(f"Query: {query[:100]}...")
        print(f"Description: {description}")
        print(f"Result sets: {len(result)}")
        
        for i, rs in enumerate(result):
            headers = rs.get('headers', [])
            rows = rs.get('rows', [])
            print(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
            if headers:
                print(f"  Headers: {headers}")
            if rows and len(rows) > 0:
                print(f"  First row type: {type(rows[0])}")
                print(f"  First row keys: {list(rows[0].keys()) if isinstance(rows[0], dict) else 'not a dict'}")
                print(f"  First row values: {str(rows[0])[:200]}...")
        print("="*50)
        
        self.log(f"Processing query result from {client.display_name}")
        self.log(f"Query: {query[:100]}...")
        self.log(f"Description: {description}")
        self.log(f"Result sets: {len(result)}")
        for i, rs in enumerate(result):
            headers = rs.get('headers', [])
            rows = rs.get('rows', [])
            self.log(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
            if headers:
                self.log(f"  Headers: {headers}")
            if rows and len(rows) > 0:
                self.log(f"  First row keys: {list(rows[0].keys()) if isinstance(rows[0], dict) else 'not a dict'}")
        
        # Proses berdasarkan description
        if description == 'get_tables' and not error:
            # Process daftar tabel
            tables = []
            for result_set in result:
                for row in result_set.get('rows', []):
                    if row and len(row) > 0:
                        try:
                            table_name = list(row.values())[0].strip()
                            if table_name:
                                tables.append(table_name)
                        except Exception as e:
                            print(f"[SERVER] Error parsing table name: {e}, row: {row}")
            
            with self.lock:
                client.tables = tables
            
            self.log(f"Menerima {len(tables)} tabel dari {client.display_name}")
            return
        
        print(f"[SERVER] Membuat tab baru untuk hasil query dari {client.display_name}")
        
        # Create result tab on the UI thread
        self.root.after(0, self._create_result_tab, client, query, description, result, error)
        
    def _create_result_tab(self, client, query, description, result, error):
        """Create result tab in UI thread"""
        try:
            print(f"[SERVER] Creating result tab in UI thread")
            # Buat tab baru untuk hasil
            tab_title = f"Result - {client.display_name}"
            result_frame = ttk.Frame(self.results_notebook)
            self.results_notebook.add(result_frame, text=tab_title)
            self.results_notebook.select(result_frame)  # Aktifkan tab baru
            
            # Tambah info query
            query_info = ttk.LabelFrame(result_frame, text="Query Info")
            query_info.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(query_info, text=f"Client: {client.display_name}").pack(anchor=tk.W)
            ttk.Label(query_info, text=f"Database: {client.db_info.get('name', 'Unknown')}").pack(anchor=tk.W)
            ttk.Label(query_info, text=f"Query: {query}").pack(anchor=tk.W)
            ttk.Label(query_info, text=f"Executed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").pack(anchor=tk.W)
            
            if error:
                # Tampilkan error
                error_frame = ttk.LabelFrame(result_frame, text="Error")
                error_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                error_text = scrolledtext.ScrolledText(error_frame, height=10)
                error_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                error_text.insert(tk.END, error)
                error_text.config(state=tk.DISABLED)
                
                self.log(f"Error pada query di {client.display_name}: {error}")
            elif not result or len(result) == 0:
                # Tidak ada hasil
                no_result_frame = ttk.LabelFrame(result_frame, text="No Results")
                no_result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                ttk.Label(no_result_frame, text="Query executed successfully, but returned no results.").pack(pady=20)
                self.log(f"Query tidak mengembalikan hasil dari {client.display_name}")
            else:
                # Tampilkan hasil
                for i, result_set in enumerate(result):
                    # Verifikasi data result set valid
                    headers = result_set.get('headers', [])
                    rows = result_set.get('rows', [])
                    
                    print(f"[SERVER] Processing result set {i+1}: {len(rows)} rows, headers: {headers}")
                    
                    if not headers:
                        print(f"[SERVER] Result set {i+1} tidak memiliki headers, dilewati")
                        self.log(f"Result set {i+1} tidak memiliki headers, dilewati")
                        continue
                    
                    result_frame_inner = ttk.LabelFrame(result_frame, text=f"Result Set {i+1}")
                    result_frame_inner.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                    
                    # Buat frame untuk menampung treeview dan status
                    tree_container = ttk.Frame(result_frame_inner)
                    tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                    
                    if not rows or len(rows) == 0:
                        ttk.Label(tree_container, text="Query returned 0 rows").pack(pady=10)
                        continue
                    
                    # Log debug info
                    print(f"[SERVER] Rendering result set {i+1} to treeview")
                    self.log(f"Rendering result set {i+1}: {len(rows)} rows with columns: {', '.join(headers)}")
                    
                    try:
                        # Buat treeview untuk hasil dengan style yang mirip ISQL
                        tree = ttk.Treeview(tree_container, columns=headers, show="headings", style="ISQL.Treeview")
                        
                        # Sesuaikan style untuk tampilan mirip ISQL
                        style = ttk.Style()
                        style.configure("ISQL.Treeview", background="white", foreground="black", rowheight=25)
                        style.configure("ISQL.Treeview.Heading", font=('Calibri', 10, 'bold'), background="#E8E8E8")
                        
                        # Set header
                        for header in headers:
                            tree.heading(header, text=header)
                            # Set lebar kolom berdasarkan konten
                            max_width = len(str(header)) * 10
                            for row in rows:
                                val = str(row.get(header, ""))
                                width = len(val) * 8
                                if width > max_width:
                                    max_width = width
                            tree.column(header, width=min(max_width, 250))
                        
                        # Tambahkan data
                        print(f"[SERVER] Adding {len(rows)} rows to treeview")
                        row_count = 0
                        for row in rows:
                            values = []
                            for header in headers:
                                values.append(row.get(header, ""))
                            tree.insert("", tk.END, values=values)
                            row_count += 1
                        
                        print(f"[SERVER] Successfully added {row_count} rows to treeview")
                        
                        # Tambahkan scrollbar vertikal
                        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
                        tree.configure(yscrollcommand=vsb.set)
                        vsb.pack(side=tk.RIGHT, fill=tk.Y)
                        
                        # Tambahkan scrollbar horizontal
                        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
                        tree.configure(xscrollcommand=hsb.set)
                        hsb.pack(side=tk.BOTTOM, fill=tk.X)
                        
                        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                        
                        # Tambahkan status bar di bawah
                        status_frame = ttk.Frame(result_frame_inner)
                        status_frame.pack(fill=tk.X, padx=5, pady=(2, 5))
                        
                        # Hitung jumlah baris
                        num_rows = len(rows)
                        
                        # Tambahkan label status dengan informasi client dan jumlah baris
                        status_label = ttk.Label(
                            status_frame, 
                            text=f"{num_rows} rows fetched from {client.display_name} @ {client.address[0]}",
                            anchor=tk.W
                        )
                        status_label.pack(side=tk.LEFT, padx=5)
                        
                        # Tambahkan timestamp
                        time_label = ttk.Label(
                            status_frame,
                            text=f"Transaction started: {datetime.datetime.now().strftime('%H:%M:%S')}",
                            anchor=tk.E
                        )
                        time_label.pack(side=tk.RIGHT, padx=5)
                    except Exception as e:
                        print(f"[SERVER] ERROR saat membuat treeview: {e}")
                        import traceback
                        traceback.print_exc()
                        
                        # Jika gagal membuat treeview, tampilkan pesan error
                        error_label = ttk.Label(
                            tree_container, 
                            text=f"Error displaying results: {e}"
                        )
                        error_label.pack(pady=20)
                
                print(f"[SERVER] Hasil query berhasil ditampilkan dari {client.display_name}")
                self.log(f"Hasil query ditampilkan dari {client.display_name}")
                
        except Exception as e:
            print(f"[SERVER] ERROR saat membuat tab hasil: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"Error saat membuat tab hasil: {e}")
    
    def send_query(self):
        """Kirim query ke client yang dipilih"""
        query = self.query_text.get("1.0", tk.END).strip()
        
        if not query:
            messagebox.showwarning("Query Empty", "Please enter a SQL query")
            return
        
        target = self.target_var.get()
        
        # Tambahkan ke history
        self.query_history.append({
            'query': query,
            'target': target,
            'timestamp': datetime.datetime.now().isoformat()
        })
        
        # Kirim ke client yang dipilih
        if target == "All Clients":
            # Kirim ke semua client
            with self.lock:
                for client_id, client in self.clients.items():
                    if client.is_connected:
                        self.send_query_to_client(client, query)
        else:
            # Extract client_id dari target
            client_id = target.split("(")[-1].split(")")[0]
            
            with self.lock:
                if client_id in self.clients:
                    client = self.clients[client_id]
                    if client.is_connected:
                        self.send_query_to_client(client, query)
                    else:
                        messagebox.showwarning("Client Disconnected", f"Client {client.display_name} tidak terhubung")
                else:
                    messagebox.showwarning("Client Not Found", f"Client {client_id} tidak ditemukan")
    
    def send_query_to_client(self, client, query):
        """Kirim query ke client tertentu"""
        try:
            query_message = NetworkMessage(NetworkMessage.TYPE_QUERY, {
                'query': query,
                'description': 'user_query'
            }, client.client_id)
            
            send_message(client.socket, query_message)
            self.log(f"Query dikirim ke {client.display_name}")
        except Exception as e:
            self.log(f"Error saat mengirim query ke {client.display_name}: {e}")
            messagebox.showerror("Send Error", f"Gagal mengirim query ke {client.display_name}: {e}")
    
    def send_query_ui(self):
        """Dialog untuk mengirim query"""
        # Langsung panggil send_query karena UI sudah tersedia
        self.send_query()
    
    def load_query(self):
        """Load query dari file"""
        import tkinter.filedialog as filedialog
        
        filename = filedialog.askopenfilename(
            title="Load SQL Query",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    query = f.read()
                
                self.query_text.delete("1.0", tk.END)
                self.query_text.insert("1.0", query)
                
                self.log(f"Query dimuat dari {filename}")
            except Exception as e:
                self.log(f"Error saat memuat query: {e}")
                messagebox.showerror("Load Error", f"Gagal memuat query: {e}")
    
    def save_query(self):
        """Simpan query ke file"""
        import tkinter.filedialog as filedialog
        
        query = self.query_text.get("1.0", tk.END).strip()
        
        if not query:
            messagebox.showwarning("Empty Query", "Tidak ada query untuk disimpan")
            return
        
        filename = filedialog.asksaveasfilename(
            title="Save SQL Query",
            defaultextension=".sql",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(query)
                
                self.log(f"Query disimpan ke {filename}")
            except Exception as e:
                self.log(f"Error saat menyimpan query: {e}")
                messagebox.showerror("Save Error", f"Gagal menyimpan query: {e}")
    
    def show_history(self):
        """Tampilkan history query"""
        history_window = tk.Toplevel(self.root)
        history_window.title("Query History")
        history_window.geometry("600x400")
        
        # Treeview untuk history
        tree = ttk.Treeview(history_window, columns=("Timestamp", "Target", "Query"), show="headings")
        tree.heading("Timestamp", text="Timestamp")
        tree.heading("Target", text="Target")
        tree.heading("Query", text="Query")
        tree.column("Timestamp", width=150)
        tree.column("Target", width=100)
        tree.column("Query", width=350)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tambahkan data
        for entry in reversed(self.query_history):
            timestamp = datetime.datetime.fromisoformat(entry['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
            tree.insert("", tk.END, values=(timestamp, entry['target'], entry['query']))
        
        # Button untuk menggunakan query yang dipilih
        def use_selected_query():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                values = item['values']
                query = values[2]
                
                self.query_text.delete("1.0", tk.END)
                self.query_text.insert("1.0", query)
                
                history_window.destroy()
        
        button_frame = ttk.Frame(history_window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(button_frame, text="Use Selected Query", command=use_selected_query).pack(side=tk.RIGHT)
    
    def show_client_menu(self, event):
        """Tampilkan menu context untuk client"""
        item = self.client_tree.identify_row(event.y)
        if item:
            self.client_tree.selection_set(item)
            self.client_menu.post(event.x_root, event.y_root)
    
    def show_client_details(self, event):
        """Tampilkan detail client yang dipilih"""
        item = self.client_tree.identify_row(event.y)
        if not item:
            return
        
        item_data = self.client_tree.item(item)
        client_id = item_data['values'][0]
        
        with self.lock:
            if client_id not in self.clients:
                return
            
            client = self.clients[client_id]
            
            # Buat dialog untuk menampilkan detail
            detail_window = tk.Toplevel(self.root)
            detail_window.title(f"Client Detail: {client.display_name}")
            detail_window.geometry("500x400")
            
            # Frame untuk info client
            info_frame = ttk.LabelFrame(detail_window, text="Client Information")
            info_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(info_frame, text=f"ID: {client.client_id}").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Label(info_frame, text=f"Name: {client.display_name}").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Label(info_frame, text=f"IP: {client.address[0]}:{client.address[1]}").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Label(info_frame, text=f"Status: {'Connected' if client.is_connected else 'Disconnected'}").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Label(info_frame, text=f"Last Seen: {datetime.datetime.fromtimestamp(client.last_seen).strftime('%Y-%m-%d %H:%M:%S')}").pack(anchor=tk.W, padx=5, pady=2)
            
            # DB Info
            db_frame = ttk.LabelFrame(detail_window, text="Database Information")
            db_frame.pack(fill=tk.X, padx=10, pady=5)
            
            for key, value in client.db_info.items():
                ttk.Label(db_frame, text=f"{key}: {value}").pack(anchor=tk.W, padx=5, pady=2)
            
            # Tables
            tables_frame = ttk.LabelFrame(detail_window, text="Tables")
            tables_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            tables_list = tk.Listbox(tables_frame)
            tables_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            for table in client.tables:
                tables_list.insert(tk.END, table)
    
    def refresh_client_tables(self):
        """Refresh daftar tabel untuk client yang dipilih"""
        selected = self.client_tree.selection()
        if not selected:
            return
        
        item_data = self.client_tree.item(selected[0])
        client_id = item_data['values'][0]
        
        with self.lock:
            if client_id not in self.clients:
                return
            
            client = self.clients[client_id]
            
            if not client.is_connected:
                messagebox.showwarning("Client Disconnected", f"Client {client.display_name} tidak terhubung")
                return
            
            # Kirim query untuk mendapatkan daftar tabel
            try:
                tables_message = NetworkMessage(NetworkMessage.TYPE_QUERY, {
                    'query': "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0 OR RDB$SYSTEM_FLAG IS NULL",
                    'description': 'get_tables'
                }, client_id)
                
                send_message(client.socket, tables_message)
                self.log(f"Refresh daftar tabel untuk {client.display_name}")
            except Exception as e:
                self.log(f"Error saat refresh tabel untuk {client.display_name}: {e}")
                messagebox.showerror("Refresh Error", f"Gagal refresh tabel: {e}")
    
    def disconnect_client(self):
        """Putuskan koneksi dengan client yang dipilih"""
        selected = self.client_tree.selection()
        if not selected:
            return
        
        item_data = self.client_tree.item(selected[0])
        client_id = item_data['values'][0]
        
        with self.lock:
            if client_id not in self.clients:
                return
            
            client = self.clients[client_id]
            
            try:
                client.socket.close()
            except:
                pass
            
            client.is_connected = False
            self.log(f"Client {client.display_name} diputuskan")
    
    def rename_client(self):
        """Rename client yang dipilih"""
        selected = self.client_tree.selection()
        if not selected:
            return
        
        item_data = self.client_tree.item(selected[0])
        client_id = item_data['values'][0]
        
        with self.lock:
            if client_id not in self.clients:
                return
            
            client = self.clients[client_id]
            
            new_name = simpledialog.askstring(
                "Rename Client", 
                "Enter new name:",
                initialvalue=client.display_name
            )
            
            if new_name:
                client.display_name = new_name
                self.log(f"Client {client_id} diganti namanya menjadi {new_name}")
                self.update_client_list()
    
    def exit_app(self):
        """Keluar dari aplikasi"""
        if messagebox.askyesno("Exit", "Apakah Anda yakin ingin keluar?"):
            # Berhenti server jika berjalan
            if self.running:
                self.stop_server()
            
            self.root.destroy()
            sys.exit(0)
    
    def run(self):
        """Jalankan aplikasi"""
        self.root.mainloop()

if __name__ == "__main__":
    app = ServerApp()
    app.run() 