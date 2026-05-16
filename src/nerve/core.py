from __future__ import annotations

import json
import os
import platform
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, Union


def load_external_config(config_path: str = "nerve.config") -> Dict[str, Any]:
    """Load configuration from a ``nerve.config`` file.

    The file can be formatted as JSON or as simple ``key=value`` pairs.
    Returns an empty dict if the file does not exist or cannot be parsed.

    Args:
        config_path: Path to the configuration file.  Defaults to
            ``nerve.config`` in the current working directory.

    Returns:
        A dictionary with the parsed configuration values.
    """
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    config: Dict[str, Any] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            config[key.strip()] = val.strip()
    return config


class NexusHub:
    """Central message-routing hub for the Nerve IPC engine.

    ``NexusHub`` manages a registry of named ``NexusClient`` connections and
    routes JSON payloads between them through a single persistent socket.

    On **Linux / macOS** the hub uses a Unix Domain Socket (``AF_UNIX``) for
    the lowest possible IPC latency.  On **Windows** it falls back to a local
    TCP socket (``AF_INET``) to retain full cross-platform compatibility.

    Args:
        verbose:        When ``True``, every routed message is printed to
                        stdout with colour coding.
        on_connect:     Optional callback invoked with ``(client_id: str)``
                        whenever a new client registers.
        on_disconnect:  Optional callback invoked with ``(client_id: str)``
                        whenever a client disconnects.
        heartbeat_interval: Seconds between heartbeat pings sent to all
                        connected clients.  Set to ``0`` to disable.
        config_path:    Path to an optional ``nerve.config`` file.

    Example::

        hub = NexusHub(verbose=True)
        hub.start()   # blocks; run in a daemon thread or subprocess
    """

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

        self._clients: Dict[str, socket.socket] = {}
        self._lock = threading.Lock()
        self._running = False
        self._server: Optional[socket.socket] = None

        self.is_windows: bool = platform.system() == "Windows"
        config = load_external_config(config_path)

        if self.is_windows:
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 50505))
            self.address: Union[Tuple[str, int], str] = (host, port)
            self.socket_family = socket.AF_INET
        else:
            self.address = str(config.get("socket_path", "/tmp/nerve.sock"))
            self.socket_family = socket.AF_UNIX

    @property
    def connected_clients(self) -> list[str]:
        """Return a snapshot list of currently registered client IDs."""
        with self._lock:
            return list(self._clients.keys())

    def _log(self, color: str, message: str) -> None:
        print(f"\033[{color}m[NERVE] {message}\033[0m")

    def _send_to(self, client_id: str, payload: Any) -> bool:
        """Send *payload* to the client identified by *client_id*.

        Args:
            client_id: Target client identifier.
            payload:   JSON-serialisable object to deliver.

        Returns:
            ``True`` on success, ``False`` if the client is unreachable.
        """
        with self._lock:
            conn = self._clients.get(client_id)
        if conn is None:
            return False
        try:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            return True
        except OSError:
            return False

    def broadcast(self, payload: Any, exclude: Optional[str] = None) -> None:
        """Send *payload* to every registered client.

        Args:
            payload: JSON-serialisable object to broadcast.
            exclude: Optional client ID to skip (useful for not echoing back
                     to the sender).
        """
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
                time.sleep(self.heartbeat_interval)
                dead: list[str] = []
                with self._lock:
                    targets = list(self._clients.items())
                for client_id, conn in targets:
                    try:
                        conn.sendall(
                            (json.dumps({"type": "ping"}) + "\n").encode("utf-8")
                        )
                    except OSError:
                        dead.append(client_id)

                for client_id in dead:
                    self._log("91", f"Heartbeat failed for '{client_id}'. Purging.")
                    self._remove_client(client_id)

        threading.Thread(target=_run, daemon=True, name="nerve-heartbeat").start()

    def _remove_client(self, client_id: str) -> None:
        with self._lock:
            conn = self._clients.pop(client_id, None)
        if conn is not None:
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
        client_id: Optional[str] = None
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
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg: Dict[str, Any] = json.loads(line)
                    except json.JSONDecodeError as exc:
                        self._log("91", f"Invalid JSON payload: {exc}")
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
                            self._clients[client_id] = conn
                        self._log("92", f"Registered: {client_id}")
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
                                f"[VERBOSE] Routing '{client_id}' → '{target}': {payload}",
                            )
                        success = self._send_to(target, payload)
                        if not success and self.verbose:
                            self._log("93", f"Target '{target}' not found or unreachable.")

                    elif msg_type == "broadcast":
                        payload = msg.get("payload")
                        if self.verbose:
                            self._log("95", f"[VERBOSE] Broadcast from '{client_id}': {payload}")
                        self.broadcast(payload, exclude=client_id)

                    elif msg_type == "list":
                        client_list = self.connected_clients
                        try:
                            conn.sendall(
                                (json.dumps({"type": "list", "clients": client_list}) + "\n").encode("utf-8")
                            )
                        except OSError:
                            pass

                    else:
                        self._log("93", f"Unknown message type: '{msg_type}' from '{client_id}'.")

        except Exception as exc:
            if self.verbose:
                self._log("91", f"Unexpected error in client handler: {exc}")
        finally:
            if client_id:
                self._remove_client(client_id)
                self._log("93", f"Disconnected: {client_id}")
            else:
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        """Start the Nerve Hub and block until stopped.

        The hub accepts new connections in a loop, spawning a daemon thread
        per client.  Call :meth:`stop` from another thread to shut down
        gracefully.

        Raises:
            OSError: If the socket cannot be bound (e.g. port already in use).
        """
        if not self.is_windows and os.path.exists(self.address):
            os.remove(self.address)

        self._server = socket.socket(self.socket_family, socket.SOCK_STREAM)
        if self.is_windows:
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._server.bind(self.address)
        self._server.listen(50)
        self._running = True

        if not self.is_windows:
            os.chmod(str(self.address), 0o666)
            self._log("95", f"Hub active via Unix Socket at {self.address}")
        else:
            host, port = self.address  # type: ignore[misc]
            self._log("95", f"Hub active via TCP at {host}:{port}")

        self._start_heartbeat()

        try:
            while self._running:
                try:
                    conn, _ = self._server.accept()
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
        """Gracefully stop the hub and close all client connections.

        Safe to call from any thread.
        """
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        with self._lock:
            client_ids = list(self._clients.keys())
        for cid in client_ids:
            self._remove_client(cid)
        self._log("93", "Hub shutdown complete.")


class NexusClient:
    """Nerve IPC client node.

    ``NexusClient`` connects to a running :class:`NexusHub` and exposes a
    simple API to send targeted messages, broadcast to all nodes, and listen
    for incoming payloads via an asynchronous callback.

    Args:
        retry_interval: Seconds to wait between reconnection attempts.
        config_path:    Path to an optional ``nerve.config`` file.

    Example::

        client = NexusClient()
        client.connect("my_tool")

        def on_message(data):
            print("Got:", data)

        client.listen(on_message)
        client.send("other_tool", {"status": "ready"})
    """

    def __init__(
        self,
        retry_interval: float = 2.0,
        config_path: str = "nerve.config",
    ) -> None:
        self.retry_interval = retry_interval
        self.client_id: Optional[str] = None

        self.is_windows: bool = platform.system() == "Windows"
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

    def _make_socket(self) -> socket.socket:
        return socket.socket(self.socket_family, socket.SOCK_STREAM)

    def connect(self, client_id: str) -> None:
        """Connect to the hub and register under *client_id*.

        Blocks and retries indefinitely until a connection is established.
        Subsequent calls (e.g. after a disconnect) safely re-register.

        Args:
            client_id: Unique identifier for this node on the hub.

        Raises:
            ValueError: If *client_id* is empty or not a string.
        """
        if not client_id or not isinstance(client_id, str):
            raise ValueError("client_id must be a non-empty string.")
        self.client_id = client_id

        while True:
            try:
                sock = self._make_socket()
                sock.connect(self.address)
                with self._lock:
                    self._socket = sock
                self._send_raw({"type": "register", "id": client_id})
                print(f"[NERVE] Connected to hub as '{client_id}'.")
                return
            except OSError as exc:
                print(
                    f"[NERVE] Hub unavailable ({exc}). Retrying in "
                    f"{self.retry_interval}s..."
                )
                time.sleep(self.retry_interval)

    def disconnect(self) -> None:
        """Close the connection to the hub gracefully."""
        with self._lock:
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
        """Send *payload* to the client identified by *to*.

        If the connection is lost, the client will attempt to reconnect
        automatically before retrying the send.

        Args:
            to:      Target client ID registered on the hub.
            payload: Any JSON-serialisable Python object.

        Raises:
            ValueError: If *to* is empty or not a string.
        """
        if not to or not isinstance(to, str):
            raise ValueError("'to' must be a non-empty string.")
        try:
            self._send_raw({"type": "send", "to": to, "payload": payload})
        except OSError as exc:
            print(f"[NERVE] Send failed ({exc}). Reconnecting...")
            self.connect(self.client_id)  # type: ignore[arg-type]
            self._send_raw({"type": "send", "to": to, "payload": payload})

    def broadcast(self, payload: Any) -> None:
        """Broadcast *payload* to all other clients connected to the hub.

        Args:
            payload: Any JSON-serialisable Python object.
        """
        try:
            self._send_raw({"type": "broadcast", "payload": payload})
        except OSError as exc:
            print(f"[NERVE] Broadcast failed ({exc}). Reconnecting...")
            self.connect(self.client_id)  # type: ignore[arg-type]
            self._send_raw({"type": "broadcast", "payload": payload})

    def list_clients(self) -> list[str]:
        """Request the list of currently connected client IDs from the hub.

        This call blocks for up to 2 seconds waiting for the hub's response.

        Returns:
            A list of registered client ID strings.
        """
        self._send_raw({"type": "list"})
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
        """Start listening for incoming messages in a background daemon thread.

        The *callback* is invoked in the listener thread each time a non-ping
        payload is received.

        Args:
            callback:     Function called with the deserialized payload object.
            on_reconnect: Optional function called each time the client
                          successfully reconnects after a connection drop.
        """
        def _listener() -> None:
            while True:
                buffer = ""
                with self._lock:
                    sock = self._socket
                if sock is None:
                    time.sleep(self.retry_interval)
                    continue
                try:
                    while True:
                        try:
                            chunk = sock.recv(4096)
                        except OSError as exc:
                            print(f"[NERVE] Connection error: {exc}. Reconnecting...")
                            break
                        if not chunk:
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
                            if isinstance(payload, dict) and payload.get("type") in ("ping", "pong"):
                                continue
                            try:
                                callback(payload)
                            except Exception as exc:
                                print(f"[NERVE] Error in message callback: {exc}")
                except Exception as exc:
                    print(f"[NERVE] Unexpected listener error: {exc}")

                self.connect(self.client_id)  # type: ignore[arg-type]
                if on_reconnect:
                    try:
                        on_reconnect()
                    except Exception:
                        pass

        threading.Thread(
            target=_listener,
            daemon=True,
            name=f"nerve-listen-{self.client_id}",
        ).start()
