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
the final destination. A partial or tampered file never reaches the final path."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
from collections.abc import Callable
from pathlib import Path

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

DEFAULT_CHUNK_SIZE = 512 * 1024

# Suffixes used for temporary and resume metadata files during receive
_TMP_SUFFIX = ".nrv_tmp"
_TMP_META_SUFFIX = ".nrv_tmp.meta"


class TransferProtocolError(Exception):
    """Raised when binary protocol framing or integrity verification fails."""


def _get_temp_paths(final_path: Path) -> tuple[Path, Path]:
    """Return (tmp_path, meta_path) derived consistently from final_path."""
    tmp_path = final_path.with_suffix(final_path.suffix + _TMP_SUFFIX)
    meta_path = final_path.with_suffix(final_path.suffix + _TMP_META_SUFFIX)
    return tmp_path, meta_path


def _cleanup_temp_files(tmp_path: Path, meta_path: Path) -> None:
    """Best-effort removal of partial transfer and resume metadata files."""
    for path in (tmp_path, meta_path):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def compute_file_sha256(
    filepath: str | Path, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> str:
    """Compute the SHA-256 hex digest of a file using bounded-memory streaming."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def get_partial_transfer_offset(
    out_dir: str | Path,
    filename: str,
    expected_size: int,
    expected_sha256: str | None,
) -> int:
    """Return resumable byte offset for a matching partial transfer, or 0.

    Verifies that both the partial payload (.nrv_tmp) and its metadata sidecar
    (.nrv_tmp.meta) exist, match the expected size and SHA-256 digest, and contain
    a non-empty prefix strictly smaller than expected_size. Stale or mismatched
    partial artifacts are cleaned up automatically.
    """
    if not expected_sha256 or expected_size <= 0:
        return 0

    final_path = Path(out_dir) / filename
    tmp_path, meta_path = _get_temp_paths(final_path)

    if not tmp_path.exists() or not meta_path.exists():
        return 0

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError("Invalid resume metadata structure")
        if meta.get("sha256") != expected_sha256 or meta.get("size") != expected_size:
            _cleanup_temp_files(tmp_path, meta_path)
            return 0
        partial_size = tmp_path.stat().st_size
        if 0 < partial_size < expected_size:
            return partial_size
        _cleanup_temp_files(tmp_path, meta_path)
        return 0
    except (OSError, json.JSONDecodeError, ValueError):
        _cleanup_temp_files(tmp_path, meta_path)
        return 0


def send_file(
    conn: socket.socket,
    filepath: str | Path,
    metadata: dict | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress_callback: Callable[[int, int], None] | None = None,
    offset: int = 0,
    precomputed_sha256: str | None = None,
) -> str:
    """Send a file over *conn* using the Nerve LAN STANDARD binary protocol.

    Supports resuming from a byte *offset* when the receiver already holds a
    verified prefix. Returns the full-file SHA-256 hex digest.
    """
    path = Path(filepath)
    file_size = path.stat().st_size

    if offset < 0 or offset > file_size:
        raise ValueError(f"Invalid resume offset {offset} for file of size {file_size}")

    file_sha256 = (
        precomputed_sha256
        if precomputed_sha256 is not None
        else compute_file_sha256(path, chunk_size)
    )

    meta = dict(metadata) if metadata else {}
    meta["filename"] = path.name
    meta["size"] = file_size
    meta["sha256"] = file_sha256  # receiver uses this for verification
    meta["offset"] = offset

    meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")

    # 1. Header
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    conn.sendall(header)

    # 2. Metadata
    conn.sendall(meta_bytes)

    # 3. Stream remaining chunks from offset
    bytes_sent = offset
    with open(path, "rb") as f:
        if offset > 0:
            f.seek(offset)
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


def receive_file(
    conn: socket.socket,
    out_dir: str | Path,
    progress_callback: Callable[[str, int, int], None] | None = None,
    conflict_policy: str = "error",
    allow_resume: bool = True,
) -> tuple[Path | None, dict, str]:
    """Receive a file over *conn* using the Nerve LAN STANDARD binary protocol.

      1. Write chunks to <filename>.nrv_tmp (resuming at offset when negotiated)
      2. Preserve non-empty partial chunks with .nrv_tmp.meta on connection drop
      3. After EOF: verify full-file SHA-256 against metadata 'sha256'
      4. On match: rename temp -> final and remove .nrv_tmp.meta
      5. On mismatch: clean up temp artifacts, raise TransferProtocolError

    conflict_policy: 'error' | 'overwrite' | 'rename' | 'skip'

    Returns (final_path | None, metadata_dict, sha256_hex).
    None is returned for the path when conflict_policy='skip'.
    """
    # 1. Header
    header_data = _recv_exactly(conn, HEADER_SIZE)
    magic, version, msg_type, _flags, meta_length = struct.unpack(
        HEADER_FORMAT, header_data
    )

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
    expected_size = int(meta.get("size", 0))
    expected_sha256: str | None = meta.get("sha256")  # may be absent in old protocol
    offset = int(meta.get("offset", 0))

    if offset < 0:
        raise TransferProtocolError(f"Invalid negative offset: {offset}")

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

    tmp_path, meta_path = _get_temp_paths(final_path)

    if offset > 0:
        if not allow_resume:
            raise TransferProtocolError("RESUME_STATE_INVALID: resume is disabled")
        if not tmp_path.exists() or tmp_path.stat().st_size < offset:
            raise TransferProtocolError(
                f"RESUME_STATE_INVALID: missing or truncated partial file for offset {offset}"
            )
        if meta_path.exists() and expected_sha256 is not None:
            try:
                stored_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if stored_meta.get("sha256") != expected_sha256:
                    raise TransferProtocolError(
                        "RESUME_STATE_INVALID: partial metadata SHA-256 mismatch"
                    )
            except (OSError, json.JSONDecodeError) as exc:
                raise TransferProtocolError(
                    f"RESUME_STATE_INVALID: unreadable resume metadata ({exc})"
                ) from exc

        file_mode = "r+b"
        bytes_received = offset
    else:
        file_mode = "wb"
        bytes_received = 0
        if allow_resume and expected_sha256 is not None:
            meta_payload = {
                "filename": filename,
                "size": expected_size,
                "sha256": expected_sha256,
            }
            meta_path.write_text(json.dumps(meta_payload), encoding="utf-8")

    hasher = hashlib.sha256() if offset == 0 else None

    # 3. Stream chunks -> temp file
    try:
        with open(tmp_path, file_mode) as f:
            if offset > 0:
                f.seek(offset)
                f.truncate(offset)

            while True:
                chunk_len_data = _recv_exactly(conn, CHUNK_HEADER_SIZE)
                (chunk_length,) = struct.unpack(CHUNK_HEADER_FORMAT, chunk_len_data)

                if chunk_length == 0:
                    break

                chunk = _recv_exactly(conn, chunk_length)
                f.write(chunk)
                if hasher is not None:
                    hasher.update(chunk)

                bytes_received += chunk_length
                if progress_callback:
                    progress_callback(filename, bytes_received, expected_size)
    except Exception:
        # Preserve non-empty resumable artifacts on network failure; clean empty/disabled temp files
        keep_partial = (
            allow_resume
            and expected_sha256 is not None
            and tmp_path.exists()
            and tmp_path.stat().st_size > 0
        )
        if not keep_partial:
            _cleanup_temp_files(tmp_path, meta_path)
        raise

    if hasher is not None:
        computed_sha256 = hasher.hexdigest()
    else:
        computed_sha256 = compute_file_sha256(tmp_path, DEFAULT_CHUNK_SIZE)

    # 4. Integrity verification
    if expected_sha256 is not None and computed_sha256 != expected_sha256:
        _cleanup_temp_files(tmp_path, meta_path)
        raise TransferProtocolError(
            f"HASH_MISMATCH: expected {expected_sha256}, got {computed_sha256}"
        )

    # 5. Atomic rename temp -> final
    try:
        os.replace(tmp_path, final_path)
        meta_path.unlink(missing_ok=True)
    except OSError as exc:
        _cleanup_temp_files(tmp_path, meta_path)
        raise TransferProtocolError(f"DISK_WRITE_ERROR: {exc}") from exc

    return final_path, meta, computed_sha256


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
