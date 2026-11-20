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

import json
import socket
import struct
import threading
from pathlib import Path

from nerve.lan.transfer import (
    _TMP_META_SUFFIX,
    _TMP_SUFFIX,
    CHUNK_HEADER_FORMAT,
    HEADER_FORMAT,
    MAGIC,
    TYPE_FILE,
    VERSION,
    TransferProtocolError,
    compute_file_sha256,
    get_partial_transfer_offset,
    receive_file,
    send_file,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_transfer_file_success(tmp_path: Path):
    port = _find_free_port()

    # Create a test file
    test_file = tmp_path / "source.txt"
    test_data = b"Hello Nerve LAN Transfer!" * 1024  # some bulk data
    test_file.write_bytes(test_data)

    out_dir = tmp_path / "received"
    out_dir.mkdir()

    # Socket pair or real sockets
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    results = {}

    def receiver_thread():
        conn, _ = server.accept()
        try:
            out_path, meta, r_hash = receive_file(conn, out_dir)
            results["out_path"] = out_path
            results["meta"] = meta
            results["hash"] = r_hash
        except Exception as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()

    # Sender side
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))

    try:
        s_hash = send_file(client, test_file)
    finally:
        client.close()

    t.join(timeout=5)

    assert "error" not in results, f"Receiver failed with {results.get('error')}"
    assert results["hash"] == s_hash, "Hashes do not match!"
    assert results["meta"]["filename"] == "source.txt"
    assert results["meta"]["sha256"] == s_hash, "sha256 must be in metadata"
    assert results["out_path"].read_bytes() == test_data
    # Verify no temp file left behind
    tmp = results["out_path"].with_suffix(results["out_path"].suffix + _TMP_SUFFIX)
    assert not tmp.exists(), "Temp file must not remain after successful transfer"


def test_transfer_hash_verified(tmp_path: Path) -> None:
    """Receiver must verify SHA-256 and accept a matching hash."""
    port = _find_free_port()
    test_file = tmp_path / "good.bin"
    test_data = b"integrity verified" * 512
    test_file.write_bytes(test_data)

    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    results: dict = {}

    def recv_th():
        conn, _ = server.accept()
        try:
            out_path, meta, recv_hash = receive_file(conn, out_dir)
            results["out_path"] = out_path
            results["recv_hash"] = recv_hash
            results["meta_hash"] = meta.get("sha256")
        except Exception as exc:
            results["error"] = exc
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=recv_th)
    t.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    sent_hash = send_file(client, test_file)
    client.close()
    t.join(timeout=5)

    assert "error" not in results, f"Unexpected error: {results.get('error')}"
    assert results["recv_hash"] == sent_hash
    assert results["meta_hash"] == sent_hash, "sha256 in metadata must match"
    assert results["out_path"].read_bytes() == test_data


def test_transfer_hash_mismatch_raises(tmp_path: Path) -> None:
    """
    Receiver must raise TransferProtocolError('HASH_MISMATCH') when the
    computed hash does not match the hash declared in metadata.
    """
    port = _find_free_port()
    test_file = tmp_path / "tampered.bin"
    test_data = b"real content" * 100
    test_file.write_bytes(test_data)

    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    results: dict = {}

    def recv_th():
        conn, _ = server.accept()
        try:
            receive_file(conn, out_dir)
        except TransferProtocolError as exc:
            results["error"] = str(exc)
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=recv_th)
    t.start()

    # Send with a deliberately wrong sha256 in metadata
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    file_size = test_file.stat().st_size
    wrong_hash = "a" * 64  # wrong, but valid hex length
    meta = {"filename": "tampered.bin", "size": file_size, "sha256": wrong_hash}
    meta_bytes = json.dumps(meta).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    client.sendall(header)
    client.sendall(meta_bytes)
    # Send actual content
    client.sendall(struct.pack(CHUNK_HEADER_FORMAT, len(test_data)))
    client.sendall(test_data)
    client.sendall(struct.pack(CHUNK_HEADER_FORMAT, 0))  # EOF
    client.close()
    t.join(timeout=5)

    assert "error" in results, "HASH_MISMATCH should have raised"
    assert "HASH_MISMATCH" in results["error"]
    # Final file must NOT exist
    assert not (out_dir / "tampered.bin").exists(), (
        "Final file must not exist on mismatch"
    )


def test_transfer_temp_file_cleanup_on_mismatch(tmp_path: Path) -> None:
    """No .nrv_tmp file must remain after a hash mismatch."""
    port = _find_free_port()
    test_file = tmp_path / "source.bin"
    test_file.write_bytes(b"x" * 1024)

    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    results: dict = {}

    def recv_th():
        conn, _ = server.accept()
        try:
            receive_file(conn, out_dir)
        except TransferProtocolError as exc:
            results["error"] = str(exc)
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=recv_th)
    t.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    data = b"x" * 1024
    meta = {"filename": "source.bin", "size": 1024, "sha256": "b" * 64}
    meta_bytes = json.dumps(meta).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    client.sendall(header + meta_bytes)
    client.sendall(struct.pack(CHUNK_HEADER_FORMAT, len(data)) + data)
    client.sendall(struct.pack(CHUNK_HEADER_FORMAT, 0))
    client.close()
    t.join(timeout=5)

    assert "HASH_MISMATCH" in results.get("error", "")
    # Temp file must be gone
    tmp = out_dir / ("source.bin" + _TMP_SUFFIX)
    assert not tmp.exists(), "Temp file must be deleted after mismatch"


def test_transfer_no_partial_file_on_premature_close(tmp_path: Path) -> None:
    """If the sender disconnects mid-transfer, no partial file at final path."""
    port = _find_free_port()
    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    results: dict = {}

    def recv_th():
        conn, _ = server.accept()
        try:
            receive_file(conn, out_dir)
        except TransferProtocolError as exc:
            results["error"] = str(exc)
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=recv_th)
    t.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    # Send header + meta, then disconnect without sending chunks
    meta = {"filename": "partial.bin", "size": 9999, "sha256": "c" * 64}
    meta_bytes = json.dumps(meta).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    client.sendall(header + meta_bytes)
    client.close()  # premature disconnect
    t.join(timeout=5)

    # Final file must not exist; temp must not exist either
    assert not (out_dir / "partial.bin").exists(), (
        "Final file must not exist after premature close"
    )
    tmp = out_dir / ("partial.bin" + _TMP_SUFFIX)
    assert not tmp.exists(), "Temp file must be cleaned up after premature close"


def test_transfer_invalid_magic(tmp_path: Path):
    port = _find_free_port()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    results = {}

    def receiver_thread():
        conn, _ = server.accept()
        try:
            receive_file(conn, tmp_path)
        except TransferProtocolError as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))

    # Send bad magic but full 16 byte header size
    import struct

    client.sendall(struct.pack("!4sBBHQ", b"BAD!", 1, 1, 0, 100))
    client.close()

    t.join(timeout=5)
    assert "error" in results
    assert "Invalid magic bytes" in str(results["error"])


def test_transfer_premature_close(tmp_path: Path):
    port = _find_free_port()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    results = {}

    def receiver_thread():
        conn, _ = server.accept()
        try:
            receive_file(conn, tmp_path)
        except TransferProtocolError as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))

    import struct

    # Send valid header but close
    client.sendall(struct.pack("!4sBBHQ", b"NLAN", 1, 1, 0, 100))
    client.close()

    t.join(timeout=5)
    assert "error" in results
    assert "Connection closed prematurely" in str(results["error"])


def test_transfer_resume_from_partial_chunks(tmp_path: Path) -> None:
    """Receiver keeps non-empty partial chunks and resumes from exact offset."""
    chunk_size = 32 * 1024
    test_file = tmp_path / "resumable.bin"
    payload = bytes((i % 251) for i in range(chunk_size * 4))
    test_file.write_bytes(payload)
    full_sha256 = compute_file_sha256(test_file, chunk_size)

    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    # Phase 1: send 2 of 4 chunks then drop connection
    port1 = _find_free_port()
    server1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server1.bind(("127.0.0.1", port1))
    server1.listen(1)
    first_attempt: dict = {}

    def recv_first() -> None:
        conn, _ = server1.accept()
        try:
            receive_file(conn, out_dir)
        except TransferProtocolError as exc:
            first_attempt["error"] = str(exc)
        finally:
            conn.close()
            server1.close()

    t1 = threading.Thread(target=recv_first)
    t1.start()

    c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c1.connect(("127.0.0.1", port1))
    meta = {
        "filename": "resumable.bin",
        "size": len(payload),
        "sha256": full_sha256,
        "offset": 0,
    }
    meta_bytes = json.dumps(meta).encode("utf-8")
    c1.sendall(
        struct.pack(HEADER_FORMAT, MAGIC, VERSION, TYPE_FILE, 0, len(meta_bytes))
    )
    c1.sendall(meta_bytes)
    for idx in range(2):
        part = payload[idx * chunk_size : (idx + 1) * chunk_size]
        c1.sendall(struct.pack(CHUNK_HEADER_FORMAT, len(part)) + part)
    c1.close()
    t1.join(timeout=5)

    assert "error" in first_attempt
    tmp_file = out_dir / ("resumable.bin" + _TMP_SUFFIX)
    meta_file = out_dir / ("resumable.bin" + _TMP_META_SUFFIX)
    assert tmp_file.exists()
    assert meta_file.exists()
    assert tmp_file.stat().st_size == chunk_size * 2

    resume_offset = get_partial_transfer_offset(
        out_dir, "resumable.bin", len(payload), full_sha256
    )
    assert resume_offset == chunk_size * 2

    # Phase 2: resume from offset and verify full integrity
    port2 = _find_free_port()
    server2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server2.bind(("127.0.0.1", port2))
    server2.listen(1)
    second_attempt: dict = {}

    def recv_second() -> None:
        conn, _ = server2.accept()
        try:
            out_path, recv_meta, recv_hash = receive_file(conn, out_dir)
            second_attempt["out_path"] = out_path
            second_attempt["meta"] = recv_meta
            second_attempt["hash"] = recv_hash
        except Exception as exc:
            second_attempt["error"] = exc
        finally:
            conn.close()
            server2.close()

    t2 = threading.Thread(target=recv_second)
    t2.start()

    c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c2.connect(("127.0.0.1", port2))
    sent_progress: list[int] = []
    sent_hash = send_file(
        c2,
        test_file,
        chunk_size=chunk_size,
        offset=resume_offset,
        precomputed_sha256=full_sha256,
        progress_callback=lambda sent, _total: sent_progress.append(sent),
    )
    c2.close()
    t2.join(timeout=5)

    assert "error" not in second_attempt, (
        f"Resume failed: {second_attempt.get('error')}"
    )
    assert sent_hash == full_sha256
    assert second_attempt["hash"] == full_sha256
    assert second_attempt["meta"]["offset"] == resume_offset
    assert second_attempt["out_path"].read_bytes() == payload
    assert sent_progress == [chunk_size * 3, chunk_size * 4]
    assert not tmp_file.exists()
    assert not meta_file.exists()


def test_transfer_resume_invalidated_when_source_hash_changes(tmp_path: Path) -> None:
    """Partial artifacts must be discarded if the source file SHA-256 changes."""
    out_dir = tmp_path / "recv"
    out_dir.mkdir()

    tmp_file = out_dir / ("changed.bin" + _TMP_SUFFIX)
    meta_file = out_dir / ("changed.bin" + _TMP_META_SUFFIX)
    tmp_file.write_bytes(b"partial-old-bytes")
    meta_file.write_text(
        json.dumps({"filename": "changed.bin", "size": 100, "sha256": "a" * 64}),
        encoding="utf-8",
    )

    offset = get_partial_transfer_offset(out_dir, "changed.bin", 100, "b" * 64)
    assert offset == 0
    assert not tmp_file.exists()
    assert not meta_file.exists()
