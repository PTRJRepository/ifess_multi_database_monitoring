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
import base64

# Tambahkan path untuk mengimpor dari direktori common
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from common.network import NetworkMessage, send_message, receive_message, DEFAULT_PORT
from common.db_utils import FirebirdConnector

# Path konfigurasi
CONFIG_FILE = os.path.join(current_dir, "client_config.json")

class ClientApp:
    """Aplikasi client yang terhubung ke server dan mengirim file database saat diminta"""
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
        """Load konfigurasi dari file"""
        try:
            config_path = os.path.join(current_dir, "..", "client_config.json")
            
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                self.server_address = config.get('server_address')
                self.server_port = config.get('server_port', DEFAULT_PORT)
                    self.client_id = config.get('client_id', self.client_id)
                    self.display_name = config.get('display_name', self.display_name)
                self.auto_reconnect = config.get('auto_reconnect', False)
                    
                    db_path = config.get('db_path')
                    if db_path and os.path.exists(db_path):
                        try:
                            self.db_connector = FirebirdConnector(db_path=db_path)
                    except Exception as e:
                            print(f"Error loading database: {e}")
                
                print(f"Config loaded: {config_path}")
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_config(self):
        """Simpan konfigurasi ke file"""
        try:
            config = {
                'server_address': self.server_address,
                'server_port': self.server_port,
                'client_id': self.client_id,
                'display_name': self.display_name,
                'auto_reconnect': self.auto_reconnect,
            }
            
            if self.db_connector and self.db_connector.db_path:
                config['db_path'] = self.db_connector.db_path
            
            config_path = os.path.join(current_dir, "..", "client_config.json")
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
                
            print(f"Config saved: {config_path}")
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def init_ui(self):
        """Inisialisasi antarmuka pengguna"""
        self.root = tk.Tk()
        self.root.title("Firebird Client")
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
        menubar.add_cascade(label="Database", menu=db_menu)
        
        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="Save Configuration", command=self.save_config)
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
        
        # Transfer Status Tab
        transfer_frame = ttk.Frame(notebook)
        notebook.add(transfer_frame, text="Transfer Status")
        
        # Status display
        self.transfer_status_text = scrolledtext.ScrolledText(transfer_frame, height=10, font=("Consolas", 9))
        self.transfer_status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.transfer_status_text.config(state=tk.DISABLED)
        
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
            self.db_status.config(text=f"Selected: {os.path.basename(self.db_connector.db_path)}")
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
                
                # Log info database yang dipilih
                self.log(f"Database terpilih: {os.path.basename(self.db_connector.db_path)}")
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
                    
                    # Proses message sesuai tipe
                    if message.msg_type == NetworkMessage.TYPE_PING:
                        # Ping dari server, balas dengan pong
                        pong_message = NetworkMessage(NetworkMessage.TYPE_PONG, 
                                                     {"timestamp": time.time()}, 
                                                     self.client_id)
                        try:
                            send_message(self.socket, pong_message)
                        except Exception as e:
                            self.log(f"Error mengirim pong: {e}")
                    
                    elif message.msg_type == NetworkMessage.TYPE_FILE_REQUEST:
                        # Permintaan untuk mengirim file database
                        try:
                            self.log("Menerima permintaan file database dari server")
                            self.send_database_file()
                        except Exception as e:
                            self.log(f"Error mengirim file database: {e}")
                            error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                                        {"error": f"Gagal mengirim file database: {e}"},
                                                        self.client_id)
                            send_message(self.socket, error_message)
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
    
    def update_transfer_status(self, message):
        """Update tampilan status transfer"""
        self.transfer_status_text.config(state=tk.NORMAL)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_message = f"[{timestamp}] {message}\n"
        self.transfer_status_text.insert(tk.END, status_message)
        self.transfer_status_text.see(tk.END)
        self.transfer_status_text.config(state=tk.DISABLED)
    
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
            # Buat koneksi baru ke file database
                from common.db_utils import FirebirdConnector
                self.db_connector = FirebirdConnector(db_path=file_path)
            
            # Update status
            self.log(f"Database dipilih: {os.path.basename(file_path)}")
            messagebox.showinfo("Database Selected", f"Database dipilih: {os.path.basename(file_path)}")
            
            # Simpan konfigurasi
            self.save_config()
            
            # Jika terhubung ke server, kirim info database
            if self.connected and self.socket:
                self.register_to_server()
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membuka database: {e}")
            self.db_connector = None
    
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
        """Tulis pesan log ke file"""
        try:
            log_dir = os.path.join(current_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, f"client_log_{datetime.datetime.now().strftime('%Y%m%d')}.txt")
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_message)
        except Exception as e:
            print(f"Error saat menyimpan log: {e}")
    
    def clear_history(self):
        """Hapus history query"""
        self.log("History dibersihkan")

    def send_database_file(self):
        """Mengirim file database ke server"""
        if not self.db_connector or not self.db_connector.db_path:
            self.log("Tidak ada database yang dipilih")
            error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                        {"error": "Database tidak dipilih"},
                                        self.client_id)
            send_message(self.socket, error_message)
            return
            
        # Dapatkan informasi file
        try:
            db_info = self.db_connector.get_database_file_info()
            if not db_info["exists"]:
                self.log(f"File database tidak ditemukan: {db_info['path']}")
                error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                            {"error": f"File database tidak ditemukan: {db_info['path']}"},
                                            self.client_id)
                send_message(self.socket, error_message)
                return
                
            # Kirim respons file info
            self.log(f"Mengirim informasi file database: {db_info['filename']} ({db_info['size']} bytes)")
            self.update_transfer_status(f"Memulai transfer file: {db_info['filename']} ({db_info['size']} bytes)")
            
            # Verifikasi ukuran file tidak terlalu besar
            if db_info["size"] > 2 * 1024 * 1024 * 1024:  # 2GB maksimum
                self.log(f"File database terlalu besar: {db_info['size']} bytes (max 2GB)")
                error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                            {"error": f"File database terlalu besar: {db_info['size']} bytes (max 2GB)"},
                                            self.client_id)
                send_message(self.socket, error_message)
                return
            
            # Jalankan transfer di thread terpisah
            transfer_thread = threading.Thread(target=self._send_database_file_thread, args=(db_info,))
            transfer_thread.daemon = True
            transfer_thread.start()
            
        except Exception as e:
            self.log(f"Error mengirim file database: {e}")
            self.update_transfer_status(f"Error transfer: {str(e)}")
            import traceback
            traceback.print_exc()
            error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                        {"error": f"Gagal mengirim file database: {str(e)}"},
                                        self.client_id)
            send_message(self.socket, error_message)
    
    def _send_database_file_thread(self, db_info):
        """Thread untuk mengirim file database ke server"""
        try:
            response_message = NetworkMessage(NetworkMessage.TYPE_FILE_RESPONSE, 
                                          {
                                              "filename": db_info["filename"],
                                              "size": db_info["size"],
                                              "db_info": self.db_connector.db_info
                                          },
                                          self.client_id)
            
            success = send_message(self.socket, response_message)
            if not success:
                self.log("Gagal mengirim informasi file database")
                return
            
            # Kirim chunks file
            chunk_size = 512 * 1024  # 512KB per chunk (lebih kecil untuk mengurangi kemungkinan timeout)
            offset = 0
            total_size = db_info["size"]
            
            start_time = time.time()
            last_update_time = start_time
            
            while offset < total_size and self.connected:
                # Cek waktu transfer, jangan lebih dari 30 menit
                current_time = time.time()
                if current_time - start_time > 30 * 60:  # 30 menit
                    self.log("Transfer timeout: lebih dari 30 menit")
                    self.update_transfer_status("Transfer dibatalkan: timeout 30 menit")
                    return
                
                # Update log progress setiap 5 detik
                if current_time - last_update_time > 5:
                    progress = min(100, int((offset / total_size) * 100))
                    self.log(f"Mengirim chunk database: {offset}/{total_size} bytes ({progress}%)")
                    self.update_transfer_status(f"Progress: {progress}% ({offset}/{total_size} bytes)")
                    last_update_time = current_time
                
                # Baca chunk dari file
                try:
                    chunk_data, is_last = self.db_connector.read_database_chunk(offset, chunk_size)
                    if chunk_data is None:
                        raise Exception("Gagal membaca chunk file database")
                    
                    # Encode data sebagai base64 untuk JSON
                    encoded_data = base64.b64encode(chunk_data).decode('utf-8')
                    
                    # Kirim chunk
                    chunk_message = NetworkMessage(NetworkMessage.TYPE_FILE_CHUNK, 
                                                {
                                                    "filename": db_info["filename"],
                                                    "offset": offset,
                                                    "size": len(chunk_data),
                                                    "data": encoded_data,
                                                    "is_last": is_last
                                                },
                                                self.client_id)
                    success = send_message(self.socket, chunk_message)
                    
                    if not success:
                        self.log("Gagal mengirim chunk file database")
                        self.update_transfer_status("Transfer gagal: error komunikasi")
                                    return
                                    
                    offset += len(chunk_data)
                    
                    # Tunggu sebentar untuk tidak membebani jaringan
                    time.sleep(0.1)
                    
                except Exception as e:
                    self.log(f"Error saat membaca/mengirim chunk: {e}")
                    self.update_transfer_status(f"Error transfer: {str(e)}")
                        return
                        
            # Kirim notifikasi selesai jika masih terhubung
            if self.connected:
                complete_message = NetworkMessage(NetworkMessage.TYPE_FILE_COMPLETE, 
                                               {
                                                   "filename": db_info["filename"],
                                                   "size": total_size
                                               },
                                               self.client_id)
                send_message(self.socket, complete_message)
                
                self.log(f"File database berhasil dikirim: {db_info['filename']} ({total_size} bytes)")
                self.update_transfer_status(f"Transfer selesai: {db_info['filename']} ({total_size} bytes)")
            
        except Exception as e:
            self.log(f"Error mengirim file database: {e}")
            self.update_transfer_status(f"Error transfer: {str(e)}")
            import traceback
            traceback.print_exc()
            
            if self.connected and self.socket:
                error_message = NetworkMessage(NetworkMessage.TYPE_ERROR, 
                                            {"error": f"Gagal mengirim file database: {str(e)}"},
                                            self.client_id)
                send_message(self.socket, error_message)

if __name__ == "__main__":
    app = ClientApp()
    app.run() 