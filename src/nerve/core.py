import socket
import os
import json
import threading
import platform
import time

def load_external_config():
    config_path = "nerve.config"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception:
            config = {}
            try:
                with open(config_path, "r") as f:
                    for line in f:
                        if "=" in line:
                            key, val = line.strip().split("=", 1)
                            config[key.strip()] = val.strip()
                return config
            except Exception:
                pass
    return {}

class NexusHub:
    def __init__(self, verbose=False):
        self.is_windows = platform.system() == "Windows"
        self.clients = {}
        self.verbose = verbose
        
        config = load_external_config()
        
        if self.is_windows:
            port = int(config.get("port", 50505))
            host = config.get("host", "127.0.0.1")
            self.address = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = config.get("socket_path", "/tmp/nerve.sock")
            self.socket_family = socket.AF_UNIX

    def start_heartbeat(self):
        def run():
            while True:
                time.sleep(5)
                dead_clients = []
                for client_id, conn in list(self.clients.items()):
                    try:
                        conn.send((json.dumps({"type": "ping"}) + "\n").encode())
                    except Exception:
                        dead_clients.append(client_id)
                
                for client_id in dead_clients:
                    print(f"\033[91m[NERVE] Heartbeat failed for client '{client_id}'. Purging connection.\033[0m")
                    if client_id in self.clients:
                        try:
                            self.clients[client_id].close()
                        except Exception:
                            pass
                        del self.clients[client_id]
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        if not self.is_windows:
            if os.path.exists(self.address):
                os.remove(self.address)

        server = socket.socket(self.socket_family, socket.SOCK_STREAM)
        
        if self.is_windows:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server.bind(self.address)
        server.listen(5)
        
        self.start_heartbeat()
        
        if not self.is_windows:
            os.chmod(self.address, 0o666) 
            print(f"\033[95m[NERVE] Hub active via Unix Socket at {self.address}\033[0m")
        else:
            print(f"\033[95m[NERVE] Hub active via TCP Port at {self.address[0]}:{self.address[1]}\033[0m")
        
        while True:
            try:
                conn, _ = server.accept()
                threading.Thread(target=self.handle_client, args=(conn,)).start()
            except Exception as e:
                print(f"\033[91m[NERVE] Error accepting connection: {e}\033[0m")
                break

    def handle_client(self, conn):
        client_id = None
        buffer = ""
        try:
            while True:
                data = conn.recv(4096)
                if not data: break
                
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    
                    try:
                        msg = json.loads(line)
                    except Exception as e:
                        print(f"\033[91m[NERVE] Invalid Payload: Failed to decode JSON ({e})\033[0m")
                        continue
                    
                    if msg.get('type') == 'ping':
                        continue
                        
                    if msg.get('type') == 'register':
                        client_id = msg['id']
                        self.clients[client_id] = conn
                        print(f"\033[92m[NERVE] Registered: {client_id}\033[0m")
                    
                    elif msg.get('type') == 'send':
                        target = msg['to']
                        if self.verbose:
                            print(f"\033[95m[VERBOSE] Routing message from '{client_id}' to '{target}': {msg['payload']}\033[0m")
                            
                        if target in self.clients:
                            try:
                                self.clients[target].send((json.dumps(msg['payload']) + "\n").encode())
                            except Exception as e:
                                print(f"\033[91m[NERVE] Error sending message to {target}: {e}\033[0m")
        except Exception:
            pass
        finally:
            if client_id in self.clients:
                del self.clients[client_id]
            conn.close()
            if client_id:
                print(f"\033[93m[NERVE] Disconnected: {client_id}\033[0m")

class NexusClient:
    def __init__(self):
        self.is_windows = platform.system() == "Windows"
        self.client_id = None
        
        config = load_external_config()
        
        if self.is_windows:
            port = int(config.get("port", 50505))
            host = config.get("host", "127.0.0.1")
            self.address = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = config.get("socket_path", "/tmp/nerve.sock")
            self.socket_family = socket.AF_UNIX
            
        self.socket = socket.socket(self.socket_family, socket.SOCK_STREAM)

    def connect(self, client_id):
        self.client_id = client_id
        while True:
            try:
                self.socket = socket.socket(self.socket_family, socket.SOCK_STREAM)
                self.socket.connect(self.address)
                self.socket.send((json.dumps({'type': 'register', 'id': client_id}) + "\n").encode())
                print(f"[CLIENT] Successfully connected to Nerve Hub as '{client_id}'")
                break
            except Exception as e:
                print(f"[CLIENT] Connection to Hub failed. Retrying in 2 seconds... ({e})")
                time.sleep(2)

    def send(self, to, payload):
        try:
            self.socket.send((json.dumps({'type': 'send', 'to': to, 'payload': payload}) + "\n").encode())
        except Exception as e:
            print(f"[CLIENT] Send failed ({e}). Reconnecting...")
            self.connect(self.client_id)

    def listen(self, callback):
        def _listen():
            while True:
                buffer = ""
                while True:
                    try:
                        data = self.socket.recv(4096)
                        if not data:
                            print("[CLIENT] Connection closed by remote host. Triggering auto-reconnect...")
                            break
                        buffer += data.decode()
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line.strip():
                                try:
                                    payload = json.loads(line)
                                    if payload.get("type") == "ping":
                                        continue
                                    callback(payload)
                                except Exception:
                                    pass
                    except Exception as e:
                        print(f"[CLIENT] Connection error: {e}. Triggering auto-reconnect...")
                        break
                
                self.connect(self.client_id)
        threading.Thread(target=_listen, daemon=True).start()
