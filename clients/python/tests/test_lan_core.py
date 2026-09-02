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

import platform
import socket
import threading
import time
from unittest.mock import patch

import pytest
from nerve.core import NexusClient, NexusHub

IS_WINDOWS = platform.system() == "Windows"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@patch("nerve.core.load_external_config", return_value={})
def test_hub_remote_requires_auth_token(mock_load):
    with pytest.raises(ValueError, match="auth_token is required when remote=True"):
        NexusHub(remote=True, auth_token=None)


@patch("nerve.core.load_external_config", return_value={})
def test_client_remote_requires_auth_token(mock_load):
    with pytest.raises(ValueError, match="auth_token is required when remote=True"):
        NexusClient(remote=True, auth_token=None)


def test_remote_hub_binds_to_tcp_any_platform():
    port = _find_free_port()
    with patch("nerve.core.load_external_config", return_value={"port": port}):
        hub = NexusHub(remote=True, auth_token="test-token")
        assert hub.socket_family == socket.AF_INET
        assert hub.address == ("0.0.0.0", port)

        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.3)
        assert hub._running

        # Verify we can connect to it via TCP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(("127.0.0.1", port))
            # Test it closes connection if we don't auth properly
            pass

        hub.stop()
        t.join(timeout=5)


def test_remote_client_connects_to_tcp():
    port = _find_free_port()
    with patch("nerve.core.load_external_config", return_value={"port": port}):
        hub = NexusHub(remote=True, auth_token="test-token")

        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.3)
        assert hub._running

        client = NexusClient(
            remote=True,
            remote_host="127.0.0.1",
            auth_token="test-token",
        )
        # Verify it configured AF_INET
        assert client.socket_family == socket.AF_INET
        assert client.address == ("127.0.0.1", port)

        # Actually connect
        client.connect(client_id="remote-test-client")
        assert client._socket is not None

        # Test basic list
        clients = client.list_clients()
        assert "remote-test-client" in clients

        client.disconnect()
        hub.stop()
        t.join(timeout=5)


def test_remote_hub_rejects_wrong_auth_token():
    port = _find_free_port()
    with patch("nerve.core.load_external_config", return_value={"port": port}):
        hub = NexusHub(remote=True, auth_token="test-token")

        t = threading.Thread(target=hub.start, daemon=True)
        t.start()
        time.sleep(0.3)
        assert hub._running

        client = NexusClient(
            remote=True,
            remote_host="127.0.0.1",
            auth_token="wrong-token",
        )

        client.connect(client_id="remote-test-bad-client")

        # the connect method currently returns, but closes the socket if auth fails
        # so _socket will be None
        assert client._socket is None

        hub.stop()
        t.join(timeout=5)
