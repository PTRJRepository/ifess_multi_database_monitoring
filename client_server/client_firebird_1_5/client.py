import os
import sys
import socket
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import platform
import datetime
import uuid
import random
import subprocess

# Tambahkan path untuk mengimpor dari direktori common
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from common.network import NetworkMessage, send_message, receive_message, DEFAULT_PORT
from common.db_utils import FirebirdConnector

# Path konfigurasi
CONFIG_FILE = os.path.join(current_dir, "client_config.json")

class ClientApp:
    """Aplikasi client yang terhubung ke server dan menjalankan query di database lokal"""
    def __init__(self):
        self.socket = None
        self.server_address = None
        self.server_port = DEFAULT_PORT
        self.client_id = f"client_{uuid.uuid4().hex[:8]}"
        self.display_name = f"FDB-Client-{platform.node()}"
        self.connected = False
        self.running = True
        self.db_connector = None
        self.receive_thread = None
        self.last_result = None
        self.query_history = []

        # Parameter untuk auto-reconnect
        self.auto_reconnect = False
        self.reconnect_interval = 5  # detik
        self.reconnect_thread = None
        self.is_connecting = False

        # Load konfigurasi jika ada
        self.load_config()

        # Inisialisasi UI
        self.init_ui()

        # Coba koneksi otomatis ke database jika ada di konfigurasi
        self.root.after(500, self.auto_connect_to_database)

        # Memulai auto-reconnect jika diaktifkan
        if self.auto_reconnect and self.server_address:
            self.start_auto_reconnect()

    def load_config(self):
        """Memuat konfigurasi dari file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)

                # Load server config
                self.server_address = config.get('server_address')
                self.server_port = config.get('server_port', DEFAULT_PORT)
                self.auto_reconnect = config.get('auto_reconnect', False)
                self.reconnect_interval = config.get('reconnect_interval', 5)

                # Load client config
                if 'client_id' in config:
                    self.client_id = config['client_id']
                if 'display_name' in config:
                    self.display_name = config['display_name']

                # Load database config
                db_config = config.get('database', {})
                if db_config and 'path' in db_config and os.path.exists(db_config['path']):
                    print(f"Debug: Found database config: {db_config['path']}")
                    try:
                        self.db_connector = FirebirdConnector(
                            db_path=db_config['path'],
                            username=db_config.get('username', 'SYSDBA'),
                            password=db_config.get('password', 'masterkey'),
                            isql_path=db_config.get('isql_path')
                        )
                        print("Debug: Database connector initialized from config")
                    except Exception as e:
                        print(f"Error initializing database from config: {e}")
        except Exception as e:
            print(f"Error loading config: {e}")

    def save_config(self):
        """Menyimpan konfigurasi ke file"""
        try:
            config = {
                'server_address': self.server_address,
                'server_port': self.server_port,
                'auto_reconnect': self.auto_reconnect,
                'reconnect_interval': self.reconnect_interval,
                'client_id': self.client_id_var.get() or self.client_id,
                'display_name': self.display_name_var.get() or self.display_name,
                'database': {}
            }

            # Simpan konfigurasi database jika ada
            if self.db_connector:
                config['database'] = {
                    'path': self.db_connector.db_path,
                    'username': self.db_connector.username,
                    'password': self.db_connector.password,
                    'isql_path': self.db_connector.isql_path
                }

            # Pastikan direktori ada
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

            # Tulis ke file
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"Config saved to {CONFIG_FILE}")
        except Exception as e:
            print(f"Error saving config: {e}")

    def init_ui(self):
        """Inisialisasi antarmuka pengguna"""
        self.root = tk.Tk()
        self.root.title("Firebird Query Client")
        self.root.geometry("800x600")

        # Menu bar
        menubar = tk.Menu(self.root)
        conn_menu = tk.Menu(menubar, tearoff=0)
        conn_menu.add_command(label="Connect to Server", command=self.connect_to_server_from_ui)
        conn_menu.add_command(label="Disconnect", command=self.disconnect_from_server)
        conn_menu.add_separator()
        conn_menu.add_command(label="Exit", command=self.exit_app)
        menubar.add_cascade(label="Connection", menu=conn_menu)

        db_menu = tk.Menu(menubar, tearoff=0)
        db_menu.add_command(label="Select Database", command=self.select_database)
        db_menu.add_command(label="Test Connection", command=self.test_db_connection)
        menubar.add_cascade(label="Database", menu=db_menu)

        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="Save Configuration", command=self.save_config)
        config_menu.add_command(label="Test Query", command=self.run_test_query)
        config_menu.add_separator()
        config_menu.add_command(label="Set ISQL Path", command=self.set_isql_path)
        config_menu.add_command(label="Test ISQL Directly", command=lambda: self.test_isql_directly(None, show_dialog=True))
        config_menu.add_command(label="Diagnose Connection", command=self.diagnose_connection)
        menubar.add_cascade(label="Config", menu=config_menu)

        self.root.config(menu=menubar)

        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Connection status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status")
        status_frame.pack(fill=tk.X, padx=5, pady=5)

        # Server connection frame dengan input fields
        server_frame = ttk.Frame(status_frame)
        server_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(server_frame, text="Server: ").pack(side=tk.LEFT)
        self.server_status = ttk.Label(server_frame, text="Disconnected")
        self.server_status.pack(side=tk.LEFT)

        # Input server
        ttk.Label(server_frame, text="Host:").pack(side=tk.LEFT, padx=(10, 2))
        self.server_address_var = tk.StringVar(value=self.server_address or "localhost")
        server_entry = ttk.Entry(server_frame, textvariable=self.server_address_var, width=15)
        server_entry.pack(side=tk.LEFT)

        ttk.Label(server_frame, text="Port:").pack(side=tk.LEFT, padx=(5, 2))
        self.server_port_var = tk.StringVar(value=str(self.server_port))
        port_entry = ttk.Entry(server_frame, textvariable=self.server_port_var, width=6)
        port_entry.pack(side=tk.LEFT)

        # Auto-reconnect checkbox
        self.auto_reconnect_var = tk.BooleanVar(value=self.auto_reconnect)
        auto_reconnect_check = ttk.Checkbutton(server_frame, text="Auto-reconnect",
                                             variable=self.auto_reconnect_var,
                                             command=self.toggle_auto_reconnect)
        auto_reconnect_check.pack(side=tk.LEFT, padx=(10, 0))

        self.connect_button = ttk.Button(server_frame, text="Connect", command=self.connect_to_server_from_ui)
        self.connect_button.pack(side=tk.RIGHT)

        # Database connection status
        db_frame = ttk.Frame(status_frame)
        db_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(db_frame, text="Database: ").pack(side=tk.LEFT)
        self.db_status = ttk.Label(db_frame, text="Not Selected")
        self.db_status.pack(side=tk.LEFT)

        # Loading indicator
        self.loading_var = tk.StringVar(value="")
        self.loading_label = ttk.Label(db_frame, textvariable=self.loading_var)
        self.loading_label.pack(side=tk.LEFT, padx=10)

        self.select_db_button = ttk.Button(db_frame, text="Select Database", command=self.select_database)
        self.select_db_button.pack(side=tk.RIGHT)

        # Client ID & Name
        client_frame = ttk.Frame(status_frame)
        client_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(client_frame, text="Client ID: ").pack(side=tk.LEFT)
        self.client_id_var = tk.StringVar(value=self.client_id)
        client_id_entry = ttk.Entry(client_frame, textvariable=self.client_id_var, state="readonly", width=20)
        client_id_entry.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(client_frame, text="Display Name: ").pack(side=tk.LEFT)
        self.display_name_var = tk.StringVar(value=self.display_name)
        display_name_entry = ttk.Entry(client_frame, textvariable=self.display_name_var, width=30)
        display_name_entry.pack(side=tk.LEFT)

        # Notebook for logs and results
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # SQL Query Editor Tab
        query_editor_frame = ttk.Frame(notebook)
        notebook.add(query_editor_frame, text="SQL Query Editor")

        # Split the query editor frame into top (editor) and bottom (results)
        query_paned = ttk.PanedWindow(query_editor_frame, orient=tk.VERTICAL)
        query_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Top frame for query editor
        editor_frame = ttk.LabelFrame(query_paned, text="SQL Query")
        query_paned.add(editor_frame, weight=40)

        # Editor toolbar
        editor_toolbar = ttk.Frame(editor_frame)
        editor_toolbar.pack(fill=tk.X, padx=5, pady=2)

        # Execute button
        execute_btn = ttk.Button(editor_toolbar, text="Execute Query", command=self.execute_editor_query)
        execute_btn.pack(side=tk.LEFT, padx=2)

        # Clear button
        clear_btn = ttk.Button(editor_toolbar, text="Clear Editor", command=self.clear_editor)
        clear_btn.pack(side=tk.LEFT, padx=2)

        # Save and load query buttons
        save_query_btn = ttk.Button(editor_toolbar, text="Save Query", command=self.save_editor_query)
        save_query_btn.pack(side=tk.LEFT, padx=2)

        load_query_btn = ttk.Button(editor_toolbar, text="Load Query", command=self.load_editor_query)
        load_query_btn.pack(side=tk.LEFT, padx=2)

        # Connection options
        ttk.Separator(editor_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)

        # Use localhost option
        self.editor_localhost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(editor_toolbar, text="Use localhost", variable=self.editor_localhost_var).pack(side=tk.LEFT, padx=2)

        # Limit results option
        ttk.Label(editor_toolbar, text="Limit results:").pack(side=tk.LEFT, padx=(5, 0))
        self.limit_var = tk.StringVar(value="100")
        limit_entry = ttk.Entry(editor_toolbar, textvariable=self.limit_var, width=5)
        limit_entry.pack(side=tk.LEFT, padx=2)

        # Query editor
        self.query_editor = scrolledtext.ScrolledText(editor_frame, height=10, font=("Consolas", 10))
        self.query_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Default query
        default_query = """-- Write your SQL query here
-- Example: SELECT * FROM GWSCANNERDATA07 WHERE ID <= 10

SELECT FIRST 5 * FROM GWSCANNERDATA07"""
        self.query_editor.insert(tk.END, default_query)

        # Bottom frame for results
        results_frame = ttk.LabelFrame(query_paned, text="Query Results")
        query_paned.add(results_frame, weight=60)

        # Results toolbar
        results_toolbar = ttk.Frame(results_frame)
        results_toolbar.pack(fill=tk.X, padx=5, pady=2)

        # Status label
        self.query_status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(results_toolbar, textvariable=self.query_status_var)
        status_label.pack(side=tk.LEFT, padx=2)

        # Export results button
        export_btn = ttk.Button(results_toolbar, text="Export Results", command=self.export_results)
        export_btn.pack(side=tk.RIGHT, padx=2)

        # Results display
        self.query_results = scrolledtext.ScrolledText(results_frame, height=15, font=("Consolas", 10))
        self.query_results.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.query_results.config(state=tk.DISABLED)

        # Log Tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Log")

        # Log toolbar
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(log_toolbar, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_toolbar, text="Save Log", command=self.save_log).pack(side=tk.LEFT, padx=2)

        # Add auto-scroll option
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_toolbar, text="Auto-scroll", variable=self.autoscroll_var).pack(side=tk.RIGHT, padx=2)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)

        # Query History Tab
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="Query History")

        # History toolbar
        history_toolbar = ttk.Frame(history_frame)
        history_toolbar.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(history_toolbar, text="Clear History", command=self.clear_history).pack(side=tk.LEFT, padx=2)

        self.history_tree = ttk.Treeview(history_frame, columns=("Timestamp", "Query", "Status"), show="headings")
        self.history_tree.heading("Timestamp", text="Timestamp")
        self.history_tree.heading("Query", text="Query")
        self.history_tree.heading("Status", text="Status")
        self.history_tree.column("Timestamp", width=150)
        self.history_tree.column("Query", width=450)
        self.history_tree.column("Status", width=100)
        self.history_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Add vertical scrollbar to history
        history_vsb = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_vsb.set)
        history_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5, side=tk.LEFT)

        # Last Result Tab (if needed)
        result_frame = ttk.Frame(notebook)
        notebook.add(result_frame, text="Last Result")

        self.result_text = scrolledtext.ScrolledText(result_frame, height=10, font=("Consolas", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.result_text.config(state=tk.DISABLED)

        # Konfigurasi closing event
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        # Update UI setiap 1 detik
        self.update_ui()

    def toggle_auto_reconnect(self):
        """Toggle status auto-reconnect"""
        self.auto_reconnect = self.auto_reconnect_var.get()

        if self.auto_reconnect and not self.connected and self.server_address:
            self.start_auto_reconnect()
        elif not self.auto_reconnect and self.reconnect_thread:
            # Stop reconnect thread
            self.auto_reconnect = False

    def start_auto_reconnect(self):
        """Memulai thread untuk auto-reconnect"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return

        self.auto_reconnect = True
        self.reconnect_thread = threading.Thread(target=self.auto_reconnect_loop)
        self.reconnect_thread.daemon = True
        self.reconnect_thread.start()
        self.log("Auto-reconnect diaktifkan")

    def auto_reconnect_loop(self):
        """Loop untuk mencoba auto-reconnect ke server"""
        while self.running and self.auto_reconnect and not self.connected:
            if not self.is_connecting:
                address = self.server_address_var.get().strip()
                try:
                    port = int(self.server_port_var.get().strip())
                except:
                    port = DEFAULT_PORT

                self.log(f"Mencoba auto-reconnect ke {address}:{port}...")
                self.connect_to_server(address, port)

            # Tunggu interval
            for i in range(self.reconnect_interval):
                if not self.running or not self.auto_reconnect or self.connected:
                    break
                time.sleep(1)

    def update_loading_indicator(self):
        """Update indikator loading"""
        animation = ["|", "/", "-", "\\"]
        i = 0

        while self.is_connecting and self.running:
            self.loading_var.set(f"Connecting... {animation[i]}")
            i = (i + 1) % len(animation)
            time.sleep(0.2)

        self.loading_var.set("")

    def update_ui(self):
        """Update antarmuka pengguna secara periodik"""
        if self.connected:
            self.server_status.config(text=f"Connected to {self.server_address}:{self.server_port}")
            self.connect_button.config(text="Disconnect", command=self.disconnect_from_server)
        else:
            self.server_status.config(text="Disconnected")
            self.connect_button.config(text="Connect", command=self.connect_to_server_from_ui)

        if self.db_connector:
            self.db_status.config(text=f"Connected: {os.path.basename(self.db_connector.db_path)}")
            self.select_db_button.config(text="Change Database")
        else:
            self.db_status.config(text="Not Selected")
            self.select_db_button.config(text="Select Database")

        # Schedule next update
        self.root.after(1000, self.update_ui)

    def log(self, message):
        """Tambahkan pesan ke log"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        if self.autoscroll_var.get():
            self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        print(log_message, end="")

        # Save log to file for persistence
        self.append_to_log_file(log_message)

    def connect_to_server_from_ui(self):
        """Menghubungkan ke server dari input UI"""
        if self.connected:
            self.disconnect_from_server()
            return

        address = self.server_address_var.get().strip()
        port_str = self.server_port_var.get().strip()

        if not address:
            messagebox.showwarning("Input Error", "Server address is required")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("Input Error", "Port must be a number")
            return

        # Hubungkan ke server
        self.connect_to_server(address, port)

    def connect_to_server(self, address, port, auto_reconnect=False):
        """Terhubung ke server"""
        if self.connected:
            if not auto_reconnect:
                messagebox.showinfo("Already Connected", "Already connected to server. Please disconnect first.")
            return

        if self.is_connecting:
            return

        self.is_connecting = True

        # Mulai indikator loading
        loading_thread = threading.Thread(target=self.update_loading_indicator)
        loading_thread.daemon = True
        loading_thread.start()

        try:
            # Buat socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)  # Tingkatkan timeout menjadi 10 detik
            self.socket.connect((address, port))

            # Update status
            self.server_address = address
            self.server_port = port
            self.connected = True

            # Daftarkan client ke server
            self.register_to_server()

            # Mulai thread untuk menerima pesan
            self.receive_thread = threading.Thread(target=self.receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()

            self.log(f"Terhubung ke server: {address}:{port}")

            # Simpan konfigurasi
            self.save_config()
        except Exception as e:
            self.log(f"Error saat terhubung ke server: {e}")
            if not auto_reconnect:
                messagebox.showerror("Connection Error", f"Tidak dapat terhubung ke server: {e}")

            # Reset status
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
        finally:
            self.is_connecting = False

    def auto_connect_to_database(self):
        """Mencoba terhubung otomatis ke database dari konfigurasi"""
        if self.db_connector:
            try:
                # Cek apakah database ada
                if not os.path.exists(self.db_connector.db_path):
                    self.log(f"File database tidak ditemukan: {self.db_connector.db_path}")
                    self.db_connector = None
                    return

                # Cek apakah ISQL ada
                if not os.path.exists(self.db_connector.isql_path):
                    self.log(f"File ISQL tidak ditemukan: {self.db_connector.isql_path}")
                    # Tanyakan ke user untuk memilih ISQL
                    isql_path = filedialog.askopenfilename(
                        title="ISQL tidak ditemukan. Pilih lokasi ISQL.exe",
                        filetypes=[("ISQL Executable", "isql.exe"), ("All Files", "*.*")]
                    )

                    if not isql_path:
                        self.log("User membatalkan pemilihan ISQL. Database tidak terhubung.")
                        self.db_connector = None
                        return

                    if not os.path.exists(isql_path):
                        self.log(f"File ISQL tidak ditemukan: {isql_path}")
                        self.db_connector = None
                        return

                    # Update path ISQL
                    self.db_connector.isql_path = isql_path
                    self.log(f"ISQL path diperbarui: {isql_path}")

                    # Simpan konfigurasi baru
                    self.save_config()

                # Coba connect ke database
                if self.db_connector.test_connection():
                    self.log(f"Berhasil terhubung ke database: {os.path.basename(self.db_connector.db_path)}")
                else:
                    self.log("Gagal terhubung ke database dari konfigurasi")
                    self.db_connector = None
            except Exception as e:
                self.log(f"Error saat auto-connect ke database: {e}")
                self.db_connector = None

        # Jika sukses terhubung ke database, dan auto-reconnect diaktifkan,
        # coba terhubung ke server
        if self.db_connector and self.auto_reconnect and self.server_address and not self.connected:
            self.start_auto_reconnect()

    def register_to_server(self):
        """Mendaftarkan client ke server"""
        if not self.connected or not self.socket:
            return

        try:
            # Persiapkan data registrasi
            display_name = self.display_name_var.get() or self.display_name
            client_id = self.client_id_var.get() or self.client_id

            db_info = {}
            if self.db_connector:
                db_info = {
                    'path': self.db_connector.db_path,
                    'name': os.path.basename(self.db_connector.db_path)
                }

            register_data = {
                'display_name': display_name,
                'db_info': db_info,
                'platform': platform.system(),
                'hostname': platform.node(),
                'timestamp': datetime.datetime.now().isoformat()
            }

            # Kirim pesan registrasi
            register_message = NetworkMessage(NetworkMessage.TYPE_REGISTER, register_data, client_id)

            # Pastikan kirim pesan registrasi berhasil
            success = send_message(self.socket, register_message)

            if success:
                self.log(f"Terhubung ke server: {self.server_address}:{self.server_port}")
            else:
                self.log("Gagal mengirim data registrasi ke server")
                self.disconnect_from_server()
        except Exception as e:
            self.log(f"Error saat mendaftarkan client: {e}")
            self.disconnect_from_server()

    def disconnect_from_server(self):
        """Putuskan koneksi dari server"""
        if not self.connected:
            messagebox.showinfo("Not Connected", "Not connected to any server.")
            return

        try:
            self.connected = False
            if self.socket:
                self.socket.close()
                self.socket = None

            self.log("Terputus dari server")

            # Mulai auto-reconnect jika diaktifkan
            if self.auto_reconnect:
                self.start_auto_reconnect()
        except Exception as e:
            self.log(f"Error saat memutuskan koneksi: {e}")

    def receive_messages(self):
        """Thread untuk menerima pesan dari server"""
        try:
            while self.running and self.connected:
                try:
                    # Set timeout untuk socket
                    if self.socket:
                        self.socket.settimeout(10.0)  # Tingkatkan timeout menjadi 10 detik
                    else:
                        break

                    # Terima pesan
                    message = receive_message(self.socket)

                    if not message:
                        # Koneksi terputus
                        break

                    # Proses pesan
                    if message.msg_type == NetworkMessage.TYPE_PING:
                        # Balas ping
                        self.send_pong()
                    elif message.msg_type == NetworkMessage.TYPE_QUERY:
                        # Eksekusi query
                        self.execute_query(message.data)
                except socket.timeout:
                    # Log timeout dan coba kirim ping untuk mengecek koneksi
                    self.log("Socket timeout, mencoba kirim heartbeat...")
                    try:
                        self.send_pong()
                    except:
                        self.log("Gagal mengirim heartbeat, koneksi terputus")
                        break
                    continue
                except ConnectionError as ce:
                    self.log(f"Connection error: {ce}")
                    break
                except Exception as e:
                    self.log(f"Error saat menerima pesan: {e}")
                    break

            # Koneksi terputus
            if self.connected:
                self.log("Koneksi ke server terputus")
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None

                # Mulai auto-reconnect jika diaktifkan
                if self.auto_reconnect:
                    self.start_auto_reconnect()
        except Exception as e:
            self.log(f"Error di thread receive_messages: {e}")
        finally:
            self.connected = False

            # Mulai auto-reconnect jika diaktifkan
            if self.auto_reconnect:
                self.start_auto_reconnect()

    def send_pong(self):
        """Kirim respons pong ke server"""
        if not self.connected or not self.socket:
            return

        try:
            pong_message = NetworkMessage(NetworkMessage.TYPE_PONG, {}, self.client_id_var.get() or self.client_id)
            send_message(self.socket, pong_message)
        except Exception as e:
            self.log(f"Error sending pong: {e}")

    def execute_query(self, query_data):
        """Eksekusi query dari server"""
        query = query_data.get('query', '')
        description = query_data.get('description', '')

        print("="*50)
        print(f"EXECUTE QUERY: Menerima permintaan eksekusi query")
        print(f"Query: {query}")
        print(f"Description: {description}")
        print("="*50)

        if not query:
            print("ERROR: Query kosong")
            self.send_error_result("Query kosong", query_data)
            return

        if not self.db_connector:
            print("ERROR: Database tidak terpilih")
            self.send_error_result("Database tidak terpilih", query_data)
            return

        # Pastikan path database masih valid
        if not os.path.exists(self.db_connector.db_path):
            print(f"ERROR: File database tidak ditemukan: {self.db_connector.db_path}")
            self.send_error_result(f"File database tidak ditemukan: {self.db_connector.db_path}", query_data)
            return

        self.log(f"Menerima query: {query}")

        # Tambahkan ke history
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_item = (timestamp, query, "Running")
        self.history_tree.insert("", 0, values=history_item)

        try:
            # Eksekusi query
            print(f"DEBUG: Mengeksekusi query via db_connector...")
            result = self.db_connector.execute_query(query)
            print(f"DEBUG: Query berhasil dieksekusi")

            # Debug info
            self.log(f"Query berhasil: {len(result)} result sets ditemukan")
            for i, rs in enumerate(result):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])
                self.log(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
                if len(rows) > 0:
                    self.log(f"  Sample first row: {list(rows[0].values())[:3]}...")

                print(f"DEBUG: Result set {i+1} details:")
                print(f"  Headers: {headers}")
                print(f"  Rows: {len(rows)}")
                if rows and len(rows) > 0:
                    print(f"  Sample row data: {str(rows[0])[:200]}...")

            # Update history
            for item in self.history_tree.get_children():
                values = self.history_tree.item(item, 'values')
                if values[0] == timestamp and values[1] == query:
                    self.history_tree.item(item, values=(timestamp, query, "Success"))
                    break

            # Kirim hasil ke server
            print("DEBUG: Mengirim hasil ke server...")
            self.send_query_result(query, result, description)

            # Simpan hasil terakhir
            self.last_result = result
            self.update_result_display(result)

            self.log("Query berhasil dieksekusi")
        except Exception as e:
            error_message = str(e)
            print(f"ERROR saat eksekusi query: {error_message}")
            import traceback
            traceback.print_exc()

            # Update history
            for item in self.history_tree.get_children():
                values = self.history_tree.item(item, 'values')
                if values[0] == timestamp and values[1] == query:
                    self.history_tree.item(item, values=(timestamp, query, "Error"))
                    break

            self.log(f"Error saat eksekusi query: {error_message}")
            self.send_error_result(error_message, query_data)

    def send_query_result(self, query, result, description):
        """Kirim hasil query ke server"""
        if not self.connected or not self.socket:
            print("DEBUG: Tidak dapat mengirim hasil - tidak terhubung ke server")
            return

        try:
            # Debug info tentang data yang akan dikirim
            print("="*50)
            print("SEND QUERY RESULT: Mempersiapkan pengiriman hasil query")
            print(f"Query: {query[:100]}...")
            print(f"Result sets: {len(result)}")

            # Verifikasi format hasil sebelum dikirim
            validated_result = []
            for i, rs in enumerate(result):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])

                # Pastikan headers ada dan valid
                if not headers:
                    print(f"WARNING: Result set {i+1} tidak memiliki headers, mencoba deteksi dari rows")
                    if rows and len(rows) > 0 and isinstance(rows[0], dict):
                        headers = list(rows[0].keys())
                        print(f"  Headers terdeteksi: {headers}")

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
                        print(f"WARNING: Format row tidak valid: {type(row)}")

                # Tambahkan result set yang sudah divalidasi
                validated_result.append({
                    'headers': headers,
                    'rows': validated_rows
                })

                print(f"Result set {i+1}:")
                print(f"  Headers ({len(headers)}): {headers}")
                print(f"  Rows: {len(validated_rows)}")
                if validated_rows and len(validated_rows) > 0:
                    print(f"  Sample row: {str(validated_rows[0])[:200]}...")

            result_data = {
                'query': query,
                'description': description,
                'result': validated_result,
                'timestamp': datetime.datetime.now().isoformat()
            }

            result_message = NetworkMessage(
                NetworkMessage.TYPE_RESULT,
                result_data,
                self.client_id_var.get() or self.client_id
            )

            print(f"DEBUG: Mengirim pesan hasil query...")
            success = send_message(self.socket, result_message)
            if success:
                print("DEBUG: Hasil query berhasil dikirim ke server")
                self.log("Hasil query berhasil dikirim ke server")
            else:
                print("DEBUG: Gagal mengirim hasil query ke server")
                self.log("Gagal mengirim hasil query ke server")
            print("="*50)
        except Exception as e:
            print(f"ERROR saat mengirim hasil query: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"Error saat mengirim hasil query: {e}")

    def send_error_result(self, error_message, query_data):
        """Kirim pesan error ke server"""
        if not self.connected or not self.socket:
            return

        try:
            error_data = {
                'query': query_data.get('query', ''),
                'description': query_data.get('description', ''),
                'error': error_message,
                'timestamp': datetime.datetime.now().isoformat()
            }

            error_message = NetworkMessage(
                NetworkMessage.TYPE_ERROR,
                error_data,
                self.client_id_var.get() or self.client_id
            )

            send_message(self.socket, error_message)
        except Exception as e:
            self.log(f"Error saat mengirim pesan error: {e}")

    def update_result_display(self, result):
        """Update tampilan hasil query"""
        if not result:
            return

        # Format hasil untuk ditampilkan
        result_str = self.format_result_for_display(result)

        # Update text widget
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, result_str)
        self.result_text.config(state=tk.DISABLED)

    def format_result_for_display(self, result):
        """Format hasil query untuk tampilan teks"""
        output = []

        for result_set in result:
            headers = result_set.get('headers', [])
            rows = result_set.get('rows', [])

            if not headers or not rows:
                continue

            # Calculate column widths
            col_widths = {}
            for header in headers:
                col_widths[header] = len(str(header))

            for row in rows:
                for header in headers:
                    value = row.get(header, "")
                    col_widths[header] = max(col_widths[header], len(str(value)))

            # Format header row
            header_row = " | ".join(header.ljust(col_widths[header]) for header in headers)
            separator = "-" * len(header_row)

            output.append(header_row)
            output.append(separator)

            # Format data rows
            for row in rows:
                data_row = " | ".join(str(row.get(header, "")).ljust(col_widths[header]) for header in headers)
                output.append(data_row)

            output.append("")
            output.append(f"Total rows: {len(rows)}")
            output.append("")

        return "\n".join(output)

    def select_database(self):
        """Buka dialog untuk memilih database"""
        file_path = filedialog.askopenfilename(
            title="Select Firebird Database",
            filetypes=[("Firebird Database", "*.fdb"), ("All Files", "*.*")]
        )

        if not file_path:
            return

        if not os.path.exists(file_path):
            messagebox.showerror("Error", f"File tidak ditemukan: {file_path}")
            return

        # Periksa terlebih dahulu apakah isql.exe dapat ditemukan
        isql_path = None
        try:
            # Coba buat koneksi awal tanpa isql_path (auto-detect)
            from common.db_utils import FirebirdConnector
            isql_detector = FirebirdConnector()
            isql_path = isql_detector.isql_path
            self.log(f"ISQL ditemukan otomatis di: {isql_path}")
        except FileNotFoundError:
            # ISQL tidak ditemukan, tanyakan user untuk memilih path manual
            self.log("ISQL tidak ditemukan otomatis. Meminta user untuk memilih lokasi ISQL...")
            isql_path = filedialog.askopenfilename(
                title="Pilih Lokasi ISQL.exe",
                filetypes=[("ISQL Executable", "isql.exe"), ("All Files", "*.*")]
            )

            if not isql_path:
                messagebox.showwarning("Warning", "ISQL tidak dipilih. Koneksi database dibatalkan.")
                return

            if not os.path.exists(isql_path):
                messagebox.showerror("Error", f"File ISQL tidak ditemukan: {isql_path}")
                return

            # Test ISQL yang dipilih
            from common.db_utils import FirebirdConnector
            try:
                test_connector = FirebirdConnector(isql_path=isql_path)
                if not test_connector.test_isql(isql_path):
                    messagebox.showerror("Error", "ISQL yang dipilih tidak dapat dijalankan.")
                    return
                self.log(f"ISQL yang dipilih berhasil diuji: {isql_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal menguji ISQL: {e}")
                return

        try:
            # Coba buat koneksi database dengan isql_path yang ditemukan atau dipilih
            if self.db_connector:
                # Gunakan koneksi yang sudah ada dengan path baru
                self.db_connector.db_path = file_path
                if isql_path:
                    self.db_connector.isql_path = isql_path
            else:
                # Buat koneksi baru
                from common.db_utils import FirebirdConnector
                self.db_connector = FirebirdConnector(db_path=file_path, isql_path=isql_path)

            # Test koneksi
            tables = self.db_connector.get_tables()

            # Update status
            self.log(f"Terhubung ke database: {os.path.basename(file_path)}")
            messagebox.showinfo("Database Connected", f"Berhasil terhubung ke {os.path.basename(file_path)}")

            # Simpan konfigurasi
            self.save_config()

            # Jika terhubung ke server, kirim info database
            if self.connected and self.socket:
                self.register_to_server()
        except Exception as e:
            self.log(f"Error saat menghubungkan ke database: {e}")
            messagebox.showerror("Connection Error", f"Gagal terhubung ke database: {e}")
            self.db_connector = None

    def test_db_connection(self):
        """Tes koneksi ke database"""
        if not self.db_connector:
            messagebox.showinfo("No Database", "No database selected. Please select a database first.")
            return

        try:
            if self.db_connector.test_connection():
                tables = self.db_connector.get_tables()
                table_count = len(tables)

                messagebox.showinfo(
                    "Connection Success",
                    f"Successfully connected to database.\n\nDatabase: {os.path.basename(self.db_connector.db_path)}\nTables: {table_count}"
                )

                self.log(f"Tes koneksi database berhasil. {table_count} tabel ditemukan.")
            else:
                messagebox.showerror("Connection Failed", "Failed to connect to database.")
                self.log("Tes koneksi database gagal.")
        except Exception as e:
            self.log(f"Error saat tes koneksi database: {e}")
            messagebox.showerror("Connection Error", f"Error testing database connection: {e}")

    def change_db_settings(self):
        """Ubah pengaturan koneksi database"""
        if not self.db_connector:
            messagebox.showinfo("No Database", "No database selected. Please select a database first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Database Settings")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Database Path:").pack(padx=10, pady=(10, 0), anchor=tk.W)
        path_var = tk.StringVar(value=self.db_connector.db_path)
        path_entry = ttk.Entry(dialog, textvariable=path_var, width=40, state="readonly")
        path_entry.pack(padx=10, pady=(0, 10), fill=tk.X)

        ttk.Label(dialog, text="Username:").pack(padx=10, pady=(0, 0), anchor=tk.W)
        username_var = tk.StringVar(value=self.db_connector.username)
        username_entry = ttk.Entry(dialog, textvariable=username_var, width=20)
        username_entry.pack(padx=10, pady=(0, 10), fill=tk.X)

        ttk.Label(dialog, text="Password:").pack(padx=10, pady=(0, 0), anchor=tk.W)
        password_var = tk.StringVar(value=self.db_connector.password)
        password_entry = ttk.Entry(dialog, textvariable=password_var, width=20, show="*")
        password_entry.pack(padx=10, pady=(0, 10), fill=tk.X)

        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        def save_settings():
            username = username_var.get().strip()
            password = password_var.get().strip()

            if not username:
                messagebox.showwarning("Input Error", "Username is required", parent=dialog)
                return

            try:
                self.db_connector.username = username
                self.db_connector.password = password

                # Test connection with new settings
                if self.db_connector.test_connection():
                    self.log("Pengaturan database berhasil diubah")
                    messagebox.showinfo("Success", "Database settings updated successfully", parent=dialog)
                    dialog.destroy()
                else:
                    messagebox.showerror("Connection Failed", "Failed to connect with new settings", parent=dialog)
            except Exception as e:
                self.log(f"Error saat mengubah pengaturan database: {e}")
                messagebox.showerror("Error", f"Error updating database settings: {e}", parent=dialog)

        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def exit_app(self):
        """Keluar dari aplikasi"""
        if messagebox.askyesno("Exit", "Apakah Anda yakin ingin keluar?"):
            # Simpan konfigurasi sebelum keluar
            self.save_config()

            self.running = False

            # Disconnect from server
            if self.connected and self.socket:
                try:
                    self.socket.close()
                except:
                    pass

            self.root.destroy()
            sys.exit(0)

    def run_test_query(self):
        """Menjalankan query test langsung dari client"""
        if not self.db_connector:
            messagebox.showwarning("Warning", "Pilih database terlebih dahulu")
            return

        query_dialog = tk.Toplevel(self.root)
        query_dialog.title("Run Test Query")
        query_dialog.geometry("800x600")
        query_dialog.transient(self.root)
        query_dialog.grab_set()

        # Frame untuk query
        query_frame = ttk.LabelFrame(query_dialog, text="SQL Query")
        query_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        query_text = scrolledtext.ScrolledText(query_frame, height=10)
        query_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Default query - menggunakan query yang diminta dengan format yang lebih sederhana
        default_query = """SELECT FIRST 5 ID, SCANNERUSEREMPID, OCFIELDID, DEFOCID, JOBCODEID,
    WORKEREMPID, VEHICLECODEID, CRDIVISIONID, UPLOADDATETIME, TRANSNO,
    TRANSDATE, TRANSTIME, RECORDTAG, TRANSSTATUS, LASTUSER,
    LASTUPDATED, ACKNOWLEDGEBY, ACKNOWLEDGEON, REMARKS, ISCONTRACT,
    SCANOUTDATE, SCANOUTTIME, SCANOUTUSEREMPID, ISVALIDSCANOUT,
    REVIEWSTATUSID, REVIEWID, REVIEWDATE
FROM GWSCANNERDATA07"""
        query_text.insert(tk.END, default_query)

        # Frame untuk opsi koneksi
        options_frame = ttk.LabelFrame(query_dialog, text="Connection Options")
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        # Opsi untuk menggunakan localhost
        use_localhost_var = tk.BooleanVar(value=True)  # Default to True for better compatibility
        use_localhost_check = ttk.Checkbutton(options_frame, text="Use localhost connection format (recommended)", variable=use_localhost_var)
        use_localhost_check.pack(anchor=tk.W, padx=5, pady=2)

        # Frame untuk ISQL path
        isql_frame = ttk.Frame(options_frame)
        isql_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(isql_frame, text="ISQL Path:").pack(side=tk.LEFT, padx=(0, 5))
        # Default to the path from memory
        default_isql_path = r"C:\Program Files (x86)\Firebird\Firebird_1_5\bin\isql.exe"
        isql_path_var = tk.StringVar(value=self.db_connector.isql_path if self.db_connector else default_isql_path)
        isql_path_entry = ttk.Entry(isql_frame, textvariable=isql_path_var, width=50)
        isql_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def browse_isql():
            path = filedialog.askopenfilename(
                title="Select ISQL Executable",
                filetypes=[("ISQL Executable", "isql.exe"), ("All Files", "*.*")]
            )
            if path:
                isql_path_var.set(path)

        browse_button = ttk.Button(isql_frame, text="Browse", command=browse_isql)
        browse_button.pack(side=tk.RIGHT)

        # Frame untuk status dan hasil
        status_frame = ttk.LabelFrame(query_dialog, text="Connection Status")
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        # Tampilkan informasi koneksi database saat ini
        ttk.Label(status_frame, text=f"Database Path: {self.db_connector.db_path}").pack(anchor=tk.W, padx=5, pady=2)

        # Tampilkan informasi koneksi yang akan digunakan
        connection_info = ttk.Label(status_frame, text="Connection Format: localhost (recommended)")
        connection_info.pack(anchor=tk.W, padx=5, pady=2)

        def update_connection_info(*args):
            if use_localhost_var.get():
                connection_info.config(text="Connection Format: localhost (recommended)")
            else:
                connection_info.config(text="Connection Format: direct path")

        use_localhost_var.trace_add("write", update_connection_info)

        # Frame untuk tombol
        button_frame = ttk.Frame(query_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        # Fungsi untuk memverifikasi ISQL
        def verify_isql():
            isql_path = isql_path_var.get()
            if not isql_path:
                messagebox.showwarning("Warning", "ISQL path tidak boleh kosong", parent=query_dialog)
                return False

            if not os.path.exists(isql_path):
                messagebox.showerror("Error", f"ISQL tidak ditemukan: {isql_path}", parent=query_dialog)
                return False

            try:
                # Test ISQL
                from common.db_utils import FirebirdConnector
                test_connector = FirebirdConnector(isql_path=isql_path)
                if test_connector.test_isql(isql_path):
                    messagebox.showinfo("Success", "ISQL berhasil diverifikasi", parent=query_dialog)
                    return True
                else:
                    messagebox.showerror("Error", "ISQL tidak dapat dijalankan", parent=query_dialog)
                    return False
            except Exception as e:
                messagebox.showerror("Error", f"Gagal memverifikasi ISQL: {e}", parent=query_dialog)
                return False

        def execute_test():
            query = query_text.get("1.0", tk.END).strip()
            if not query:
                messagebox.showwarning("Warning", "Query tidak boleh kosong", parent=query_dialog)
                return

            # Dapatkan opsi koneksi
            use_localhost = use_localhost_var.get()
            custom_isql_path = isql_path_var.get()

            # Validasi ISQL path jika diubah
            if custom_isql_path and custom_isql_path != self.db_connector.isql_path:
                if not os.path.exists(custom_isql_path):
                    messagebox.showerror("Error", f"ISQL tidak ditemukan: {custom_isql_path}", parent=query_dialog)
                    return

            try:
                print("="*50)
                print(f"RUN TEST QUERY: Mengeksekusi test query...")
                print(f"Database: {self.db_connector.db_path}")
                print(f"Use localhost: {use_localhost}")
                print(f"ISQL Path: {custom_isql_path if custom_isql_path else self.db_connector.isql_path}")
                print(f"Query: {query}")

                # Buat connector baru dengan opsi yang dipilih
                from common.db_utils import FirebirdConnector
                test_connector = FirebirdConnector(
                    db_path=self.db_connector.db_path,
                    username=self.db_connector.username,
                    password=self.db_connector.password,
                    isql_path=custom_isql_path if custom_isql_path else self.db_connector.isql_path,
                    use_localhost=use_localhost
                )

                # Catat waktu mulai
                start_time = time.time()

                # Eksekusi query
                result = test_connector.execute_query(query)

                # Catat waktu selesai
                end_time = time.time()
                execution_time = end_time - start_time

                # Log hasil
                self.log(f"Test query berhasil: {len(result)} result sets (waktu: {execution_time:.2f} detik)")
                for i, rs in enumerate(result):
                    headers = rs.get('headers', [])
                    rows = rs.get('rows', [])
                    self.log(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
                    if len(rows) > 0:
                        self.log(f"  Sample first row: {list(rows[0].values())[:3]}...")

                # Debug detail
                print("DEBUG HASIL QUERY:")
                for i, rs in enumerate(result):
                    headers = rs.get('headers', [])
                    rows = rs.get('rows', [])
                    print(f"Result set {i+1}:")
                    print(f"  Headers ({len(headers)}): {headers}")
                    print(f"  Rows: {len(rows)}")
                    if len(rows) > 0:
                        print(f"  First row data: {rows[0]}")

                # Update tampilan hasil
                self.last_result = result
                self.update_result_display(result)

                # Jika terhubung ke server, kirim hasil ke server
                if self.connected and self.socket:
                    print("DEBUG: Client terhubung ke server, mengirim hasil test query...")
                    result_data = {
                        'query': query,
                        'description': 'test_query',
                        'result': result,
                        'timestamp': datetime.datetime.now().isoformat()
                    }

                    result_message = NetworkMessage(
                        NetworkMessage.TYPE_RESULT,
                        result_data,
                        self.client_id_var.get() or self.client_id
                    )

                    success = send_message(self.socket, result_message)
                    if success:
                        print("DEBUG: Hasil test query berhasil dikirim ke server")
                        self.log("Hasil test query berhasil dikirim ke server")
                    else:
                        print("DEBUG: Gagal mengirim hasil test query ke server")
                        self.log("Gagal mengirim hasil test query ke server")
                else:
                    print("DEBUG: Client tidak terhubung ke server, hasil hanya ditampilkan di client")

                print("="*50)
                messagebox.showinfo("Success", f"Query berhasil dieksekusi dalam {execution_time:.2f} detik", parent=query_dialog)
                query_dialog.destroy()
            except Exception as e:
                print(f"ERROR saat eksekusi test query: {e}")
                import traceback
                traceback.print_exc()
                self.log(f"Error saat eksekusi test query: {e}")
                messagebox.showerror("Error", f"Gagal mengeksekusi query: {e}", parent=query_dialog)

        # Tombol verifikasi ISQL
        verify_button = ttk.Button(button_frame, text="Verify ISQL", command=verify_isql)
        verify_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Tombol eksekusi
        execute_button = ttk.Button(button_frame, text="Execute Query", command=execute_test)
        execute_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # Tombol batal
        cancel_button = ttk.Button(button_frame, text="Cancel", command=query_dialog.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # Focus text area
        query_text.focus_set()

    def run(self):
        """Jalankan aplikasi"""
        self.root.mainloop()

    def execute_editor_query(self):
        """Execute the SQL query from the editor"""
        if not self.db_connector:
            messagebox.showwarning("Warning", "Pilih database terlebih dahulu")
            return

        # Get the query from the editor
        query = self.query_editor.get("1.0", tk.END).strip()
        if not query:
            messagebox.showwarning("Warning", "Query tidak boleh kosong")
            return

        # Update status
        self.query_status_var.set("Executing query...")
        self.root.update()

        try:
            # Get connection options
            use_localhost = self.editor_localhost_var.get()

            # Create a connector with the selected options
            from common.db_utils import FirebirdConnector
            query_connector = FirebirdConnector(
                db_path=self.db_connector.db_path,
                username=self.db_connector.username,
                password=self.db_connector.password,
                isql_path=self.db_connector.isql_path,
                use_localhost=use_localhost
            )

            # Record start time
            start_time = time.time()

            # Execute the query
            result = query_connector.execute_query(query)

            # Record end time
            end_time = time.time()
            execution_time = end_time - start_time

            # Log the result
            self.log(f"Query executed successfully in {execution_time:.2f} seconds")
            for i, rs in enumerate(result):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])
                self.log(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")

            # Update the results display
            self.display_query_results(result, execution_time)

            # Update status
            self.query_status_var.set(f"Query completed in {execution_time:.2f} seconds")

            # Add to history
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.history_tree.insert("", 0, values=(timestamp, query[:50] + "..." if len(query) > 50 else query, "Success"))

        except Exception as e:
            error_message = str(e)
            self.log(f"Error executing query: {error_message}")
            self.query_status_var.set(f"Error: {error_message[:50]}..." if len(error_message) > 50 else error_message)
            messagebox.showerror("Error", f"Failed to execute query: {error_message}")

            # Add to history
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.history_tree.insert("", 0, values=(timestamp, query[:50] + "..." if len(query) > 50 else query, "Error"))

    def display_query_results(self, result, execution_time=None):
        """Display query results in the results text area"""
        if not result:
            self.query_results.config(state=tk.NORMAL)
            self.query_results.delete("1.0", tk.END)
            self.query_results.insert(tk.END, "No results returned.")
            self.query_results.config(state=tk.DISABLED)
            return

        # Format the results
        output = []
        if execution_time is not None:
            output.append(f"Query executed in {execution_time:.2f} seconds\n")

        total_rows = 0
        for i, result_set in enumerate(result):
            headers = result_set.get('headers', [])
            rows = result_set.get('rows', [])
            total_rows += len(rows)

            if i > 0:
                output.append("\n" + "-" * 80 + "\n")

            output.append(f"Result Set {i+1}: {len(rows)} rows, {len(headers)} columns\n")

            if not headers or not rows:
                output.append("No data in this result set.\n")
                continue

            # Calculate column widths
            col_widths = {}
            for header in headers:
                col_widths[header] = len(str(header))

            for row in rows:
                for header in headers:
                    value = row.get(header, "")
                    col_widths[header] = max(col_widths[header], len(str(value)))

            # Format header row
            header_row = " | ".join(header.ljust(col_widths[header]) for header in headers)
            separator = "-" * len(header_row)

            output.append(header_row)
            output.append(separator)

            # Format data rows
            for row in rows:
                data_row = " | ".join(str(row.get(header, "")).ljust(col_widths[header]) for header in headers)
                output.append(data_row)

        # Update the results text widget
        self.query_results.config(state=tk.NORMAL)
        self.query_results.delete("1.0", tk.END)
        self.query_results.insert(tk.END, "\n".join(output))
        self.query_results.config(state=tk.DISABLED)

        # Save the last result
        self.last_result = result

    def clear_editor(self):
        """Clear the query editor"""
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the editor?"):
            self.query_editor.delete("1.0", tk.END)

    def save_editor_query(self):
        """Save the current query to a file"""
        query = self.query_editor.get("1.0", tk.END).strip()
        if not query:
            messagebox.showwarning("Warning", "No query to save")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".sql",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            with open(file_path, "w") as f:
                f.write(query)
            self.log(f"Query saved to {file_path}")
            messagebox.showinfo("Success", f"Query saved to {file_path}")
        except Exception as e:
            self.log(f"Error saving query: {e}")
            messagebox.showerror("Error", f"Failed to save query: {e}")

    def load_editor_query(self):
        """Load a query from a file into the editor"""
        file_path = filedialog.askopenfilename(
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            with open(file_path, "r") as f:
                query = f.read()

            if messagebox.askyesno("Confirm", "Replace current query with loaded query?"):
                self.query_editor.delete("1.0", tk.END)
                self.query_editor.insert(tk.END, query)
                self.log(f"Query loaded from {file_path}")
        except Exception as e:
            self.log(f"Error loading query: {e}")
            messagebox.showerror("Error", f"Failed to load query: {e}")

    def export_results(self):
        """Export query results to a file"""
        if not self.last_result:
            messagebox.showwarning("Warning", "No results to export")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            with open(file_path, "w") as f:
                for result_set in self.last_result:
                    headers = result_set.get('headers', [])
                    rows = result_set.get('rows', [])

                    if not headers or not rows:
                        continue

                    # Write headers
                    f.write(",".join(f'"{h}"' for h in headers) + "\n")

                    # Write rows
                    for row in rows:
                        f.write(",".join(f'"{row.get(h, "")}"' for h in headers) + "\n")

                    f.write("\n")

            self.log(f"Results exported to {file_path}")
            messagebox.showinfo("Success", f"Results exported to {file_path}")
        except Exception as e:
            self.log(f"Error exporting results: {e}")
            messagebox.showerror("Error", f"Failed to export results: {e}")

    def clear_log(self):
        """Bersihkan log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def save_log(self):
        """Simpan log ke file"""
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

    def append_to_log_file(self, log_message):
        """Tambahkan log ke file secara otomatis"""
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)

            today = datetime.datetime.now().strftime("%Y-%m-%d")
            log_file = os.path.join(log_dir, f"client_{today}.log")

            with open(log_file, 'a') as f:
                f.write(log_message)
        except Exception as e:
            print(f"Error writing to log file: {e}")

    def clear_history(self):
        """Bersihkan history query"""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.query_history = []

    def set_isql_path(self):
        """Dialog untuk mengatur path ISQL secara manual"""
        # Cari path ISQL saat ini jika ada
        current_path = None
        if self.db_connector and hasattr(self.db_connector, 'isql_path'):
            current_path = self.db_connector.isql_path

        # Dialog dengan instruksi
        info_dialog = tk.Toplevel(self.root)
        info_dialog.title("Pilih ISQL.exe")
        info_dialog.geometry("600x400")
        info_dialog.transient(self.root)

        # Tampilkan instruksi
        ttk.Label(info_dialog, text="Petunjuk Memilih ISQL Firebird 1.5", font=("Arial", 12, "bold")).pack(pady=(20, 10))

        ttk.Label(info_dialog, text="Lokasi ISQL Firebird 1.5 yang umum:").pack(anchor="w", padx=20, pady=(10, 5))
        locations_frame = ttk.Frame(info_dialog)
        locations_frame.pack(fill=tk.X, padx=20, pady=5)

        locations = [
            r"C:\Program Files (x86)\Firebird-1.5.6.5026-0_win32_Manual\bin\isql.exe",
            r"C:\Program Files (x86)\Firebird\Firebird_1_5\bin\isql.exe",
            r"C:\Program Files\Firebird\Firebird_1_5\bin\isql.exe",
            r"D:\Firebird\Firebird_1_5\bin\isql.exe"
        ]

        for loc in locations:
            exists = os.path.exists(loc)
            color = "green" if exists else "gray"
            font = ("Consolas", 9, "bold" if exists else "normal")

            loc_frame = ttk.Frame(locations_frame)
            loc_frame.pack(fill=tk.X, pady=2)

            ttk.Label(loc_frame, text="✓ " if exists else "○ ", foreground=color).pack(side=tk.LEFT)
            path_lbl = ttk.Label(loc_frame, text=loc, foreground=color, font=font)
            path_lbl.pack(side=tk.LEFT)

            if exists:
                # Jika path ada, tambahkan tombol untuk langsung memilih
                def select_this_path(path=loc):
                    info_dialog.destroy()
                    self.verify_and_set_isql(path)

                ttk.Button(loc_frame, text="Pilih", command=select_this_path).pack(side=tk.RIGHT)

        ttk.Label(info_dialog, text="Masalah umum dengan ISQL:", font=("Arial", 10, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        ttk.Label(info_dialog, text="1. File isql.exe tidak ditemukan di lokasi standar").pack(anchor="w", padx=30)
        ttk.Label(info_dialog, text="2. File DLL yang diperlukan (seperti fbclient.dll) tidak ditemukan").pack(anchor="w", padx=30)
        ttk.Label(info_dialog, text="3. Versi isql.exe tidak cocok dengan versi database").pack(anchor="w", padx=30)

        # Tombol-tombol
        btn_frame = ttk.Frame(info_dialog)
        btn_frame.pack(fill=tk.X, padx=20, pady=20)

        ttk.Button(btn_frame, text="Browse ISQL.exe", command=lambda: [info_dialog.destroy(), self.browse_isql_path()]).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Batal", command=info_dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def browse_isql_path(self):
        """Buka dialog untuk memilih file ISQL.exe"""
        # Cari path ISQL saat ini jika ada
        current_path = None
        if self.db_connector and hasattr(self.db_connector, 'isql_path'):
            current_path = self.db_connector.isql_path

        # Buka dialog untuk memilih file
        isql_path = filedialog.askopenfilename(
            title="Pilih Lokasi ISQL.exe",
            filetypes=[("ISQL Executable", "isql.exe"), ("All Files", "*.*")],
            initialdir=os.path.dirname(current_path) if current_path else None
        )

        if not isql_path:
            return

        if not os.path.exists(isql_path):
            messagebox.showerror("Error", f"File tidak ditemukan: {isql_path}")
            return

        # Verifikasi file yang dipilih
        self.verify_and_set_isql(isql_path)

    def verify_and_set_isql(self, isql_path):
        """Verifikasi dan set path ISQL yang dipilih"""
        if not os.path.exists(isql_path):
            messagebox.showerror("Error", f"File tidak ditemukan: {isql_path}")
            return

        # Buat dialog untuk verifikasi
        verify_dialog = tk.Toplevel(self.root)
        verify_dialog.title("Verifikasi ISQL")
        verify_dialog.geometry("700x500")
        verify_dialog.transient(self.root)

        # Label informasi
        ttk.Label(verify_dialog, text=f"Memverifikasi ISQL: {isql_path}", font=("Arial", 10, "bold")).pack(pady=(10, 5), padx=10)

        # Area hasil
        result_text = scrolledtext.ScrolledText(verify_dialog, height=25, font=("Consolas", 9))
        result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        result_text.config(state=tk.DISABLED)

        # Fungsi untuk menampilkan hasil
        def add_result(text, success=None):
            result_text.config(state=tk.NORMAL)
            if success is True:
                result_text.insert(tk.END, f"✓ {text}\n", "success")
            elif success is False:
                result_text.insert(tk.END, f"✗ {text}\n", "error")
            else:
                result_text.insert(tk.END, f"{text}\n")
            result_text.see(tk.END)
            result_text.config(state=tk.DISABLED)
            verify_dialog.update()

        # Konfigurasi tag warna
        result_text.tag_configure("success", foreground="green")
        result_text.tag_configure("error", foreground="red")

        add_result(f"Memeriksa file: {isql_path}")

        # Periksa apakah file ada dan executable
        is_file = os.path.isfile(isql_path)
        add_result(f"File ditemukan: {isql_path}", is_file)

        if not is_file:
            add_result("File ISQL tidak ditemukan atau bukan file.", False)
            ttk.Button(verify_dialog, text="Pilih File Lain",
                     command=lambda: [verify_dialog.destroy(), self.browse_isql_path()]).pack(side=tk.LEFT, padx=5, pady=10)
            ttk.Button(verify_dialog, text="Tutup",
                     command=verify_dialog.destroy).pack(side=tk.RIGHT, padx=5)
            return

        # Periksa apakah file executable
        is_exe = os.path.splitext(isql_path)[1].lower() == '.exe'
        add_result(f"File adalah executable (.exe)", is_exe)

        if not is_exe:
            add_result("File yang dipilih bukan executable (.exe).", False)
            ttk.Button(verify_dialog, text="Pilih File Lain",
                     command=lambda: [verify_dialog.destroy(), self.browse_isql_path()]).pack(side=tk.LEFT, padx=5, pady=10)
            ttk.Button(verify_dialog, text="Tutup",
                     command=verify_dialog.destroy).pack(side=tk.RIGHT, padx=5)
            return

        # Coba jalankan ISQL untuk verifikasi
        add_result("\nMencoba menjalankan ISQL...")

        try:
            # Buat tempat pengujian untuk FirebirdConnector
            from common.db_utils import FirebirdConnector
            test_connector = FirebirdConnector(isql_path=isql_path)
            isql_works = test_connector.test_isql(isql_path)
            add_result(f"ISQL dapat dijalankan", isql_works)

            if not isql_works:
                add_result("ISQL yang dipilih tidak dapat dijalankan.", False)
                add_result("\nKemungkinan penyebab masalah:")
                add_result("1. File DLL yang dibutuhkan (seperti fbclient.dll) tidak ditemukan")
                add_result("2. ISQL membutuhkan akses admin")
                add_result("3. File ISQL rusak atau tidak kompatibel dengan sistem")

                btn_frame = ttk.Frame(verify_dialog)
                btn_frame.pack(fill=tk.X, padx=10, pady=10)

                ttk.Button(btn_frame, text="Set Anyway (Forced)",
                        command=lambda: [verify_dialog.destroy(), self.force_set_isql(isql_path)]).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Pilih File Lain",
                        command=lambda: [verify_dialog.destroy(), self.browse_isql_path()]).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Batal",
                        command=verify_dialog.destroy).pack(side=tk.RIGHT, padx=5)
                return

            # Jika sampai di sini, ISQL berhasil dijalankan
            add_result("\n✓ ISQL berhasil diverifikasi!", True)

            # Set path ke konfigurasi
            if self.db_connector:
                self.db_connector.isql_path = isql_path

            self.log(f"ISQL path diperbarui: {isql_path}")
            add_result(f"\nISQl path berhasil diperbarui: {isql_path}", True)

            # Simpan konfigurasi
            self.save_config()

            # Tombol
            btn_frame = ttk.Frame(verify_dialog)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)

            ttk.Button(btn_frame, text="Test ISQL",
                     command=lambda: [verify_dialog.destroy(), self.test_isql_directly(None, show_dialog=True)]).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Tutup",
                     command=verify_dialog.destroy).pack(side=tk.RIGHT, padx=5)

        except Exception as e:
            add_result(f"Error saat memverifikasi ISQL: {e}", False)

            btn_frame = ttk.Frame(verify_dialog)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)

            ttk.Button(btn_frame, text="Set Anyway (Forced)",
                     command=lambda: [verify_dialog.destroy(), self.force_set_isql(isql_path)]).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Pilih File Lain",
                     command=lambda: [verify_dialog.destroy(), self.browse_isql_path()]).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Batal",
                     command=verify_dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def force_set_isql(self, isql_path):
        """Set ISQL path secara paksa (tanpa verifikasi)"""
        try:
            if self.db_connector:
                self.db_connector.isql_path = isql_path

            self.log(f"ISQL path diperbarui (forced): {isql_path}")
            messagebox.showwarning("ISQL Path", f"ISQL path diperbarui secara paksa:\n{isql_path}\n\nPeringatan: ISQL tidak terverifikasi bekerja dengan baik.")

            # Simpan konfigurasi
            self.save_config()
        except Exception as e:
            self.log(f"Error saat mengatur ISQL path: {e}")
            messagebox.showerror("Error", f"Gagal mengatur ISQL path: {e}")

    def diagnose_connection(self):
        """Menjalankan diagnosa koneksi Firebird"""
        if not self.db_connector:
            messagebox.showinfo("No Database", "Tidak ada database yang dipilih. Silakan pilih database terlebih dahulu.")
            return

        # Buat dialog untuk menampilkan hasil diagnosa
        diag_dialog = tk.Toplevel(self.root)
        diag_dialog.title("Diagnosa Koneksi Firebird")
        diag_dialog.geometry("800x600")
        diag_dialog.transient(self.root)

        # Area hasil
        result_text = scrolledtext.ScrolledText(diag_dialog, height=30, font=("Consolas", 10))
        result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Fungsi untuk menambahkan teks ke hasil
        def add_result(text, success=None):
            result_text.config(state=tk.NORMAL)
            if success is True:
                result_text.insert(tk.END, f"✓ {text}\n", "success")
            elif success is False:
                result_text.insert(tk.END, f"✗ {text}\n", "error")
            else:
                result_text.insert(tk.END, f"{text}\n")
            result_text.see(tk.END)
            result_text.config(state=tk.DISABLED)
            diag_dialog.update()

        # Konfigurasi tag warna
        result_text.tag_configure("success", foreground="green")
        result_text.tag_configure("error", foreground="red")

        # Mulai diagnosa
        add_result("=== DIAGNOSA KONEKSI FIREBIRD ===\n")

        # 1. Cek path ISQL
        add_result(f"ISQL Path: {self.db_connector.isql_path}")
        isql_exists = os.path.exists(self.db_connector.isql_path)
        add_result(f"ISQL Executable ditemukan", isql_exists)

        if not isql_exists:
            add_result("DIAGNOSA GAGAL: ISQL tidak ditemukan. Silakan set path ISQL yang benar.", False)

            # Tambahkan tombol untuk set ISQL path
            button_frame = ttk.Frame(diag_dialog)
            button_frame.pack(fill=tk.X, pady=10)

            ttk.Button(button_frame, text="Browse ISQL Path",
                    command=lambda: [diag_dialog.destroy(), self.set_isql_path()]).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Tutup",
                    command=diag_dialog.destroy).pack(side=tk.RIGHT, padx=5)
            return

        # 2. Cek path database
        add_result(f"\nDatabase Path: {self.db_connector.db_path}")
        db_exists = os.path.exists(self.db_connector.db_path)
        add_result(f"File database ditemukan", db_exists)

        if not db_exists:
            add_result("DIAGNOSA GAGAL: File database tidak ditemukan.", False)

            button_frame = ttk.Frame(diag_dialog)
            button_frame.pack(fill=tk.X, pady=10)

            ttk.Button(button_frame, text="Tutup",
                    command=diag_dialog.destroy).pack(side=tk.RIGHT, padx=5)
            return

        # 3. Test ISQL executable
        add_result("\nMengecek ISQL executable...")
        try:
            # Panggil method test_isql_directly
            isql_success = self.test_isql_directly(add_result)
            if not isql_success:
                add_result("ISQL executable tidak berfungsi dengan baik. Pilih ISQL lain.", False)

                button_frame = ttk.Frame(diag_dialog)
                button_frame.pack(fill=tk.X, pady=10)

                ttk.Button(button_frame, text="Pilih ISQL Lain",
                        command=lambda: [diag_dialog.destroy(), self.set_isql_path()]).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="Test ISQL Saja",
                        command=lambda: self.test_isql_directly(None, show_dialog=True)).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="Tutup",
                        command=diag_dialog.destroy).pack(side=tk.RIGHT, padx=5)
                return
        except Exception as e:
            add_result(f"Error saat mengecek ISQL: {e}", False)
            return

        # 4. Test koneksi database
        add_result("\nMengecek koneksi ke database...")
        conn_success = False
        try:
            conn_success = self.db_connector.test_connection()
            add_result("Koneksi database berhasil", conn_success)
        except Exception as e:
            add_result(f"Error saat koneksi ke database: {e}", False)
            conn_success = False

        # Tampilkan hasil akhir
        if conn_success:
            add_result("\n✓ DIAGNOSA SUKSES: Database dan ISQL berfungsi dengan baik.", True)
        else:
            add_result("\n✗ DIAGNOSA GAGAL: Koneksi ke database gagal.", False)
            add_result("\nUntuk Firebird 1.5, pastikan:")
            add_result("1. User dan password benar (biasanya SYSDBA/masterkey)")
            add_result("2. Database path benar dan file ada")
            add_result("3. Database tidak digunakan secara eksklusif oleh aplikasi lain")
            add_result("4. Coba restart komputer untuk membersihkan lock database")
            add_result("5. Periksa apakah database dalam keadaan baik (tidak korup)")

        # Tombol aksi
        button_frame = ttk.Frame(diag_dialog)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="Test ISQL Saja",
                command=lambda: self.test_isql_directly(None, show_dialog=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Set ISQL Path",
                command=lambda: [diag_dialog.destroy(), self.set_isql_path()]).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Tutup",
                command=diag_dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def test_isql_directly(self, add_result_func=None, show_dialog=False):
        """Test ISQL secara langsung tanpa database"""
        if not self.db_connector:
            if show_dialog:
                messagebox.showinfo("No ISQL", "Tidak ada ISQL yang dipilih.")
            return False

        isql_path = self.db_connector.isql_path
        if not os.path.exists(isql_path):
            if show_dialog:
                messagebox.showerror("Error", f"ISQL tidak ditemukan: {isql_path}")
            return False

        # Fungsi untuk menampilkan hasil
        def log_result(text, success=None):
            if add_result_func:
                add_result_func(text, success)
            else:
                self.log(text)

        # Jika show_dialog, buat dialog baru
        if show_dialog:
            dialog = tk.Toplevel(self.root)
            dialog.title("Test ISQL Langsung")
            dialog.geometry("700x500")
            dialog.transient(self.root)

            # Area hasil
            result_text = scrolledtext.ScrolledText(dialog, height=25, font=("Consolas", 10))
            result_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # Override fungsi
            def dialog_log(text, success=None):
                result_text.config(state=tk.NORMAL)
                if success is True:
                    result_text.insert(tk.END, f"✓ {text}\n", "success")
                elif success is False:
                    result_text.insert(tk.END, f"✗ {text}\n", "error")
                else:
                    result_text.insert(tk.END, f"{text}\n")
                result_text.see(tk.END)
                result_text.config(state=tk.DISABLED)
                dialog.update()

            # Konfigurasi tag warna
            result_text.tag_configure("success", foreground="green")
            result_text.tag_configure("error", foreground="red")

            log_result = dialog_log

            log_result(f"Test ISQL di: {isql_path}\n")

        # Test berbagai metode
        methods_to_test = [
            {"name": "Versi ISQL", "cmd": [isql_path, "-z"]},
            {"name": "Help ISQL", "cmd": [isql_path, "-h"]},
            {"name": "Versi ISQL (metode lain)", "cmd": [isql_path, "-version"]},
            {"name": "Command sederhana", "cmd": [isql_path], "input": "HELP;\nEXIT;\n"}
        ]

        success_count = 0
        for test in methods_to_test:
            try:
                log_result(f"\nMenjalankan test: {test['name']}")
                log_result(f"Command: {' '.join(test['cmd'])}")

                if "input" in test:
                    # Jika test membutuhkan input
                    proc = subprocess.Popen(
                        test['cmd'],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    try:
                        stdout, stderr = proc.communicate(input=test["input"], timeout=10)
                        log_result(f"Return code: {proc.returncode}")
                        if stdout:
                            log_result(f"STDOUT:\n{stdout[:500]}")
                        if stderr:
                            log_result(f"STDERR:\n{stderr[:500]}")

                        # Anggap berhasil jika tidak ada error besar
                        success = True
                        log_result(f"Test {test['name']} berhasil dijalankan", success)
                        if success:
                            success_count += 1
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        log_result(f"Test {test['name']} timeout, mungkin menunggu input lebih lanjut")
                        # Untuk input, timeout bisa saja normal
                        success_count += 1
                else:
                    # Test tanpa input
                    proc = subprocess.run(
                        test['cmd'],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False
                    )
                    log_result(f"Return code: {proc.returncode}")
                    if proc.stdout:
                        log_result(f"STDOUT:\n{proc.stdout[:500]}")
                    if proc.stderr:
                        log_result(f"STDERR:\n{proc.stderr[:500]}")

                    # Anggap berhasil jika process jalan, meski return code tidak 0
                    success = True
                    log_result(f"Test {test['name']} berhasil dijalankan", success)
                    if success:
                        success_count += 1
            except Exception as e:
                log_result(f"Error pada test {test['name']}: {e}", False)

        overall_success = success_count > 0
        log_result(f"\nHasil test ISQL: {success_count}/{len(methods_to_test)} test berhasil dijalankan", overall_success)

        # Tips jika ISQL bermasalah
        if success_count == 0:
            log_result("\nTips untuk memperbaiki masalah ISQL:")
            log_result("1. Pastikan ISQL.exe ada dan tidak rusak")
            log_result("2. Pastikan path ke ISQL.exe benar")
            log_result("3. Coba jalankan Command Prompt sebagai Administrator")
            log_result("4. Coba instal ulang Firebird jika masih bermasalah")
            log_result("5. Periksa apakah library yang dibutuhkan oleh ISQL ada (cek file DLL)")
        elif success_count < len(methods_to_test):
            log_result("\nBeberapa test berhasil, ISQL mungkin bisa digunakan.")

        if show_dialog:
            ttk.Button(dialog, text="Tutup", command=dialog.destroy).pack(pady=10)

            # Tambah tombol untuk memilih ISQL lain jika gagal
            if not overall_success:
                ttk.Button(dialog, text="Pilih ISQL Lain",
                        command=lambda: [dialog.destroy(), self.set_isql_path()]).pack(pady=5)

        return overall_success

if __name__ == "__main__":
    app = ClientApp()
    app.run()