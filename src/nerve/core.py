
import json
import os
import platform
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, Union, List


def load_external_config(config_path: str = "nerve.config") -> Dict[str, Any]:
    try:
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            return json.loads(raw)
        except Exception:
            pass
        config = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                config[key.strip()] = val.strip()
        return config
    except Exception:
        return {}


class NexusHub:
    def __init__(
        self,
        verbose: bool = False,
        on_connect: Optional[Callable[[str], None]] = None,
        on_disconnect: Optional[Callable[[str], None]] = None,
        heartbeat_interval: float = 5.0,
        config_path: str = "nerve.config",
    ) -> None:
        self.verbose = verbose
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.heartbeat_interval = heartbeat_interval
        self._clients = {}
        self._write_locks = {}
        self._lock = threading.Lock()
        self._running = False
        self._server = None
        self._active_sockets = set()
        self._stop_event = threading.Event()
        self.is_windows = platform.system() == "Windows"
        config = load_external_config(config_path)
        if self.is_windows:
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 50505))
            self.address = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = str(config.get("socket_path", "/tmp/nerve.sock"))
            self.socket_family = socket.AF_UNIX

    @property
    def connected_clients(self) -> List[str]:
        with self._lock:
            return list(self._clients.keys())

    def _log(self, color: str, message: str) -> None:
        print("\033[{}m[NERVE] {}\033[0m".format(color, message))

    def _send_to(self, client_id: str, payload: Any) -> bool:
        with self._lock:
            conn = self._clients.get(client_id)
            lock = self._write_locks.get(conn) if conn else None
        if conn is None or lock is None:
            return False
        try:
            with lock:
                conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            return True
        except OSError:
            return False

    def broadcast(self, payload: Any, exclude: Optional[str] = None) -> None:
        with self._lock:
            targets = list(self._clients.keys())
        for client_id in targets:
            if client_id == exclude:
                continue
            self._send_to(client_id, payload)

    def _start_heartbeat(self) -> None:
        if self.heartbeat_interval <= 0:
            return

        def _run() -> None:
            while self._running:
                if self._stop_event.wait(self.heartbeat_interval):
                    break
                dead = []
                with self._lock:
                    targets = list(self._clients.items())
                for client_id, conn in targets:
                    lock = None
                    with self._lock:
                        lock = self._write_locks.get(conn)
                    if lock is None:
                        continue
                    try:
                        with lock:
                            conn.sendall(
                                (json.dumps({"type": "ping"}) + "\n").encode("utf-8")
                            )
                    except OSError:
                        dead.append((client_id, conn))

                for client_id, conn in dead:
                    self._log("91", "Heartbeat failed for '{}'. Purging.".format(client_id))
                    self._remove_client(client_id, conn)

        threading.Thread(target=_run, daemon=True, name="nerve-heartbeat").start()

    def _remove_client(self, client_id: str, conn: socket.socket) -> None:
        with self._lock:
            current_conn = self._clients.get(client_id)
            if current_conn is conn:
                self._clients.pop(client_id, None)
                self._write_locks.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass
        if client_id and self.on_disconnect:
            try:
                self.on_disconnect(client_id)
            except Exception:
                pass

    def _handle_client(self, conn: socket.socket) -> None:
        client_id = None
        buffer = ""
        try:
            while self._running:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break

                buffer += chunk.decode("utf-8", errors="replace")
                if len(buffer) > 10 * 1024 * 1024:
                    break

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = json.loads(line)
                    except Exception as exc:
                        self._log("91", "Invalid JSON payload: {}".format(exc))
                        continue

                    msg_type = msg.get("type")

                    if msg_type == "ping":
                        continue

                    if msg_type == "pong":
                        continue

                    if msg_type == "register":
                        raw_id = msg.get("id")
                        if not raw_id or not isinstance(raw_id, str):
                            self._log("91", "Register message missing valid 'id' field.")
                            continue
                        client_id = raw_id
                        with self._lock:
                            if raw_id in self._clients:
                                self._log("93", "Re-registration of ID '{}': closing old connection.".format(raw_id))
                                old_conn = self._clients[raw_id]
                                try:
                                    old_conn.close()
                                except OSError:
                                    pass
                                self._clients.pop(raw_id, None)
                                self._write_locks.pop(old_conn, None)
                            self._clients[client_id] = conn
                            self._write_locks[conn] = threading.Lock()
                        self._log("92", "Registered: {}".format(client_id))
                        if self.on_connect:
                            try:
                                self.on_connect(client_id)
                            except Exception:
                                pass

                    elif msg_type == "send":
                        target = msg.get("to")
                        payload = msg.get("payload")
                        if not target or not isinstance(target, str):
                            self._log("91", "Send message missing valid 'to' field.")
                            continue
                        if self.verbose:
                            self._log(
                                "95",
                                "[VERBOSE] Routing '{}' → '{}': {}".format(client_id, target, payload),
                            )
                        success = self._send_to(target, payload)
                        if not success and self.verbose:
                            self._log("93", "Target '{}' not found or unreachable.".format(target))

                    elif msg_type == "broadcast":
                        payload = msg.get("payload")
                        if self.verbose:
                            self._log("95", "[VERBOSE] Broadcast from '{}': {}".format(client_id, payload))
                        self.broadcast(payload, exclude=client_id)

                    elif msg_type == "list":
                        client_list = self.connected_clients
                        try:
                            lock = None
                            with self._lock:
                                lock = self._write_locks.get(conn)
                            if lock is not None:
                                with lock:
                                    conn.sendall(
                                        (json.dumps({"type": "list", "clients": client_list}) + "\n").encode("utf-8")
                                    )
                        except OSError:
                            pass

                    else:
                        self._log("93", "Unknown message type: '{}' from '{}'.".format(msg_type, client_id))

        except Exception as exc:
            if self.verbose:
                self._log("91", "Unexpected error in client handler: {}".format(exc))
        finally:
            with self._lock:
                self._active_sockets.discard(conn)
            if client_id:
                self._remove_client(client_id, conn)
                self._log("93", "Disconnected: {}".format(client_id))
            else:
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        if not self.is_windows and os.path.exists(self.address):
            test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                test_sock.connect(self.address)
                test_sock.close()
                raise OSError("Address '{}' is already in use.".format(self.address))
            except OSError:
                try:
                    os.remove(self.address)
                except OSError:
                    pass

        self._server = socket.socket(self.socket_family, socket.SOCK_STREAM)
        if self.is_windows:
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._stop_event.clear()

        if not self.is_windows:
            orig_umask = os.umask(0o077)
            try:
                self._server.bind(self.address)
            finally:
                os.umask(orig_umask)
        else:
            self._server.bind(self.address)

        self._server.listen(50)
        self._running = True

        if not self.is_windows:
            os.chmod(str(self.address), 0o600)
            self._log("95", "Hub active via Unix Socket at {}".format(self.address))
        else:
            host, port = self.address
            self._log("95", "Hub active via TCP at {}:{}".format(host, port))

        self._start_heartbeat()

        try:
            while self._running:
                try:
                    conn, _ = self._server.accept()
                    with self._lock:
                        if not self._running:
                            conn.close()
                            break
                        self._active_sockets.add(conn)
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn,),
                        daemon=True,
                        name="nerve-client",
                    ).start()
                except OSError:
                    break
        finally:
            self._running = False
            self._log("93", "Hub has stopped.")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        with self._lock:
            active_socks = list(self._active_sockets)
            self._active_sockets.clear()
        for conn in active_socks:
            try:
                conn.close()
            except OSError:
                pass
        with self._lock:
            client_items = list(self._clients.items())
        for cid, conn in client_items:
            self._remove_client(cid, conn)
        self._log("93", "Hub shutdown complete.")


class NexusClient:
    def __init__(
        self,
        retry_interval: float = 2.0,
        config_path: str = "nerve.config",
    ) -> None:
        self.retry_interval = retry_interval
        self.client_id = None
        self.is_windows = platform.system() == "Windows"
        config = load_external_config(config_path)

        if self.is_windows:
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 50505))
            self.address: Union[Tuple[str, int], str] = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = str(config.get("socket_path", "/tmp/nerve.sock"))
            self.socket_family = socket.AF_UNIX

        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._closed = False
        self._listening = False
        self._list_lock = threading.Lock()
        self._list_event = threading.Event()
        self._list_result = None

    def _make_socket(self) -> socket.socket:
        return socket.socket(self.socket_family, socket.SOCK_STREAM)

    def connect(self, client_id: str) -> None:
        if not client_id or not isinstance(client_id, str):
            raise ValueError("client_id must be a non-empty string.")
        self.client_id = client_id
        self._closed = False

        while not self._closed:
            sock = None
            try:
                sock = self._make_socket()
                sock.connect(self.address)
                with self._lock:
                    if self._closed:
                        sock.close()
                        return
                    self._socket = sock
                self._send_raw({"type": "register", "id": client_id})
                print(f"[NERVE] Connected to hub as '{client_id}'.")
                return
            except OSError as exc:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
                with self._lock:
                    self._socket = None
                if self._closed:
                    return
                print(
                    f"[NERVE] Hub unavailable ({exc}). Retrying in "
                    f"{self.retry_interval}s..."
                )
                time.sleep(self.retry_interval)

    def disconnect(self) -> None:
        with self._lock:
            self._closed = True
            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
        print(f"[NERVE] '{self.client_id}' disconnected.")

    def _send_raw(self, message: Dict[str, Any]) -> None:
        with self._lock:
            sock = self._socket
        if sock is None:
            raise OSError("Not connected to hub.")
        sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def send(self, to: str, payload: Any) -> None:
        if not to or not isinstance(to, str):
            raise ValueError("'to' must be a non-empty string.")
        try:
            self._send_raw({"type": "send", "to": to, "payload": payload})
        except OSError as exc:
            print(f"[NERVE] Send failed ({exc}). Reconnecting...")
            if self.client_id is not None:
                self.connect(self.client_id)
            self._send_raw({"type": "send", "to": to, "payload": payload})

    def broadcast(self, payload: Any) -> None:
        try:
            self._send_raw({"type": "broadcast", "payload": payload})
        except OSError as exc:
            print(f"[NERVE] Broadcast failed ({exc}). Reconnecting...")
            if self.client_id is not None:
                self.connect(self.client_id)
            self._send_raw({"type": "broadcast", "payload": payload})

    def list_clients(self) -> List[str]:
        if self._listening:
            with self._list_lock:
                self._list_result = None
                self._list_event.clear()
                try:
                    self._send_raw({"type": "list"})
                except OSError:
                    return []
                if self._list_event.wait(timeout=2.0):
                    return self._list_result or []
                return []
        else:
            try:
                self._send_raw({"type": "list"})
            except OSError:
                return []
            with self._lock:
                sock = self._socket
            if sock is None:
                return []
            sock.settimeout(2.0)
            buffer = ""
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "list":
                                return msg.get("clients", [])
                        except json.JSONDecodeError:
                            pass
            except socket.timeout:
                pass
            finally:
                sock.settimeout(None)
            return []

    def listen(
        self,
        callback: Callable[[Any], None],
        on_reconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._listening = True
        def _listener() -> None:
            while not self._closed:
                buffer = ""
                with self._lock:
                    sock = self._socket
                if sock is None:
                    if self._closed:
                        break
                    time.sleep(self.retry_interval)
                    continue
                try:
                    while not self._closed:
                        try:
                            chunk = sock.recv(4096)
                        except OSError as exc:
                            if self._closed:
                                break
                            print(f"[NERVE] Connection error: {exc}. Reconnecting...")
                            break
                        if not chunk:
                            if self._closed:
                                break
                            print("[NERVE] Hub closed connection. Reconnecting...")
                            break

                        buffer += chunk.decode("utf-8", errors="replace")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(payload, dict):
                                msg_type = payload.get("type")
                                if msg_type in ("ping", "pong"):
                                    continue
                                if msg_type == "list":
                                    self._list_result = payload.get("clients", [])
                                    self._list_event.set()
                                    continue
                            try:
                                callback(payload)
                            except Exception as exc:
                                print(f"[NERVE] Error in message callback: {exc}")
                except Exception as exc:
                    if self._closed:
                        break
                    print(f"[NERVE] Unexpected listener error: {exc}")

                if self._closed:
                    break

                if self.client_id is not None:
                    self.connect(self.client_id)
                if on_reconnect and not self._closed:
                    try:
                        on_reconnect()
                    except Exception:
                        pass

        threading.Thread(
            target=_listener,
            daemon=True,
            name=f"nerve-listen-{self.client_id}",
        ).start()
