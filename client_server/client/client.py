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
                            password=db_config.get('password', 'masterkey')
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
                    'password': self.db_connector.password
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
                self.connect_to_server(address, port, auto_reconnect=True)
            
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
            
            for i, rs in enumerate(result):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])
                print(f"Result set {i+1}:")
                print(f"  Headers ({len(headers)}): {headers}")
                print(f"  Rows: {len(rows)}")
                if rows and len(rows) > 0:
                    print(f"  Sample row: {str(rows[0])[:200]}...")
            
            result_data = {
                'query': query,
                'description': description,
                'result': result,
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
        
        try:
            # Coba buat koneksi database
            if self.db_connector:
                # Gunakan koneksi yang sudah ada dengan path baru
                self.db_connector.db_path = file_path
            else:
                # Buat koneksi baru
                from common.db_utils import FirebirdConnector
                self.db_connector = FirebirdConnector(db_path=file_path)
            
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
        query_dialog.geometry("700x500")
        query_dialog.transient(self.root)
        query_dialog.grab_set()
        
        # Frame untuk query
        query_frame = ttk.LabelFrame(query_dialog, text="SQL Query")
        query_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        query_text = scrolledtext.ScrolledText(query_frame, height=10)
        query_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Default query
        default_query = "SELECT a.ID, a.SCANUSERID, a.OCID, a.VEHICLECODEID, a.FIELDID, a.BUNCHES, a.LOOSEFRUIT, a.TRANSNO, a.FFBTRANSNO, a.TRANSSTATUS, a.TRANSDATE, a.TRANSTIME, a.UPLOADDATETIME, a.LASTUSER, a.LASTUPDATED, a.RECORDTAG, a.DRIVERNAME, a.DRIVERID, a.HARVESTINGDATE, a.PROCESSFLAG\nFROM FFBLOADINGCROP02 a WHERE ID <= 10"
        query_text.insert(tk.END, default_query)
        
        # Frame untuk tombol
        button_frame = ttk.Frame(query_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        def execute_test():
            query = query_text.get("1.0", tk.END).strip()
            if not query:
                messagebox.showwarning("Warning", "Query tidak boleh kosong", parent=query_dialog)
                return
                
            try:
                print("="*50)
                print(f"RUN TEST QUERY: Mengeksekusi test query...")
                print(f"Database: {self.db_connector.db_path}")
                print(f"Query: {query}")
                
                # Eksekusi query
                result = self.db_connector.execute_query(query)
                
                # Log hasil
                self.log(f"Test query berhasil: {len(result)} result sets")
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
                messagebox.showinfo("Success", "Query berhasil dieksekusi", parent=query_dialog)
                query_dialog.destroy()
            except Exception as e:
                print(f"ERROR saat eksekusi test query: {e}")
                import traceback
                traceback.print_exc()
                self.log(f"Error saat eksekusi test query: {e}")
                messagebox.showerror("Error", f"Gagal mengeksekusi query: {e}", parent=query_dialog)
        
        ttk.Button(button_frame, text="Execute", command=execute_test).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=query_dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Focus text area
        query_text.focus_set()
    
    def run(self):
        """Jalankan aplikasi"""
        self.root.mainloop()

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

if __name__ == "__main__":
    app = ClientApp()
    app.run() 