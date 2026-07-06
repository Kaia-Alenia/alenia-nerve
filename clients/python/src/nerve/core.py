import json
import os
import platform
import socket
import threading
import time
import ssl
from collections import deque
from typing import Any, Callable, Dict, Optional, Tuple, Union, List


def load_external_config(config_path: str = "nerve.config") -> Dict[str, Any]:
    """
    Load an external configuration file for Nerve.

    Supports both JSON and simple key=value text formats.

    Args:
        config_path (str, optional): Path to the configuration file. Defaults to "nerve.config".

    Returns:
        Dict[str, Any]: A dictionary containing configuration values. Returns an empty
            dictionary if the file does not exist or cannot be read.
    """
    try:
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
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
    except OSError:
        return {}


class NexusHub:
    """
    The central message broker (Server) for Nerve IPC.

    Coordinates message routing between connected NexusClient instances, using
    either Unix Domain Sockets or TCP depending on the host platform.
    """

    def __init__(
        self,
        verbose: bool = False,
        on_connect: Optional[Callable[[str], None]] = None,
        on_disconnect: Optional[Callable[[str], None]] = None,
        heartbeat_interval: float = 5.0,
        config_path: str = "nerve.config",
        auth_token: Optional[str] = None,
        max_connections: Optional[int] = None,
        rate_limit_messages_per_sec: Optional[float] = None,
        rate_limit_bytes_per_min: Optional[int] = None,
        ssl_context: Optional["ssl.SSLContext"] = None,
        ssl_cert: Optional[str] = None,
        ssl_key: Optional[str] = None,
    ) -> None:
        """
        Initialize the NexusHub server.

        Args:
            verbose (bool): Whether to log detailed message routing info. Defaults to False.
            on_connect (Optional[Callable[[str], None]]): Callback executed when a client connects.
                Passed the `client_id` as an argument.
            on_disconnect (Optional[Callable[[str], None]]): Callback executed when a client disconnects.
                Passed the `client_id` as an argument.
            heartbeat_interval (float): Interval in seconds between heartbeat pings sent to clients. Defaults to 5.0.
            config_path (str): Path to external configuration file. Defaults to "nerve.config".
        """
        self.verbose: bool = verbose
        self.on_connect: Optional[Callable[[str], None]] = on_connect
        self.on_disconnect: Optional[Callable[[str], None]] = on_disconnect
        self.heartbeat_interval: float = heartbeat_interval
        self._clients: Dict[str, socket.socket] = {}
        self._write_locks: Dict[socket.socket, threading.Lock] = {}
        self._lock: threading.Lock = threading.Lock()
        self._running: bool = False
        self._server: Optional[socket.socket] = None
        self._active_sockets: set = set()
        self._stop_event: threading.Event = threading.Event()

        self._uptime_start: float = time.time()
        self._total_messages_sent: int = 0
        self._total_messages_received: int = 0
        self._total_bytes_sent: int = 0
        self._total_bytes_received: int = 0

        self.is_windows: bool = platform.system() == "Windows"
        config = load_external_config(config_path)
        self.auth_token = auth_token or config.get("auth_token")

        raw_max = (
            max_connections
            if max_connections is not None
            else config.get("max_connections")
        )
        self.max_connections = int(raw_max) if raw_max is not None else None

        raw_rate = (
            rate_limit_messages_per_sec
            if rate_limit_messages_per_sec is not None
            else config.get("rate_limit_messages_per_sec")
        )
        self.rate_limit_messages_per_sec = (
            float(raw_rate) if raw_rate is not None else None
        )

        raw_byte_rate = (
            rate_limit_bytes_per_min
            if rate_limit_bytes_per_min is not None
            else config.get("rate_limit_bytes_per_min")
        )
        self.rate_limit_bytes_per_min = (
            int(raw_byte_rate) if raw_byte_rate is not None else None
        )

        self.ssl_context = ssl_context
        if self.ssl_context is None:
            cert = ssl_cert or config.get("ssl_cert")
            key = ssl_key or config.get("ssl_key")
            if cert and key:
                self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                self.ssl_context.load_cert_chain(certfile=cert, keyfile=key)
        if self.is_windows:
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 50505))
            self.address: Union[Tuple[str, int], str] = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = str(config.get("socket_path", "/tmp/nerve.sock"))
            self.socket_family = socket.AF_UNIX

    def update_auth_token(self, new_token: Optional[str]) -> None:
        """Update the authentication token dynamically."""
        self.auth_token = new_token
        self._log("93", "Auth token updated dynamically.")

    @property
    def connected_clients(self) -> List[str]:
        """
        List of currently connected client IDs.

        Returns:
            List[str]: A list of active client IDs registered with the Hub.
        """
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
            serialized = json.dumps(payload) + "\n"
        except (TypeError, ValueError):
            return False
        try:
            raw_bytes = serialized.encode("utf-8")
            with lock:
                conn.sendall(raw_bytes)
            with self._lock:
                self._total_bytes_sent += len(raw_bytes)
                self._total_messages_sent += 1
            return True
        except OSError:
            return False

    def _send_raw_bytes_to(self, client_id: str, raw_bytes: bytes) -> bool:
        with self._lock:
            conn = self._clients.get(client_id)
            lock = self._write_locks.get(conn) if conn else None
        if conn is None or lock is None:
            return False
        try:
            with lock:
                conn.sendall(raw_bytes)
            with self._lock:
                self._total_bytes_sent += len(raw_bytes)
                self._total_messages_sent += 1
            return True
        except OSError:
            return False

    def broadcast(self, payload: Any, exclude: Optional[str] = None) -> bool:
        try:
            raw_bytes = (json.dumps(payload) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            return False
        with self._lock:
            targets = list(self._clients.keys())
        for client_id in targets:
            if client_id == exclude:
                continue
            self._send_raw_bytes_to(client_id, raw_bytes)
        return True

    def _start_heartbeat(self) -> None:
        if self.heartbeat_interval <= 0:
            return

        ping_payload = (json.dumps({"type": "ping"}) + "\n").encode("utf-8")

        def _run() -> None:
            while self._running:
                if self._stop_event.wait(self.heartbeat_interval):
                    break
                dead = []
                with self._lock:
                    targets = [
                        (client_id, conn, self._write_locks.get(conn))
                        for client_id, conn in self._clients.items()
                    ]
                for client_id, conn, lock in targets:
                    if lock is None:
                        continue
                    try:
                        with lock:
                            conn.sendall(ping_payload)
                    except OSError:
                        dead.append((client_id, conn))

                for client_id, conn in dead:
                    self._log(
                        "91", "Heartbeat failed for '{}'. Purging.".format(client_id)
                    )
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
        msg_times = deque()
        byte_times = deque()
        try:
            while self._running:
                try:
                    chunk = conn.recv(4096)
                except (socket.timeout, TimeoutError):
                    self._log("91", "Client connection timeout.")
                    break
                except OSError:
                    break
                if not chunk:
                    break

                with self._lock:
                    self._total_bytes_received += len(chunk)

                if self.rate_limit_bytes_per_min is not None:
                    now = time.time()
                    byte_times.append((now, len(chunk)))
                    while byte_times and byte_times[0][0] < now - 60.0:
                        byte_times.popleft()
                    if (
                        sum(size for _, size in byte_times)
                        > self.rate_limit_bytes_per_min
                    ):
                        self._log("91", "Byte rate limit exceeded for client.")
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
                        with self._lock:
                            self._total_messages_received += 1
                    except json.JSONDecodeError as exc:
                        self._log("91", "Invalid JSON payload: {}".format(exc))
                        continue

                    if self.rate_limit_messages_per_sec is not None:
                        now = time.time()
                        msg_times.append(now)
                        while msg_times and msg_times[0] < now - 1.0:
                            msg_times.popleft()
                        if len(msg_times) > self.rate_limit_messages_per_sec:
                            self._log("91", "Rate limit exceeded for client.")
                            return

                    msg_type = msg.get("type")

                    if msg_type == "ping":
                        continue

                    if msg_type == "pong":
                        continue

                    if msg_type == "register":
                        raw_id = msg.get("id")
                        if not raw_id or not isinstance(raw_id, str):
                            self._log(
                                "91", "Register message missing valid 'id' field."
                            )
                            continue

                        if self.auth_token:
                            client_token = msg.get("token")
                            if not client_token or client_token != self.auth_token:
                                self._log(
                                    "91",
                                    "Authentication failed for client registration.",
                                )
                                try:
                                    conn.sendall(
                                        (
                                            json.dumps(
                                                {
                                                    "type": "registered",
                                                    "status": "failed",
                                                    "reason": "auth",
                                                }
                                            )
                                            + "\n"
                                        ).encode("utf-8")
                                    )
                                except OSError:
                                    pass
                                break

                        client_id = raw_id
                        with self._lock:
                            if raw_id in self._clients:
                                self._log(
                                    "93",
                                    "Re-registration of ID '{}': closing old connection.".format(
                                        raw_id
                                    ),
                                )
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
                        try:
                            conn.sendall(
                                (
                                    json.dumps(
                                        {"type": "registered", "status": "success"}
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                        except OSError:
                            pass
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
                                "[VERBOSE] Routing '{}' → '{}'".format(
                                    client_id, target
                                ),
                            )
                        success = self._send_to(target, payload)
                        if not success and self.verbose:
                            self._log(
                                "93",
                                "Target '{}' not found or unreachable.".format(target),
                            )

                    elif msg_type == "broadcast":
                        payload = msg.get("payload")
                        if self.verbose:
                            self._log(
                                "95", "[VERBOSE] Broadcast from '{}'".format(client_id)
                            )
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
                                        (
                                            json.dumps(
                                                {"type": "list", "clients": client_list}
                                            )
                                            + "\n"
                                        ).encode("utf-8")
                                    )
                        except OSError:
                            pass

                    elif msg_type == "metrics":
                        with self._lock:
                            metrics = {
                                "type": "metrics",
                                "uptime": time.time() - self._uptime_start,
                                "clients": len(self._clients),
                                "total_messages_sent": self._total_messages_sent,
                                "total_messages_received": self._total_messages_received,
                                "total_bytes_sent": self._total_bytes_sent,
                                "total_bytes_received": self._total_bytes_received,
                            }
                        try:
                            lock = None
                            with self._lock:
                                lock = self._write_locks.get(conn)
                            if lock is not None:
                                with lock:
                                    conn.sendall(
                                        (json.dumps(metrics) + "\n").encode("utf-8")
                                    )
                        except OSError:
                            pass

                    else:
                        self._log(
                            "93",
                            "Unknown message type: '{}' from '{}'.".format(
                                msg_type, client_id
                            ),
                        )

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
        if (
            not self.is_windows
            and isinstance(self.address, str)
            and os.path.exists(self.address)
        ):
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

        if not self.is_windows and isinstance(self.address, str):
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
            if isinstance(self.address, tuple):
                host, port = self.address
                self._log("95", "Hub active via TCP at {}:{}".format(host, port))
            else:
                self._log("95", "Hub active via TCP at {}".format(self.address))

        self._server.settimeout(0.5)
        self._start_heartbeat()

        try:
            while self._running and self._server:
                try:
                    conn, _ = self._server.accept()
                    conn.settimeout(10.0)
                    with self._lock:
                        if not self._running:
                            conn.close()
                            break
                        if (
                            self.max_connections is not None
                            and len(self._active_sockets) >= self.max_connections
                        ):
                            conn.close()
                            continue

                    if self.ssl_context and self.socket_family == socket.AF_INET:
                        try:
                            conn = self.ssl_context.wrap_socket(conn, server_side=True)
                        except ssl.SSLError as e:
                            self._log("91", "SSL handshake failed: {}".format(e))
                            conn.close()
                            continue

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
                except (socket.timeout, TimeoutError):
                    continue
                except OSError:
                    break
        except Exception as exc:
            self._log("91", "Error in server acceptance loop: {}".format(exc))
        finally:
            self.stop()

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
    """
    Client interface for Nerve IPC.

    Allows connection to a NexusHub, enabling bidirectional message passing
    and broadcasting to other connected nodes. Handles auto-reconnection implicitly.
    """

    def __init__(
        self,
        retry_interval: float = 2.0,
        config_path: str = "nerve.config",
        auth_token: Optional[str] = None,
        ssl_context: Optional["ssl.SSLContext"] = None,
        ssl_cert: Optional[str] = None,
        ssl_key: Optional[str] = None,
        ssl_ca: Optional[str] = None,
    ) -> None:
        self.retry_interval: float = retry_interval
        self.client_id: Optional[str] = None
        self.is_windows: bool = platform.system() == "Windows"
        config = load_external_config(config_path)
        self.auth_token = auth_token or config.get("auth_token")

        self.ssl_context = ssl_context
        if self.ssl_context is None:
            use_ssl = config.get("use_ssl", False)
            if isinstance(use_ssl, str):
                use_ssl = use_ssl.lower() in ("true", "1", "yes")
            cert = ssl_cert or config.get("ssl_cert")
            key = ssl_key or config.get("ssl_key")
            ca = ssl_ca or config.get("ssl_ca")
            insecure = config.get("ssl_insecure", False)
            if isinstance(insecure, str):
                insecure = insecure.lower() in ("true", "1", "yes")

            if use_ssl or cert or key or ca:
                if insecure:
                    self.ssl_context = ssl._create_unverified_context()
                else:
                    self.ssl_context = ssl.create_default_context(cafile=ca)
                if cert and key:
                    self.ssl_context.load_cert_chain(certfile=cert, keyfile=key)

        if self.is_windows:
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 50505))
            self.address: Union[Tuple[str, int], str] = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = str(config.get("socket_path", "/tmp/nerve.sock"))
            self.socket_family = socket.AF_UNIX

        self._socket: Optional[socket.socket] = None
        self._lock: threading.Lock = threading.Lock()
        self._closed: bool = False
        self._listening: bool = False
        self._list_lock: threading.Lock = threading.Lock()
        self._list_event: threading.Event = threading.Event()
        self._list_result: Optional[List[str]] = None
        self._metrics_lock: threading.Lock = threading.Lock()
        self._metrics_event: threading.Event = threading.Event()
        self._metrics_result: Optional[Dict[str, Any]] = None
        self._write_lock: threading.Lock = threading.Lock()
        self._read_lock: threading.Lock = threading.Lock()

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
                if self.ssl_context and self.socket_family == socket.AF_INET:
                    hostname = (
                        self.address[0] if isinstance(self.address, tuple) else None
                    )
                    sock = self.ssl_context.wrap_socket(sock, server_hostname=hostname)

                sock.connect(self.address)

                reg_msg = {"type": "register", "id": client_id}
                if self.auth_token:
                    reg_msg["token"] = self.auth_token

                sock.sendall((json.dumps(reg_msg) + "\n").encode("utf-8"))

                sock.settimeout(5.0)
                buffer = ""
                auth_failed = False
                success = False
                while not self._closed:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    if "\n" in buffer:
                        line, _ = buffer.split("\n", 1)
                        try:
                            resp = json.loads(line)
                            if resp.get("type") == "registered":
                                if resp.get("status") == "success":
                                    success = True
                                elif (
                                    resp.get("status") == "failed"
                                    and resp.get("reason") == "auth"
                                ):
                                    auth_failed = True
                                break
                        except json.JSONDecodeError:
                            pass

                if auth_failed:
                    self._closed = True
                    try:
                        sock.close()
                    except OSError:
                        pass
                    with self._lock:
                        self._socket = None
                    print(f"[NERVE] Connected to hub as '{client_id}' failed (auth).")
                    return

                if not success:
                    raise OSError("Handshake failed or connection closed.")

                sock.settimeout(None)
                with self._lock:
                    if self._closed:
                        sock.close()
                        return
                    self._socket = sock
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
        """
        Disconnect gracefully from the Hub and disable auto-reconnection.
        """
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
        with self._write_lock:
            sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def _send_with_retry(self, message: Dict[str, Any], action_name: str) -> None:
        try:
            self._send_raw(message)
        except OSError as exc:
            print(f"[NERVE] {action_name} failed ({exc}). Reconnecting...")
            if self.client_id is not None:
                self.connect(self.client_id)
            self._send_raw(message)

    def send(self, to: str, payload: Any) -> None:
        """
        Send a payload to a specific client node by ID.

        If sending fails, attempts to reconnect and send again.

        Args:
            to (str): Target client ID to send the payload to.
            payload (Any): The payload to send (must be JSON serializable).

        Raises:
            ValueError: If 'to' is invalid.
        """
        if not to or not isinstance(to, str):
            raise ValueError("'to' must be a non-empty string.")
        self._send_with_retry({"type": "send", "to": to, "payload": payload}, "Send")

    def broadcast(self, payload: Any) -> None:
        """
        Broadcast a payload to all connected clients except self.

        If broadcasting fails, attempts to reconnect and broadcast again.

        Args:
            payload (Any): The payload to broadcast (must be JSON serializable).
        """
        self._send_with_retry({"type": "broadcast", "payload": payload}, "Broadcast")

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
            with self._read_lock:
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

    def get_metrics(self) -> Dict[str, Any]:
        """Request hub metrics."""
        if self._listening:
            with self._metrics_lock:
                self._metrics_result = None
                self._metrics_event.clear()
                try:
                    self._send_raw({"type": "metrics"})
                except OSError:
                    return {}
                if self._metrics_event.wait(timeout=2.0):
                    return self._metrics_result or {}
                return {}
        else:
            with self._read_lock:
                try:
                    self._send_raw({"type": "metrics"})
                except OSError:
                    return {}
                with self._lock:
                    sock = self._socket
                if sock is None:
                    return {}
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
                                if msg.get("type") == "metrics":
                                    return msg
                            except json.JSONDecodeError:
                                pass
                except socket.timeout:
                    pass
                finally:
                    sock.settimeout(None)
                return {}

    def listen(
        self,
        callback: Callable[[Any], None],
        on_reconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Spawn a daemon thread to listen for incoming stream data from the Hub.

        Args:
            callback (Callable[[Any], None]): A function to invoke when a payload is received.
            on_reconnect (Optional[Callable[[], None]], optional): An optional callback triggered
                after successfully reconnecting to the Hub.
        """
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
                                if msg_type == "metrics":
                                    self._metrics_result = payload
                                    self._metrics_event.set()
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
