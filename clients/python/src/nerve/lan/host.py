# -----------------------------------------------------------------------------
# This file is part of Nerve.
#
# Nerve is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Nerve is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nerve. If not, see <https://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------
"""
nerve host — foreground LAN host mode.

Frozen requirements:
  Decision #9  — nerve host Lifecycle and Shutdown
  Decision #10 — Authentication, Credentials, and First Pairing
  F-1   nerve host is a new foreground command, separate from nerve start.
  F-2   nerve host binds to a LAN-reachable address (not loopback-only).
  F-3   nerve host must never operate as an unauthenticated open listener.
  F-4   Interactive missing credentials: may enter the official setup/generation flow.
  F-5   Non-interactive missing credentials: clear failure, no silent generation.
  F-6   Ctrl+C stops all host-owned resources cleanly.
  F-7   No orphan listener or hidden daemon remains after exit.
  F-12  nerve host shows the receive destination at startup.
  F-13  Existing nerve start / NexusHub is completely unchanged.

LAN control plane protocol (Phase 1):
  host → client:  {type: lan_hello, peer_id, hostname, platform, protocol_version}
  client → host:  {type: lan_auth, token, client_peer_id, client_hostname,
                   client_platform, protocol_version}
  host → client:  {type: lan_auth_result, status: ok|failed, peer_id, hostname,
                   platform, protocol_version, reason?}

Data Plane:
  Separate persistent listener on LAN_DATA_PORT_DEFAULT (50510).
  Registered in _active_peer_threads so stop() owns its lifecycle.
  Port offset (+3 hack) removed.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import threading
import time
from pathlib import Path
from typing import Any

from nerve.core import load_external_config
from nerve.lan.connect import LAN_CONTROL_PORT_DEFAULT, LAN_PROTOCOL_VERSION
from nerve.lan.peer_registry import _registry_path
from nerve.lan.transfer import LAN_DATA_PORT_DEFAULT, receive_file
from nerve.lan.util import (
    get_or_create_host_identity,
    recv_message,
    resolve_auth_token,
    send_message,
)

logger = logging.getLogger("nerve.lan.host")


def _auto_detect_capacity() -> int:
    """
    Return a safe concurrent transfer limit based on total system RAM.

    Linux: reads /proc/meminfo (MemTotal).
    Other platforms: uses cpu_count as a rough proxy.

    Thresholds:
      < 2 GB  → 1 concurrent transfer
      2–4 GB  → 2 concurrent transfers
      > 4 GB  → 3 concurrent transfers
    """
    ram_gb = 0.0
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo", "r") as _f:
                for _line in _f:
                    if _line.startswith("MemTotal:"):
                        ram_kb = int(_line.split()[1])
                        ram_gb = ram_kb / (1024 * 1024)
                        break
        else:
            cpus = os.cpu_count() or 1
            # Conservative proxy: each CPU can handle ~1 GB
            ram_gb = float(cpus)
    except Exception:
        pass

    if ram_gb >= 4.0:
        return 3
    elif ram_gb >= 2.0:
        return 2
    return 1


PURPLE = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# Timeout for accept() — allows clean shutdown polling
_ACCEPT_TIMEOUT: float = 0.5

# Timeout for auth handshake per peer
_PEER_HANDSHAKE_TIMEOUT: float = 15.0


# ---------------------------------------------------------------------------
# Receive destination resolution
# ---------------------------------------------------------------------------


def _get_os_downloads_dir() -> Path:
    """
    Return the platform Downloads directory (frozen fallback, Decision #2).

    Linux / macOS: ~/Downloads
    Windows:       User's Downloads (resolved via registry or USERPROFILE)
    """
    if platform.system() == "Windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            val, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            return Path(val)
        except Exception:
            pass
    return Path.home() / "Downloads"


def _resolve_display_receive_dir(cli_receive_dir: str | None, config: dict) -> Path:
    """
    Resolve the receive destination displayed at startup.

    Priority (Decision #2 / Decision #11):
        1. Explicit CLI --receive-dir
        2. Persistent nerve.config receive_dir
        3. OS Downloads directory fallback
    """
    if cli_receive_dir:
        return Path(cli_receive_dir)
    config_dir = config.get("receive_dir")
    if config_dir:
        return Path(str(config_dir))
    return _get_os_downloads_dir()


# ---------------------------------------------------------------------------
# NerveHost
# ---------------------------------------------------------------------------


class NerveHost:
    """
    The Nerve LAN foreground host (nerve host command).

    Starts a TCP control-plane listener and a persistent Data Plane listener,
    plus a UDP discovery responder. All owned threads and sockets are tracked
    so stop() can perform a deterministic, complete shutdown (Decision #9).

    Architecturally separate from NexusHub (nerve start). Existing local IPC
    is completely unchanged (Decision #9 F-13).
    """

    def __init__(
        self,
        receive_dir: str | None = None,
        lan_port: int | None = None,
        auth_token: str | None = None,
        config_path: str = "nerve.config",
        verbose: bool = False,
        max_concurrent_transfers: int | None = None,
    ) -> None:
        self._config_path = config_path
        self._verbose = verbose
        self._config: dict[str, Any] = load_external_config(config_path)

        # Token resolved at start() time
        self._auth_token_arg: str | None = auth_token
        self._auth_token: str | None = None

        # Port resolution: param > config > default
        resolved_port = (
            lan_port
            if lan_port is not None
            else int(self._config.get("lan_port", LAN_CONTROL_PORT_DEFAULT))
        )
        self._lan_port: int = resolved_port
        self._data_port: int = LAN_DATA_PORT_DEFAULT  # fixed, not derived from +3

        # Stable peer identity for this host
        self._peer_id: str = get_or_create_host_identity(_registry_path().parent)

        # Receive destination (Decision #2)
        self._receive_dir: Path = _resolve_display_receive_dir(
            receive_dir, self._config
        )

        # Concurrent transfer capacity (auto-detected from RAM if not provided)
        if max_concurrent_transfers is not None:
            self._max_concurrent_transfers: int = max(1, int(max_concurrent_transfers))
            self._capacity_source: str = "user-set"
        else:
            self._max_concurrent_transfers = _auto_detect_capacity()
            self._capacity_source = "auto-detected"

        # Runtime state
        self._running: bool = False
        self._server: socket.socket | None = None
        self._data_server: socket.socket | None = None
        self._udp_server: socket.socket | None = None
        self._lock: threading.Lock = threading.Lock()
        self._active_peer_sockets: set[socket.socket] = set()
        self._active_peer_threads: list[threading.Thread] = []
        self._stop_event: threading.Event = threading.Event()

        # Active transfer counter (protected by _transfer_lock)
        self._active_transfers: int = 0
        self._transfer_lock: threading.Lock = threading.Lock()

        # Set by _start_server() once bind succeeds — used by start() to confirm readiness
        self._ready_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the foreground LAN host.

        Blocks until Ctrl+C or stop() is called.
        Raises SystemExit(1) if authentication is not configured
        in a non-interactive context.
        """
        self._ensure_auth_configured()
        self._start_server()
        self._print_startup_banner()
        self._accept_loop()

    def stop(self) -> None:
        """
        Stop the host and release all owned resources (Decision #9 F-6/F-7).

        Closes all sockets, joins all registered threads within a bounded
        deadline, and signals the stop event. Safe to call multiple times.
        """
        self._running = False
        self._stop_event.set()

        # Close all owned server sockets
        for attr in ("_server", "_data_server", "_udp_server"):
            sock = getattr(self, attr, None)
            setattr(self, attr, None)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

        with self._lock:
            peer_socks = list(self._active_peer_sockets)
            threads = list(self._active_peer_threads)
            self._active_peer_sockets.clear()

        # Unblock all handler threads waiting on recv
        for sock in peer_socks:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

        # Join all threads with a shared bounded deadline (Decision #9)
        deadline = time.time() + 3.0
        for th in threads:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                th.join(timeout=remaining)
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Authentication enforcement (F-3, F-4, F-5)
    # ------------------------------------------------------------------

    def _ensure_auth_configured(self) -> None:
        from nerve.lan.util import LanAuthenticationError

        try:
            self._auth_token = resolve_auth_token(
                self._auth_token_arg, self._config, allow_interactive=True
            )
        except LanAuthenticationError as exc:
            print(f"{RED}[NERVE HOST] {exc}{RESET}")
            raise SystemExit(1)

        # Persist token to nerve.config if it was just generated
        if (
            self._auth_token
            and not self._auth_token_arg
            and not os.environ.get("NERVE_AUTH_TOKEN")
            and not self._config.get("auth_token")
        ):
            self._try_persist_token(self._auth_token)

    def _try_persist_token(self, token: str) -> None:
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "a", encoding="utf-8") as fh:
                fh.write(f"\nauth_token={token}\n")
            print(f"{GREEN}[NERVE HOST] Token saved to {self._config_path}{RESET}")
        except OSError as exc:
            print(
                f"{YELLOW}[NERVE HOST] Could not save token to config: {exc}"
                f"\nAdd it manually.{RESET}"
            )

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def _start_server(self) -> None:
        """
        Bind and listen on all three interfaces:
          - TCP control plane on self._lan_port
          - TCP data plane on LAN_DATA_PORT_DEFAULT (50510)
          - UDP discovery on 50511

        Sets _ready_event after all binds succeed.
        Registered threads (discovery, data listener) are tracked in
        _active_peer_threads so stop() owns them.
        """
        # Control Plane
        ctrl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctrl.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ctrl.bind(("0.0.0.0", self._lan_port))
        ctrl.listen(50)
        ctrl.settimeout(_ACCEPT_TIMEOUT)
        self._server = ctrl

        # Data Plane — persistent listener (fixed port 50510, not +3 offset)
        data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        data.bind(("0.0.0.0", self._data_port))
        data.listen(10)
        data.settimeout(_ACCEPT_TIMEOUT)
        self._data_server = data

        # Discovery UDP — non-fatal: if the OS blocks the port (e.g. Windows
        # firewall or restricted CI environments), the host still starts and
        # serves TCP transfers. Discovery is disabled silently in that case.
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            udp.bind(("0.0.0.0", 50511))
            udp.settimeout(_ACCEPT_TIMEOUT)
            self._udp_server = udp
        except OSError as exc:
            udp.close()
            self._udp_server = None
            logger.warning(
                "UDP discovery unavailable (port 50511 blocked): %s — "
                "host starts without peer discovery.",
                exc,
            )

        self._running = True
        self._stop_event.clear()

        # Discovery thread — only started if UDP bind succeeded
        if self._udp_server is not None:
            disc_th = threading.Thread(
                target=self._discovery_loop,
                daemon=True,
                name="nerve-lan-discovery",
            )
            with self._lock:
                self._active_peer_threads.append(disc_th)
            disc_th.start()

        # Data Plane listener thread — registered so stop() joins it (Bug #6 fix)
        data_th = threading.Thread(
            target=self._data_accept_loop,
            daemon=True,
            name="nerve-lan-data",
        )
        with self._lock:
            self._active_peer_threads.append(data_th)
        data_th.start()

        # Signal readiness after all binds succeed (Bug #7 fix)
        self._ready_event.set()

    def _print_startup_banner(self) -> None:
        print(f"{PURPLE}[NERVE HOST] Direct device communication host started.{RESET}")
        print(
            f"{GREEN}[NERVE HOST] Control Plane on port {self._lan_port} "
            f"(all interfaces){RESET}"
        )
        print(f"{GREEN}[NERVE HOST] Data Plane on port {self._data_port}{RESET}")
        print(f"{GREEN}[NERVE HOST] Discovery active on UDP 50511{RESET}")
        print(f"{GREEN}[NERVE HOST] Receive destination: {self._receive_dir}{RESET}")
        cap = self._max_concurrent_transfers
        src = self._capacity_source
        cap_label = "file" if cap == 1 else "files"
        print(
            f"{YELLOW}[NERVE HOST] Transfer capacity: {cap} concurrent {cap_label} "
            f"({src}){RESET}"
        )
        print(f"{YELLOW}[NERVE HOST] Press Ctrl+C to stop.{RESET}")

    # ------------------------------------------------------------------
    # Verbose print helper
    # ------------------------------------------------------------------

    def _vprint(self, msg: str, color: str = "") -> None:
        """Print a timestamped verbose log line to stdout (no-op if not verbose)."""
        if not self._verbose:
            return
        import time as _time

        ts = _time.strftime("%H:%M:%S")
        print(f"{color}[{ts}] {msg}{RESET}", flush=True)

    # ------------------------------------------------------------------
    # Discovery responder
    # ------------------------------------------------------------------

    def _discovery_loop(self) -> None:
        """Listen for UDP discovery broadcasts and respond with stable peer_id."""
        from nerve import __version__

        while self._running and self._udp_server:
            try:
                data, addr = self._udp_server.recvfrom(1024)
            except TimeoutError:
                continue
            except OSError:
                break

            text = data.decode("utf-8", errors="ignore")
            if not text.startswith("NERVE_DISCOVERY"):
                continue

            resp = {
                "type": "nerve_discovery_response",
                "peer_id": self._peer_id,  # stable identity (Bug #9 fix)
                "hostname": socket.gethostname(),
                "platform": platform.system(),
                "version": __version__,
                "control_port": self._lan_port,
                "transfer_port": self._data_port,
            }
            try:
                self._udp_server.sendto(json.dumps(resp).encode("utf-8"), addr)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Data Plane accept loop
    # ------------------------------------------------------------------

    def _data_accept_loop(self) -> None:
        """
        Persistent Data Plane TCP listener on self._data_port.

        Spawns a handler thread per incoming data connection. All handler
        threads are registered in _active_peer_threads.
        """
        while self._running and self._data_server:
            try:
                dconn, daddr = self._data_server.accept()
            except TimeoutError:
                continue
            except OSError:
                break

            with self._lock:
                if not self._running:
                    try:
                        dconn.close()
                    except OSError:
                        pass
                    break
                self._active_peer_sockets.add(dconn)

            dth = threading.Thread(
                target=self._handle_data_connection,
                args=(dconn, daddr),
                daemon=True,
                name="nerve-lan-data-handler",
            )
            with self._lock:
                self._active_peer_threads.append(dth)
            dth.start()

    def _handle_data_connection(
        self, conn: socket.socket, addr: tuple[str, int]
    ) -> None:
        """Receive a single file transfer from the Data Plane connection."""
        self._vprint(
            f"Data plane connection opened from {addr[0]}:{addr[1]}",
            YELLOW,
        )

        import time

        start_time = time.time()
        last_pct = [0]

        def _on_progress(filename: str, bytes_rcv: int, total: int) -> None:
            if total > 0:
                pct = int((bytes_rcv / total) * 100)
                # Print progress every 10% (or when reaching 100%)
                if pct >= last_pct[0] + 10 or pct == 100:
                    last_pct[0] = (
                        pct if pct < 100 else 101
                    )  # prevent printing 100% multiple times
                    elapsed = time.time() - start_time
                    speed = (bytes_rcv / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                    print(
                        f"{GREEN}[NERVE HOST] Receiving '{filename}' from {addr[0]}: {pct}% ({speed:.1f} MB/s){RESET}"
                    )

        try:
            receive_file(
                conn,
                self._receive_dir,
                progress_callback=_on_progress,
                conflict_policy="rename",
            )
            self._vprint(
                f"File received from {addr[0]}:{addr[1]} → {self._receive_dir}",
                GREEN,
            )
        except Exception as exc:
            self._vprint(
                f"Data plane error from {addr[0]}:{addr[1]}: {exc}",
                RED,
            )
        finally:
            # Release the transfer slot so the next sender can proceed
            with self._transfer_lock:
                self._active_transfers = max(0, self._active_transfers - 1)
                remaining = self._active_transfers
            self._vprint(
                f"Slot released — active transfers: {remaining}/{self._max_concurrent_transfers}",
                YELLOW,
            )
            with self._lock:
                self._active_peer_sockets.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Control Plane accept loop
    # ------------------------------------------------------------------

    def _accept_loop(self) -> None:
        """
        Main blocking accept loop for the Control Plane.

        Handles KeyboardInterrupt for clean shutdown (F-6, F-7).
        """
        try:
            while self._running and self._server:
                try:
                    conn, addr = self._server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break

                with self._lock:
                    if not self._running:
                        try:
                            conn.close()
                        except OSError:
                            pass
                        break
                    self._active_peer_sockets.add(conn)

                th = threading.Thread(
                    target=self._handle_peer,
                    args=(conn, addr),
                    daemon=True,
                    name="nerve-lan-peer",
                )
                with self._lock:
                    self._active_peer_threads.append(th)
                th.start()

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
            print(f"\n{PURPLE}[NERVE HOST] Stopped.{RESET}")

    # ------------------------------------------------------------------
    # Control Plane peer handshake
    # ------------------------------------------------------------------

    def _handle_peer(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        """
        Handle a single Control Plane peer connection.

        Performs the LAN auth handshake and negotiates transfer requests.
        The Data Plane connection for file data is made separately by the
        sender to self._data_port.
        """
        peer_addr = f"{addr[0]}:{addr[1]}"
        self._vprint(f"Control plane connection from {peer_addr}", YELLOW)
        try:
            conn.settimeout(_PEER_HANDSHAKE_TIMEOUT)
        except OSError:
            with self._lock:
                self._active_peer_sockets.discard(conn)
            return

        buf: bytearray = bytearray()
        try:
            # HELLO
            send_message(
                conn,
                {
                    "type": "lan_hello",
                    "peer_id": self._peer_id,
                    "hostname": socket.gethostname(),
                    "platform": platform.system(),
                    "protocol_version": LAN_PROTOCOL_VERSION,
                },
            )

            # AUTH
            auth_msg, buf = recv_message(conn, buf)
            if auth_msg.get("type") != "lan_auth":
                self._reject(conn, "protocol_error", peer_addr)
                return

            client_token = auth_msg.get("token", "")
            if self._auth_token and client_token != self._auth_token:
                self._reject(conn, "auth", peer_addr)
                return

            # AUTH_RESULT ok
            send_message(
                conn,
                {
                    "type": "lan_auth_result",
                    "status": "ok",
                    "peer_id": self._peer_id,
                    "hostname": socket.gethostname(),
                    "platform": platform.system(),
                    "protocol_version": LAN_PROTOCOL_VERSION,
                },
            )

            client_host = auth_msg.get("client_hostname", peer_addr)
            client_platform = auth_msg.get("client_platform", "?")
            if self._verbose:
                self._vprint(
                    f"Peer authenticated: {client_host} [{client_platform}] ({peer_addr})",
                    GREEN,
                )
            else:
                print(
                    f"{GREEN}[NERVE HOST] Peer connected: {client_host} ({peer_addr}){RESET}"
                )

            # Transfer request or status query
            req, buf = recv_message(conn, buf)
            req_type = req.get("type", "unknown")
            self._vprint(f"Request from {client_host}: {req_type}", YELLOW)

            if req.get("type") == "lan_status":
                # Lightweight capacity query — no transfer initiated
                with self._transfer_lock:
                    current = self._active_transfers
                self._vprint(
                    f"Status query from {client_host} — "
                    f"capacity: {current}/{self._max_concurrent_transfers}",
                    GREEN,
                )
                send_message(
                    conn,
                    {
                        "type": "lan_status_result",
                        "current": current,
                        "max": self._max_concurrent_transfers,
                    },
                )

            elif req.get("type") == "lan_transfer_request":
                filename = req.get("filename", "?")
                filesize = req.get("size", 0)
                size_kb = filesize / 1024 if filesize else 0
                with self._transfer_lock:
                    current = self._active_transfers
                    if current >= self._max_concurrent_transfers:
                        # Peer is at capacity — reject gracefully
                        send_message(
                            conn,
                            {
                                "type": "lan_transfer_result",
                                "status": "busy",
                                "current": current,
                                "max": self._max_concurrent_transfers,
                            },
                        )
                        self._vprint(
                            f"Transfer REJECTED (busy {current}/{self._max_concurrent_transfers}): "
                            f"{filename} from {client_host}",
                            RED,
                        )
                        return
                    self._active_transfers += 1
                    active_now = self._active_transfers

                self._vprint(
                    f"Transfer ACCEPTED: {filename} ({size_kb:.1f} KB) from {client_host} — "
                    f"slot {active_now}/{self._max_concurrent_transfers}",
                    GREEN,
                )
                # Inform sender of the fixed Data Plane port (Bug #5 fix)
                send_message(
                    conn,
                    {
                        "type": "lan_transfer_result",
                        "status": "accepted",
                        "port": self._data_port,
                    },
                )

        except (OSError, TimeoutError, Exception) as exc:
            self._vprint(f"Handshake error with {peer_addr}: {exc}", RED)
        finally:
            with self._lock:
                self._active_peer_sockets.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _reject(self, conn: socket.socket, reason: str, peer_addr: str) -> None:
        try:
            send_message(
                conn,
                {
                    "type": "lan_auth_result",
                    "status": "failed",
                    "reason": reason,
                },
            )
        except OSError:
            pass
        print(f"{RED}[NERVE HOST] Peer rejected ({reason}): {peer_addr}{RESET}")
