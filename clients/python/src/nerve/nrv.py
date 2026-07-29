"""
ALENIA NERVE - NRV Secure Container Module
Author: KXLT (Alenia Studios)
License: GPL
Description: Packs and unpacks any file or directory in encrypted .nrv format
"""

import getpass
import json
import os
import struct
import tarfile

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC_BYTES = b"NRV\x00"
VERSION = 1
CHUNK_SIZE = 1024 * 1024  # 1 MB

# Argon2id parameters
ARGON2_MEMORY_COST = 262144  # 256 MB in KB
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

ARGON2_MIN_MEMORY_COST = 8192
ARGON2_MAX_MEMORY_COST = 1048576  # 1 GB
ARGON2_MIN_TIME_COST = 1
ARGON2_MAX_TIME_COST = 10
ARGON2_MIN_PARALLELISM = 1
ARGON2_MAX_PARALLELISM = 16


def _derive_key(
    password: str,
    salt: bytes,
    time_cost: int = ARGON2_TIME_COST,
    mem_cost: int = ARGON2_MEMORY_COST,
    parallelism: int = ARGON2_PARALLELISM,
) -> bytes:
    """Derive a 32-byte key using Argon2id."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=mem_cost,
        parallelism=parallelism,
        hash_len=32,
        type=Type.ID,
    )


def _get_password(password: str | None = None) -> str:
    """Obtain the password from parameter, environment variable, or interactively."""
    if password is not None:
        return password
    env_pass = os.environ.get("NERVE_NRV_PASSWORD")
    if env_pass:
        return env_pass
    return getpass.getpass("Password for .nrv container: ")


class _ChunkWriter:
    """Virtual buffer for on-the-fly TAR packing by writing encrypted chunks."""

    def __init__(self, write_chunk_cb):
        self.buffer = bytearray()
        self.write_chunk = write_chunk_cb

    def write(self, b):
        self.buffer.extend(b)
        while len(self.buffer) >= CHUNK_SIZE:
            chunk = bytes(self.buffer[:CHUNK_SIZE])
            self.buffer = self.buffer[CHUNK_SIZE:]
            self.write_chunk(chunk, False)
        return len(b)

    def flush(self):
        pass


def pack_nrv(source_path: str, output_nrv_path: str, password: str | None = None):
    """Packs any file or directory into an encrypted .nrv container."""
    base, ext = os.path.splitext(output_nrv_path)
    if ext.lower() != ".nrv":
        output_nrv_path = base + ".nrv"

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"[ERROR] Source file not found: {source_path}")

    password_str = _get_password(password)
    is_dir = os.path.isdir(source_path)

    # 1. Metadata
    if is_dir:
        original_size = 0
        try:
            for f in os.scandir(source_path):
                try:
                    if f.is_file(follow_symlinks=False) or f.is_symlink():
                        original_size += f.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
        except OSError:
            pass
    else:
        original_size = os.path.getsize(source_path)

    metadata = {
        "filename": os.path.basename(source_path.rstrip(os.sep)),
        "is_dir": is_dir,
        "original_size": original_size,
        "chunk_size": CHUNK_SIZE,
        "format_version": VERSION,
    }

    metadata_bytes = json.dumps(metadata).encode("utf-8")

    # 2. Cryptographic setup
    salt = os.urandom(16)
    meta_nonce = os.urandom(12)
    # Purely random generation per call to maintain AES-GCM confidentiality
    base_chunk_nonce = os.urandom(12)

    key = _derive_key(password_str, salt)
    aesgcm = AESGCM(key)

    # 3. Encrypt metadata
    meta_ciphertext = aesgcm.encrypt(meta_nonce, metadata_bytes, None)

    with open(output_nrv_path, "wb") as f_out:
        # Public Header
        f_out.write(MAGIC_BYTES)
        f_out.write(struct.pack("<H", VERSION))
        f_out.write(salt)
        f_out.write(struct.pack("<I", ARGON2_MEMORY_COST))
        f_out.write(struct.pack("<I", ARGON2_TIME_COST))
        f_out.write(struct.pack("<I", ARGON2_PARALLELISM))
        f_out.write(meta_nonce)
        f_out.write(struct.pack("<I", len(meta_ciphertext)))

        # Encrypted Metadata
        f_out.write(meta_ciphertext)

        # Base Chunk Nonce
        f_out.write(base_chunk_nonce)

        # 4. Streaming Data
        chunk_counter = 0

        def write_chunk(data: bytes, is_last: bool):
            nonlocal chunk_counter
            counter_bytes = struct.pack("<Q", chunk_counter)
            derived_nonce = (
                bytes(a ^ b for a, b in zip(base_chunk_nonce[:8], counter_bytes))
                + base_chunk_nonce[8:]
            )

            flag = b"\x01" if is_last else b"\x00"
            aad = salt + counter_bytes + flag

            ciphertext = aesgcm.encrypt(derived_nonce, data, aad)
            f_out.write(ciphertext)
            chunk_counter += 1

        if is_dir:
            cw = _ChunkWriter(write_chunk)
            with tarfile.open(fileobj=cw, mode="w|") as tar:
                tar.add(source_path, arcname=metadata["filename"])
            write_chunk(bytes(cw.buffer), True)
        else:
            with open(source_path, "rb") as f_in:
                chunk = f_in.read(CHUNK_SIZE)
                while True:
                    next_chunk = f_in.read(CHUNK_SIZE)
                    if not next_chunk:
                        write_chunk(chunk, True)
                        break
                    else:
                        write_chunk(chunk, False)
                        chunk = next_chunk

    print(f"[NERVE] Secure file successfully created: {output_nrv_path}")


def _is_safe_tarinfo(tarinfo, dest_dir):
    """Manually validate that a TAR entry is safe (fallback for Python < 3.12)."""
    # Prevent absolute paths and path traversal '..'
    if tarinfo.name.startswith("/") or ".." in tarinfo.name.split(os.sep):
        return False

    # Prevent symlinks or hardlinks pointing outside extraction directory
    if tarinfo.issym() or tarinfo.islnk():
        link_path = os.path.normpath(
            os.path.join(dest_dir, os.path.dirname(tarinfo.name), tarinfo.linkname)
        )
        dest_dir_real = os.path.realpath(dest_dir)
        link_path_real = os.path.realpath(link_path)
        if not link_path_real.startswith(dest_dir_real):
            return False

    return True


def unpack_nrv(nrv_path: str, output_dir: str, password: str | None = None) -> str:
    """Decrypts a .nrv container and reconstructs the original file or directory."""
    if not os.path.exists(nrv_path):
        raise FileNotFoundError(f"[ERROR] .nrv file not found: {nrv_path}")

    password_str = _get_password(password)

    with open(nrv_path, "rb") as f_in:
        magic = f_in.read(4)
        if magic != MAGIC_BYTES:
            raise ValueError("[ERROR] The file is not a valid .nrv.")

        version = struct.unpack("<H", f_in.read(2))[0]
        if version != 1:
            raise ValueError(f"[ERROR] Unsupported version: {version}")

        salt = f_in.read(16)
        mem_cost = struct.unpack("<I", f_in.read(4))[0]
        time_cost = struct.unpack("<I", f_in.read(4))[0]
        parallelism = struct.unpack("<I", f_in.read(4))[0]

        if not (ARGON2_MIN_MEMORY_COST <= mem_cost <= ARGON2_MAX_MEMORY_COST):
            raise ValueError(
                f"[ERROR] Argon2 memory_cost out of allowed range: {mem_cost}"
            )
        if not (ARGON2_MIN_TIME_COST <= time_cost <= ARGON2_MAX_TIME_COST):
            raise ValueError(
                f"[ERROR] Argon2 time_cost out of allowed range: {time_cost}"
            )
        if not (ARGON2_MIN_PARALLELISM <= parallelism <= ARGON2_MAX_PARALLELISM):
            raise ValueError(
                f"[ERROR] Argon2 parallelism out of allowed range: {parallelism}"
            )

        meta_nonce = f_in.read(12)
        meta_len = struct.unpack("<I", f_in.read(4))[0]

        meta_ciphertext = f_in.read(meta_len)

        key = _derive_key(password_str, salt, time_cost, mem_cost, parallelism)
        aesgcm = AESGCM(key)

        try:
            meta_bytes = aesgcm.decrypt(meta_nonce, meta_ciphertext, None)
        except InvalidTag:
            raise ValueError("[ACCESS DENIED] Incorrect password or corrupt metadata.")

        metadata = json.loads(meta_bytes.decode("utf-8"))
        is_dir = metadata.get("is_dir", False)
        chunk_size = metadata.get("chunk_size", CHUNK_SIZE)

        base_chunk_nonce = f_in.read(12)

        os.makedirs(output_dir, exist_ok=True)
        destination_path = os.path.join(output_dir, metadata["filename"])

        chunk_counter = 0

        # Read buffer for streaming decryption
        def read_decrypted_chunks():
            nonlocal chunk_counter
            chunk_ciphertext = f_in.read(chunk_size + 16)
            if not chunk_ciphertext:
                raise ValueError("[ERROR] Empty or truncated file in the data section.")

            while True:
                next_chunk_ciphertext = f_in.read(chunk_size + 16)
                is_last = not next_chunk_ciphertext

                counter_bytes = struct.pack("<Q", chunk_counter)
                derived_nonce = (
                    bytes(a ^ b for a, b in zip(base_chunk_nonce[:8], counter_bytes))
                    + base_chunk_nonce[8:]
                )
                flag = b"\x01" if is_last else b"\x00"
                aad = salt + counter_bytes + flag

                try:
                    plaintext = aesgcm.decrypt(derived_nonce, chunk_ciphertext, aad)
                except InvalidTag:
                    if is_last:
                        raise ValueError(
                            "[ERROR] Corruption in the last chunk (or truncation attack)."
                        )
                    else:
                        raise ValueError(
                            f"[ERROR] Corruption detected (or attempt to inject extra data). Chunk {chunk_counter} failed MAC."
                        )

                yield plaintext
                chunk_counter += 1

                if is_last:
                    # Validate trailing data after the last chunk flag
                    break
                else:
                    chunk_ciphertext = next_chunk_ciphertext

        if is_dir:
            # Process TAR streaming
            class ChunkReader:
                def __init__(self, generator):
                    self.generator = generator
                    self.buffer = b""

                def read(self, size=-1):
                    if size < 0:
                        ret = self.buffer + b"".join(self.generator)
                        self.buffer = b""
                        return ret

                    while len(self.buffer) < size:
                        try:
                            self.buffer += next(self.generator)
                        except StopIteration:
                            break

                    ret = self.buffer[:size]
                    self.buffer = self.buffer[size:]
                    return ret

            cr = ChunkReader(read_decrypted_chunks())
            with tarfile.open(fileobj=cr, mode="r|") as tar:
                try:
                    for member in tar:
                        dest_path = os.path.join(output_dir, member.name)
                        dest_path_real = os.path.realpath(dest_path)
                        output_dir_real = os.path.realpath(output_dir)
                        if (
                            os.path.commonpath([output_dir_real, dest_path_real])
                            != output_dir_real
                        ):
                            raise ValueError(
                                f"Path traversal attempt detected in: {member.name}"
                            )

                        if member.issym() or member.islnk():
                            if os.path.isabs(member.linkname):
                                print(
                                    f"[WARNING] Skipping absolute symlink/hardlink: {member.name} -> {member.linkname}"
                                )
                                continue
                            link_path = os.path.normpath(
                                os.path.join(
                                    output_dir,
                                    os.path.dirname(member.name),
                                    member.linkname,
                                )
                            )
                            link_path_real = os.path.realpath(link_path)
                            if (
                                os.path.commonpath([output_dir_real, link_path_real])
                                != output_dir_real
                            ):
                                print(
                                    f"[WARNING] Skipping unsafe symlink/hardlink pointing outside extraction dir: {member.name} -> {member.linkname}"
                                )
                                continue

                        if hasattr(tarfile, "data_filter"):
                            try:
                                tar.extract(
                                    member, path=output_dir, filter=tarfile.data_filter
                                )
                            except Exception as filter_err:  # noqa: BLE001
                                print(f"[WARNING] Skipping {member.name}: {filter_err}")
                        else:
                            tar.extract(member, path=output_dir)
                except Exception as e:  # noqa: BLE001
                    import shutil

                    if os.path.exists(destination_path):
                        if os.path.isdir(destination_path):
                            shutil.rmtree(destination_path)
                        else:
                            os.remove(destination_path)
                    raise ValueError(
                        f"Extraction aborted due to security violation or error: {e}"
                    )
        else:
            with open(destination_path, "wb") as f_out:
                f_out.writelines(read_decrypted_chunks())

    print(f"[NERVE] File reconstructed at: {destination_path}")
    return destination_path
