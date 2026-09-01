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

Security layer in Phase 1: Layer 1 only (auth_token authentication).
Layer 2 (TLS) and Layer 3 (NRV_SECURE payload) are Phase 3 concerns.

LAN control plane protocol (Phase 1):
  host → client:  {"type": "lan_hello", "peer_id": ..., "hostname": ...,
                   "platform": ..., "protocol_version": 1}
  client → host:  {"type": "lan_auth", "token": ..., "client_peer_id": ...,
                   "client_hostname": ..., "client_platform": ...,
                   "protocol_version": 1}
  host → client:  {"type": "lan_auth_result", "status": "ok"|"failed",
                   "peer_id": ..., "hostname": ..., "platform": ...,
                   "reason": ...}  # reason only on failure
"""

from __future__ import annotations

import json
import os
import platform
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from nerve.core import load_external_config
from nerve.lan.connect import LAN_CONTROL_PORT_DEFAULT, LAN_PROTOCOL_VERSION
from nerve.lan.peer_registry import _registry_path
from nerve.lan.util import (
    get_or_create_host_identity,
    recv_message,
    resolve_auth_token,
    send_message,
)


PURPLE = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# Timeout for the accept() call — allows clean shutdown polling.
_ACCEPT_TIMEOUT: float = 0.5

# Timeout for each peer's auth handshake.
_PEER_HANDSHAKE_TIMEOUT: float = 15.0


# ---------------------------------------------------------------------------
# Receive destination helper (Phase 1: display only)
# ---------------------------------------------------------------------------


def _get_os_downloads_dir() -> Path:
    """
    Return the platform Downloads directory (frozen fallback, Decision #2).

    Linux / macOS: ~/Downloads
    Windows:       User's Downloads (resolved via USERPROFILE or shell folder)
    """
    system = platform.system()
    home = Path.home()
    if system == "Windows":
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
    return home / "Downloads"


def _resolve_display_receive_dir(
    cli_receive_dir: str | None,
    config: dict,
) -> Path:
    """
    Resolve the receive destination to display at startup (Phase 1 display only).

    Priority (frozen, Decision #2 / Decision #11):
        1. Explicit CLI --receive-dir
        2. Persistent nerve.config receive_dir
        3. OS Downloads directory fallback

    The full destination resolver (per-transfer and nerve receive session tiers)
    is implemented in Phase 4.
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

    Starts a TCP listener on a LAN-reachable address, accepts peer connections,
    and performs authenticated LAN handshakes.

    This is architecturally separate from NexusHub (nerve start).
    Existing local IPC is completely unchanged.
    """

    def __init__(
        self,
        receive_dir: str | None = None,
        lan_port: int | None = None,
        auth_token: str | None = None,
        config_path: str = "nerve.config",
        verbose: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        receive_dir:
            Incoming receive destination (CLI --receive-dir passthrough).
            Displayed at startup. Full destination resolution is Phase 4.
        lan_port:
            LAN control plane TCP port. Defaults to config lan_port or
            LAN_CONTROL_PORT_DEFAULT (50507).
        auth_token:
            Explicit auth token. If None, loaded from nerve.config or env.
        config_path:
            Path to nerve.config.
        verbose:
            If True, log additional connection details.
        """
        self._config_path = config_path
        self._verbose = verbose
        self._config: dict[str, Any] = load_external_config(config_path)

        # Token will be resolved during start() via _ensure_auth_configured
        self._auth_token_arg: str | None = auth_token
        self._auth_token: str | None = None


        # Resolve LAN port: constructor param > nerve.config > default
        resolved_port = (
            lan_port
            if lan_port is not None
            else int(self._config.get("lan_port", LAN_CONTROL_PORT_DEFAULT))
        )
        self._lan_port: int = resolved_port

        # Stable peer_id for this host instance
        self._peer_id: str = get_or_create_host_identity(_registry_path().parent)

        # Receive destination (display only in Phase 1)
        self._receive_dir: Path = _resolve_display_receive_dir(
            receive_dir, self._config
        )

        # Runtime state
        self._running: bool = False
        self._server: socket.socket | None = None
        self._lock: threading.Lock = threading.Lock()
        self._active_peer_sockets: set[socket.socket] = set()
        self._active_peer_threads: list[threading.Thread] = []
        self._stop_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the foreground LAN host.

        This method blocks until Ctrl+C or stop() is called.
        Raises SystemExit(1) if authentication is not configured
        and the context is non-interactive.
        """
        self._ensure_auth_configured()
        self._start_server()
        self._print_startup_banner()
        self._accept_loop()

    def stop(self) -> None:
        """
        Stop the host and release all owned resources.

        Called automatically on KeyboardInterrupt (Ctrl+C).
        Safe to call multiple times.
        """
        self._running = False
        self._stop_event.set()

        server = self._server
        if server is not None:
            self._server = None
            try:
                server.close()
            except OSError:
                pass

        with self._lock:
            sockets = list(self._active_peer_sockets)
            threads = list(self._active_peer_threads)
            self._active_peer_sockets.clear()

        # Closing sockets unblocks any handlers waiting on recv()
        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass
                
        # Cooperative shutdown: wait for threads to exit within a bounded global deadline
        deadline = time.time() + 2.0
        for th in threads:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                th.join(timeout=remaining)
            except RuntimeError:
                pass  # Thread was not started yet

    # ------------------------------------------------------------------
    # Authentication enforcement (F-3, F-4, F-5)
    # ------------------------------------------------------------------

    def _ensure_auth_configured(self) -> None:
        """
        Enforce the authentication requirement before starting the listener.
        """
        from nerve.lan.util import LanAuthenticationError
        
        try:
            self._auth_token = resolve_auth_token(
                self._auth_token_arg, self._config, allow_interactive=True
            )
        except LanAuthenticationError as exc:
            # Replicate F-5/F-4 legacy behavior for tests
            print(f"\033[91m[NERVE HOST] {exc}\033[0m")
            raise SystemExit(1)
            
        # Optionally persist the generated token if we just generated it and it's not in config
        if self._auth_token and not self._auth_token_arg and not os.environ.get("NERVE_AUTH_TOKEN") and not self._config.get("auth_token"):
             self._try_persist_token(self._auth_token)

    # ------------------------------------------------------------------
    # Authentication token persistence helper
    # ------------------------------------------------------------------

    def _try_persist_token(self, token: str) -> None:
        """Append auth_token to nerve.config if the file already exists."""
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "a", encoding="utf-8") as fh:
                fh.write(f"\nauth_token={token}\n")
            print(
                f"{GREEN}[NERVE HOST] Token saved to {self._config_path}{RESET}"
            )
        except OSError as exc:
            print(
                f"{YELLOW}[NERVE HOST] Could not save token to config: {exc}"
                f"\nYou must add it manually.{RESET}"
            )

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def _start_server(self) -> None:
        """Bind and listen on the LAN-reachable TCP address."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # F-2: bind to 0.0.0.0, not loopback.
        srv.bind(("0.0.0.0", self._lan_port))
        srv.listen(50)
        srv.settimeout(_ACCEPT_TIMEOUT)
        self._server = srv
        self._running = True
        self._stop_event.clear()

    def _print_startup_banner(self) -> None:
        """Display startup information including receive destination (F-12)."""
        print(
            f"{PURPLE}[NERVE HOST] Direct device communication host started.{RESET}"
        )
        print(
            f"{GREEN}[NERVE HOST] Listening on port {self._lan_port} "
            f"(LAN-reachable, all interfaces){RESET}"
        )
        print(
            f"{GREEN}[NERVE HOST] Receive destination: {self._receive_dir}{RESET}"
        )
        print(f"{YELLOW}[NERVE HOST] Press Ctrl+C to stop.{RESET}")

    def _accept_loop(self) -> None:
        """
        Main blocking accept loop.

        Handles KeyboardInterrupt (Ctrl+C) for clean shutdown (F-6, F-7).
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
    # Peer handshake handler
    # ------------------------------------------------------------------

    def _handle_peer(
        self, conn: socket.socket, addr: tuple[str, int]
    ) -> None:
        """
        Handle a single incoming peer connection.

        Performs the LAN auth handshake (Layer 1 only — Phase 1).
        The connection is closed after the handshake; it is not held open.
        Phase 3 will extend this to keep the connection alive for transfers.
        """
        peer_addr = f"{addr[0]}:{addr[1]}"
        try:
            conn.settimeout(_PEER_HANDSHAKE_TIMEOUT)
        except OSError:
            # Socket was closed by stop() before this thread started.
            with self._lock:
                self._active_peer_sockets.discard(conn)
            return
        buf: bytearray = bytearray()
        try:
            # Send HELLO
            hello = {
                "type": "lan_hello",
                "peer_id": self._peer_id,
                "hostname": socket.gethostname(),
                "platform": platform.system(),
                "protocol_version": LAN_PROTOCOL_VERSION,
            }
            send_message(conn, hello)

            # Receive AUTH
            auth_msg, buf = recv_message(conn, buf)
            if auth_msg.get("type") != "lan_auth":
                self._reject(conn, "protocol_error", peer_addr)
                return

            client_token = auth_msg.get("token", "")
            if self._auth_token and client_token != self._auth_token:
                self._reject(conn, "auth", peer_addr)
                return

            # Send AUTH_RESULT (ok)
            result = {
                "type": "lan_auth_result",
                "status": "ok",
                "peer_id": self._peer_id,
                "hostname": socket.gethostname(),
                "platform": platform.system(),
                "protocol_version": LAN_PROTOCOL_VERSION,
            }
            send_message(conn, result)

            client_id = auth_msg.get("client_peer_id", "unknown")
            client_host = auth_msg.get("client_hostname", peer_addr)
            if self._verbose:
                print(
                    f"{GREEN}[NERVE HOST] Peer authenticated: "
                    f"{client_host} ({peer_addr}) — id={client_id}{RESET}"
                )
            else:
                print(
                    f"{GREEN}[NERVE HOST] Peer connected: {client_host} ({peer_addr}){RESET}"
                )

        except (OSError, TimeoutError, Exception) as exc:
            if self._verbose:
                print(
                    f"{YELLOW}[NERVE HOST] Handshake error with {peer_addr}: {exc}{RESET}"
                )
        finally:
            with self._lock:
                self._active_peer_sockets.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _reject(self, conn: socket.socket, reason: str, peer_addr: str) -> None:
        """Send an auth failure result and log the rejection."""
        try:
            send_message(
                conn,
                {"type": "lan_auth_result", "status": "failed", "reason": reason},
            )
        except OSError:
            pass
        print(
            f"{RED}[NERVE HOST] Peer rejected ({reason}): {peer_addr}{RESET}"
        )
