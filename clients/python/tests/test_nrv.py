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
import struct

import pytest

from nerve.nrv import CHUNK_SIZE, pack_nrv, unpack_nrv


def test_empty_file(tmp_path):
    """Tests packing and unpacking an empty file."""
    source_file = tmp_path / "empty.txt"
    source_file.write_bytes(b"")

    nrv_file = tmp_path / "empty.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    assert nrv_file.exists()

    res_path = unpack_nrv(str(nrv_file), str(out_dir), "test_pass")
    assert os.path.exists(res_path)
    assert os.path.getsize(res_path) == 0


def test_wrong_password(tmp_path):
    """Tests that it fails fast with incorrect password (metadata MAC fails)."""
    source_file = tmp_path / "data.txt"
    source_file.write_bytes(b"Hello Nerve")

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "correct_pass")

    with pytest.raises(ValueError, match="Incorrect password or corrupt metadata"):
        unpack_nrv(str(nrv_file), str(out_dir), "wrong_pass")


def test_malicious_argon2_parameters(tmp_path):
    """Tests that abnormally high Argon2 parameters are rejected before key derivation."""
    source_file = tmp_path / "data.txt"
    source_file.write_bytes(b"Hello Nerve")

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    # Modify memory_cost in header.
    # Header format: MAGIC(4) + VERSION(2) + SALT(16) + MEM_COST(4)
    # MEM_COST starts at byte 4 + 2 + 16 = 22
    data = bytearray(nrv_file.read_bytes())

    # Pack an absurdly high memory cost (e.g. 2GB in KB: 2097152)
    malicious_mem_cost = 2097152
    data[22:26] = struct.pack("<I", malicious_mem_cost)
    nrv_file.write_bytes(data)

    with pytest.raises(ValueError, match="out of allowed range"):
        unpack_nrv(str(nrv_file), str(out_dir), "test_pass")


def test_metadata_corruption(tmp_path):
    """Tests that header manipulation is detected."""
    source_file = tmp_path / "data.txt"
    source_file.write_bytes(b"Hello Nerve")

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    # Corrupt 1 byte of metadata
    data = bytearray(nrv_file.read_bytes())
    data[50] ^= 0x01
    nrv_file.write_bytes(data)

    with pytest.raises(ValueError, match="corrupt metadata"):
        unpack_nrv(str(nrv_file), str(out_dir), "test_pass")


def test_chunk_corruption(tmp_path):
    """Tests that data chunk corruption is detected."""
    source_file = tmp_path / "data.txt"
    source_file.write_bytes(os.urandom(CHUNK_SIZE * 2 + 100))

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    # Corrupt a byte near the end of the file (in a data chunk)
    data = bytearray(nrv_file.read_bytes())
    data[-50] ^= 0x01
    nrv_file.write_bytes(data)

    with pytest.raises(ValueError, match="Corruption"):
        unpack_nrv(str(nrv_file), str(out_dir), "test_pass")


def test_truncation_attack(tmp_path):
    """Tests that if a .nrv file is cut in half, it is rejected."""
    source_file = tmp_path / "data.txt"

    source_file.write_bytes(os.urandom(CHUNK_SIZE * 2 + 100))

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    data = bytearray(nrv_file.read_bytes())
    # Truncate by removing the last chunk
    truncated_data = data[: -(100 + 16)]
    nrv_file.write_bytes(truncated_data)

    with pytest.raises(ValueError) as exc:
        unpack_nrv(str(nrv_file), str(out_dir), "test_pass")
    assert "Corruption" in str(exc.value) or "truncated" in str(exc.value).lower()


def test_trailing_data_attack(tmp_path):
    """Test that extra data after the last chunk is rejected."""
    source_file = tmp_path / "data.txt"
    source_file.write_bytes(b"Small payload")

    nrv_file = tmp_path / "data.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")

    data = bytearray(nrv_file.read_bytes())
    data.extend(b"injected garbage")
    nrv_file.write_bytes(data)

    with pytest.raises(ValueError) as exc:
        unpack_nrv(str(nrv_file), str(out_dir), "test_pass")
    assert "Corruption" in str(exc.value) or "failed MAC" in str(exc.value)


def test_directory_packing_and_symlinks(tmp_path):
    """Pack directory and validate secure extraction filters (Path Traversal)."""
    src_dir = tmp_path / "srcdir"
    src_dir.mkdir()
    (src_dir / "file1.txt").write_text("Hello")
    (src_dir / "file2.txt").write_text("World")

    # Create dangerous symlink if supported
    if hasattr(os, "symlink") and os.name != "nt":
        try:
            os.symlink("/etc/passwd", src_dir / "evil.txt")
        except OSError:
            pass

    nrv_file = tmp_path / "dir.nrv"
    out_dir = tmp_path / "outdir"

    pack_nrv(str(src_dir), str(nrv_file), "test_pass")

    res_path = unpack_nrv(str(nrv_file), str(out_dir), "test_pass")
    assert os.path.isdir(res_path)
    assert os.path.exists(os.path.join(res_path, "file1.txt"))

    evil_path = os.path.join(res_path, "evil.txt")
    # Validate that evil_path is not an absolute symlink to /etc/passwd.
    if os.path.exists(evil_path) and os.path.islink(evil_path):
        target = os.readlink(evil_path)
        assert not os.path.isabs(target) or not target.startswith("/etc")


def test_large_file_simulation(tmp_path):
    """Tests that a large file is processed without memory error."""
    source_file = tmp_path / "large.bin"
    # Write 5MB to disk sequentially
    with open(source_file, "wb") as f:
        f.writelines(os.urandom(1024 * 1024) for _ in range(5))

    nrv_file = tmp_path / "large.nrv"
    out_dir = tmp_path / "out"

    pack_nrv(str(source_file), str(nrv_file), "test_pass")
    unpack_nrv(str(nrv_file), str(out_dir), "test_pass")

    res_file = out_dir / "large.bin"
    assert res_file.exists()
    assert res_file.stat().st_size == 5 * 1024 * 1024
