import os
import sys
import socket
import json
import threading
import time
import queue
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
    # Status constants
    STATUS_IDLE = "Idle"
    STATUS_WAITING = "Waiting"
    STATUS_PROCESSING = "Processing"
    STATUS_COMPLETED = "Completed"
    STATUS_ERROR = "Error"

    # File transfer status constants
    TRANSFER_NONE = "Not Started"
    TRANSFER_PENDING = "Pending"
    TRANSFER_IN_PROGRESS = "In Progress"
    TRANSFER_COMPLETED = "Completed"
    TRANSFER_FAILED = "Failed"

    def __init__(self, client_id, display_name, socket, address):
        self.client_id = client_id
        self.display_name = display_name
        self.socket = socket
        self.address = address
        self.last_seen = time.time()
        self.is_connected = True
        self.db_info = {}
        self.tables = []
        self.query_status = self.STATUS_IDLE
        self.current_query = None
        self.query_start_time = None
        self.query_end_time = None
        self.last_error = None

        # Database file transfer properties
        self.transfer_status = self.TRANSFER_NONE
        self.file_name = None
        self.file_size = 0
        self.received_size = 0
        self.chunks_received = 0
        self.total_chunks = 0
        self.transfer_start_time = None
        self.transfer_end_time = None
        self.transfer_error = None

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
        self.query_thread = None
        self.query_history = []
        self.max_result_rows = 10000  # Batasan maksimum jumlah baris yang akan ditampilkan (diubah menjadi lebih kecil)
        self.default_socket_timeout = 60.0  # Timeout socket default yang lebih besar

        # Queue for sequential query execution
        self.query_queue = queue.Queue()
        self.is_processing_queue = False

        # Inisialisasi UI
        self.init_ui()

    def init_ui(self):
        """Inisialisasi antarmuka pengguna"""
        self.root = tk.Tk()
        self.root.title("Firebird Query Server")
        self.root.geometry("1200x900")

        # Set tema dan style untuk mirip MSSQL
        self.configure_mssql_style()

        # Menu bar
        menubar = tk.Menu(self.root)
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

        # Tampilan status server + tombol
        server_status_container = ttk.Frame(status_frame)
        server_status_container.pack(fill=tk.X, pady=5, padx=5)

        self.server_status = ttk.Label(server_status_container, text="Server: Stopped")
        self.server_status.pack(side=tk.LEFT, pady=5)

        # Tombol dinamis untuk start/stop server
        self.server_button_frame = ttk.Frame(server_status_container)
        self.server_button_frame.pack(side=tk.RIGHT, pady=5)

        self.start_server_button = ttk.Button(self.server_button_frame, text="Start Server",
                                            command=self.start_server, width=15)
        self.start_server_button.pack(side=tk.RIGHT, padx=(0, 5))
        self.stop_server_button = ttk.Button(self.server_button_frame, text="Stop Server",
                                           command=self.stop_server, width=15, state=tk.DISABLED)
        self.stop_server_button.pack(side=tk.RIGHT)

        # Daftar client
        clients_frame = ttk.LabelFrame(left_frame, text="Connected Clients")
        clients_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Header toolbar dengan tombol minimize/maximize
        clients_toolbar = ttk.Frame(clients_frame)
        clients_toolbar.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        # Toggle button untuk collapse/expand daftar client
        self.client_collapsed = tk.BooleanVar(value=False)
        self.toggle_clients_btn = ttk.Button(clients_toolbar, text="▼", width=3,
                               command=self.toggle_clients_panel)
        self.toggle_clients_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(clients_toolbar, text="Client List").pack(side=tk.LEFT, padx=5)

        # Frame untuk treeview dan scrollbar
        self.client_tree_frame = ttk.Frame(clients_frame)
        self.client_tree_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.client_tree = ttk.Treeview(self.client_tree_frame, columns=("Name", "Connection", "Query Status", "Time", "Transfer Status"), show="headings")
        self.client_tree.heading("Name", text="Client Name")
        self.client_tree.heading("Connection", text="Connection")
        self.client_tree.heading("Query Status", text="Query Status")
        self.client_tree.heading("Time", text="Execution Time")
        self.client_tree.heading("Transfer Status", text="DB Transfer")
        self.client_tree.column("Name", width=150)
        self.client_tree.column("Connection", width=80)
        self.client_tree.column("Query Status", width=100)
        self.client_tree.column("Time", width=80)
        self.client_tree.column("Transfer Status", width=100)

        # Menambahkan scrollbar vertikal
        client_vsb = ttk.Scrollbar(self.client_tree_frame, orient="vertical", command=self.client_tree.yview)
        self.client_tree.configure(yscrollcommand=client_vsb.set)
        client_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.client_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # Tombol detail client
        detail_frame = ttk.Frame(clients_frame)
        detail_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=2, pady=2)

        # Button to request database files from all clients
        ttk.Button(detail_frame, text="Get All DB Files",
                 command=self.request_all_database_files).pack(side=tk.LEFT, padx=2)

        # Button to request database file from selected client
        ttk.Button(detail_frame, text="Get Selected DB",
                 command=self.request_selected_database_file).pack(side=tk.LEFT, padx=2)

        ttk.Button(detail_frame, text="Show Details",
                 command=self.show_selected_client_details).pack(side=tk.RIGHT, padx=2)

        # Client context menu
        self.client_menu = tk.Menu(self.client_tree, tearoff=0)
        self.client_menu.add_command(label="Show Details", command=self.show_selected_client_details)
        self.client_menu.add_separator()
        self.client_menu.add_command(label="Request Database File", command=self.request_selected_database_file)
        self.client_menu.add_separator()
        self.client_menu.add_command(label="Refresh Tables", command=self.refresh_client_tables)
        self.client_menu.add_command(label="Disconnect Client", command=self.disconnect_client)
        self.client_menu.add_command(label="Rename Client", command=self.rename_client)

        self.client_tree.bind("<Button-3>", self.show_client_menu)
        self.client_tree.bind("<Double-1>", self.show_client_details)

        # Panel kanan untuk query dan hasil
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=4)

        # Query editor
        query_frame = ttk.LabelFrame(right_frame, text="SQL Query")
        query_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Toolbar untuk query editor
        query_toolbar = ttk.Frame(query_frame)
        query_toolbar.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        # Tombol untuk operasi umum
        ttk.Button(query_toolbar, text="Clear", command=lambda: self.query_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(query_toolbar, text="Load", command=self.load_query).pack(side=tk.LEFT, padx=2)
        ttk.Button(query_toolbar, text="Save", command=self.save_query).pack(side=tk.LEFT, padx=2)
        ttk.Button(query_toolbar, text="History", command=self.show_history).pack(side=tk.LEFT, padx=2)
        ttk.Separator(query_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y, pady=2)

        # Tambahkan template query sederhana
        ttk.Button(query_toolbar, text="SELECT Template",
                  command=lambda: self.insert_template("SELECT * FROM table_name WHERE condition")).pack(side=tk.LEFT, padx=2)
        ttk.Button(query_toolbar, text="INSERT Template",
                  command=lambda: self.insert_template("INSERT INTO table_name (col1, col2) VALUES (val1, val2)")).pack(side=tk.LEFT, padx=2)
        ttk.Button(query_toolbar, text="UPDATE Template",
                  command=lambda: self.insert_template("UPDATE table_name SET col1 = val1 WHERE condition")).pack(side=tk.LEFT, padx=2)

        self.query_text = scrolledtext.ScrolledText(query_frame, height=10, font=("Consolas", 10))
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

        # Toolbar untuk hasil
        results_toolbar = ttk.Frame(results_frame)
        results_toolbar.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        # Tombol untuk operasi tab hasil
        ttk.Button(results_toolbar, text="Close Current Tab",
                  command=self.close_current_tab).pack(side=tk.LEFT, padx=2)
        ttk.Button(results_toolbar, text="Close All Tabs",
                  command=self.close_all_tabs).pack(side=tk.LEFT, padx=2)
        ttk.Separator(results_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y, pady=2)
        ttk.Button(results_toolbar, text="Export Results",
                  command=self.export_results).pack(side=tk.LEFT, padx=2)

        self.results_notebook = ttk.Notebook(results_frame)
        self.results_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Log frame
        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill=tk.X, padx=10, pady=5)

        # Toolbar untuk log
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, side=tk.TOP, padx=2, pady=2)

        ttk.Button(log_toolbar, text="Clear Log",
                  command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_toolbar, text="Save Log",
                  command=self.save_log).pack(side=tk.LEFT, padx=2)

        # Toggle untuk auto-scroll
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_toolbar, text="Auto-scroll",
                       variable=self.autoscroll_var).pack(side=tk.RIGHT, padx=2)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)

        # Konfigurasi closing event
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        # Update UI setiap 1 detik
        self.update_ui()

    def configure_mssql_style(self):
        """Konfigurasi style untuk tampilan mirip MSSQL"""
        style = ttk.Style()

        # Warna dasar MSSQL
        bg_color = "#f0f0f0"
        header_bg = "#e1e1e1"
        selected_bg = "#d0d7e5"

        # Konfigurasi style untuk treeview
        style.configure("Treeview",
                      background=bg_color,
                      fieldbackground=bg_color,
                      foreground="black",
                      rowheight=24)

        style.configure("Treeview.Heading",
                      background=header_bg,
                      foreground="black",
                      font=("Segoe UI", 9, "bold"))

        style.map("Treeview",
                background=[("selected", selected_bg)],
                foreground=[("selected", "black")])

        # Styling untuk tab dan notebook
        style.configure("TNotebook", background=bg_color)
        style.configure("TNotebook.Tab", background=header_bg, padding=[10, 4])
        style.map("TNotebook.Tab",
                background=[("selected", bg_color)],
                foreground=[("selected", "black")])

        # Style untuk button
        style.configure("TButton",
                      background=header_bg,
                      foreground="black",
                      padding=4)

        # Style untuk label frame
        style.configure("TLabelframe",
                      background=bg_color)
        style.configure("TLabelframe.Label",
                      foreground="black",
                      font=("Segoe UI", 9, "bold"))

        # Style khusus untuk hasil query
        style.configure("ISQL.Treeview",
                      background="white",
                      fieldbackground="white",
                      font=("Consolas", 9))
        style.configure("ISQL.Treeview.Heading",
                      background="#e8e8e8",
                      font=("Segoe UI", 9, "bold"))
        style.map("ISQL.Treeview",
                background=[("selected", "#ccddff")],
                foreground=[("selected", "black")])

    def update_ui(self):
        """Update UI secara periodik"""
        self.update_client_list()
        self.root.after(1000, self.update_ui)

    def toggle_clients_panel(self):
        """Toggle tampilan panel client list"""
        self.client_collapsed.set(not self.client_collapsed.get())

        if self.client_collapsed.get():
            # Collapse panel
            self.client_tree_frame.pack_forget()
            self.toggle_clients_btn.config(text="▶")
        else:
            # Expand panel
            self.client_tree_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            self.toggle_clients_btn.config(text="▼")

    def update_client_list(self):
        """Update daftar client di UI"""
        # Clear treeview
        for item in self.client_tree.get_children():
            self.client_tree.delete(item)

        # Tambahkan client yang terhubung
        with self.lock:
            for client_id, client in self.clients.items():
                connection_status = "Connected" if client.is_connected else "Disconnected"

                # Calculate execution time if applicable
                execution_time = ""
                if client.query_start_time:
                    if client.query_end_time:
                        # Query completed, show total time
                        time_diff = client.query_end_time - client.query_start_time
                        execution_time = f"{time_diff:.2f}s"
                    else:
                        # Query still running, show elapsed time
                        time_diff = time.time() - client.query_start_time
                        execution_time = f"{time_diff:.2f}s"

                # Get database transfer status
                transfer_status = client.transfer_status
                if client.transfer_status == client.TRANSFER_IN_PROGRESS and client.file_size > 0:
                    # Show progress percentage
                    progress = min(100, int(client.received_size * 100 / client.file_size))
                    transfer_status = f"{progress}%"

                # Set tag based on query status
                if not client.is_connected:
                    tag = "disconnected"
                elif client.query_status == client.STATUS_IDLE:
                    tag = "idle"
                elif client.query_status == client.STATUS_WAITING:
                    tag = "waiting"
                elif client.query_status == client.STATUS_PROCESSING:
                    tag = "processing"
                elif client.query_status == client.STATUS_COMPLETED:
                    tag = "completed"
                elif client.query_status == client.STATUS_ERROR:
                    tag = "error"
                else:
                    tag = "connected"

                self.client_tree.insert("", tk.END, values=(
                    client.display_name,
                    connection_status,
                    client.query_status,
                    execution_time,
                    transfer_status
                ), tags=(tag,))

        # Configure tag colors
        self.client_tree.tag_configure("connected", foreground="green")
        self.client_tree.tag_configure("disconnected", foreground="red")
        self.client_tree.tag_configure("idle", foreground="green")
        self.client_tree.tag_configure("waiting", foreground="orange")
        self.client_tree.tag_configure("processing", foreground="blue")
        self.client_tree.tag_configure("completed", foreground="green")
        self.client_tree.tag_configure("error", foreground="red")

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

        # Auto-scroll jika diaktifkan
        if self.autoscroll_var.get():
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

            # Update tombol
            self.start_server_button.config(state=tk.DISABLED)
            self.stop_server_button.config(state=tk.NORMAL)

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

        # Update tombol
        self.start_server_button.config(state=tk.NORMAL)
        self.stop_server_button.config(state=tk.DISABLED)

        self.update_client_list()

    def accept_connections(self):
        """Thread untuk menerima koneksi dari client"""
        try:
            while self.running:
                try:
                    # Timeout kecil untuk socket accept, agar bisa cek self.running secara berkala
                    self.server_socket.settimeout(1.0)
                    client_socket, client_address = self.server_socket.accept()

                    # Set timeout yang lebih besar untuk operasi data transfer
                    client_socket.settimeout(self.default_socket_timeout)

                    # Set buffer size yang lebih besar
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)  # 256KB
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)  # 256KB

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
                    elif message.msg_type == NetworkMessage.TYPE_DB_INFO:
                        # Informasi file database yang akan dikirim
                        self.log(f"Menerima informasi file database dari {display_name}")
                        self.process_db_file_info(client, message.data)
                    elif message.msg_type == NetworkMessage.TYPE_DB_CHUNK:
                        # Chunk dari file database
                        self.process_db_file_chunk(client, message.data)
                    elif message.msg_type == NetworkMessage.TYPE_DB_COMPLETE:
                        # Notifikasi transfer file selesai
                        self.log(f"Transfer file database dari {display_name} selesai")
                        self.process_db_file_complete(client, message.data)
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

        # Update client status to completed
        client.query_end_time = time.time()
        if error:
            client.query_status = client.STATUS_ERROR
            client.last_error = error
        else:
            client.query_status = client.STATUS_COMPLETED

        # Update client list in UI
        self.root.after(0, self.update_client_list)

        # Debug info detail
        print("="*50)
        print(f"[SERVER] PROCESS_QUERY_RESULT dari {client.display_name}")
        print(f"Query: {query[:100]}...")
        print(f"Description: {description}")
        print(f"Result sets: {len(result)}")

        # Validasi dan perbaiki format hasil jika diperlukan
        validated_result = []
        for i, rs in enumerate(result):
            headers = rs.get('headers', [])
            rows = rs.get('rows', [])

            print(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
            if headers:
                print(f"  Headers: {headers}")
            if rows and len(rows) > 0:
                print(f"  First row type: {type(rows[0])}")
                if isinstance(rows[0], dict):
                    print(f"  First row keys: {list(rows[0].keys())}")
                    print(f"  First row values: {str(rows[0])[:200]}...")
                else:
                    print(f"  First row is not a dict: {str(rows[0])[:200]}...")

            # Pastikan headers ada dan valid
            if not headers and rows and len(rows) > 0 and isinstance(rows[0], dict):
                headers = list(rows[0].keys())
                print(f"  Headers terdeteksi dari rows: {headers}")

            # Pastikan rows dalam format yang benar
            validated_rows = []
            for row in rows:
                if isinstance(row, dict):
                    # Format sudah benar
                    validated_rows.append(row)
                elif isinstance(row, (list, tuple)):
                    # Konversi list/tuple ke dict
                    row_dict = {}
                    for j, header in enumerate(headers):
                        if j < len(row):
                            row_dict[header] = row[j]
                        else:
                            row_dict[header] = None
                    validated_rows.append(row_dict)
                else:
                    print(f"  WARNING: Format row tidak valid: {type(row)}")

            # Tambahkan result set yang sudah divalidasi
            validated_result.append({
                'headers': headers,
                'rows': validated_rows
            })

        print("="*50)

        self.log(f"Processing query result from {client.display_name}")
        self.log(f"Query: {query[:100]}...")
        self.log(f"Description: {description}")
        self.log(f"Result sets: {len(validated_result)}")
        for i, rs in enumerate(validated_result):
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

        # Create result tab on the UI thread with validated result
        self.root.after(0, self._create_result_tab, client, query, description, validated_result, error)

    def _create_result_tab(self, client, query, description, result, error):
        """Create result tab in UI thread"""
        try:
            print(f"[SERVER] Creating result tab in UI thread")
            print(f"[SERVER] Result data: {len(result)} result sets")

            # Verify result format
            for i, rs in enumerate(result):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])
                print(f"[SERVER] Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
                if headers:
                    print(f"[SERVER] Headers: {headers[:5]}{'...' if len(headers) > 5 else ''}")
                if rows and len(rows) > 0:
                    print(f"[SERVER] First row type: {type(rows[0])}")
                    if isinstance(rows[0], dict):
                        print(f"[SERVER] First row keys: {list(rows[0].keys())[:5]}{'...' if len(rows[0].keys()) > 5 else ''}")
            # Buat tab baru untuk hasil
            tab_title = f"Result - {client.display_name}"

            # Cek apakah sudah ada tab untuk client ini
            existing_tabs = self.results_notebook.tabs()

            # Jika tab sudah ada untuk client ini, buat tab baru dengan nama yang berbeda
            tab_count = 1
            base_title = tab_title
            while any(self.results_notebook.tab(tab_id, "text") == tab_title for tab_id in existing_tabs):
                tab_title = f"{base_title} ({tab_count})"
                tab_count += 1

            result_frame = ttk.Frame(self.results_notebook)
            self.results_notebook.add(result_frame, text=tab_title)
            self.results_notebook.select(result_frame)  # Aktifkan tab baru

            # Simpan query info sebagai atribut tab (tidak ditampilkan)
            result_frame.query_info = {
                'client': client.display_name,
                'database': client.db_info.get('name', 'Unknown'),
                'query': query,
                'executed': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

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
                total_rows = 0
                truncated = False

                for i, result_set in enumerate(result):
                    # Verifikasi data result set valid
                    headers = result_set.get('headers', [])
                    rows = result_set.get('rows', [])

                    total_rows += len(rows)

                    print(f"[SERVER] Processing result set {i+1}: {len(rows)} rows, headers: {headers}")

                    if not headers:
                        print(f"[SERVER] Result set {i+1} tidak memiliki headers, dilewati")
                        self.log(f"Result set {i+1} tidak memiliki headers, dilewati")
                        continue

                    result_frame_inner = ttk.LabelFrame(result_frame, text=f"Result Set {i+1}")
                    result_frame_inner.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

                    # Controls frame untuk toolbar
                    controls_frame = ttk.Frame(result_frame_inner)
                    controls_frame.pack(fill=tk.X, padx=5, pady=5)

                    # Tambahkan tombol untuk membuka di jendela baru - ini akan diatur nanti
                    open_window_button = ttk.Button(controls_frame, text="Open in New Window", width=20)
                    open_window_button.pack(side=tk.RIGHT, padx=5)

                    # Tambahkan search controls
                    search_frame = ttk.LabelFrame(controls_frame, text="Search")
                    search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    search_var = tk.StringVar()
                    search_column_var = tk.StringVar(value="All Columns")
                    search_status_var = tk.StringVar()

                    ttk.Entry(search_frame, textvariable=search_var, width=30).pack(side=tk.LEFT, padx=5, pady=2)

                    # Column selector
                    search_columns = ["All Columns"] + headers
                    ttk.Combobox(search_frame, textvariable=search_column_var, values=search_columns, width=15).pack(side=tk.LEFT, padx=5, pady=2)

                    # Search button
                    ttk.Button(search_frame, text="Search", command=lambda: search_tree()).pack(side=tk.LEFT, padx=5, pady=2)

                    # Search status
                    ttk.Label(search_frame, textvariable=search_status_var).pack(side=tk.LEFT, padx=5, pady=2)

                    # Pagination setup
                    if len(rows) > 100:
                        page_size = 100
                        truncated = True

                        page_var = tk.IntVar(value=1)
                        total_pages = (len(rows) + page_size - 1) // page_size

                        paging_frame = ttk.Frame(search_frame)
                        paging_frame.pack(side=tk.RIGHT, padx=10)

                        ttk.Label(paging_frame, text="Page:").pack(side=tk.LEFT)

                        # Prev button
                        ttk.Button(paging_frame, text="◀", width=2,
                                  command=lambda: page_var.set(max(1, page_var.get() - 1)) or show_page()).pack(side=tk.LEFT)

                        # Page indicator
                        page_label = ttk.Label(paging_frame, text=f"1/{total_pages}")
                        page_label.pack(side=tk.LEFT, padx=5)

                        # Next button
                        ttk.Button(paging_frame, text="▶", width=2,
                                  command=lambda: page_var.set(min(total_pages, page_var.get() + 1)) or show_page()).pack(side=tk.LEFT)

                        # Go to page
                        ttk.Button(paging_frame, text="Go", width=3,
                                  command=lambda: show_go_page_dialog()).pack(side=tk.LEFT, padx=5)

                        # Function to show specific page dialog
                        def show_go_page_dialog():
                            page = simpledialog.askinteger("Go to Page", f"Enter page number (1-{total_pages}):",
                                                         minvalue=1, maxvalue=total_pages)
                            if page:
                                page_var.set(page)
                                show_page()
                    else:
                        page_size = len(rows)
                        paging_frame = None

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
                        # Buat treeview dengan scrollbar
                        treeview_frame = ttk.Frame(tree_container)
                        treeview_frame.pack(fill=tk.BOTH, expand=True)

                        # Buat treeview untuk hasil dengan style mirip MSSQL
                        tree = ttk.Treeview(treeview_frame, columns=headers, show="headings", style="ISQL.Treeview")

                        # Tambahkan scrollbar vertikal
                        vsb = ttk.Scrollbar(treeview_frame, orient="vertical", command=tree.yview)
                        tree.configure(yscrollcommand=vsb.set)
                        vsb.pack(side=tk.RIGHT, fill=tk.Y)

                        # Tambahkan scrollbar horizontal
                        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
                        tree.configure(xscrollcommand=hsb.set)
                        hsb.pack(side=tk.BOTTOM, fill=tk.X)

                        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                        # Set header
                        for header in headers:
                            tree.heading(header, text=header, anchor=tk.W)
                            # Set lebar kolom berdasarkan konten
                            max_width = len(str(header)) * 10
                            for row_idx, row in enumerate(rows):
                                if row_idx >= 100:  # Hanya cek 100 baris pertama untuk efisiensi
                                    break
                                val = str(row.get(header, ""))
                                width = len(val) * 8
                                if width > max_width:
                                    max_width = width
                            tree.column(header, width=min(max_width, 300), stretch=True, anchor=tk.W)

                        # Sekarang kita dapat mengatur tombol open in new window
                        open_window_button.config(command=lambda t=tree, h=headers, r=rows: self.open_result_in_new_window(t, h, r))

                        # Fungsi untuk menampilkan semua data (tanpa paging)
                        def show_all_data():
                            # Hapus semua baris yang ada
                            for item in tree.get_children():
                                tree.delete(item)

                            # Tambahkan semua data
                            row_ids = []
                            for row in rows:
                                values = []
                                for header in headers:
                                    values.append(row.get(header, ""))
                                row_id = tree.insert("", tk.END, values=values)
                                row_ids.append(row_id)

                            return row_ids

                            # Reset search jika pencarian aktif
                            if search_var.get():
                                # Panggil fungsi search untuk meng-highlight hasil
                                search_tree()

                            return row_ids

                        # Menampilkan data awal
                        row_ids = show_all_data()

                        # Fungsi pencarian
                        def search_tree():
                            # Reset semua pengaturan sebelumnya
                            for row_id in tree.get_children():
                                tree.item(row_id, tags=())

                            search_text = search_var.get().strip().lower()
                            if not search_text:
                                search_status_var.set("")
                                return

                            search_col = search_column_var.get()
                            found_count = 0

                            for row_id in tree.get_children():
                                values = tree.item(row_id)['values']
                                found = False

                                if search_col == "All Columns":
                                    # Cari di semua kolom
                                    for value in values:
                                        if str(value).lower().find(search_text) >= 0:
                                            found = True
                                            break
                                else:
                                    # Cari di kolom spesifik
                                    col_idx = headers.index(search_col)
                                    if str(values[col_idx]).lower().find(search_text) >= 0:
                                        found = True

                                if found:
                                    tree.item(row_id, tags=('found',))
                                    found_count += 1

                            if found_count > 0:
                                search_status_var.set(f"Found: {found_count} rows")
                                tree.tag_configure('found', background='#FFFFCC')

                                # Auto-scroll ke hasil pertama
                                for row_id in tree.get_children():
                                    if 'found' in tree.item(row_id)['tags']:
                                        tree.see(row_id)
                                        break
                            else:
                                search_status_var.set("Not found")

                                # Jika tidak ditemukan di halaman saat ini, tanyakan untuk mencari di seluruh halaman
                                if paging_frame and len(rows) > page_size:
                                    if messagebox.askyesno("Search", "Pencarian tidak ditemukan di halaman ini. Cari di semua halaman?"):
                                        self.search_all_pages(tree, rows, headers, search_text, search_col)

                        # Tombol pencarian
                        ttk.Button(search_frame, text="Search", command=search_tree).pack(side=tk.LEFT, padx=5)
                        ttk.Button(search_frame, text="Clear",
                                command=lambda: [search_var.set(""), search_status_var.set(""),
                                              [tree.item(row_id, tags=()) for row_id in tree.get_children()]]
                                ).pack(side=tk.LEFT, padx=5)

                        # Pastikan search_entry tersedia sebelum binding
                        for child in search_frame.winfo_children():
                            if isinstance(child, ttk.Entry):
                                search_entry = child
                                search_entry.bind("<Return>", lambda event: search_tree())
                                break

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

                        # Total rows message
                        total_msg = f"{len(rows)} rows"
                        if truncated:
                            total_msg += f" (showing {page_size} per page)"

                        # Tambahkan label status dengan informasi client dan jumlah baris
                        status_label = ttk.Label(
                            status_frame,
                            text=f"{total_msg} | Database: {client.db_info.get('name', 'Unknown')} | {client.display_name}",
                            anchor=tk.W
                        )
                        status_label.pack(side=tk.LEFT, padx=5)

                        # Tambahkan timestamp dan link untuk view query
                        time_label = ttk.Label(
                            status_frame,
                            text=f"Executed: {datetime.datetime.now().strftime('%H:%M:%S')}",
                            anchor=tk.E
                        )
                        time_label.pack(side=tk.RIGHT, padx=5)

                        # Tambahkan tombol untuk view query
                        view_query_button = ttk.Button(
                            status_frame,
                            text="View Query",
                            command=lambda q=query: self.show_query_dialog(q)
                        )
                        view_query_button.pack(side=tk.RIGHT, padx=5)

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

                # Tampilkan peringatan jika hasil melebihi batas yang aman
                if total_rows > 50000:
                    messagebox.showwarning(
                        "Large Result Set",
                        f"Hasil query berisi {total_rows} baris yang bisa mempengaruhi performa aplikasi.\n\n"
                        f"Pertimbangkan untuk menambahkan batasan FIRST atau WHERE untuk mengurangi jumlah hasil."
                    )

                print(f"[SERVER] Hasil query berhasil ditampilkan dari {client.display_name}")
                self.log(f"Hasil query ditampilkan dari {client.display_name}")

        except Exception as e:
            print(f"[SERVER] ERROR saat membuat tab hasil: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"Error saat membuat tab hasil: {e}")

    def search_all_pages(self, tree, rows, headers, search_text, search_column):
        """Mencari teks di semua halaman dan menampilkan hasil yang ditemukan"""
        found_indices = []
        search_text = search_text.lower()

        # Cari di semua baris
        for i, row in enumerate(rows):
            found = False

            if search_column == "All Columns":
                for header in headers:
                    value = str(row.get(header, "")).lower()
                    if search_text in value:
                        found = True
                        break
            else:
                value = str(row.get(search_column, "")).lower()
                if search_text in value:
                    found = True

            if found:
                found_indices.append(i)

        if not found_indices:
            messagebox.showinfo("Search Results", "No matches found in any page.")
            return

        # Tampilkan dialog hasil pencarian
        result_dialog = tk.Toplevel(self.root)
        result_dialog.title(f"Search Results: '{search_text}'")
        result_dialog.geometry("600x400")

        ttk.Label(result_dialog, text=f"Found {len(found_indices)} matches across all pages:").pack(padx=10, pady=5)

        # Treeview untuk hasil
        result_tree = ttk.Treeview(result_dialog, columns=("Page", "Row", "Content"), show="headings")
        result_tree.heading("Page", text="Page")
        result_tree.heading("Row", text="Row")
        result_tree.heading("Content", text="Content")
        result_tree.column("Page", width=50)
        result_tree.column("Row", width=50)
        result_tree.column("Content", width=450)

        # Scrollbar
        scrollbar = ttk.Scrollbar(result_dialog, orient=tk.VERTICAL, command=result_tree.yview)
        result_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        result_tree.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Tambahkan hasil
        page_size = 5000
        for idx in found_indices:
            page_num = idx // page_size + 1
            row_num = idx % page_size + 1

            # Ambil nilai yang cocok untuk ditampilkan
            row_data = rows[idx]
            if search_column == "All Columns":
                # Cari kolom mana yang mengandung teks pencarian
                matching_content = []
                for header in headers:
                    value = str(row_data.get(header, ""))
                    if search_text in value.lower():
                        matching_content.append(f"{header}: {value}")
                content = " | ".join(matching_content)
            else:
                content = str(row_data.get(search_column, ""))

            result_tree.insert("", tk.END, values=(page_num, row_num, content))

        # Tombol untuk menuju ke halaman yang berisi hasil
        def go_to_result():
            selected = result_tree.selection()
            if not selected:
                return

            values = result_tree.item(selected[0])["values"]
            page_num = int(values[0])

            # Set halaman di treeview utama dan highlight baris yang dipilih
            # Ini perlu diimplementasikan dengan callback ke fungsi pergantian halaman

            result_dialog.destroy()

            # Tampilkan pesan
            messagebox.showinfo("Navigation", f"Please go to page {page_num} to see this result.")

        ttk.Button(result_dialog, text="Go to Result", command=go_to_result).pack(side=tk.LEFT, padx=10, pady=10)
        ttk.Button(result_dialog, text="Close", command=result_dialog.destroy).pack(side=tk.RIGHT, padx=10, pady=10)

    def send_query(self):
        """Kirim query ke client yang dipilih"""
        query = self.query_text.get("1.0", tk.END).strip()

        if not query:
            messagebox.showwarning("Query Empty", "Please enter a SQL query")
            return

        # Periksa apakah query terlalu kompleks
        estimated_complexity = self.estimate_query_complexity(query)
        if estimated_complexity > 5:  # Skala 1-10 untuk kompleksitas
            # Tampilkan dialog konfirmasi dengan peringatan lebih jelas
            if not messagebox.askyesno("Complex Query Warning",
                             "Query ini terdeteksi kompleks dan mungkin mengembalikan dataset besar.\n\n"
                             "Periksa query Anda untuk memastikan:\n"
                             "1. Tambahkan klausa WHERE untuk membatasi hasil\n"
                             "2. Hanya pilih kolom yang benar-benar diperlukan\n"
                             "3. Batasi jumlah baris dengan FIRST/ROWS\n\n"
                             "Tetap lanjutkan?",
                             icon="warning"):
                return

        # Tambahkan batasan FIRST/ROWS jika belum ada
        if not self.has_row_limit(query) and query.strip().upper().startswith("SELECT"):
            result = messagebox.askyesnocancel(
                "Row Limit",
                f"Query tidak memiliki batasan jumlah baris. Tambahkan batasan {self.max_result_rows} baris?\n\n"
                f"Ya = Tambahkan batasan\nTidak = Kirim tanpa batasan (risiko koneksi terputus)\nBatal = Batalkan query",
                icon="warning"
            )

            if result is None:  # Cancel was clicked
                return
            elif result:  # Yes was clicked
                query = self.add_row_limit(query, self.max_result_rows)
                self.query_text.delete("1.0", tk.END)
                self.query_text.insert("1.0", query)

        target = self.target_var.get()

        # Tampilkan dialog konfirmasi untuk query yang mungkin berbahaya
        if self.is_potentially_dangerous(query):
            if not messagebox.askyesno("Warning",
                                     "Query ini berpotensi mengubah data (INSERT/UPDATE/DELETE).\n\nApakah Anda yakin ingin melanjutkan?",
                                     icon="warning"):
                return

        # Tambahkan ke history
        self.query_history.append({
            'query': query,
            'target': target,
            'timestamp': datetime.datetime.now().isoformat()
        })

        # Tampilkan indikator loading
        self.show_loading_indicator("Mengirim dan menunggu hasil query...")

        # Kirim ke client yang dipilih dalam thread terpisah untuk mencegah UI freeze
        threading.Thread(target=self._send_query_thread, args=(query, target), daemon=True).start()

    def _send_query_thread(self, query, target):
        """Mengirim query dalam thread terpisah untuk mencegah UI freeze"""
        try:
            # Add query to queue instead of executing immediately
            if target == "All Clients":
                # Add all connected clients to queue
                with self.lock:
                    for client_id, client in self.clients.items():
                        if client.is_connected:
                            # Reset client status
                            client.query_status = client.STATUS_WAITING
                            client.current_query = query
                            client.query_start_time = None
                            client.query_end_time = None
                            client.last_error = None

                            # Add to queue
                            self.query_queue.put((client, query))
                            self.log(f"Added {client.display_name} to query queue")
            else:
                # Extract client_id dari target
                client_id = target.split("(")[-1].split(")")[0]

                with self.lock:
                    if client_id in self.clients:
                        client = self.clients[client_id]
                        if client.is_connected:
                            # Reset client status
                            client.query_status = client.STATUS_WAITING
                            client.current_query = query
                            client.query_start_time = None
                            client.query_end_time = None
                            client.last_error = None

                            # Add to queue
                            self.query_queue.put((client, query))
                            self.log(f"Added {client.display_name} to query queue")
                        else:
                            self.root.after(0, lambda: messagebox.showwarning("Client Disconnected",
                                                                          f"Client {client.display_name} tidak terhubung"))
                    else:
                        self.root.after(0, lambda: messagebox.showwarning("Client Not Found",
                                                                      f"Client {client_id} tidak ditemukan"))

            # Start processing the queue if not already processing
            self.start_query_queue_processing()

        finally:
            # Update client list to show waiting status
            self.root.after(0, self.update_client_list)

            # Keep loading indicator until all queries are processed
            if self.query_queue.empty() and not self.is_processing_queue:
                self.root.after(0, self.hide_loading_indicator)

    def start_query_queue_processing(self):
        """Mulai thread untuk memproses antrian query secara berurutan"""
        if not self.is_processing_queue:
            self.is_processing_queue = True
            self.query_thread = threading.Thread(target=self.process_query_queue, daemon=True)
            self.query_thread.start()
            self.log("Started query queue processing")

    def process_query_queue(self):
        """Proses antrian query secara berurutan"""
        try:
            while not self.query_queue.empty():
                # Get next client and query from queue
                client, query = self.query_queue.get()

                # Check if client is still connected
                if not client.is_connected:
                    self.log(f"Skipping {client.display_name} - disconnected")
                    client.query_status = client.STATUS_ERROR
                    client.last_error = "Client disconnected"
                    client.query_end_time = time.time()
                    self.root.after(0, self.update_client_list)
                    self.query_queue.task_done()
                    continue

                # Update client status to processing
                client.query_status = client.STATUS_PROCESSING
                client.query_start_time = time.time()
                self.root.after(0, self.update_client_list)

                # Execute query for this client
                try:
                    self.log(f"Processing query for {client.display_name}")
                    self.send_query_to_client(client, query)

                    # Wait a bit to allow the client to start processing
                    # This helps prevent overwhelming the server with responses
                    time.sleep(0.5)

                except Exception as e:
                    self.log(f"Error processing query for {client.display_name}: {e}")
                    client.query_status = client.STATUS_ERROR
                    client.last_error = str(e)
                    client.query_end_time = time.time()

                # Update UI
                self.root.after(0, self.update_client_list)

                # Mark task as done
                self.query_queue.task_done()
        finally:
            self.is_processing_queue = False
            self.log("Query queue processing completed")
            # Hide loading indicator if needed
            if self.query_queue.empty():
                self.root.after(0, self.hide_loading_indicator)

    def show_loading_indicator(self, message="Loading..."):
        """Tampilkan indikator loading"""
        # Buat jendela loading jika belum ada
        try:
            if hasattr(self, 'loading_window') and self.loading_window.winfo_exists():
                # Update pesan jika jendela sudah ada
                if hasattr(self, 'loading_label'):
                    self.loading_label.config(text=message)
                return

            self.loading_window = tk.Toplevel(self.root)
            self.loading_window.title("Loading")
            self.loading_window.transient(self.root)
            self.loading_window.geometry("300x100")
            self.loading_window.resizable(False, False)

            # Posisi di tengah layar relatif terhadap parent
            self.loading_window.update_idletasks()
            width = self.loading_window.winfo_width()
            height = self.loading_window.winfo_height()
            parent_x = self.root.winfo_rootx()
            parent_y = self.root.winfo_rooty()
            parent_width = self.root.winfo_width()
            parent_height = self.root.winfo_height()
            x = parent_x + (parent_width // 2) - (width // 2)
            y = parent_y + (parent_height // 2) - (height // 2)
            self.loading_window.geometry(f"+{x}+{y}")

            # Label dan progress bar
            self.loading_label = ttk.Label(self.loading_window, text=message)
            self.loading_label.pack(pady=(15, 5))

            self.loading_progress = ttk.Progressbar(self.loading_window, mode="indeterminate", length=250)
            self.loading_progress.pack(pady=10)
            self.loading_progress.start(10)

            # Tombol untuk batalkan operasi (jika perlu)
            # ttk.Button(self.loading_window, text="Cancel", command=self.cancel_operation).pack(pady=5)

            # Nonaktifkan tombol close
            self.loading_window.protocol("WM_DELETE_WINDOW", lambda: None)
        except Exception as e:
            print(f"Error showing loading indicator: {e}")

    def hide_loading_indicator(self):
        """Sembunyikan indikator loading"""
        try:
            if hasattr(self, 'loading_window') and self.loading_window.winfo_exists():
                self.loading_window.destroy()
                delattr(self, 'loading_window')
        except Exception as e:
            print(f"Error hiding loading indicator: {e}")

    def estimate_query_complexity(self, query):
        """Estimasi kompleksitas query untuk mendeteksi query yang mungkin berat"""
        query = query.upper()
        complexity = 0

        # 1. Jumlah tabel yang terlibat (joins)
        complexity += query.count(" JOIN ") * 2

        # 2. Kompleksitas WHERE
        if " WHERE " in query:
            where_clause = query.split(" WHERE ")[1].split(" ORDER BY ")[0].split(" GROUP BY ")[0]
            complexity += where_clause.count(" AND ") + where_clause.count(" OR ")

            # Jika tidak ada kondisi pembatas yang cukup ketat
            if " = " not in where_clause and " < " not in where_clause and " > " not in where_clause:
                complexity += 3
        else:
            # Query tanpa WHERE lebih berbahaya
            complexity += 5

        # 3. Banyaknya kolom yang dipilih
        if "SELECT * " in query:
            # Memilih semua kolom
            complexity += 3
        else:
            # Hitung jumlah kolom
            select_clause = query.split("SELECT ")[1].split(" FROM ")[0]
            complexity += min(select_clause.count(",") / 5, 2)  # Max 2 poin untuk banyak kolom

        # 4. Agregasi dan grouping
        if " GROUP BY " in query:
            complexity += 2

        # 5. Subquery dan kompleksitas lainnya
        complexity += query.count("(SELECT") * 2

        # Normalisasi ke skala 1-10
        return min(max(complexity, 1), 10)

    def send_query_to_client(self, client, query):
        """Kirim query ke client tertentu"""
        try:
            # Mendeteksi apakah query adalah SELECT tanpa batasan baris
            if not self.has_row_limit(query) and query.strip().upper().startswith("SELECT"):
                # Auto-batasi query dengan FIRST untuk menghindari dataset terlalu besar
                original_query = query
                query = self.add_row_limit(query, self.max_result_rows)
                self.log(f"Query otomatis dibatasi menjadi {self.max_result_rows} baris")

                # Simpan versi asli dan batasan untuk referensi
                query_message = NetworkMessage(NetworkMessage.TYPE_QUERY, {
                    'query': query,
                    'description': 'user_query',
                    'original_query': original_query,
                    'row_limit': self.max_result_rows
                }, client.client_id)
            else:
                query_message = NetworkMessage(NetworkMessage.TYPE_QUERY, {
                    'query': query,
                    'description': 'user_query'
                }, client.client_id)

            # Tingkatkan timeout socket hanya untuk pengiriman query yang mungkin besar
            previous_timeout = client.socket.gettimeout()
            client.socket.settimeout(self.default_socket_timeout)

            try:
                send_message(client.socket, query_message)
                self.log(f"Query dikirim ke {client.display_name}")
                # Update client status to processing
                client.query_status = client.STATUS_PROCESSING
                client.query_start_time = time.time()
                self.root.after(0, self.update_client_list)
            finally:
                # Kembalikan timeout ke nilai sebelumnya
                client.socket.settimeout(previous_timeout)
        except Exception as e:
            self.log(f"Error saat mengirim query ke {client.display_name}: {e}")
            client.query_status = client.STATUS_ERROR
            client.last_error = str(e)
            client.query_end_time = time.time()
            self.root.after(0, self.update_client_list)
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

    def show_selected_client_details(self):
        """Tampilkan detail client yang dipilih dari tombol detail"""
        selected = self.client_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a client first")
            return

        selected_item = selected[0]
        item_data = self.client_tree.item(selected_item)
        client_name = item_data['values'][0]

        # Cari client berdasarkan nama
        with self.lock:
            for client_id, client in self.clients.items():
                if client.display_name == client_name:
                    self.show_client_details_window(client)
                    return

        messagebox.showinfo("Not Found", "Client not found")

    def show_client_details_window(self, client):
        """Tampilkan window detail client"""
        # Buat dialog untuk menampilkan detail
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"Client Detail: {client.display_name}")
        detail_window.geometry("600x500")

        # Frame untuk info client
        info_frame = ttk.LabelFrame(detail_window, text="Client Information")
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(info_frame, text=f"ID: {client.client_id}").pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(info_frame, text=f"Name: {client.display_name}").pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(info_frame, text=f"IP: {client.address[0]}:{client.address[1]}").pack(anchor=tk.W, padx=5, pady=2)
        status_text = "Connected" if client.is_connected else "Disconnected"
        status_label = ttk.Label(info_frame, text=f"Status: {status_text}")
        status_label.pack(anchor=tk.W, padx=5, pady=2)
        if client.is_connected:
            status_label.config(foreground="green")
        else:
            status_label.config(foreground="red")
        ttk.Label(info_frame, text=f"Last Seen: {datetime.datetime.fromtimestamp(client.last_seen).strftime('%Y-%m-%d %H:%M:%S')}").pack(anchor=tk.W, padx=5, pady=2)

        # Query Status Frame
        query_frame = ttk.LabelFrame(detail_window, text="Query Status")
        query_frame.pack(fill=tk.X, padx=10, pady=5)

        # Status label with color
        status_text = client.query_status
        query_status_label = ttk.Label(query_frame, text=f"Current Status: {status_text}")
        query_status_label.pack(anchor=tk.W, padx=5, pady=2)

        # Set color based on status
        if status_text == client.STATUS_IDLE:
            query_status_label.config(foreground="green")
        elif status_text == client.STATUS_WAITING:
            query_status_label.config(foreground="orange")
        elif status_text == client.STATUS_PROCESSING:
            query_status_label.config(foreground="blue")
        elif status_text == client.STATUS_COMPLETED:
            query_status_label.config(foreground="green")
        elif status_text == client.STATUS_ERROR:
            query_status_label.config(foreground="red")

        # Show execution time if applicable
        if client.query_start_time:
            if client.query_end_time:
                # Query completed, show total time
                time_diff = client.query_end_time - client.query_start_time
                ttk.Label(query_frame, text=f"Execution Time: {time_diff:.2f} seconds").pack(anchor=tk.W, padx=5, pady=2)
            else:
                # Query still running, show elapsed time
                time_diff = time.time() - client.query_start_time
                ttk.Label(query_frame, text=f"Elapsed Time: {time_diff:.2f} seconds (running)").pack(anchor=tk.W, padx=5, pady=2)

        # Show current query if available
        if client.current_query:
            query_text_frame = ttk.LabelFrame(query_frame, text="Current/Last Query")
            query_text_frame.pack(fill=tk.X, padx=5, pady=5)

            query_text = scrolledtext.ScrolledText(query_text_frame, height=4, width=50, wrap=tk.WORD)
            query_text.insert(tk.END, client.current_query)
            query_text.config(state=tk.DISABLED)
            query_text.pack(fill=tk.X, padx=5, pady=5)

        # Show error if applicable
        if client.last_error:
            error_frame = ttk.LabelFrame(query_frame, text="Error")
            error_frame.pack(fill=tk.X, padx=5, pady=5)

            error_text = scrolledtext.ScrolledText(error_frame, height=3, width=50, wrap=tk.WORD)
            error_text.insert(tk.END, client.last_error)
            error_text.config(state=tk.DISABLED)
            error_text.pack(fill=tk.X, padx=5, pady=5)

        # Database Transfer Status Frame
        transfer_frame = ttk.LabelFrame(detail_window, text="Database Transfer Status")
        transfer_frame.pack(fill=tk.X, padx=10, pady=5)

        # Status label with color
        transfer_status_text = client.transfer_status
        transfer_status_label = ttk.Label(transfer_frame, text=f"Current Status: {transfer_status_text}")
        transfer_status_label.pack(anchor=tk.W, padx=5, pady=2)

        # Set color based on status
        if transfer_status_text == client.TRANSFER_NONE or transfer_status_text == client.TRANSFER_PENDING:
            transfer_status_label.config(foreground="black")
        elif transfer_status_text == client.TRANSFER_IN_PROGRESS:
            transfer_status_label.config(foreground="blue")
        elif transfer_status_text == client.TRANSFER_COMPLETED:
            transfer_status_label.config(foreground="green")
        elif transfer_status_text == client.TRANSFER_FAILED:
            transfer_status_label.config(foreground="red")

        # Show file details if available
        if client.file_name:
            ttk.Label(transfer_frame, text=f"File: {client.file_name}").pack(anchor=tk.W, padx=5, pady=2)

        # Show progress if in progress
        if client.transfer_status == client.TRANSFER_IN_PROGRESS and client.file_size > 0:
            progress = min(100, int(client.received_size * 100 / client.file_size))
            ttk.Label(transfer_frame, text=f"Progress: {progress}% ({client.received_size}/{client.file_size} bytes)").pack(anchor=tk.W, padx=5, pady=2)

        # Show transfer time if completed
        if client.transfer_status == client.TRANSFER_COMPLETED and client.transfer_start_time and client.transfer_end_time:
            transfer_time = client.transfer_end_time - client.transfer_start_time
            transfer_speed = client.received_size / transfer_time if transfer_time > 0 else 0
            ttk.Label(transfer_frame, text=f"Transfer Time: {transfer_time:.2f} seconds").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Label(transfer_frame, text=f"Transfer Speed: {transfer_speed:.2f} bytes/sec").pack(anchor=tk.W, padx=5, pady=2)

        # Show error if applicable
        if client.transfer_error:
            error_frame = ttk.LabelFrame(transfer_frame, text="Transfer Error")
            error_frame.pack(fill=tk.X, padx=5, pady=5)

            error_text = scrolledtext.ScrolledText(error_frame, height=3, width=50, wrap=tk.WORD)
            error_text.insert(tk.END, client.transfer_error)
            error_text.config(state=tk.DISABLED)
            error_text.pack(fill=tk.X, padx=5, pady=5)

        # Button to request database file
        if client.is_connected:
            def request_db():
                if self.request_database_file(client):
                    self.log(f"Requested database file from {client.display_name}")
                    detail_window.destroy()  # Close the window
                    self.show_client_details_window(client)  # Reopen with updated info
                else:
                    self.log(f"Failed to request database file from {client.display_name}")

            ttk.Button(transfer_frame, text="Request Database File",
                      command=request_db).pack(anchor=tk.CENTER, padx=5, pady=5)

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

        # Button frame
        button_frame = ttk.Frame(detail_window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        # Reset status button
        def reset_status():
            client.query_status = client.STATUS_IDLE
            client.current_query = None
            client.query_start_time = None
            client.query_end_time = None
            client.last_error = None
            self.update_client_list()
            detail_window.destroy()
            self.show_client_details_window(client)

        ttk.Button(button_frame, text="Reset Status",
                  command=reset_status).pack(side=tk.LEFT, padx=5, pady=5)

        # Close button
        ttk.Button(button_frame, text="Close",
                  command=detail_window.destroy).pack(side=tk.RIGHT, padx=5, pady=5)

    def show_client_details(self, event):
        """Handler untuk double-click di client tree"""
        item = self.client_tree.identify_row(event.y)
        if not item:
            return

        item_data = self.client_tree.item(item)
        client_name = item_data['values'][0]

        # Cari client berdasarkan nama
        with self.lock:
            for client_id, client in self.clients.items():
                if client.display_name == client_name:
                    self.show_client_details_window(client)
                    return

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
        try:
            # Mengatur penanganan eksepsi di thread utama
            self.root.report_callback_exception = self.handle_exception
            self.root.mainloop()
        except Exception as e:
            self.log(f"Uncaught exception in main thread: {e}")
            import traceback
            traceback.print_exc()

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions"""
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"Uncaught exception: {error_msg}")
        self.log(f"Error: {exc_value}")

        # Coba untuk menampilkan dialog error
        try:
            messagebox.showerror("Application Error",
                             f"An error occurred:\n{exc_value}\n\nThe application will continue running.")
        except:
            pass  # Jika dialog juga gagal, setidaknya error tercatat di log

    def insert_template(self, template):
        """Masukkan template query ke editor"""
        self.query_text.insert(tk.INSERT, template)

    def close_current_tab(self):
        """Tutup tab hasil yang aktif"""
        current = self.results_notebook.select()
        if current:
            self.results_notebook.forget(current)

    def close_all_tabs(self):
        """Tutup semua tab hasil"""
        for tab_id in self.results_notebook.tabs():
            self.results_notebook.forget(tab_id)

    def export_results(self):
        """Export hasil query ke file"""
        current = self.results_notebook.select()
        if not current:
            messagebox.showinfo("Export", "Tidak ada tab hasil yang aktif")
            return

        import tkinter.filedialog as filedialog

        filename = filedialog.asksaveasfilename(
            title="Export Results",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
            defaultextension=".csv"
        )

        if not filename:
            return

        try:
            # Simpan hasil yang ada di tab aktif ke file
            # Ini adalah implementasi sederhana, bisa disesuaikan untuk format CSV yang lebih baik
            with open(filename, 'w') as f:
                # Temukan treeview di tab aktif
                result_frame = self.results_notebook.nametowidget(current)

                # Cari treeview dalam frame
                treeviews = []
                def find_treeviews(widget):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Treeview):
                            treeviews.append(child)
                        find_treeviews(child)

                find_treeviews(result_frame)

                if not treeviews:
                    messagebox.showinfo("Export", "Tidak ada data yang bisa diekspor")
                    return

                # Ambil treeview pertama yang ditemukan
                tree = treeviews[0]

                # Tulis header
                headers = [tree.heading(col)["text"] for col in tree["columns"]]
                f.write(",".join(headers) + "\n")

                # Tulis data
                for item_id in tree.get_children():
                    values = tree.item(item_id)["values"]
                    f.write(",".join([str(v) for v in values]) + "\n")

            self.log(f"Hasil berhasil diekspor ke {filename}")
            messagebox.showinfo("Export", f"Hasil berhasil diekspor ke {filename}")
        except Exception as e:
            self.log(f"Error saat mengekspor hasil: {e}")
            messagebox.showerror("Export Error", f"Gagal mengekspor hasil: {e}")

    def clear_log(self):
        """Bersihkan log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def save_log(self):
        """Simpan log ke file"""
        import tkinter.filedialog as filedialog

        filename = filedialog.asksaveasfilename(
            title="Save Log",
            filetypes=[("Text files", "*.txt"), ("Log files", "*.log"), ("All files", "*.*")],
            defaultextension=".log"
        )

        if not filename:
            return

        try:
            with open(filename, 'w') as f:
                f.write(self.log_text.get("1.0", tk.END))

            messagebox.showinfo("Save Log", f"Log berhasil disimpan ke {filename}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Gagal menyimpan log: {e}")

    def process_db_file_info(self, client, info_data):
        """Process database file information from client"""
        try:
            # Extract file information
            file_name = info_data.get('file_name')
            file_size = info_data.get('file_size', 0)

            if not file_name:
                self.log(f"Error: No file name provided by {client.display_name}")
                return

            # Create database directory if it doesn't exist
            db_dir = os.path.join(current_dir, "databases")
            os.makedirs(db_dir, exist_ok=True)

            # Create client directory
            client_dir = os.path.join(db_dir, client.client_id)
            os.makedirs(client_dir, exist_ok=True)

            # Set file path
            file_path = os.path.join(client_dir, file_name)

            # Update client status
            client.transfer_status = client.TRANSFER_PENDING
            client.file_name = file_name
            client.file_size = file_size
            client.received_size = 0
            client.chunks_received = 0
            client.total_chunks = 0
            client.transfer_start_time = time.time()
            client.transfer_error = None

            # Create empty file
            with open(file_path, 'wb') as f:
                pass

            self.log(f"Preparing to receive database file from {client.display_name}: {file_name} ({file_size} bytes)")
            self.update_client_list()

        except Exception as e:
            self.log(f"Error processing database file info from {client.display_name}: {e}")
            client.transfer_status = client.TRANSFER_FAILED
            client.transfer_error = str(e)
            self.update_client_list()

    def process_db_file_chunk(self, client, chunk_data):
        """Process database file chunk from client"""
        try:
            # Extract chunk information
            chunk_number = chunk_data.get('chunk_number', 0)
            total_chunks = chunk_data.get('total_chunks', 0)
            chunk_size = chunk_data.get('chunk_size', 0)
            encoded_data = chunk_data.get('data', '')

            if not encoded_data:
                self.log(f"Error: Empty chunk data from {client.display_name}")
                return

            # Update client status if this is the first chunk
            if chunk_number == 0:
                client.transfer_status = client.TRANSFER_IN_PROGRESS
                client.total_chunks = total_chunks

            # Decode chunk data
            import base64
            chunk_data = base64.b64decode(encoded_data)

            # Get file path
            db_dir = os.path.join(current_dir, "databases")
            client_dir = os.path.join(db_dir, client.client_id)
            file_path = os.path.join(client_dir, client.file_name)

            # Append chunk to file
            with open(file_path, 'ab') as f:
                f.write(chunk_data)

            # Update client status
            client.received_size += chunk_size
            client.chunks_received += 1

            # Log progress every 10 chunks or for the first and last chunk
            if chunk_number % 10 == 0 or chunk_number == 0 or chunk_number == total_chunks - 1:
                progress = min(100, int(client.received_size * 100 / client.file_size))
                self.log(f"Receiving database file from {client.display_name}: {progress}% ({client.received_size}/{client.file_size} bytes)")
                self.update_client_list()

        except Exception as e:
            self.log(f"Error processing database file chunk from {client.display_name}: {e}")
            client.transfer_status = client.TRANSFER_FAILED
            client.transfer_error = str(e)
            self.update_client_list()

    def process_db_file_complete(self, client, complete_data):
        """Process database file transfer completion"""
        try:
            # Extract completion information
            file_name = complete_data.get('file_name')
            file_size = complete_data.get('file_size', 0)
            chunks_sent = complete_data.get('chunks_sent', 0)

            # Get file path
            db_dir = os.path.join(current_dir, "databases")
            client_dir = os.path.join(db_dir, client.client_id)
            file_path = os.path.join(client_dir, client.file_name)

            # Verify file size
            actual_size = os.path.getsize(file_path)

            if actual_size != file_size:
                self.log(f"Warning: File size mismatch for {file_name} from {client.display_name}. Expected: {file_size}, Actual: {actual_size}")

            # Update client status
            client.transfer_status = client.TRANSFER_COMPLETED
            client.transfer_end_time = time.time()
            client.received_size = actual_size

            # Calculate transfer time and speed
            transfer_time = client.transfer_end_time - client.transfer_start_time
            transfer_speed = actual_size / transfer_time if transfer_time > 0 else 0

            self.log(f"Database file transfer completed from {client.display_name}: {file_name}")
            self.log(f"Transfer details: {actual_size} bytes in {transfer_time:.2f} seconds ({transfer_speed:.2f} bytes/sec)")

            # Update UI
            self.update_client_list()

        except Exception as e:
            self.log(f"Error processing database file completion from {client.display_name}: {e}")
            client.transfer_status = client.TRANSFER_FAILED
            client.transfer_error = str(e)
            self.update_client_list()

    def request_database_file(self, client):
        """Request database file from client"""
        if not client or not client.is_connected:
            self.log("Cannot request database file: Client not connected")
            return False

        try:
            # Create request message
            request_data = {
                'timestamp': datetime.datetime.now().isoformat()
            }

            request_message = NetworkMessage(
                NetworkMessage.TYPE_DB_REQUEST,
                request_data,
                client.client_id
            )

            # Send request to client
            if send_message(client.socket, request_message):
                self.log(f"Database file request sent to {client.display_name}")
                return True
            else:
                self.log(f"Failed to send database file request to {client.display_name}")
                return False

        except Exception as e:
            self.log(f"Error requesting database file from {client.display_name}: {e}")
            return False

    def request_all_database_files(self):
        """Request database files from all connected clients"""
        with self.lock:
            connected_clients = [client for client in self.clients.values() if client.is_connected]

        if not connected_clients:
            messagebox.showinfo("No Clients", "No connected clients to request database files from.")
            return

        success_count = 0
        for client in connected_clients:
            if self.request_database_file(client):
                success_count += 1

        self.log(f"Requested database files from {success_count}/{len(connected_clients)} clients")

    def request_selected_database_file(self):
        """Request database file from selected client"""
        selected = self.client_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select a client first")
            return

        selected_item = selected[0]
        item_data = self.client_tree.item(selected_item)
        client_name = item_data['values'][0]

        # Find client by name
        with self.lock:
            for client_id, client in self.clients.items():
                if client.display_name == client_name:
                    if not client.is_connected:
                        messagebox.showwarning("Client Disconnected", f"Client {client_name} is not connected")
                        return

                    if self.request_database_file(client):
                        self.log(f"Requested database file from {client_name}")
                    else:
                        self.log(f"Failed to request database file from {client_name}")
                    return

        messagebox.showinfo("Not Found", "Client not found")

    def show_query_dialog(self, query):
        """Tampilkan dialog berisi query yang dieksekusi"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Query")
        dialog.geometry("600x400")

        # Query text
        query_text = scrolledtext.ScrolledText(dialog, font=("Consolas", 10))
        query_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        query_text.insert(tk.END, query)
        query_text.config(state=tk.DISABLED)

        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        # Tombol copy
        def copy_to_clipboard():
            dialog.clipboard_clear()
            dialog.clipboard_append(query)
            messagebox.showinfo("Copy", "Query copied to clipboard")

        ttk.Button(button_frame, text="Copy to Clipboard", command=copy_to_clipboard).pack(side=tk.LEFT, padx=5)

        # Tombol use query
        def use_query():
            self.query_text.delete("1.0", tk.END)
            self.query_text.insert(tk.END, query)
            dialog.destroy()

        ttk.Button(button_frame, text="Use This Query", command=use_query).pack(side=tk.LEFT, padx=5)

        # Tombol close
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def has_row_limit(self, query):
        """Cek apakah query sudah memiliki batasan jumlah baris"""
        # Deteksi pola FIRST X atau ROWS X
        upper_query = query.upper()
        return " FIRST " in upper_query or " ROWS " in upper_query or " LIMIT " in upper_query or " TOP " in upper_query

    def add_row_limit(self, query, limit):
        """Tambahkan batasan jumlah baris ke query"""
        # Mengasumsikan format Firebird SQL
        query = query.strip()

        # Jaga-jaga untuk query yang mengandung multiple statements
        if ";" in query:
            parts = query.split(";")
            parts = [self.add_row_limit(part.strip(), limit) for part in parts if part.strip()]
            return ";".join(parts)

        # Penanganan untuk SELECT DISTINCT dan kasus lainnya
        if query.upper().startswith("SELECT "):
            parts = query.split(" ", 1)
            rest = parts[1]

            if rest.upper().startswith("DISTINCT "):
                # Format: SELECT DISTINCT -> SELECT FIRST X DISTINCT
                rest_parts = rest.split(" ", 1)
                return f"SELECT FIRST {limit} {rest_parts[0]} {rest_parts[1]}"
            else:
                # Format: SELECT ... -> SELECT FIRST X ...
                return f"SELECT FIRST {limit} {rest}"

        return query  # Return query asli jika bukan SELECT

    def is_potentially_dangerous(self, query):
        """Cek apakah query berpotensi mengubah data"""
        upper_query = query.upper().strip()

        # Cek multiple statements
        if ";" in upper_query:
            # Jika ada satu statement yang berbahaya, seluruh query dianggap berbahaya
            return any(self.is_potentially_dangerous(part) for part in upper_query.split(";") if part.strip())

        # DML dan DDL statements yang berbahaya
        dangerous_keywords = [
            "INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP ", "CREATE ",
            "TRUNCATE ", "GRANT ", "REVOKE ", "EXECUTE BLOCK", "EXECUTE PROCEDURE"
        ]

        for keyword in dangerous_keywords:
            if upper_query.startswith(keyword) or f" {keyword}" in upper_query:
                return True

        return False

    def open_result_in_new_window(self, parent_tree, headers, all_rows, page_size=100):
        """Buka hasil query di jendela baru dengan lebih banyak ruang"""
        window = tk.Toplevel(self.root)
        window.title("Query Results")
        window.geometry("1000x600")

        # Buat frame utama
        main_frame = ttk.Frame(window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Buat frame untuk treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Buat frame untuk scrollbar
        scroll_frame = ttk.Frame(tree_frame)
        scroll_frame.pack(fill=tk.BOTH, expand=True)

        # Buat treeview dengan scrollbar
        tree = ttk.Treeview(scroll_frame, columns=headers, show="headings", style="ISQL.Treeview")

        # Tambahkan scrollbar vertikal
        v_scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=v_scrollbar.set)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Tambahkan scrollbar horizontal
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=h_scrollbar.set)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Set header dan kolom
        try:
            for header in headers:
                tree.heading(header, text=header, anchor=tk.W)
                # Gunakan lebar kolom dari tree asal jika tersedia
                if parent_tree:
                    width = parent_tree.column(header, "width")
                    tree.column(header, width=width, stretch=tk.YES, anchor=tk.W)
                else:
                    # Default jika parent_tree tidak tersedia
                    max_width = len(str(header)) * 10
                    for row_idx, row in enumerate(all_rows):
                        if row_idx >= 100:  # Hanya cek 100 baris pertama untuk efisiensi
                            break
                        val = str(row.get(header, ""))
                        width = len(val) * 8
                        if width > max_width:
                            max_width = width
                    tree.column(header, width=min(max_width, 300), stretch=tk.YES, anchor=tk.W)
        except Exception as e:
            print(f"Error setting column width: {e}")
            # Fallback ke lebar default
            for header in headers:
                tree.column(header, width=150, stretch=tk.YES, anchor=tk.W)

        # Paging
        total_rows = len(all_rows)
        total_pages = (total_rows + page_size - 1) // page_size
        page_var = tk.IntVar(value=1)

        # Controls frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        # Search frame
        search_frame = ttk.LabelFrame(controls_frame, text="Search")
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        # Dropdown untuk memilih kolom pencarian
        search_column_var = tk.StringVar(value="All Columns")
        search_columns = ["All Columns"] + headers
        search_column_dropdown = ttk.Combobox(search_frame, textvariable=search_column_var, values=search_columns, width=15)
        search_column_dropdown.pack(side=tk.LEFT, padx=5, pady=5)

        # Status variable untuk hasil pencarian
        status_var = tk.StringVar(value=f"Total rows: {total_rows}")

        # Search button dan fungsi pencarian
        def search_in_window():
            search_text = search_var.get().strip().lower()
            if not search_text:
                status_var.set(f"Total rows: {total_rows}")
                return

            search_col = search_column_var.get()
            found_count = 0

            # Reset semua highlight
            for row_id in tree.get_children():
                tree.item(row_id, tags=())

            # Cari di semua baris yang ditampilkan
            for row_id in tree.get_children():
                values = tree.item(row_id, "values")

                found = False
                if search_col == "All Columns":
                    # Cari di semua kolom
                    for val in values:
                        if search_text in str(val).lower():
                            found = True
                            found_count += 1
                            break
                else:
                    # Cari di kolom tertentu
                    col_idx = headers.index(search_col)
                    if col_idx < len(values) and search_text in str(values[col_idx]).lower():
                        found = True
                        found_count += 1

                if found:
                    tree.item(row_id, tags=("found",))

            # Set style untuk highlight hasil pencarian
            tree.tag_configure("found", background="#ffffcc")

            # Update status
            status_var.set(f"Total rows: {total_rows} | Found: {found_count} matches")

        search_button = ttk.Button(search_frame, text="Search", command=search_in_window)
        search_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Clear button
        clear_button = ttk.Button(search_frame, text="Clear",
                            command=lambda: [search_var.set(""), status_var.set(f"Total rows: {total_rows}"),
                                          [tree.item(row_id, tags=()) for row_id in tree.get_children()]])
        clear_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Bind enter key pada search entry
        search_entry.bind("<Return>", lambda e: search_in_window())

        # Paging frame
        paging_frame = ttk.LabelFrame(controls_frame, text="Page Navigation")
        paging_frame.pack(side=tk.RIGHT, padx=5)

        # Fungsi untuk menampilkan halaman
        def show_page():
            # Hapus semua baris yang ada
            for item in tree.get_children():
                tree.delete(item)

            # Hitung rentang data untuk halaman ini
            current_page = page_var.get()
            start_idx = (current_page - 1) * page_size
            end_idx = min(start_idx + page_size, total_rows)

            # Update label halaman
            page_label.config(text=f"{current_page}/{total_pages}")

            # Tambahkan data untuk halaman ini
            for idx in range(start_idx, end_idx):
                row = all_rows[idx]
                values = []
                for header in headers:
                    values.append(row.get(header, ""))
                tree.insert("", tk.END, values=values)

            # Update status
            status_var.set(f"Total rows: {total_rows} | Showing rows {start_idx+1}-{end_idx}")

        # Dialog untuk menuju ke halaman tertentu
        def show_go_page_dialog():
            page = simpledialog.askinteger("Go to Page", f"Enter page number (1-{total_pages}):",
                                         minvalue=1, maxvalue=total_pages)
            if page:
                page_var.set(page)
                show_page()

        # Navigation buttons
        ttk.Button(paging_frame, text="◀◀", width=3,
                 command=lambda: page_var.set(1) or show_page()).pack(side=tk.LEFT, padx=2)

        ttk.Button(paging_frame, text="◀", width=2,
                 command=lambda: page_var.set(max(1, page_var.get() - 1)) or show_page()).pack(side=tk.LEFT, padx=2)

        # Page indicator
        page_label = ttk.Label(paging_frame, text=f"1/{total_pages}")
        page_label.pack(side=tk.LEFT, padx=5)

        # Next buttons
        ttk.Button(paging_frame, text="▶", width=2,
                 command=lambda: page_var.set(min(total_pages, page_var.get() + 1)) or show_page()).pack(side=tk.LEFT, padx=2)

        ttk.Button(paging_frame, text="▶▶", width=3,
                 command=lambda: page_var.set(total_pages) or show_page()).pack(side=tk.LEFT, padx=2)

        # Go to page
        ttk.Button(paging_frame, text="Go", width=3,
                 command=lambda: show_go_page_dialog()).pack(side=tk.LEFT, padx=5)

        # Status bar
        status_bar = ttk.Label(main_frame, textvariable=status_var, anchor=tk.W)
        status_bar.pack(fill=tk.X, padx=5, pady=5)

        # Tampilkan halaman pertama
        show_page()

        # Fokus ke jendela baru
        window.focus_force()

        return window

if __name__ == "__main__":
    app = ServerApp()
    app.run()