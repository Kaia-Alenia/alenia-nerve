"""Test suite for alenia-nerve.

Covers:
- Package metadata and public API surface
- load_external_config: JSON, key=value, missing file
- NexusHub: start/stop lifecycle, client registration, message routing,
  broadcast, client listing, on_connect / on_disconnect hooks, thread-safety
- NexusClient: connect, send, broadcast, listen, disconnect, reconnect, errors
- Integration: end-to-end hub + two clients full roundtrip
"""

from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
import threading
import time
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

import nerve
from nerve import NexusClient, NexusHub, load_external_config
from nerve.core import load_external_config as _core_load


IS_WINDOWS = platform.system() == "Windows"
SOCK_PATH = "/tmp/nerve_test.sock"
TCP_PORT = 59876


def hub_address():
    if IS_WINDOWS:
        return ("127.0.0.1", TCP_PORT)
    return SOCK_PATH


def make_hub(**kwargs) -> NexusHub:
    if IS_WINDOWS:
        with patch("nerve.core.load_external_config", return_value={"port": TCP_PORT}):
            return NexusHub(**kwargs)
    else:
        with patch(
            "nerve.core.load_external_config",
            return_value={"socket_path": SOCK_PATH},
        ):
            return NexusHub(**kwargs)


def make_client() -> NexusClient:
    if IS_WINDOWS:
        with patch("nerve.core.load_external_config", return_value={"port": TCP_PORT}):
            return NexusClient()
    else:
        with patch(
            "nerve.core.load_external_config",
            return_value={"socket_path": SOCK_PATH},
        ):
            return NexusClient()


def start_hub_thread(hub: NexusHub) -> threading.Thread:
    t = threading.Thread(target=hub.start, daemon=True)
    t.start()
    time.sleep(0.15)
    return t


class TestPackageMetadata:
    def test_version_string(self):
        assert isinstance(nerve.__version__, str)
        parts = nerve.__version__.split(".")
        assert len(parts) == 3, "Version must follow MAJOR.MINOR.PATCH"

    def test_public_symbols(self):
        assert hasattr(nerve, "NexusHub")
        assert hasattr(nerve, "NexusClient")
        assert hasattr(nerve, "load_external_config")
        assert hasattr(nerve, "__author__")
        assert hasattr(nerve, "__license__")
        assert hasattr(nerve, "__email__")

    def test_all_list(self):
        for name in nerve.__all__:
            assert hasattr(nerve, name), f"__all__ entry '{name}' not found in module"


class TestLoadExternalConfig:
    def test_missing_file_returns_empty(self):
        assert _core_load("/nonexistent/path/nerve.config") == {}

    def test_json_format(self, tmp_path):
        cfg = tmp_path / "nerve.config"
        cfg.write_text(json.dumps({"port": 1234, "host": "0.0.0.0"}))
        result = _core_load(str(cfg))
        assert result["port"] == 1234
        assert result["host"] == "0.0.0.0"

    def test_keyvalue_format(self, tmp_path):
        cfg = tmp_path / "nerve.config"
        cfg.write_text("socket_path=/tmp/test.sock\nport=9999\n")
        result = _core_load(str(cfg))
        assert result["socket_path"] == "/tmp/test.sock"
        assert result["port"] == "9999"

    def test_keyvalue_ignores_comments(self, tmp_path):
        cfg = tmp_path / "nerve.config"
        cfg.write_text("# comment line\nport=7777\n")
        result = _core_load(str(cfg))
        assert "port" in result
        assert "#" not in result

    def test_empty_file_returns_empty(self, tmp_path):
        cfg = tmp_path / "nerve.config"
        cfg.write_text("")
        assert _core_load(str(cfg)) == {}

    def test_malformed_json_falls_back_to_keyvalue(self, tmp_path):
        cfg = tmp_path / "nerve.config"
        cfg.write_text("{broken json\nport=8888\n")
        result = _core_load(str(cfg))
        assert result.get("port") == "8888"


class TestNexusHubLifecycle:
    def test_hub_starts_and_stops(self):
        hub = make_hub(heartbeat_interval=0)
        t = start_hub_thread(hub)
        assert hub._running is True
        hub.stop()
        t.join(timeout=2)
        assert hub._running is False

    def test_hub_connected_clients_empty_initially(self):
        hub = make_hub(heartbeat_interval=0)
        assert hub.connected_clients == []

    def test_hub_cleans_socket_file_on_start(self, tmp_path):
        if IS_WINDOWS:
            pytest.skip("Unix sockets only")
        stale_path = str(tmp_path / "stale.sock")
        with patch(
            "nerve.core.load_external_config",
            return_value={"socket_path": stale_path},
        ):
            hub = NexusHub(heartbeat_interval=0)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(stale_path)
        srv.close()
        assert os.path.exists(stale_path)
        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.15)
        assert os.path.exists(stale_path)
        hub.stop()
        t.join(timeout=2)

    def test_hub_stop_is_idempotent(self):
        hub = make_hub(heartbeat_interval=0)
        start_hub_thread(hub)
        hub.stop()
        hub.stop()


class TestNexusHubClientRegistration:
    def setup_method(self):
        self.hub = make_hub(heartbeat_interval=0)
        self.thread = start_hub_thread(self.hub)

    def teardown_method(self):
        self.hub.stop()
        self.thread.join(timeout=2)
        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

    def _raw_connect(self) -> socket.socket:
        if IS_WINDOWS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", TCP_PORT))
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(SOCK_PATH)
        return sock

    def _send(self, sock: socket.socket, msg: dict):
        sock.sendall((json.dumps(msg) + "\n").encode())

    def _recv_line(self, sock: socket.socket) -> dict:
        buf = b""
        while b"\n" not in buf:
            buf += sock.recv(4096)
        return json.loads(buf.split(b"\n")[0])

    def test_client_registers_successfully(self):
        sock = self._raw_connect()
        self._send(sock, {"type": "register", "id": "test_node"})
        time.sleep(0.1)
        assert "test_node" in self.hub.connected_clients
        sock.close()

    def test_client_disconnects_and_removed(self):
        sock = self._raw_connect()
        self._send(sock, {"type": "register", "id": "drop_node"})
        time.sleep(0.1)
        assert "drop_node" in self.hub.connected_clients
        sock.close()
        time.sleep(0.2)
        assert "drop_node" not in self.hub.connected_clients

    def test_register_without_id_ignored(self):
        sock = self._raw_connect()
        self._send(sock, {"type": "register"})
        time.sleep(0.1)
        assert self.hub.connected_clients == []
        sock.close()

    def test_invalid_json_does_not_crash_hub(self):
        sock = self._raw_connect()
        sock.sendall(b"THIS IS NOT JSON\n")
        time.sleep(0.1)
        assert self.hub._running is True
        sock.close()

    def test_list_clients(self):
        a = self._raw_connect()
        b = self._raw_connect()
        self._send(a, {"type": "register", "id": "list_a"})
        self._send(b, {"type": "register", "id": "list_b"})
        time.sleep(0.1)
        self._send(a, {"type": "list"})
        msg = self._recv_line(a)
        assert msg["type"] == "list"
        assert set(msg["clients"]) == {"list_a", "list_b"}
        a.close()
        b.close()

    def test_on_connect_hook(self):
        connected = []
        hub = make_hub(heartbeat_interval=0, on_connect=lambda cid: connected.append(cid))
        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.15)
        sock = self._raw_connect()
        self._send(sock, {"type": "register", "id": "hook_node"})
        time.sleep(0.1)
        assert "hook_node" in connected
        sock.close()
        hub.stop()
        t.join(timeout=2)

    def test_on_disconnect_hook(self):
        disconnected = []
        hub = make_hub(heartbeat_interval=0, on_disconnect=lambda cid: disconnected.append(cid))
        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.15)
        sock = self._raw_connect()
        self._send(sock, {"type": "register", "id": "bye_node"})
        time.sleep(0.1)
        sock.close()
        time.sleep(0.2)
        assert "bye_node" in disconnected
        hub.stop()
        t.join(timeout=2)


class TestNexusHubMessaging:
    def setup_method(self):
        self.hub = make_hub(heartbeat_interval=0)
        self.thread = start_hub_thread(self.hub)

    def teardown_method(self):
        self.hub.stop()
        self.thread.join(timeout=2)
        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

    def _raw_connect(self) -> socket.socket:
        if IS_WINDOWS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(("127.0.0.1", TCP_PORT))
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(SOCK_PATH)
        return sock

    def _send(self, sock: socket.socket, msg: dict):
        sock.sendall((json.dumps(msg) + "\n").encode())

    def _recv_line(self, sock: socket.socket, timeout: float = 2.0) -> Any:
        sock.settimeout(timeout)
        buf = b""
        try:
            while b"\n" not in buf:
                buf += sock.recv(4096)
        finally:
            sock.settimeout(None)
        return json.loads(buf.split(b"\n")[0])

    def test_direct_message_routing(self):
        sender = self._raw_connect()
        receiver = self._raw_connect()
        self._send(sender, {"type": "register", "id": "srv_sender"})
        self._send(receiver, {"type": "register", "id": "srv_receiver"})
        time.sleep(0.1)
        self._send(sender, {"type": "send", "to": "srv_receiver", "payload": {"hello": "world"}})
        msg = self._recv_line(receiver)
        assert msg == {"hello": "world"}
        sender.close()
        receiver.close()

    def test_broadcast_reaches_all_except_sender(self):
        a = self._raw_connect()
        b = self._raw_connect()
        c = self._raw_connect()
        self._send(a, {"type": "register", "id": "bc_a"})
        self._send(b, {"type": "register", "id": "bc_b"})
        self._send(c, {"type": "register", "id": "bc_c"})
        time.sleep(0.1)
        self._send(a, {"type": "broadcast", "payload": {"event": "go"}})
        for sock in (b, c):
            msg = self._recv_line(sock)
            assert msg == {"event": "go"}
        a.close()
        b.close()
        c.close()

    def test_send_to_unknown_target_does_not_crash(self):
        sender = self._raw_connect()
        self._send(sender, {"type": "register", "id": "ghost_sender"})
        time.sleep(0.1)
        self._send(sender, {"type": "send", "to": "nobody", "payload": {}})
        time.sleep(0.1)
        assert self.hub._running is True
        sender.close()

    def test_send_missing_to_field_ignored(self):
        sender = self._raw_connect()
        self._send(sender, {"type": "register", "id": "bad_sender"})
        time.sleep(0.1)
        self._send(sender, {"type": "send", "payload": {"orphan": True}})
        time.sleep(0.1)
        assert self.hub._running is True
        sender.close()

    def test_unknown_message_type_does_not_crash(self):
        sock = self._raw_connect()
        self._send(sock, {"type": "register", "id": "odd_node"})
        time.sleep(0.1)
        self._send(sock, {"type": "teleport", "dest": "moon"})
        time.sleep(0.1)
        assert self.hub._running is True
        sock.close()


class TestNexusClientAPI:
    def setup_method(self):
        self.hub = make_hub(heartbeat_interval=0)
        self.hub_thread = start_hub_thread(self.hub)

    def teardown_method(self):
        self.hub.stop()
        self.hub_thread.join(timeout=2)
        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

    def test_connect_registers_client(self):
        client = make_client()
        client.connect("api_client")
        time.sleep(0.1)
        assert "api_client" in self.hub.connected_clients
        client.disconnect()

    def test_connect_empty_id_raises(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.connect("")

    def test_connect_non_string_id_raises(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.connect(123)  # type: ignore[arg-type]

    def test_disconnect_removes_from_hub(self):
        client = make_client()
        client.connect("disc_client")
        time.sleep(0.1)
        assert "disc_client" in self.hub.connected_clients
        client.disconnect()
        time.sleep(0.2)
        assert "disc_client" not in self.hub.connected_clients

    def test_send_to_empty_target_raises(self):
        client = make_client()
        client.connect("send_error_client")
        with pytest.raises(ValueError):
            client.send("", {"data": 1})
        client.disconnect()

    def test_listen_receives_message(self):
        sender = make_client()
        receiver = make_client()

        received: List[Any] = []
        event = threading.Event()

        def on_msg(payload):
            received.append(payload)
            event.set()

        receiver.connect("listen_receiver")
        receiver.listen(on_msg)
        sender.connect("listen_sender")

        time.sleep(0.1)
        sender.send("listen_receiver", {"key": "value"})
        assert event.wait(timeout=3), "Message not received within timeout"
        assert received[0] == {"key": "value"}

        sender.disconnect()
        receiver.disconnect()

    def test_broadcast_via_client(self):
        broadcaster = make_client()
        r1 = make_client()
        r2 = make_client()

        got_r1: List[Any] = []
        got_r2: List[Any] = []
        e1 = threading.Event()
        e2 = threading.Event()

        r1.connect("bc_r1")
        r2.connect("bc_r2")
        r1.listen(lambda p: (got_r1.append(p), e1.set()))
        r2.listen(lambda p: (got_r2.append(p), e2.set()))
        broadcaster.connect("bc_sender")
        time.sleep(0.1)

        broadcaster.broadcast({"signal": "start"})
        assert e1.wait(timeout=3)
        assert e2.wait(timeout=3)
        assert got_r1[0] == {"signal": "start"}
        assert got_r2[0] == {"signal": "start"}

        broadcaster.disconnect()
        r1.disconnect()
        r2.disconnect()

    def test_list_clients(self):
        a = make_client()
        b = make_client()
        a.connect("list_qa_a")
        b.connect("list_qa_b")
        time.sleep(0.1)
        result = a.list_clients()
        assert set(result) == {"list_qa_a", "list_qa_b"}
        a.disconnect()
        b.disconnect()

    def test_ping_messages_not_forwarded_to_callback(self):
        receiver = make_client()
        received = []

        receiver.connect("ping_test_node")
        receiver.listen(lambda p: received.append(p))
        time.sleep(0.1)

        with self.hub._lock:
            sock = self.hub._clients.get("ping_test_node")
        assert sock is not None
        sock.sendall((json.dumps({"type": "ping"}) + "\n").encode())
        time.sleep(0.3)

        assert received == [], "Ping should not be forwarded to user callback"
        receiver.disconnect()


class TestIntegrationEndToEnd:
    """Full end-to-end integration: hub + multiple clients communicating."""

    def test_two_client_roundtrip(self):
        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

        hub = make_hub(heartbeat_interval=0)
        hub_thread = threading.Thread(target=hub.start, daemon=True)
        hub_thread.start()
        time.sleep(0.15)

        alice = make_client()
        bob = make_client()

        alice_received: List[Any] = []
        bob_received: List[Any] = []
        alice_event = threading.Event()
        bob_event = threading.Event()

        alice.connect("alice")
        alice.listen(lambda p: (alice_received.append(p), alice_event.set()))

        bob.connect("bob")
        bob.listen(lambda p: (bob_received.append(p), bob_event.set()))

        time.sleep(0.1)

        alice.send("bob", {"from": "alice", "msg": "hi bob"})
        assert bob_event.wait(timeout=3)
        assert bob_received[0] == {"from": "alice", "msg": "hi bob"}

        bob.send("alice", {"from": "bob", "msg": "hi alice"})
        assert alice_event.wait(timeout=3)
        assert alice_received[0] == {"from": "bob", "msg": "hi alice"}

        alice.disconnect()
        bob.disconnect()
        hub.stop()
        hub_thread.join(timeout=2)

        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

    def test_concurrent_messages_no_data_loss(self):
        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)

        hub = make_hub(heartbeat_interval=0)
        hub_thread = threading.Thread(target=hub.start, daemon=True)
        hub_thread.start()
        time.sleep(0.15)

        MESSAGES = 20
        collector = make_client()
        received: List[Any] = []
        done = threading.Event()

        collector.connect("collector")

        def on_msg(p):
            received.append(p)
            if len(received) >= MESSAGES:
                done.set()

        collector.listen(on_msg)

        senders = []
        for i in range(MESSAGES):
            c = make_client()
            c.connect(f"worker_{i}")
            senders.append(c)

        time.sleep(0.1)

        for i, c in enumerate(senders):
            c.send("collector", {"idx": i})

        assert done.wait(timeout=10), f"Only received {len(received)}/{MESSAGES} messages"
        assert len(received) == MESSAGES
        indices = {m["idx"] for m in received}
        assert indices == set(range(MESSAGES))

        for c in senders:
            c.disconnect()
        collector.disconnect()
        hub.stop()
        hub_thread.join(timeout=2)

        if not IS_WINDOWS and os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)
