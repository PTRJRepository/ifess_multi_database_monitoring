import socket
import json
import struct
import time

# Konstanta untuk komunikasi
DEFAULT_PORT = 5555
BUFFER_SIZE = 4096
ENCODING = 'utf-8'

class NetworkMessage:
    """Kelas untuk merepresentasikan pesan jaringan"""
    TYPE_QUERY = 'query'
    TYPE_RESULT = 'result'
    TYPE_ERROR = 'error'
    TYPE_REGISTER = 'register'
    TYPE_PING = 'ping'
    TYPE_PONG = 'pong'
    TYPE_FILE_REQUEST = 'file_request'  # Request untuk mentransfer file database
    TYPE_FILE_RESPONSE = 'file_response'  # Response file database
    TYPE_FILE_CHUNK = 'file_chunk'  # Chunk data file
    TYPE_FILE_COMPLETE = 'file_complete'  # Notifikasi file telah lengkap diterima
    TYPE_DB_QUERY = 'db_query'  # Query untuk dijalankan pada database yang sudah ditransfer
    
    def __init__(self, msg_type, data, client_id=None):
        self.msg_type = msg_type
        self.data = data
        self.client_id = client_id
        self.timestamp = time.time()
        
    def to_json(self):
        """Konversi pesan ke format JSON"""
        return json.dumps({
            'msg_type': self.msg_type,
            'data': self.data,
            'client_id': self.client_id,
            'timestamp': self.timestamp
        })
    
    @classmethod
    def from_json(cls, json_str):
        """Buat objek pesan dari string JSON"""
        try:
            data = json.loads(json_str)
            return cls(
                data.get('msg_type'),
                data.get('data'),
                data.get('client_id')
            )
        except json.JSONDecodeError:
            return cls(cls.TYPE_ERROR, "Invalid JSON message", None)

def send_message(sock, message):
    """
    Kirim pesan melalui socket.
    Protokol: [4-byte length prefix][message bytes]
    
    :param sock: Socket terhubung untuk mengirim data
    :param message: Objek NetworkMessage untuk dikirim
    :return: True jika berhasil, False jika gagal
    """
    try:
        # Konversi pesan ke JSON
        json_data = message.to_json()
        
        # Debug info tentang pesan yang akan dikirim
        msg_type = message.msg_type
        client_id = message.client_id
        data_keys = list(message.data.keys()) if isinstance(message.data, dict) else "non-dict"
        print(f"Sending message: type={msg_type}, client={client_id}, data_keys={data_keys}")
        
        if msg_type == 'result' and isinstance(message.data, dict) and 'result' in message.data:
            result_data = message.data['result']
            print(f"Result data: {len(result_data)} result sets")
            for i, rs in enumerate(result_data):
                headers = rs.get('headers', [])
                rows = rs.get('rows', [])
                print(f"  Result set {i+1}: {len(rows)} rows, {len(headers)} columns")
        
        # Konversi string JSON ke bytes
        data = json_data.encode(ENCODING)
        # Dapatkan panjang data dalam bytes
        msg_len = len(data)
        print(f"Message size: {msg_len} bytes")
        
        # Kirim panjang pesan sebagai unsigned int (4 bytes)
        sock.sendall(struct.pack('>I', msg_len))
        # Kirim data pesan
        sock.sendall(data)
        print(f"Message sent successfully")
        return True
    except ConnectionError as ce:
        print(f"Connection error while sending message: {ce}")
        return False
    except socket.timeout as to:
        print(f"Socket timeout while sending message: {to}")
        return False
    except (socket.error, struct.error) as e:
        print(f"Error saat mengirim pesan: {e}")
        return False

def receive_message(sock):
    """
    Terima pesan dari socket.
    Protokol: [4-byte length prefix][message bytes]
    
    :param sock: Socket terhubung untuk menerima data
    :return: Objek NetworkMessage atau None jika terjadi kesalahan
    """
    try:
        # Terima 4 byte pertama yang menunjukkan panjang pesan
        len_bytes = sock.recv(4)
        if not len_bytes or len(len_bytes) < 4:
            print("Koneksi terputus: tidak ada data panjang pesan")
            return None  # Koneksi ditutup
            
        # Unpack 4 bytes menjadi unsigned int
        msg_len = struct.unpack('>I', len_bytes)[0]
        
        # Validasi ukuran pesan untuk mencegah DoS
        if msg_len > 10 * 1024 * 1024:  # 10MB batas maksimum
            print(f"Pesan terlalu besar: {msg_len} bytes")
            return None
        
        # Terima semua data pesan
        data = b''
        remaining = msg_len
        start_time = time.time()
        timeout = 15  # 15 detik timeout untuk menerima seluruh pesan
        
        while remaining > 0:
            # Cek apakah sudah timeout
            if time.time() - start_time > timeout:
                print("Timeout saat menerima data pesan")
                return None
                
            chunk = sock.recv(min(remaining, BUFFER_SIZE))
            if not chunk:
                print("Koneksi terputus saat menerima data")
                return None  # Koneksi ditutup secara tidak terduga
            data += chunk
            remaining -= len(chunk)
            
        # Dekode data ke string JSON
        try:
            json_data = data.decode(ENCODING)
            # Parse pesan JSON
            return NetworkMessage.from_json(json_data)
        except UnicodeDecodeError as ude:
            print(f"Error saat mendekode pesan: {ude}")
            return None
        except json.JSONDecodeError as jde:
            print(f"Error saat parsing JSON: {jde}")
            return None
    except socket.timeout as to:
        print(f"Socket timeout: {to}")
        return None
    except ConnectionError as ce:
        print(f"Connection error: {ce}")
        return None
    except (socket.error, struct.error) as e:
        print(f"Error saat menerima pesan: {e}")
        return None 