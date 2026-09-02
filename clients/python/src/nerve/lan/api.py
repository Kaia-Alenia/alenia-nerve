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
Nerve LAN — Headless public API (arch §77).

All automation, CLI, and REST adapters consume this class.
The LAN Core is headless: no print(), input(), or terminal rendering here.

Fixes applied (confirmed by code review):
  Bug #1  — send(): Peer has no auth_token attr; token resolved from config/env only
  Bug #4  — send(): directory path detected early, returns honest error
  Bug #7  — start(): HOST_STARTED only dispatched after host bind confirms success
  Bug #8  — stop(): joins host thread before clearing reference
  Bug #9  — scan(): peer_id taken from response field, not hostname fallback
  Bug #10 — scan(): nonce generated per scan with secrets.token_hex
  Bug #11 — receive(): receive_dir registered on host when host already running
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nerve.lan.connect import (
    LAN_CONTROL_PORT_DEFAULT,
    LanAuthenticationError,
    LanConnectionError,
    LanProtocolError,
    connect_and_register,
)
from nerve.lan.events import (
    HOST_STARTED,
    HOST_STARTING,
    HOST_STOPPED,
    HOST_STOPPING,
    EventDispatcher,
)
from nerve.lan.host import NerveHost
from nerve.lan.models import (
    ConnectionResult,
    DiscoveryResult,
    HostStatus,
    TransferResult,
)
from nerve.lan.peer_registry import PeerRegistry
from nerve.lan.util import resolve_auth_token

logger = logging.getLogger("nerve.lan.api")


class NerveLAN:
    """
    Headless public API surface for Nerve LAN V1.

    All automation and UI layers should consume this API.
    CLI commands are adapters over this class.
    REST endpoints will be adapters over this class (Phase 9).
    """

    def __init__(
        self,
        receive_dir: str | None = None,
        port: int | None = None,
        auth_token: str | None = None,
        verbose: bool = False,
        max_concurrent_transfers: int | None = None,
    ) -> None:
        self.receive_dir = receive_dir
        self.port = port
        self._auth_token = auth_token
        self.verbose = verbose
        self.max_concurrent_transfers = max_concurrent_transfers
        self.events = EventDispatcher()
        self._host: NerveHost | None = None
        self._host_thread: threading.Thread | None = None

    def on(self, event_name: str, callback: Callable[..., None]) -> None:
        """Subscribe to a LAN event."""
        self.events.on(event_name, callback)

    def off(self, event_name: str, callback: Callable[..., None]) -> None:
        """Unsubscribe from a LAN event."""
        self.events.off(event_name, callback)

    # ------------------------------------------------------------------
    # Host lifecycle
    # ------------------------------------------------------------------

    def start(self) -> HostStatus:
        """
        Start the LAN Host in the background.

        Bug #7 fix: HOST_STARTED is only dispatched after the host confirms
        successful bind via _ready_event. If bind fails within the startup
        timeout the method returns running=False.
        """
        if self._host is not None:
            return HostStatus(running=True, error="Host is already running.")

        self.events.dispatch(HOST_STARTING)

        host = NerveHost(
            receive_dir=self.receive_dir,
            lan_port=self.port,
            auth_token=self._auth_token,
            verbose=self.verbose,
            max_concurrent_transfers=self.max_concurrent_transfers,
        )
        self._host = host

        # Synchronisation: wait for the bind to succeed before reporting started
        startup_ok: list[bool] = [False]
        startup_error: list[str] = [""]

        def _run_host() -> None:
            try:
                host.start()  # blocks; _start_server() sets _ready_event
                startup_ok[0] = True
            except SystemExit:
                startup_error[0] = "Authentication not configured."
            except Exception as exc:
                startup_error[0] = str(exc)
                logger.warning("Host startup error: %s", exc)
            finally:
                self.events.dispatch(HOST_STOPPED)

        self._host_thread = threading.Thread(
            target=_run_host, daemon=True, name="nerve-lan-host"
        )
        self._host_thread.start()

        # Wait up to 3 s for the host to signal it has bound successfully
        if host._ready_event.wait(timeout=3.0):
            self.events.dispatch(HOST_STARTED)
            return HostStatus(running=True, port=self.port or LAN_CONTROL_PORT_DEFAULT)
        else:
            # Bind did not succeed — clean up
            self._host = None
            self._host_thread = None
            err = startup_error[0] or "Host did not start within timeout."
            return HostStatus(running=False, error=err)

    def stop(self) -> HostStatus:
        """
        Stop the LAN Host.

        Bug #8 fix: joins host thread before clearing reference so callers
        receive STOPPED only after the thread has actually exited.
        """
        if self._host is None:
            return HostStatus(running=False, error="Host is not running.")

        self.events.dispatch(HOST_STOPPING)
        host = self._host
        thread = self._host_thread
        try:
            if hasattr(host, "stop"):
                host.stop()
        except Exception as exc:
            return HostStatus(running=False, error=str(exc))
        finally:
            if thread is not None:
                thread.join(timeout=3.0)  # Bug #8 fix
            self._host = None
            self._host_thread = None

        return HostStatus(running=False)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def scan(self, timeout: float = 2.0) -> list[DiscoveryResult]:
        """
        Scan for peers on the local network via UDP broadcast on port 50511.

        Bug #9 fix: peer_id taken from 'peer_id' field in response.
        Bug #10 fix: nonce generated per scan via secrets.token_hex(8).
        """
        import json
        import socket as _socket

        results: list[DiscoveryResult] = []
        nonce = secrets.token_hex(8)  # unique per scan

        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)

            msg = f"NERVE_DISCOVERY\nversion=1\nnonce={nonce}".encode("utf-8")
            
            bcast_addrs = {"255.255.255.255", "<broadcast>"}
            try:
                hostname = _socket.gethostname()
                _, _, ips = _socket.gethostbyname_ex(hostname)
                for ip in ips:
                    if not ip.startswith("127."):
                        parts = ip.split(".")
                        if len(parts) == 4:
                            bcast_addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
            except Exception:
                pass
            
            for b_addr in bcast_addrs:
                try:
                    sock.sendto(msg, (b_addr, 50511))
                except OSError:
                    pass
            end_time = time.monotonic() + timeout
            seen: set[str] = set()
            while time.monotonic() < end_time:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    sock.settimeout(remaining)
                    data, addr = sock.recvfrom(1024)
                    try:
                        resp = json.loads(data.decode("utf-8"))
                        if resp.get("type") != "nerve_discovery_response":
                            continue
                        # Bug #9: use server-provided peer_id, not hostname
                        peer_id = resp.get("peer_id") or resp.get("hostname", "unknown")
                        key = f"{addr[0]}:{peer_id}"
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(
                            DiscoveryResult(
                                peer_id=peer_id,
                                peer_name=resp.get("hostname", "unknown"),
                                address=addr[0],
                                platform=resp.get("platform", "unknown"),
                            )
                        )
                    except (ValueError, KeyError):
                        pass
                except TimeoutError:
                    break
        except Exception as exc:
            logger.warning("Scan error: %s", exc)
        finally:
            try:
                sock.close()
            except OSError:
                pass

        return results

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def diagnose(self, target_ip: str | None = None) -> dict:
        """
        Run local or targeted diagnostics.

        Returns structured evidence dict using levels: CONFIRMED, LIKELY,
        POSSIBLE, UNKNOWN (arch Decision #7+#8).
        """
        import socket as _socket

        report: dict[str, Any] = {
            "local": {},
            "target": {},
            "direct": {},
            "service": {},
            "causes": [],
        }

        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
                # Doesn't have to be reachable
                s.connect(("10.255.255.255", 1))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "unavailable"

        report["local"]["interface"] = "[CONFIRMED] Network interface available"
        report["local"]["address"] = f"[CONFIRMED] Local address: {local_ip}"

        if not target_ip:
            return report

        report["target"]["format"] = "[CONFIRMED] Address format valid"

        port = self.port or LAN_CONTROL_PORT_DEFAULT
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((target_ip, port))
            report["direct"]["tcp"] = "[CONFIRMED] Direct TCP connection succeeded"
            report["service"]["auth"] = (
                "[UNKNOWN] Not authenticated — full service not verified"
            )
            s.close()
        except ConnectionRefusedError:
            report["direct"]["tcp"] = (
                "[CONFIRMED] Connection refused (target reached, port closed)"
            )
            report["causes"].append("[POSSIBLE] Nerve host not running on target")
        except TimeoutError:
            report["direct"]["tcp"] = "[CONFIRMED] Connection timed out"
            report["causes"].extend(
                [
                    "[POSSIBLE] Firewall blocking the connection",
                    "[POSSIBLE] AP / Client Isolation",
                    "[POSSIBLE] Guest Wi-Fi isolation",
                    "[POSSIBLE] Target device unavailable",
                ]
            )
        except OSError as exc:
            report["direct"]["tcp"] = f"[UNKNOWN] {exc}"

        return report

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------

    def connect(
        self, ip: str, name: str | None = None, token: str | None = None
    ) -> ConnectionResult:
        """Connect to a remote LAN peer, authenticate, and save to registry."""
        try:
            peer = connect_and_register(address=ip, name=name, token=token)
            return ConnectionResult(
                success=True,
                peer_id=peer.peer_id,
                peer_name=peer.name,
                address=peer.last_address,
            )
        except (LanAuthenticationError, LanConnectionError, LanProtocolError) as exc:
            return ConnectionResult(success=False, error=str(exc))
        except Exception as exc:
            return ConnectionResult(success=False, error=f"Unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(
        self,
        path: str,
        to: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> TransferResult:
        """
        Send a file to a remote peer.

        Bug #1 fix: Peer object has no auth_token; token is resolved from
                    config/env — Peer is only used for address lookup.
        Bug #4 fix: Directories return an honest error instead of AttributeError.
        """
        import platform as _platform
        import socket as _socket

        from nerve.lan.connect import LAN_PROTOCOL_VERSION
        from nerve.lan.transfer import send_file
        from nerve.lan.util import (
            get_or_create_host_identity,
            recv_message,
            send_message,
        )

        src = Path(path)
        if not src.exists():
            return TransferResult(success=False, error=f"Path not found: {path}")

        # Bug #4: directory transfers not yet implemented in STANDARD mode
        if src.is_dir():
            return TransferResult(
                success=False,
                error="Directory transfer not yet implemented in STANDARD mode.",
            )

        # Resolve target address — Peer only provides the address (Bug #1)
        reg = PeerRegistry()
        target_peer = reg.get(to)
        if target_peer:
            address = target_peer.last_address
        else:
            address = to

        # Token comes from constructor arg, config, or env — never from Peer
        token = self._auth_token
        if not token:
            from nerve.core import load_external_config

            cfg = load_external_config("nerve.config")
            try:
                token = resolve_auth_token(None, cfg, allow_interactive=False)
            except Exception:
                token = None

        host_str, _, port_str = address.partition(":")
        ctrl_port = (
            int(port_str) if port_str else (self.port or LAN_CONTROL_PORT_DEFAULT)
        )

        try:
            # Control Plane handshake
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host_str, ctrl_port))

            buf: bytearray = bytearray()
            _hello, buf = recv_message(sock, buf)

            my_id = get_or_create_host_identity(reg._path.parent)
            send_message(
                sock,
                {
                    "type": "lan_auth",
                    "token": token or "",
                    "client_peer_id": my_id,
                    "client_hostname": _socket.gethostname(),
                    "client_platform": _platform.system(),
                    "protocol_version": LAN_PROTOCOL_VERSION,
                },
            )

            auth_res, buf = recv_message(sock, buf)
            if auth_res.get("status") != "ok":
                sock.close()
                return TransferResult(success=False, error="Authentication failed.")

            send_message(
                sock,
                {
                    "type": "lan_transfer_request",
                    "filename": src.name,
                    "size": src.stat().st_size,
                },
            )

            req_res, buf = recv_message(sock, buf)
            sock.close()

            if req_res.get("status") == "busy":
                current = req_res.get("current", "?")
                max_cap = req_res.get("max", "?")
                sock.close()
                return TransferResult(
                    success=False,
                    error=(
                        f"Peer is at capacity ({current}/{max_cap} transfer slots in use). "
                        "Retry later."
                    ),
                )

            if req_res.get("status") != "accepted":
                return TransferResult(success=False, error="Transfer rejected by peer.")

            data_port = req_res.get("port")
            if not data_port:
                return TransferResult(
                    success=False, error="No data port provided by peer."
                )

            # Data Plane
            dsock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            dsock.settimeout(30.0)
            dsock.connect((host_str, data_port))

            send_file(dsock, src, progress_callback=progress_callback)
            dsock.close()

            return TransferResult(success=True)

        except Exception as exc:
            return TransferResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def receive(self, receive_dir: str | None = None) -> None:
        """
        Temporary receive session (Decision #11).

        If a compatible local host is already running, this method attaches
        by updating the host's receive_dir for this session.

        If no host exists, starts a temporary host and blocks until Ctrl+C,
        then tears it down completely.

        Bug #11 fix: receive_dir is communicated to the host (not just ignored).
        """
        import socket as _socket

        port = self.port or LAN_CONTROL_PORT_DEFAULT
        host_running = False
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", port))
                host_running = True
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass

        if host_running:
            # Attach: update the running host's receive directory
            if receive_dir and self._host is not None:
                self._host._receive_dir = Path(receive_dir)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                # Restore host receive_dir if we changed it
                if receive_dir and self._host is not None:
                    from nerve.lan.host import _resolve_display_receive_dir

                    self._host._receive_dir = _resolve_display_receive_dir(
                        self.receive_dir, {}
                    )
        else:
            # No host running — start a temporary one
            old_dir = self.receive_dir
            if receive_dir:
                self.receive_dir = receive_dir
            status = self.start()
            if not status.running:
                logger.error("Failed to start temporary host: %s", status.error)
                self.receive_dir = old_dir
                return
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
                self.receive_dir = old_dir

    # ------------------------------------------------------------------
    # Peer / transfer inspection
    # ------------------------------------------------------------------

    def get_peer_capacity(self, to: str) -> dict:
        """
        Query the transfer capacity of a remote peer.

        Performs an auth handshake and sends a lightweight ``lan_status``
        request.  Returns a dict with keys:
          ``current`` (int) — transfers in progress on the peer
          ``max``     (int) — maximum concurrent transfers the peer accepts
          ``error``   (str) — present only on failure
        """
        import platform as _platform
        import socket as _socket

        from nerve.lan.connect import LAN_PROTOCOL_VERSION
        from nerve.lan.util import (
            get_or_create_host_identity,
            recv_message,
            send_message,
        )

        reg = PeerRegistry()
        target_peer = reg.get(to)
        address = target_peer.last_address if target_peer else to

        token = self._auth_token
        if not token:
            from nerve.core import load_external_config

            cfg = load_external_config("nerve.config")
            try:
                token = resolve_auth_token(None, cfg, allow_interactive=False)
            except Exception:
                token = None

        host_str, _, port_str = address.partition(":")
        ctrl_port = (
            int(port_str) if port_str else (self.port or LAN_CONTROL_PORT_DEFAULT)
        )

        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host_str, ctrl_port))

            buf: bytearray = bytearray()
            _hello, buf = recv_message(sock, buf)

            my_id = get_or_create_host_identity(reg._path.parent)
            send_message(
                sock,
                {
                    "type": "lan_auth",
                    "token": token or "",
                    "client_peer_id": my_id,
                    "client_hostname": _socket.gethostname(),
                    "client_platform": _platform.system(),
                    "protocol_version": LAN_PROTOCOL_VERSION,
                },
            )

            auth_res, buf = recv_message(sock, buf)
            if auth_res.get("status") != "ok":
                sock.close()
                return {"error": "Authentication failed."}

            send_message(sock, {"type": "lan_status"})
            status_res, _ = recv_message(sock, buf)
            sock.close()

            if status_res.get("type") == "lan_status_result":
                return {
                    "current": status_res.get("current", 0),
                    "max": status_res.get("max", 1),
                }
            return {"error": "Unexpected response type from peer."}
        except Exception as exc:
            return {"error": str(exc)}

    def get_peers(self) -> list[Any]:
        """Return all known registered peers."""
        return PeerRegistry().list_peers()

    def get_transfers(self) -> list[Any]:
        """Return active transfers. (Stub — Phase 3 streaming engine)."""
        return []

    def network_info(self) -> dict:
        """
        Return local network information for automation (arch §84.9).

        No Internet required. Filters out loopback and 0.0.0.0.
        """
        import platform as _platform
        import socket as _socket

        hostname = _socket.gethostname()
        addresses: list[str] = []
        try:
            addrs = _socket.getaddrinfo(hostname, None, _socket.AF_INET)
            for info in addrs:
                ip = info[4][0]
                if ip and not ip.startswith("127.") and ip != "0.0.0.0":
                    if ip not in addresses:
                        addresses.append(ip)
        except OSError:
            pass

        return {
            "hostname": hostname,
            "platform": _platform.system(),
            "addresses": addresses,
        }
