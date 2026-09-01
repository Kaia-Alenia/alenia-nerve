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

import os
from pathlib import Path
import socket
import threading

import pytest

from nerve.lan.transfer import receive_file, send_file

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def test_conflict_error_default(tmp_path: Path):
    port = _find_free_port()
    test_file = tmp_path / "source.txt"
    test_file.write_text("Hello")
    
    out_dir = tmp_path / "received"
    out_dir.mkdir()
    
    # Create the conflicting file
    conflict = out_dir / "source.txt"
    conflict.write_text("Old Data")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    
    results = {}
    
    def receiver_thread():
        conn, _ = server.accept()
        try:
            # Default policy is error
            receive_file(conn, out_dir)
        except Exception as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    
    try:
        send_file(client, test_file)
    except Exception as e:
        results["sender_error"] = e
    finally:
        client.close()
        
    t.join(timeout=5)
    
    assert "error" in results
    assert isinstance(results["error"], FileExistsError)
    assert conflict.read_text() == "Old Data"  # Existing file untouched

def test_conflict_skip(tmp_path: Path):
    port = _find_free_port()
    test_file = tmp_path / "source.txt"
    test_file.write_text("Hello")
    
    out_dir = tmp_path / "received"
    out_dir.mkdir()
    
    conflict = out_dir / "source.txt"
    conflict.write_text("Old Data")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    
    results = {}
    
    def receiver_thread():
        conn, _ = server.accept()
        try:
            out_path, meta, h = receive_file(conn, out_dir, conflict_policy="skip")
            results["out_path"] = out_path
        except Exception as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    send_file(client, test_file)
    client.close()
    
    t.join(timeout=5)
    
    assert "error" not in results
    assert results.get("out_path") is None  # None when skipped
    assert conflict.read_text() == "Old Data"  # Existing file untouched

def test_conflict_overwrite(tmp_path: Path):
    port = _find_free_port()
    test_file = tmp_path / "source.txt"
    test_file.write_text("New Data")
    
    out_dir = tmp_path / "received"
    out_dir.mkdir()
    
    conflict = out_dir / "source.txt"
    conflict.write_text("Old Data")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    
    results = {}
    
    def receiver_thread():
        conn, _ = server.accept()
        try:
            out_path, meta, h = receive_file(conn, out_dir, conflict_policy="overwrite")
            results["out_path"] = out_path
        except Exception as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    send_file(client, test_file)
    client.close()
    
    t.join(timeout=5)
    
    assert "error" not in results
    assert results["out_path"] == conflict
    assert conflict.read_text() == "New Data"  # Replaced!

def test_conflict_rename(tmp_path: Path):
    port = _find_free_port()
    test_file = tmp_path / "source.txt"
    test_file.write_text("New Data")
    
    out_dir = tmp_path / "received"
    out_dir.mkdir()
    
    conflict = out_dir / "source.txt"
    conflict.write_text("Old Data")
    conflict2 = out_dir / "source_1.txt"
    conflict2.write_text("Old Data 1")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    
    results = {}
    
    def receiver_thread():
        conn, _ = server.accept()
        try:
            out_path, meta, h = receive_file(conn, out_dir, conflict_policy="rename")
            results["out_path"] = out_path
        except Exception as e:
            results["error"] = e
        finally:
            conn.close()
            server.close()

    t = threading.Thread(target=receiver_thread)
    t.start()
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    send_file(client, test_file)
    client.close()
    
    t.join(timeout=5)
    
    assert "error" not in results
    assert results["out_path"] == out_dir / "source_2.txt"
    assert results["out_path"].read_text() == "New Data"
    assert conflict.read_text() == "Old Data"
    assert conflict2.read_text() == "Old Data 1"
