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
Shared utilities for Nerve LAN V1.

This module centralizes minimal shared logic required by the Nerve LAN architecture
to satisfy security, memory, and persistence constraints without duplicating code
or polluting core IPC functionality.

Responsibilities:
- Control message size bounding (send/recv)
- Token resolution (explicit > config > env)
- Atomic JSON persistence
- Persistent stable host identity
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import uuid
from pathlib import Path

# Maximum size for a JSON control message in bytes (64KB).
# This is an implementation detail chosen to satisfy the bounded memory requirement.
MAX_CONTROL_MESSAGE_SIZE = 1024 * 64


class LanProtocolError(Exception):
    """Raised when the remote host sends unexpected or oversized data."""


class LanAuthenticationError(Exception):
    """Raised when authentication fails or required credentials are missing."""


# ---------------------------------------------------------------------------
# Control Message Framing
# ---------------------------------------------------------------------------


def send_message(sock: socket.socket, msg: dict) -> None:
    """
    Send a JSON-newline-delimited message over the socket.
    Raises LanProtocolError if the encoded message exceeds MAX_CONTROL_MESSAGE_SIZE.
    """
    raw = json.dumps(msg) + "\n"
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_CONTROL_MESSAGE_SIZE:
        raise LanProtocolError("Outgoing control message exceeds maximum size limit.")
    sock.sendall(encoded)


def recv_message(sock: socket.socket, buffer: bytearray) -> tuple[dict, bytearray]:
    """
    Receive a single JSON-newline-delimited message from the socket.

    The caller provides the existing buffer. This function reads from the socket
    until a newline is found, parses the first message, and explicitly returns
    a tuple containing the parsed message and a new bytearray with the remaining
    unread bytes.

    Raises LanProtocolError if the message exceeds MAX_CONTROL_MESSAGE_SIZE before
    a newline is found, or if the connection is closed prematurely.
    """
    while b"\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise LanProtocolError("Connection closed before message was complete.")
        buffer.extend(chunk)
        if len(buffer) > MAX_CONTROL_MESSAGE_SIZE:
            raise LanProtocolError(
                "Incoming control message exceeded maximum size limit."
            )

    line, _, remainder = buffer.partition(b"\n")
    try:
        msg = json.loads(line.decode("utf-8"))
        return msg, bytearray(remainder)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LanProtocolError(f"Invalid JSON from remote: {exc}") from exc


# ---------------------------------------------------------------------------
# Atomic Persistence & Identity
# ---------------------------------------------------------------------------


def atomic_json_write(target_path: Path, data: dict) -> None:
    """
    Safely write a dictionary to a JSON file using atomic replacement.
    Ensures data durability and prevents partial writes.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a unique temporary file in the same directory and filesystem
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=target_path.parent, prefix=f"{target_path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)

    try:
        # Write JSON data
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Explicitly close before replacing to satisfy Windows requirements
        os.replace(tmp_path, target_path)

    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def get_or_create_host_identity(registry_dir: Path) -> str:
    """
    Retrieve the persistent stable host identity (peer_id) for this Nerve installation.
    If it does not exist or is corrupt, generates a new one safely.

    This is the minimal implementation detail required to satisfy the MD's
    PERSISTENT STABLE IDENTITY requirement without overloading nerve.config.
    """
    identity_path = registry_dir / "identity.json"

    if identity_path.exists():
        try:
            raw = identity_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            host_id = data["host_id"]
            if not isinstance(host_id, str) or not host_id:
                raise ValueError("Invalid host_id format")
            return host_id
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            import time

            # Corruption handling: preserve evidence, do not overwrite silently.
            backup_name = f"identity.json.corrupt.{int(time.time())}"
            backup_path = identity_path.with_name(backup_name)
            try:
                os.replace(identity_path, backup_path)
                print(
                    f"[WARNING] Local host identity was corrupt. Preserved as {backup_name}"
                )
            except OSError:
                pass

    # Generate and persist new identity
    new_id = str(uuid.uuid4())
    atomic_json_write(identity_path, {"host_id": new_id})
    return new_id


# ---------------------------------------------------------------------------
# Authentication Resolution
# ---------------------------------------------------------------------------


def resolve_auth_token(
    explicit_token: str | None, config: dict, allow_interactive: bool = False
) -> str:
    """
    Resolve the LAN authentication token.
    Order of precedence:
      1. Explicit token (passed as argument)
      2. Configuration file (auth_token key)
      3. Environment variable (NERVE_AUTH_TOKEN)

    If missing and non-interactive, raises LanAuthenticationError.
    If missing and interactive, reuses existing Nerve credential generation flow.
    """
    token = (
        explicit_token or config.get("auth_token") or os.environ.get("NERVE_AUTH_TOKEN")
    )

    if token:
        return token

    if not allow_interactive:
        raise LanAuthenticationError(
            "Authentication token required but not provided in arguments, config, or environment."
        )

    # Missing credentials in interactive mode: securely generate
    from nerve import ui
    from nerve.genpass import generate_passphrase

    if not ui.is_tty():
        raise LanAuthenticationError(
            "Authentication token is missing and terminal is non-interactive. "
            "Please configure 'auth_token' in nerve.config or provide it explicitly."
        )

    ui.print_warning("No LAN authentication token configured.")
    choice = input("Do you want to generate a secure random token now? (y/N) ")
    if choice.strip().lower() != "y":
        raise LanAuthenticationError("User declined token generation.")

    new_token = generate_passphrase(4)
    ui.print_info(f"Generated secure token:\n\n    {new_token}\n")
    ui.print_info(
        "Please add this token to nerve.config as 'auth_token = ...'\n"
        "Starting temporary session with this token..."
    )
    return new_token
