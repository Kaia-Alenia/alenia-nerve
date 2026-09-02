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

import time
from typing import Any
from unittest.mock import MagicMock, patch

from nerve.lan.api import NerveLAN
from nerve.lan.events import HOST_STARTED, HOST_STARTING, HOST_STOPPED, HOST_STOPPING


def test_lan_event_dispatcher() -> None:
    lan = NerveLAN()

    events_fired = []

    def on_starting(*args: Any, **kwargs: Any) -> None:
        events_fired.append("starting")

    def on_started(*args: Any, **kwargs: Any) -> None:
        events_fired.append("started")

    def on_stopping(*args: Any, **kwargs: Any) -> None:
        events_fired.append("stopping")

    def on_stopped(*args: Any, **kwargs: Any) -> None:
        events_fired.append("stopped")

    lan.on(HOST_STARTING, on_starting)
    lan.on(HOST_STARTED, on_started)
    lan.on(HOST_STOPPING, on_stopping)
    lan.on(HOST_STOPPED, on_stopped)

    # We monkeypatch the underlying _host to prevent actual socket binding in simple unit tests
    # Wait, NerveHost by default attempts to bind. We will just test the events fire properly.

    # Actually, we can just test the dispatcher manually
    lan.events.dispatch(HOST_STARTING)
    assert "starting" in events_fired

    lan.events.dispatch(HOST_STARTED)
    assert "started" in events_fired

    lan.events.dispatch(HOST_STOPPING)
    assert "stopping" in events_fired

    lan.events.dispatch(HOST_STOPPED)
    assert "stopped" in events_fired

    lan.off(HOST_STARTING, on_starting)
    lan.events.dispatch(HOST_STARTING)
    # The count of "starting" shouldn't increase
    assert events_fired.count("starting") == 1


def test_lan_api_scan() -> None:
    lan = NerveLAN(verbose=False)

    with patch("socket.socket") as mock_socket:
        mock_sock_inst = MagicMock()
        mock_socket.return_value = mock_sock_inst

        # Simulate one valid response and then timeout
        mock_sock_inst.recvfrom.side_effect = [
            (
                b'{"type": "nerve_discovery_response", "hostname": "test-peer", "platform": "linux"}',
                ("192.168.1.100", 50511),
            ),
            TimeoutError(),
        ]

        results = lan.scan(timeout=0.1)
        assert len(results) == 1
        assert results[0].peer_name == "test-peer"
        assert results[0].address == "192.168.1.100"


def test_lan_api_send_file_not_found() -> None:
    lan = NerveLAN()
    res = lan.send("nonexistent_file.txt", to="192.168.1.10")
    assert not res.success
    assert "Path not found" in str(res.error)


def test_lan_api_diagnose_local() -> None:
    lan = NerveLAN()
    rep = lan.diagnose()
    assert "CONFIRMED" in rep["local"]["interface"]
    assert "CONFIRMED" in rep["local"]["address"]
    assert not rep["causes"]


def test_lan_api_get_transfers() -> None:
    lan = NerveLAN()
    transfers = lan.get_transfers()
    assert isinstance(transfers, list)
    assert len(transfers) == 0


# ---------------------------------------------------------------------------
# Bug #10 — scan nonce must be unique per call
# ---------------------------------------------------------------------------


def test_scan_nonce_unique() -> None:
    """Each scan must send a different nonce (Bug #10 fix).

    scan() broadcasts the same nonce to multiple addresses per call, so we
    collect the *set* of nonces seen per call and verify the two sets differ.
    """
    from unittest.mock import MagicMock, patch

    # nonces_per_scan[i] = set of nonces captured during scan call i
    nonces_per_scan: list[set[str]] = [set(), set()]
    call_count = [0]

    lan = NerveLAN(verbose=False)

    def capture_sendto(data: bytes, addr: tuple) -> None:
        text = data.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            if line.startswith("nonce="):
                idx = min(call_count[0], 1)
                nonces_per_scan[idx].add(line.split("=", 1)[1])

    mock_sock = MagicMock()
    mock_sock.sendto.side_effect = capture_sendto
    mock_sock.recvfrom.side_effect = TimeoutError()

    # Patch socket as seen from within nerve.lan.api (module-level import).
    with patch("nerve.lan.api.socket") as mock_socket_module:
        mock_socket_module.socket.return_value = mock_sock
        mock_socket_module.AF_INET = 2
        mock_socket_module.SOCK_DGRAM = 2
        mock_socket_module.SOL_SOCKET = 1
        mock_socket_module.SO_BROADCAST = 6
        mock_socket_module.gethostname.return_value = "testhost"
        mock_socket_module.gethostbyname_ex.return_value = (
            "testhost",
            [],
            ["10.0.0.5"],
        )

        call_count[0] = 0
        lan.scan(timeout=0.01)
        call_count[0] = 1
        lan.scan(timeout=0.01)

    assert nonces_per_scan[0], "scan() must call sendto at least once per call"
    assert nonces_per_scan[1], "scan() must call sendto at least once per call"
    nonce_first = next(iter(nonces_per_scan[0]))
    nonce_second = next(iter(nonces_per_scan[1]))
    assert nonce_first != nonce_second, "Nonce must differ between scans"


# ---------------------------------------------------------------------------
# Bug #9 — scan must use peer_id from response, not hostname
# ---------------------------------------------------------------------------


def test_scan_uses_peer_id_from_response() -> None:
    """DiscoveryResult.peer_id must come from the 'peer_id' field in the response."""
    import json
    from unittest.mock import MagicMock, patch

    stable_peer_id = "stable-uuid-1234"
    response = json.dumps(
        {
            "type": "nerve_discovery_response",
            "peer_id": stable_peer_id,
            "hostname": "my-machine",
            "platform": "Linux",
        }
    ).encode("utf-8")

    lan = NerveLAN(verbose=False)
    with patch("socket.socket") as mock_socket:
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sock.recvfrom.side_effect = [
            (response, ("192.168.1.50", 50511)),
            TimeoutError(),
        ]

        results = lan.scan(timeout=0.01)

    assert len(results) == 1
    assert results[0].peer_id == stable_peer_id, (
        f"peer_id should be '{stable_peer_id}', got '{results[0].peer_id}'"
    )
    assert results[0].peer_name == "my-machine"


# ---------------------------------------------------------------------------
# Bug #1 — send() must not crash when peer is in registry (no auth_token attr)
# ---------------------------------------------------------------------------


def test_send_known_peer_no_auth_token_attr(tmp_path: Any) -> None:
    """
    NerveLAN.send() must not raise AttributeError when the target is a
    known peer (Peer object has no auth_token attribute).
    """
    from unittest.mock import MagicMock, patch

    from nerve.lan.peer_registry import Peer, PeerRegistry

    # A peer with no auth_token field (correct design)
    fake_peer = Peer(
        peer_id="test-peer-001",
        name="mi-pc",
        hostname="mi-pc",
        platform="Linux",
        last_address="192.168.1.99",
        last_seen=time.time(),
    )
    assert not hasattr(fake_peer, "auth_token"), "Peer must not have auth_token"

    lan = NerveLAN(verbose=False)

    mock_reg = MagicMock(spec=PeerRegistry)
    mock_reg.get.return_value = fake_peer
    mock_reg._path = tmp_path / "peers.json"

    with patch("nerve.lan.api.PeerRegistry", return_value=mock_reg):
        # Connection will fail (no real host), but it must NOT raise AttributeError
        result = lan.send(str(tmp_path / "nonexistent.txt"), to="mi-pc")

    # Must fail gracefully — 'File not found' or connection error, NOT AttributeError
    assert not result.success
    assert "AttributeError" not in str(result.error), (
        f"send() must not raise AttributeError: {result.error}"
    )


# ---------------------------------------------------------------------------
# Bug #4 — send() of a directory must return an honest error
# ---------------------------------------------------------------------------


def test_send_directory_returns_honest_error(tmp_path: Any) -> None:
    """NerveLAN.send() must return an error for directories, not crash."""
    lan = NerveLAN(verbose=False)
    result = lan.send(str(tmp_path), to="192.168.1.10")
    assert not result.success
    assert result.error is not None
    assert "Directory" in result.error or "directory" in result.error.lower()
