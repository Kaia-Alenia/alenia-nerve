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

All automation, CLI, and REST adapters consume this class.
The LAN Core is headless: no print(), input(), or terminal rendering here.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import secrets
import socket
import subprocess
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
    TransferRecord,
    TransferResult,
    TransferState,
)
from nerve.lan.peer_registry import PeerRegistry
from nerve.lan.util import (
    append_audit_log,
    detect_platform_name,
    enable_tcp_keepalive,
    read_audit_log,
    resolve_auth_token,
)

logger = logging.getLogger("nerve.lan.api")

_VIRTUAL_IFACE_PREFIXES = (
    "lo",
    "docker",
    "veth",
    "br-",
    "virbr",
    "wsl",
    "tun",
    "tap",
    "vmnet",
    "vboxnet",
)


def _is_usable_lan_ipv4(ip: str) -> bool:
    """Return True if *ip* is a non-loopback, non-APIPA IPv4 address."""
    if not ip or ip == "0.0.0.0" or ip.startswith("127.") or ip.startswith("169.254."):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def _collect_os_interface_ipv4() -> set[str]:
    """Inspect OS network interfaces directly for Linux, Android, macOS, and Windows."""
    found: set[str] = set()
    system = platform.system()

    if system == "Windows":
        try:
            proc = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            for match in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", proc.stdout):
                if _is_usable_lan_ipv4(match):
                    found.add(match)
        except (OSError, subprocess.SubprocessError):
            pass
        return found

    # Linux / Android (Termux) via `ip -4 -o addr show`
    try:
        proc = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                tokens = line.split()
                if len(tokens) < 4:
                    continue
                iface = tokens[1].rstrip(":")
                if iface.startswith(_VIRTUAL_IFACE_PREFIXES):
                    continue
                ip = tokens[3].split("/", 1)[0]
                if _is_usable_lan_ipv4(ip):
                    found.add(ip)
            return found
    except (OSError, subprocess.SubprocessError):
        pass

    # macOS / BSD / Termux fallback via `ifconfig`
    try:
        proc = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        current_iface = ""
        for line in proc.stdout.splitlines():
            if line and not line[0].isspace():
                current_iface = line.split(":", 1)[0].split()[0]
                continue
            if current_iface.startswith(_VIRTUAL_IFACE_PREFIXES):
                continue
            match = re.search(r"\binet\s+(?:addr:)?(\d{1,3}(?:\.\d{1,3}){3})\b", line)
            if match and _is_usable_lan_ipv4(match.group(1)):
                found.add(match.group(1))
    except (OSError, subprocess.SubprocessError):
        pass

    return found


def _local_ipv4_addresses() -> set[str]:
    """Return local IPv4 addresses without requiring DNS or Internet.

    Combines hostname resolution, UDP route probes (no packet transmitted), and
    OS interface inspection across Windows, macOS, Linux, and Android/Termux.
    """
    addresses: set[str] = set()

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if isinstance(ip, str) and _is_usable_lan_ipv4(ip):
                addresses.add(ip)
    except Exception:
        pass

    for probe_target in ("255.255.255.255", "10.255.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_sock:
                route_sock.connect((probe_target, 1))
                ip = route_sock.getsockname()[0]
                if isinstance(ip, str) and _is_usable_lan_ipv4(ip):
                    addresses.add(ip)
        except Exception:
            pass

    addresses.update(_collect_os_interface_ipv4())
    return addresses


class NerveLAN:
    """
    Headless public API surface for Nerve LAN V1.

    All automation and UI layers should consume this API.
    CLI commands are adapters over this class.
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
        self._transfers: list[TransferRecord] = []
        self._transfers_lock = threading.Lock()
        self._audit_log_path: Path | None = None

    @property
    def status(self) -> HostStatus:
        """Return live status of the embedded LAN host."""
        running = self._host is not None and bool(
            getattr(self._host, "_running", False)
        )
        return HostStatus(
            running=running,
            port=self.port or LAN_CONTROL_PORT_DEFAULT,
        )

    def _record_transfer(self, record: TransferRecord) -> None:
        with self._transfers_lock:
            self._transfers.append(record)
        try:
            append_audit_log(
                {
                    "transfer_id": record.transfer_id,
                    "direction": record.direction,
                    "filename": record.filename,
                    "size": record.size,
                    "sha256": record.sha256,
                    "peer": record.peer,
                    "state": record.state,
                    "transferred_bytes": record.transferred_bytes,
                    "resumed_from": record.resumed_from,
                    "timestamp": record.timestamp,
                    "error": record.error,
                },
                log_path=self._audit_log_path,
            )
        except OSError as exc:
            logger.warning("Failed to append audit log: %s", exc)

    def on(self, event_name: str, callback: Callable[..., None]) -> None:
        """Subscribe to a LAN event."""
        self.events.on(event_name, callback)

    def off(self, event_name: str, callback: Callable[..., None]) -> None:
        """Unsubscribe from a LAN event."""
        self.events.off(event_name, callback)

    def start(self) -> HostStatus:
        """
        Start the LAN Host in the background.

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
                thread.join(timeout=3.0)
            self._host = None
            self._host_thread = None

        return HostStatus(running=False)

    def scan(
        self,
        timeout: float = 2.0,
        target_ip: str | None = None,
        subnet_fallback: bool = False,
    ) -> list[DiscoveryResult]:
        """
        Scan for peers on the local network via UDP broadcast on port 50511.

        If *target_ip* is given, a unicast probe is sent directly to that IP
        instead of broadcast — useful on networks where routers block broadcast
        packets between clients (AP/Client Isolation). Known peers from the
        PeerRegistry are also probed directly via unicast, and *subnet_fallback*
        enables a fast /24 unicast sweep when needed.
        """
        results: list[DiscoveryResult] = []
        nonce = secrets.token_hex(8)  # unique per scan

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)

            msg = f"NERVE_DISCOVERY\nversion=1\nnonce={nonce}".encode()

            if target_ip:
                # Unicast mode: probe the specific IP directly (bypasses AP Isolation).
                addrs_to_probe = {target_ip}
            else:
                # Broadcast mode plus direct probes for known peers (survives AP Isolation).
                addrs_to_probe = {"255.255.255.255"}
                local_ips = _local_ipv4_addresses()
                for ip in local_ips:
                    parts = ip.split(".")
                    if len(parts) == 4 and all(part.isdigit() for part in parts):
                        prefix = f"{parts[0]}.{parts[1]}.{parts[2]}"
                        addrs_to_probe.add(f"{prefix}.255")
                        if subnet_fallback:
                            for host_octet in range(1, 255):
                                candidate = f"{prefix}.{host_octet}"
                                if candidate != ip:
                                    addrs_to_probe.add(candidate)

                try:
                    for peer in PeerRegistry().list_peers():
                        peer_ip = peer.last_address.partition(":")[0].strip()
                        if peer_ip:
                            addrs_to_probe.add(peer_ip)
                except Exception:
                    pass

            for addr_str in addrs_to_probe:
                try:
                    sock.sendto(msg, (addr_str, 50511))
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

    def diagnose(self, target_ip: str | None = None) -> dict:
        """
        Run local or targeted diagnostics.

        Returns structured evidence dict using levels: CONFIRMED, LIKELY,
        """
        import socket as _socket

        report: dict[str, Any] = {
            "local": {},
            "target": {},
            "direct": {},
            "service": {},
            "causes": [],
        }

        local_addrs = sorted(_local_ipv4_addresses())
        if local_addrs:
            local_ip = local_addrs[0]
        else:
            local_ip = "unavailable"
            try:
                with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
                    # Doesn't have to be reachable
                    s.connect(("10.255.255.255", 1))
                    candidate = s.getsockname()[0]
                    if candidate:
                        local_ip = candidate
            except Exception:
                try:
                    # Verify local IPv4 stack via loopback when isolated from LAN/WAN
                    with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as s:
                        s.connect(("127.0.0.1", 1))
                        local_ip = s.getsockname()[0] or "127.0.0.1"
                except Exception:
                    local_ip = "unavailable"

        if local_ip == "unavailable":
            report["local"]["interface"] = (
                "[FAILED] No active IPv4 interface was detected"
            )
            report["local"]["address"] = (
                "[FAILED] The device is disconnected from the LAN"
            )
            report["causes"].append(
                "[LIKELY] Wi-Fi/Ethernet is disabled or the devices are not on the same local network"
            )
        else:
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

    def _resolve_token(self) -> str | None:
        token = self._auth_token
        if not token:
            from nerve.core import load_external_config

            cfg = load_external_config("nerve.config")
            try:
                token = resolve_auth_token(None, cfg, allow_interactive=False)
            except Exception:
                token = None
        return token

    def _resolve_target(self, to: str) -> tuple[str, int, PeerRegistry]:
        reg = PeerRegistry()
        target_peer = reg.get(to)
        address = target_peer.last_address if target_peer else to
        host_str, _, port_str = address.partition(":")
        ctrl_port = (
            int(port_str) if port_str else (self.port or LAN_CONTROL_PORT_DEFAULT)
        )
        return host_str, ctrl_port, reg

    def send(
        self,
        path: str,
        to: str,
        progress_callback: Callable[[int, int], None] | None = None,
        max_retries: int = 2,
    ) -> TransferResult:
        """Send a file to a remote peer with automatic chunk-level resume on drop."""
        import socket as _socket

        from nerve.lan.connect import LAN_PROTOCOL_VERSION
        from nerve.lan.transfer import (
            TransferProtocolError,
            compute_file_sha256,
            send_file,
        )
        from nerve.lan.util import (
            get_or_create_host_identity,
            recv_message,
            send_message,
        )

        src = Path(path)
        if not src.exists():
            return TransferResult(success=False, error=f"Path not found: {path}")

        if src.is_dir():
            return TransferResult(
                success=False,
                error="Directory transfer not yet implemented in STANDARD mode.",
            )

        host_str, ctrl_port, reg = self._resolve_target(to)
        token = self._resolve_token()
        file_size = src.stat().st_size
        file_sha256 = compute_file_sha256(src)
        my_id = get_or_create_host_identity(reg._path.parent)
        platform_name = detect_platform_name()
        transfer_id = secrets.token_hex(6)
        last_error = "Transfer failed."
        last_resume_offset = 0

        def _fail(err_msg: str) -> TransferResult:
            self._record_transfer(
                TransferRecord(
                    transfer_id=transfer_id,
                    filename=src.name,
                    size=file_size,
                    sha256=file_sha256,
                    peer=to,
                    direction="send",
                    state=TransferState.FAILED.value,
                    transferred_bytes=0,
                    timestamp=time.time(),
                    resumed_from=last_resume_offset,
                    error=err_msg,
                )
            )
            return TransferResult(success=False, transfer_id=transfer_id, error=err_msg)

        for attempt in range(max_retries + 1):
            sock = None
            dsock = None
            try:
                # Control Plane handshake
                sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                sock.settimeout(10.0)
                sock.connect((host_str, ctrl_port))
                enable_tcp_keepalive(sock)

                buf: bytearray = bytearray()
                _hello, buf = recv_message(sock, buf)

                send_message(
                    sock,
                    {
                        "type": "lan_auth",
                        "token": token or "",
                        "client_peer_id": my_id,
                        "client_hostname": _socket.gethostname(),
                        "client_platform": platform_name,
                        "protocol_version": LAN_PROTOCOL_VERSION,
                    },
                )

                auth_res, buf = recv_message(sock, buf)
                if auth_res.get("status") != "ok":
                    return _fail("Authentication failed.")

                send_message(
                    sock,
                    {
                        "type": "lan_transfer_request",
                        "filename": src.name,
                        "size": file_size,
                        "sha256": file_sha256,
                    },
                )

                req_res, buf = recv_message(sock, buf)
                sock.close()
                sock = None

                if req_res.get("status") == "busy":
                    current = req_res.get("current", "?")
                    max_cap = req_res.get("max", "?")
                    last_error = (
                        f"Peer is at capacity ({current}/{max_cap} transfer slots in use). "
                        "Retry later."
                    )
                    if attempt > 0 and attempt < max_retries:
                        time.sleep(0.2)
                        continue
                    return _fail(last_error)

                if req_res.get("status") != "accepted":
                    return _fail("Transfer rejected by peer.")

                data_port = req_res.get("port")
                if not data_port:
                    return _fail("No data port provided by peer.")

                resume_offset = int(req_res.get("resume_offset", 0) or 0)
                last_resume_offset = resume_offset

                # Data Plane
                dsock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                dsock.settimeout(30.0)
                dsock.connect((host_str, data_port))
                enable_tcp_keepalive(dsock)

                try:
                    send_file(
                        dsock,
                        src,
                        progress_callback=progress_callback,
                        offset=resume_offset,
                        precomputed_sha256=file_sha256,
                    )
                except (OSError, TimeoutError, TransferProtocolError) as data_exc:
                    last_error = str(data_exc)
                    if attempt < max_retries:
                        time.sleep(0.2)
                        continue
                    return _fail(last_error)

                self._record_transfer(
                    TransferRecord(
                        transfer_id=transfer_id,
                        filename=src.name,
                        size=file_size,
                        sha256=file_sha256,
                        peer=to,
                        direction="send",
                        state=TransferState.COMPLETED.value,
                        transferred_bytes=file_size,
                        timestamp=time.time(),
                        resumed_from=resume_offset,
                    )
                )
                return TransferResult(success=True, transfer_id=transfer_id)

            except Exception as exc:
                return _fail(str(exc))
            finally:
                for active_sock in (sock, dsock):
                    if active_sock is not None:
                        try:
                            active_sock.close()
                        except OSError:
                            pass

        return _fail(last_error)

    def receive(self, receive_dir: str | None = None) -> None:
        """

        If a compatible local host is already running, this method attaches
        by updating the host's receive_dir for this session.

        If no host exists, starts a temporary host and blocks until Ctrl+C,
        then tears it down completely.

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

    def get_peer_capacity(self, to: str) -> dict:
        """
        Query the transfer capacity of a remote peer.

        Performs an auth handshake and sends a lightweight ``lan_status``
        request.  Returns a dict with keys:
          ``current`` (int) — transfers in progress on the peer
          ``max``     (int) — maximum concurrent transfers the peer accepts
          ``error``   (str) — present only on failure
        """
        import socket as _socket

        from nerve.lan.connect import LAN_PROTOCOL_VERSION
        from nerve.lan.util import (
            get_or_create_host_identity,
            recv_message,
            send_message,
        )

        host_str, ctrl_port, reg = self._resolve_target(to)
        token = self._resolve_token()
        sock = None

        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host_str, ctrl_port))
            enable_tcp_keepalive(sock)

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
                    "client_platform": detect_platform_name(),
                    "protocol_version": LAN_PROTOCOL_VERSION,
                },
            )

            auth_res, buf = recv_message(sock, buf)
            if auth_res.get("status") != "ok":
                return {"error": "Authentication failed."}

            send_message(sock, {"type": "lan_status"})
            status_res, _ = recv_message(sock, buf)

            if status_res.get("type") == "lan_status_result":
                return {
                    "current": status_res.get("current", 0),
                    "max": status_res.get("max", 1),
                }
            return {"error": "Unexpected response type from peer."}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def get_peers(self) -> list[Any]:
        """Return all known registered peers."""
        return PeerRegistry().list_peers()

    def get_transfers(self) -> list[TransferRecord]:
        """Return transfer records captured by this NerveLAN instance."""
        with self._transfers_lock:
            return list(self._transfers)

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Return recent SHA-256 chain-of-custody records from the audit log."""
        return read_audit_log(limit=limit, log_path=self._audit_log_path)

    def pack_container(
        self, source_path: str, output_path: str, password: str
    ) -> dict[str, Any]:
        """Encrypt a file or directory into a .nrv container and record SHA-256 custody."""
        if not password:
            return {"success": False, "error": "Password is required."}

        from nerve.lan.transfer import compute_file_sha256
        from nerve.nrv import pack_nrv

        base, ext = os.path.splitext(output_path)
        final_out = output_path if ext.lower() == ".nrv" else base + ".nrv"

        try:
            pack_nrv(source_path, final_out, password)
            sha256 = compute_file_sha256(final_out)
            size = Path(final_out).stat().st_size
            append_audit_log(
                {
                    "transfer_id": secrets.token_hex(6),
                    "direction": "pack",
                    "filename": Path(final_out).name,
                    "size": size,
                    "sha256": sha256,
                    "peer": "local",
                    "state": TransferState.COMPLETED.value,
                    "transferred_bytes": size,
                    "resumed_from": 0,
                },
                log_path=self._audit_log_path,
            )
            return {
                "success": True,
                "output_path": str(final_out),
                "sha256": sha256,
                "size": size,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def unpack_container(
        self, nrv_path: str, output_dir: str, password: str
    ) -> dict[str, Any]:
        """Decrypt and verify a .nrv container and record SHA-256 custody."""
        if not password:
            return {"success": False, "error": "Password is required."}

        from nerve.lan.transfer import compute_file_sha256
        from nerve.nrv import unpack_nrv

        try:
            src = Path(nrv_path)
            if not src.exists():
                return {"success": False, "error": f"Container not found: {nrv_path}"}
            sha256 = compute_file_sha256(src)
            size = src.stat().st_size
            unpack_nrv(str(src), output_dir, password)
            append_audit_log(
                {
                    "transfer_id": secrets.token_hex(6),
                    "direction": "unpack",
                    "filename": src.name,
                    "size": size,
                    "sha256": sha256,
                    "peer": "local",
                    "state": TransferState.COMPLETED.value,
                    "transferred_bytes": size,
                    "resumed_from": 0,
                },
                log_path=self._audit_log_path,
            )
            return {
                "success": True,
                "output_dir": str(output_dir),
                "sha256": sha256,
                "size": size,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def network_info(self) -> dict:
        """Return local hostname, platform, and non-loopback IPv4 addresses."""
        import socket as _socket

        hostname = _socket.gethostname()
        addresses = sorted(_local_ipv4_addresses())

        return {
            "hostname": hostname,
            "platform": detect_platform_name(),
            "addresses": addresses,
        }
