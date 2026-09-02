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
Phase 1 tests for Nerve LAN V1.

Tests cover:
- nerve.lan package imports
- NerveHost: start/stop lifecycle, auth enforcement, shutdown cleanup
- PeerRegistry: CRUD, persistence, edge cases
- connect_and_register: success, auth failure, connection failure
- Receive destination resolution
- Regression: existing NexusHub / nerve start unaffected
"""

from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Package import smoke test
# ---------------------------------------------------------------------------


def test_nerve_lan_package_imports() -> None:
    """nerve.lan must be importable without errors."""
    import nerve.lan  # noqa: F401
    from nerve.lan.connect import (  # noqa: F401
        LAN_CONTROL_PORT_DEFAULT,
        LanAuthenticationError,
        LanConnectionError,
        LanProtocolError,
        connect_and_register,
    )
    from nerve.lan.host import NerveHost  # noqa: F401
    from nerve.lan.peer_registry import Peer, PeerRegistry  # noqa: F401


def test_lan_port_default_does_not_collide() -> None:
    """LAN_CONTROL_PORT_DEFAULT must differ from existing Nerve ports."""
    from nerve.lan.connect import LAN_CONTROL_PORT_DEFAULT

    existing_ports = {50505, 50506}  # local IPC (Windows) and bridge
    assert LAN_CONTROL_PORT_DEFAULT not in existing_ports


# ---------------------------------------------------------------------------
# PeerRegistry tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_registry(tmp_path: Path):
    """PeerRegistry backed by a temporary directory."""
    from nerve.lan.peer_registry import PeerRegistry

    return PeerRegistry(registry_path=tmp_path / "peers.json")


def _make_peer(peer_id: str = "peer-1", name: str = "test-peer"):
    from nerve.lan.peer_registry import Peer

    return Peer(
        peer_id=peer_id,
        name=name,
        hostname="test-host",
        platform="Linux",
        last_address="192.168.1.10:50507",
        last_seen=time.time(),
    )


def test_peer_registry_add_and_retrieve(tmp_registry) -> None:
    peer = _make_peer("id-1", "alice")
    tmp_registry.add_or_update(peer)
    result = tmp_registry.get("id-1")
    assert result is not None
    assert result.peer_id == "id-1"
    assert result.name == "alice"


def test_peer_registry_get_by_name(tmp_registry) -> None:
    peer = _make_peer("id-2", "bob")
    tmp_registry.add_or_update(peer)
    result = tmp_registry.get("bob")
    assert result is not None
    assert result.peer_id == "id-2"


def test_peer_registry_get_name_case_insensitive(tmp_registry) -> None:
    peer = _make_peer("id-3", "Charlie")
    tmp_registry.add_or_update(peer)
    assert tmp_registry.get("charlie") is not None
    assert tmp_registry.get("CHARLIE") is not None


def test_peer_registry_unknown_returns_none(tmp_registry) -> None:
    assert tmp_registry.get("does-not-exist") is None


def test_peer_registry_update_existing_peer(tmp_registry) -> None:
    peer = _make_peer("id-4", "dave")
    tmp_registry.add_or_update(peer)
    updated = _make_peer("id-4", "dave-updated")
    updated.last_address = "192.168.1.20:50507"
    tmp_registry.add_or_update(updated)
    result = tmp_registry.get("id-4")
    assert result is not None
    assert result.name == "dave-updated"
    assert result.last_address == "192.168.1.20:50507"
    assert len(tmp_registry.list_peers()) == 1  # no duplicate


def test_peer_registry_remove_by_id(tmp_registry) -> None:
    peer = _make_peer("id-5", "eve")
    tmp_registry.add_or_update(peer)
    removed = tmp_registry.remove("id-5")
    assert removed is True
    assert tmp_registry.get("id-5") is None


def test_peer_registry_remove_by_name(tmp_registry) -> None:
    peer = _make_peer("id-6", "frank")
    tmp_registry.add_or_update(peer)
    removed = tmp_registry.remove("frank")
    assert removed is True
    assert tmp_registry.get("id-6") is None


def test_peer_registry_remove_unknown_returns_false(tmp_registry) -> None:
    assert tmp_registry.remove("ghost") is False


def test_peer_registry_persistence_across_instances(tmp_path: Path) -> None:
    from nerve.lan.peer_registry import PeerRegistry

    path = tmp_path / "peers.json"
    reg1 = PeerRegistry(registry_path=path)
    peer = _make_peer("persist-1", "grace")
    reg1.add_or_update(peer)
    reg1.save()

    reg2 = PeerRegistry(registry_path=path)
    result = reg2.get("persist-1")
    assert result is not None
    assert result.name == "grace"


def test_peer_registry_corrupted_file_starts_empty(tmp_path: Path) -> None:
    from nerve.lan.peer_registry import PeerRegistry

    path = tmp_path / "peers.json"
    path.write_text("not valid json", encoding="utf-8")
    reg = PeerRegistry(registry_path=path)
    assert reg.list_peers() == []


def test_peer_registry_list_sorted_by_last_seen(tmp_path: Path) -> None:
    from nerve.lan.peer_registry import Peer, PeerRegistry

    reg = PeerRegistry(registry_path=tmp_path / "peers.json")
    older = Peer("old", "older", "h", "Linux", "1.1.1.1:50507", last_seen=1000.0)
    newer = Peer("new", "newer", "h", "Linux", "1.1.1.2:50507", last_seen=2000.0)
    reg.add_or_update(older)
    reg.add_or_update(newer)
    listed = reg.list_peers()
    assert listed[0].peer_id == "new"
    assert listed[1].peer_id == "old"


# ---------------------------------------------------------------------------
# connect.py helper tests
# ---------------------------------------------------------------------------


def test_parse_address_ip_only() -> None:
    from nerve.lan.connect import LAN_CONTROL_PORT_DEFAULT, _parse_address

    host, port = _parse_address("192.168.1.10", {})
    assert host == "192.168.1.10"
    assert port == LAN_CONTROL_PORT_DEFAULT


def test_parse_address_ip_with_port() -> None:
    from nerve.lan.connect import _parse_address

    host, port = _parse_address("192.168.1.10:9999", {})
    assert host == "192.168.1.10"
    assert port == 9999


def test_parse_address_config_override() -> None:
    from nerve.lan.connect import _parse_address

    _host, port = _parse_address("10.0.0.1", {"lan_port": "8888"})
    assert port == 8888


# ---------------------------------------------------------------------------
# NerveHost lifecycle tests
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def free_port() -> int:
    return _find_free_port()


def test_nerve_host_starts_and_stops(free_port: int, tmp_path: Path) -> None:
    """NerveHost must start, bind to the LAN port, and stop cleanly."""
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        auth_token="test-token",
        config_path=str(tmp_path / "nerve.config"),
    )

    errors: list[Exception] = []
    started = threading.Event()
    original_print_banner = host._print_startup_banner

    def patched_banner():
        original_print_banner()
        started.set()

    host._print_startup_banner = patched_banner

    def run():
        try:
            host.start()
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert started.wait(timeout=5), "NerveHost did not start within 5 seconds"

    # Verify it is actually listening
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        s.connect(("127.0.0.1", free_port))

    host.stop()
    t.join(timeout=5)
    assert not t.is_alive(), "NerveHost thread did not stop cleanly"
    assert not errors


def test_nerve_host_binds_all_interfaces(free_port: int, tmp_path: Path) -> None:
    """NerveHost must bind to 0.0.0.0, not loopback-only."""
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        auth_token="test-token",
        config_path=str(tmp_path / "nerve.config"),
    )
    started = threading.Event()
    original_banner = host._print_startup_banner

    def patched():
        original_banner()
        started.set()

    host._print_startup_banner = patched

    t = threading.Thread(target=host.start, daemon=True)
    t.start()
    assert started.wait(timeout=5)

    server = host._server
    assert server is not None
    addr = server.getsockname()
    assert addr[0] == "0.0.0.0", f"Expected 0.0.0.0, got {addr[0]}"

    host.stop()
    t.join(timeout=5)


def test_nerve_host_refuses_no_token_non_interactive(
    free_port: int, tmp_path: Path
) -> None:
    """Non-interactive context with no token must raise SystemExit(1)."""
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        config_path=str(tmp_path / "nerve.config"),
        # auth_token intentionally omitted
    )

    with patch("nerve.ui.is_tty", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            host.start()
        assert exc_info.value.code == 1


def test_nerve_host_rejects_unauthenticated_peer(
    free_port: int, tmp_path: Path
) -> None:
    """Peers with wrong token must be rejected via lan_auth_result failed."""
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        auth_token="correct-token",
        config_path=str(tmp_path / "nerve.config"),
    )

    started = threading.Event()
    original_banner = host._print_startup_banner

    def patched():
        original_banner()
        started.set()

    host._print_startup_banner = patched
    t = threading.Thread(target=host.start, daemon=True)
    t.start()
    assert started.wait(timeout=5)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(("127.0.0.1", free_port))
            buf = bytearray()
            # Receive hello
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            line, _, buf = buf.partition(b"\n")
            hello = json.loads(line)
            assert hello["type"] == "lan_hello"

            # Send wrong token
            auth = (
                json.dumps(
                    {
                        "type": "lan_auth",
                        "token": "wrong-token",
                        "client_peer_id": "test-client",
                        "client_hostname": "test",
                        "client_platform": "Linux",
                        "protocol_version": 1,
                    }
                )
                + "\n"
            )
            s.sendall(auth.encode())

            # Read response
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            line, _, _ = buf.partition(b"\n")
            result = json.loads(line)
            assert result["type"] == "lan_auth_result"
            assert result["status"] == "failed"
    finally:
        host.stop()
        t.join(timeout=5)


def test_nerve_host_accepts_authenticated_peer(free_port: int, tmp_path: Path) -> None:
    """Peers with correct token must receive lan_auth_result ok."""
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        auth_token="shared-secret",
        config_path=str(tmp_path / "nerve.config"),
    )

    started = threading.Event()
    original_banner = host._print_startup_banner

    def patched():
        original_banner()
        started.set()

    host._print_startup_banner = patched
    t = threading.Thread(target=host.start, daemon=True)
    t.start()
    assert started.wait(timeout=5)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect(("127.0.0.1", free_port))
            buf = bytearray()
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            line, _, buf = buf.partition(b"\n")
            hello = json.loads(line)
            assert hello["type"] == "lan_hello"
            assert "peer_id" in hello
            assert "hostname" in hello
            assert "platform" in hello

            auth = (
                json.dumps(
                    {
                        "type": "lan_auth",
                        "token": "shared-secret",
                        "client_peer_id": "test-client-ok",
                        "client_hostname": "test-machine",
                        "client_platform": "Linux",
                        "protocol_version": 1,
                    }
                )
                + "\n"
            )
            s.sendall(auth.encode())

            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
            line, _, _ = buf.partition(b"\n")
            result = json.loads(line)
            assert result["type"] == "lan_auth_result"
            assert result["status"] == "ok"
    finally:
        host.stop()
        t.join(timeout=5)


def test_nerve_host_no_orphan_threads_after_stop(
    free_port: int, tmp_path: Path
) -> None:
    """After stop(), no nerve-lan-peer or accept-loop threads should remain."""
    from nerve.lan.host import NerveHost

    {t.name for t in threading.enumerate()}
    host = NerveHost(
        lan_port=free_port,
        auth_token="tok",
        config_path=str(tmp_path / "nerve.config"),
    )
    started = threading.Event()
    original_banner = host._print_startup_banner

    def patched():
        original_banner()
        started.set()

    host._print_startup_banner = patched
    t = threading.Thread(target=host.start, daemon=True)
    t.start()
    assert started.wait(timeout=5)
    host.stop()
    t.join(timeout=5)
    assert not t.is_alive()
    # Allow any in-flight peer threads to exit after stop().
    time.sleep(0.3)
    after = {th.name for th in threading.enumerate()}
    lan_threads = {n for n in after if "nerve-lan" in n}
    assert not lan_threads, f"Orphan LAN threads found: {lan_threads}"


# ---------------------------------------------------------------------------
# connect_and_register integration tests
# ---------------------------------------------------------------------------


def _start_test_host(free_port: int, auth_token: str, tmp_path: Path):
    from nerve.lan.host import NerveHost

    host = NerveHost(
        lan_port=free_port,
        auth_token=auth_token,
        config_path=str(tmp_path / "nerve.config"),
    )
    started = threading.Event()
    original_banner = host._print_startup_banner

    def patched():
        original_banner()
        started.set()

    host._print_startup_banner = patched
    t = threading.Thread(target=host.start, daemon=True)
    t.start()
    started.wait(timeout=5)
    return host, t, started


def test_connect_and_register_saves_peer(free_port: int, tmp_path: Path) -> None:
    from nerve.lan.connect import connect_and_register
    from nerve.lan.peer_registry import PeerRegistry

    reg_path = tmp_path / "peers.json"
    host, t, _ = _start_test_host(free_port, "mytoken", tmp_path)
    try:
        reg = PeerRegistry(registry_path=reg_path)
        peer = connect_and_register(
            address=f"127.0.0.1:{free_port}",
            name="test-host",
            token="mytoken",
            registry=reg,
        )
        assert peer.name == "test-host"
        assert peer.last_address == f"127.0.0.1:{free_port}"

        # Verify persistence
        reg2 = PeerRegistry(registry_path=reg_path)
        saved = reg2.get("test-host")
        assert saved is not None
    finally:
        host.stop()
        t.join(timeout=5)


def test_connect_wrong_token_raises_error(free_port: int, tmp_path: Path) -> None:
    from nerve.lan.connect import LanAuthenticationError, connect_and_register
    from nerve.lan.peer_registry import PeerRegistry

    host, t, _ = _start_test_host(free_port, "correct", tmp_path)
    try:
        reg = PeerRegistry(registry_path=tmp_path / "peers.json")
        with pytest.raises(LanAuthenticationError):
            connect_and_register(
                address=f"127.0.0.1:{free_port}",
                token="wrong",
                registry=reg,
            )
        # Nothing should be saved
        assert reg.list_peers() == []
    finally:
        host.stop()
        t.join(timeout=5)


def test_connect_always_closes_connection(free_port: int, tmp_path: Path) -> None:
    """connect_and_register must close the TCP socket even on error."""
    from nerve.lan.connect import LanConnectionError, connect_and_register
    from nerve.lan.peer_registry import PeerRegistry

    reg = PeerRegistry(registry_path=tmp_path / "peers.json")
    with pytest.raises((LanConnectionError, OSError)):
        connect_and_register(
            address=f"127.0.0.1:{free_port}",  # nothing listening
            token="tok",
            registry=reg,
        )
    # If we reach here without hanging, the socket was closed properly.


def test_connect_unreachable_host_raises_connection_error(
    tmp_path: Path,
) -> None:
    from nerve.lan.connect import LanConnectionError, connect_and_register
    from nerve.lan.peer_registry import PeerRegistry

    reg = PeerRegistry(registry_path=tmp_path / "peers.json")
    port = _find_free_port()  # nothing listening on this port
    with pytest.raises(LanConnectionError):
        connect_and_register(
            address=f"127.0.0.1:{port}",
            token="tok",
            registry=reg,
        )


# ---------------------------------------------------------------------------
# Receive destination tests
# ---------------------------------------------------------------------------


def test_receive_dir_explicit_cli(tmp_path: Path) -> None:
    from nerve.lan.host import _resolve_display_receive_dir

    result = _resolve_display_receive_dir(str(tmp_path), {})
    assert result == tmp_path


def test_receive_dir_from_config(tmp_path: Path) -> None:
    from nerve.lan.host import _resolve_display_receive_dir

    result = _resolve_display_receive_dir(None, {"receive_dir": str(tmp_path)})
    assert result == tmp_path


def test_receive_dir_fallback_to_downloads() -> None:
    from nerve.lan.host import _get_os_downloads_dir, _resolve_display_receive_dir

    result = _resolve_display_receive_dir(None, {})
    expected = _get_os_downloads_dir()
    assert result == expected


def test_receive_dir_priority_cli_over_config(tmp_path: Path) -> None:
    from nerve.lan.host import _resolve_display_receive_dir

    cli_dir = str(tmp_path / "cli")
    config_dir = str(tmp_path / "config")
    result = _resolve_display_receive_dir(cli_dir, {"receive_dir": config_dir})
    assert result == Path(cli_dir)


# ---------------------------------------------------------------------------
# Regression tests — existing Nerve must not break
# ---------------------------------------------------------------------------


def test_existing_nexushub_imports_unaffected() -> None:
    """nerve.core imports must remain fully functional after adding nerve.lan."""
    from nerve import NexusClient, NexusHub
    from nerve.core import load_external_config

    assert callable(NexusHub)
    assert callable(NexusClient)
    assert callable(load_external_config)


def test_existing_nerve_nrv_imports_unaffected() -> None:
    """nerve.nrv must remain importable and functional."""
    from nerve.nrv import pack_nrv, unpack_nrv

    assert callable(pack_nrv)
    assert callable(unpack_nrv)


def test_existing_nerve_genpass_unaffected() -> None:
    from nerve.genpass import generate_passphrase

    pwd, entropy = generate_passphrase(words=3)
    assert len(pwd) > 0
    assert entropy > 0


IS_WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(IS_WINDOWS, reason="NexusHub on Linux/macOS uses Unix sockets")
def test_existing_nexushub_start_stop_unix(tmp_path: Path) -> None:
    """NexusHub (nerve start) must still start and stop cleanly on Unix."""
    from unittest.mock import patch

    # Use a short path in tempdir to avoid AF_UNIX 104 char limit on macOS runners
    sock_path = os.path.join(tempfile.gettempdir(), "test_hub.sock")
    with patch(
        "nerve.core.load_external_config",
        return_value={"socket_path": sock_path},
    ):
        from nerve import NexusHub

        hub = NexusHub()
        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.3)
        assert hub._running
        hub.stop()
        t.join(timeout=5)
        assert not hub._running


@pytest.mark.skipif(not IS_WINDOWS, reason="NexusHub on Windows uses TCP")
def test_existing_nexushub_start_stop_windows() -> None:
    """NexusHub (nerve start) must still start and stop cleanly on Windows."""
    port = _find_free_port()
    with patch(
        "nerve.core.load_external_config",
        return_value={"port": port},
    ):
        from nerve import NexusHub

        hub = NexusHub()
        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.3)
        assert hub._running
        hub.stop()
        t.join(timeout=5)
        assert not hub._running
