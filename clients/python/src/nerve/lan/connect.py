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
nerve connect — LAN peer verification and registration.

Frozen requirement: Decision #4 — Peer Registry, connect, and Connection Lifetime.

nerve connect <IP> [--name NAME] [--token TOKEN]

Behavior:
1. Open a TCP connection to the remote LAN control plane.
2. Perform the auth handshake (auth_token).
3. Read peer identity (peer_id, hostname, platform).
4. Close the connection immediately — no idle TCP is held open.
5. Save or update the peer in the PeerRegistry.
6. Return the saved Peer.

Authentication is Layer 1 only (Phase 1). TLS (Layer 2) and NRV_SECURE
payload encryption (Layer 3) are Phase 3 concerns.
"""

from __future__ import annotations

import json
import platform
import socket

from nerve.lan.peer_registry import Peer, PeerRegistry, peer_from_handshake
from nerve.lan.util import (
    get_or_create_host_identity,
    recv_message,
    resolve_auth_token,
    send_message,
)

# LAN control plane default port.
# Implementation Proposal: 50507 (next free after 50505 IPC and 50506 bridge).
# This value is NOT frozen in any CLOSED — V1 decision.
# It is configurable via nerve.config key "lan_port".
LAN_CONTROL_PORT_DEFAULT: int = 50507

# Socket timeout for the connect handshake (seconds).
CONNECT_TIMEOUT: float = 10.0

# Protocol version advertised in handshake messages.
LAN_PROTOCOL_VERSION: int = 1


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LanAuthenticationError(Exception):
    """Raised when the remote host rejects authentication."""


class LanProtocolError(Exception):
    """Raised when the remote host sends an unexpected message."""


class LanConnectionError(Exception):
    """Raised when the TCP connection to the remote host fails."""


# ---------------------------------------------------------------------------
# Connect and register
# ---------------------------------------------------------------------------


def connect_and_register(
    address: str,
    name: str | None = None,
    token: str | None = None,
    config_path: str = "nerve.config",
    registry: PeerRegistry | None = None,
) -> Peer:
    """
    Connect to a remote Nerve LAN host, authenticate, and save the peer.

    Parameters
    ----------
    address:
        IP address or host:port of the remote LAN control plane.
        If no port is included, LAN_CONTROL_PORT_DEFAULT is used.
    name:
        Optional human-readable name to store for this peer.
        Defaults to the hostname reported by the remote peer.
    token:
        Auth token for this connection. If None, the token is loaded
        from nerve.config (auth_token key).
    config_path:
        Path to nerve.config for token and port defaults.
    registry:
        PeerRegistry instance to use. If None, the default registry is used.

    Returns
    -------
    Peer
        The saved peer entry.

    Raises
    ------
    LanAuthenticationError
        When the remote host rejects the token.
    LanConnectionError
        When the TCP connection cannot be established.
    LanProtocolError
        When the remote host sends unexpected data.
    """
    from nerve.core import load_external_config

    config = load_external_config(config_path)

    # Resolve token (must be present for non-interactive connect)
    resolved_token = resolve_auth_token(token, config, allow_interactive=False)

    # Parse address
    host, port = _parse_address(address, config)

    # Use provided registry or default
    reg = registry if registry is not None else PeerRegistry()

    # Use our persistent host identity as the client_peer_id
    client_peer_id = get_or_create_host_identity(reg._path.parent)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(CONNECT_TIMEOUT)
    buf: bytearray = bytearray()

    try:
        try:
            sock.connect((host, port))
        except (ConnectionRefusedError, OSError) as exc:
            raise LanConnectionError(
                f"Cannot connect to Nerve host at {host}:{port} — {exc}\n"
                "Verify that 'nerve host' is running on the target device."
            ) from exc

        # Receive HELLO from host
        hello, buf = recv_message(sock, buf)
        if hello.get("type") != "lan_hello":
            raise LanProtocolError(
                f"Expected 'lan_hello', got '{hello.get('type')}'. "
                "The remote service may not be a Nerve LAN host."
            )

        # Send authentication
        send_message(
            sock,
            {
                "type": "lan_auth",
                "token": resolved_token,
                "client_peer_id": client_peer_id,
                "client_hostname": socket.gethostname(),
                "client_platform": platform.system(),
                "protocol_version": LAN_PROTOCOL_VERSION,
            },
        )

        # Receive authentication result
        auth_result, buf = recv_message(sock, buf)
        if auth_result.get("type") != "lan_auth_result":
            raise LanProtocolError(
                f"Expected 'lan_auth_result', got '{auth_result.get('type')}'."
            )
        if auth_result.get("status") != "ok":
            reason = auth_result.get("reason", "unknown")
            raise LanAuthenticationError(
                f"Authentication rejected by {host}:{port} — reason: {reason}"
            )

        # Build and save peer
        peer_address = f"{host}:{port}"
        peer = peer_from_handshake(auth_result, peer_address, name)
        reg.add_or_update(peer)
        reg.save()
        return peer

    finally:
        # Connection is always closed after verification — Decision #4.
        try:
            sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_address(address: str, config: dict) -> tuple[str, int]:
    """
    Parse an address string into (host, port).

    Accepts:
        "192.168.1.10"
        "192.168.1.10:50507"
    """
    default_port = int(config.get("lan_port", LAN_CONTROL_PORT_DEFAULT))
    if ":" in address:
        host, _, port_str = address.rpartition(":")
        try:
            return host, int(port_str)
        except ValueError:
            # Not a valid port — treat the whole string as host
            return address, default_port
    return address, default_port
