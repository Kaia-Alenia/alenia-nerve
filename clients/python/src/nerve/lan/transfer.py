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
Nerve LAN — STANDARD Data Plane (binary framing, streaming, SHA-256 integrity).

Protocol framing (big-endian):
  Header: MAGIC(4s) VERSION(B) TYPE(B) FLAGS(H) META_LENGTH(Q)
  Meta:   JSON-encoded dict (utf-8)
  Chunks: CHUNK_LEN(I=4 bytes) followed by chunk bytes; 0-length chunk = EOF

Sender includes 'sha256' in metadata.
Receiver writes to a temporary file and verifies the hash before renaming to
the final destination. A partial or tampered file never reaches the final path.

Frozen requirements:
  Decision #3  — File and Directory Conflict Policy
  Decision #6  — Streaming / no full-file RAM loading / 512 KB default chunk
  §72.3        — STANDARD transfer test matrix (SHA-256 success/mismatch)
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
from pathlib import Path
from typing import Callable, Optional

MAGIC = b"NLAN"
VERSION = 1

TYPE_FILE = 1
TYPE_DIRECTORY_MANIFEST = 2

# Network byte-order (big-endian): magic, version, type, flags, meta_length
HEADER_FORMAT = "!4sBBHQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# 4-byte unsigned int for chunk length; 0 signals EOF
CHUNK_HEADER_FORMAT = "!I"
CHUNK_HEADER_SIZE = struct.calcsize(CHUNK_HEADER_FORMAT)

LAN_DATA_PORT_DEFAULT = 50510

# Decision #6: default chunk size 512 KB
DEFAULT_CHUNK_SIZE = 512 * 1024

# Suffix used for temporary files during receive; never exposed as final output
_TMP_SUFFIX = ".nrv_tmp"


class TransferProtocolError(Exception):
    """Raised when binary protocol framing or integrity verification fails."""
    pass


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------


def send_file(
    conn: socket.socket,
    filepath: str | Path,
    metadata: Optional[dict] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Send a file over *conn* using the Nerve LAN STANDARD binary protocol.

    The SHA-256 hash of the file content is computed and included in the
    metadata so the receiver can verify integrity.

    Returns the SHA-256 hex digest of the bytes sent.
    """
    path = Path(filepath)
    file_size = path.stat().st_size

    # Compute SHA-256 before sending so it can be embedded in metadata.
    # For very large files this is a second read, but correctness requires it.
    # Future optimisation: two-pass streaming or separate hash channel.
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            hasher.update(block)
    file_sha256 = hasher.hexdigest()

    meta = dict(metadata) if metadata else {}
    meta["filename"] = path.name
    meta["size"] = file_size
    meta["sha256"] = file_sha256          # receiver uses this for verification

    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")

    # 1. Header
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    conn.sendall(header)

    # 2. Metadata
    conn.sendall(meta_bytes)

    # 3. Stream chunks
    bytes_sent = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            conn.sendall(struct.pack(CHUNK_HEADER_FORMAT, len(chunk)))
            conn.sendall(chunk)
            bytes_sent += len(chunk)
            if progress_callback:
                progress_callback(bytes_sent, file_size)

    # 4. EOF marker
    conn.sendall(struct.pack(CHUNK_HEADER_FORMAT, 0))

    return file_sha256


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------


def receive_file(
    conn: socket.socket,
    out_dir: str | Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    conflict_policy: str = "error",
) -> tuple[Optional[Path], dict, str]:
    """
    Receive a file over *conn* using the Nerve LAN STANDARD binary protocol.

    Write flow (Decision #5 — no partial file at final path):
      1. Write chunks to <filename>.nrv_tmp
      2. After EOF: compare computed SHA-256 against metadata 'sha256'
      3. On match: rename temp → final (atomic on POSIX, best-effort on Windows)
      4. On mismatch: delete temp, raise TransferProtocolError("HASH_MISMATCH")

    conflict_policy: 'error' | 'overwrite' | 'rename' | 'skip'

    Returns (final_path | None, metadata_dict, sha256_hex).
    None is returned for the path when conflict_policy='skip'.
    """
    # 1. Header
    header_data = _recv_exactly(conn, HEADER_SIZE)
    magic, version, msg_type, _flags, meta_length = struct.unpack(HEADER_FORMAT, header_data)

    if magic != MAGIC:
        raise TransferProtocolError(f"Invalid magic bytes: {magic!r}")
    if version != VERSION:
        raise TransferProtocolError(f"Unsupported protocol version: {version}")
    if msg_type != TYPE_FILE:
        raise TransferProtocolError(f"Expected FILE transfer, got type {msg_type}")

    # 2. Metadata
    meta_bytes = _recv_exactly(conn, meta_length)
    meta = json.loads(meta_bytes.decode("utf-8"))

    filename = meta.get("filename", "received_file")
    expected_size = meta.get("size", 0)
    expected_sha256: Optional[str] = meta.get("sha256")   # may be absent in old protocol

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    final_path = out_dir_path / filename

    # Conflict policy — applied to the FINAL path before writing temp
    if final_path.exists():
        if conflict_policy == "error":
            raise FileExistsError(
                f"Destination {final_path} already exists (conflict_policy='error')."
            )
        elif conflict_policy == "skip":
            # Must still drain the socket to keep the stream consistent
            _drain_chunks(conn)
            return None, meta, ""
        elif conflict_policy == "rename":
            base = final_path.stem
            ext = final_path.suffix
            counter = 1
            while final_path.exists():
                final_path = out_dir_path / f"{base}_{counter}{ext}"
                counter += 1
        elif conflict_policy == "overwrite":
            pass  # will replace at rename step
        else:
            raise ValueError(f"Unknown conflict_policy: {conflict_policy!r}")

    tmp_path = final_path.with_suffix(final_path.suffix + _TMP_SUFFIX)

    hasher = hashlib.sha256()
    bytes_received = 0

    # 3. Stream chunks → temp file
    try:
        with open(tmp_path, "wb") as f:
            while True:
                chunk_len_data = _recv_exactly(conn, CHUNK_HEADER_SIZE)
                (chunk_length,) = struct.unpack(CHUNK_HEADER_FORMAT, chunk_len_data)

                if chunk_length == 0:
                    break

                chunk = _recv_exactly(conn, chunk_length)
                f.write(chunk)
                hasher.update(chunk)

                bytes_received += chunk_length
                if progress_callback:
                    progress_callback(bytes_received, expected_size)
    except Exception:
        # Best-effort cleanup of the temp file on any receive error
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    computed_sha256 = hasher.hexdigest()

    # 4. Integrity verification
    if expected_sha256 is not None and computed_sha256 != expected_sha256:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise TransferProtocolError(
            f"HASH_MISMATCH: expected {expected_sha256}, got {computed_sha256}"
        )

    # 5. Atomic rename temp → final
    try:
        os.replace(tmp_path, final_path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise TransferProtocolError(f"DISK_WRITE_ERROR: {exc}") from exc

    return final_path, meta, computed_sha256


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _recv_exactly(conn: socket.socket, num_bytes: int) -> bytes:
    """Receive exactly *num_bytes* from *conn*, raising on premature close."""
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = conn.recv(num_bytes - len(buf))
        if not chunk:
            raise TransferProtocolError(
                f"Connection closed prematurely (expected {num_bytes} B, got {len(buf)} B)."
            )
        buf.extend(chunk)
    return bytes(buf)


def _drain_chunks(conn: socket.socket) -> None:
    """
    Read and discard all chunks from the socket (used by skip policy).
    Keeps the TCP stream in sync so the sender does not get a broken pipe.
    """
    while True:
        chunk_len_data = _recv_exactly(conn, CHUNK_HEADER_SIZE)
        (chunk_length,) = struct.unpack(CHUNK_HEADER_FORMAT, chunk_len_data)
        if chunk_length == 0:
            break
        _recv_exactly(conn, chunk_length)
