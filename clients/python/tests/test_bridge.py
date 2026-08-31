import asyncio
import http
from unittest.mock import MagicMock, patch

import pytest

websockets = pytest.importorskip(
    "websockets",
    reason="optional 'bridge' dependency not installed (pip install alenia-nerve[bridge])",
)
import nerve.bridge
from nerve.bridge import NerveBridge


@pytest.fixture
def mock_websockets_serve():
    with patch("nerve.bridge.websockets.serve") as mock_serve:
        yield mock_serve


@pytest.fixture
def mock_nexus_client():
    with patch("nerve.bridge.NexusClient") as mock_client_class:
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_probe_hub():
    with patch("nerve.bridge._probe_hub", return_value=True) as mock_probe:
        yield mock_probe


def test_bridge_initialization(mock_nexus_client):
    bridge = NerveBridge(
        host="10.0.0.1", port=1234, allowed_origins=["http://localhost"]
    )
    assert bridge.host == "10.0.0.1"
    assert bridge.port == 1234
    assert bridge.allowed_origins == ["http://localhost"]
    assert bridge.nerve_client == mock_nexus_client


@pytest.mark.asyncio
async def test_process_request_allowed_origin(mock_nexus_client):
    bridge = NerveBridge(allowed_origins=["http://allowed.com"])

    mock_headers = {"Origin": "http://allowed.com"}
    result = bridge._process_request("/ws", mock_headers)
    assert result is None


@pytest.mark.asyncio
async def test_process_request_disallowed_origin(mock_nexus_client):
    bridge = NerveBridge(allowed_origins=["http://allowed.com"])

    mock_headers = {"Origin": "http://evil.com"}
    result = bridge._process_request("/ws", mock_headers)
    assert result is not None
    status, _, _ = result
    assert status == http.HTTPStatus.FORBIDDEN


@pytest.mark.asyncio
async def test_process_request_no_origin(mock_nexus_client):
    bridge = NerveBridge(allowed_origins=["http://allowed.com"])

    mock_headers = {}
    result = bridge._process_request("/ws", mock_headers)
    assert result is None


@pytest.mark.asyncio
async def test_process_request_default_origins(mock_nexus_client):
    bridge = NerveBridge(host="127.0.0.1", port=50506)

    # Should allow exact match
    mock_headers = {"Origin": "http://127.0.0.1:50506"}
    result = bridge._process_request("/ws", mock_headers)
    assert result is None

    # Should reject arbitrary
    mock_headers = {"Origin": "http://evil.com"}
    result = bridge._process_request("/ws", mock_headers)
    assert result is not None
    assert result[0] == http.HTTPStatus.FORBIDDEN


def test_bridge_start(mock_nexus_client, mock_probe_hub, mock_websockets_serve):
    bridge = NerveBridge()

    def mock_run(coro):
        coro.close()

    with patch("nerve.bridge.asyncio.run", side_effect=mock_run) as mock_asyncio_run:
        bridge.start()

        mock_nexus_client.connect.assert_called_once_with("nerve_bridge_node")
        mock_nexus_client.listen.assert_called_once_with(bridge._handle_hub_message)
        mock_asyncio_run.assert_called_once()
        mock_nexus_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_ws_handler_and_hub_message(mock_nexus_client):
    bridge = NerveBridge(host="10.0.0.1", port=1234)
    bridge._loop = asyncio.get_running_loop()

    # Mock a websocket connection that simulates an async generator
    class MockWebsocket:
        def __init__(self):
            self.sent_messages = []

        async def __aiter__(self):
            yield '{"to": "hub", "payload": {"foo": "bar"}}'
            # Also yield a bad message to hit the exception branch
            yield "invalid json"
            raise websockets.exceptions.ConnectionClosedOK(
                websockets.frames.Close(1000, ""),
                websockets.frames.Close(1000, ""),
                False,
            )

        async def send(self, msg):
            self.sent_messages.append(msg)

    mock_websocket = MockWebsocket()

    await bridge._ws_handler(mock_websocket)

    # Check state updates
    assert mock_websocket not in bridge.active_websockets
    assert mock_websocket not in bridge.ws_to_client_id

    # Check if nerve client was called
    mock_nexus_client.send.assert_called_once()
    _args, kwargs = mock_nexus_client.send.call_args
    assert kwargs["to"] == "hub"
    assert kwargs["payload"]["data"] == {"foo": "bar"}
    ws_id = kwargs["payload"]["ws_id"]

    # Check handle hub message routing
    bridge.client_id_to_ws[ws_id] = mock_websocket

    def mock_run_coroutine_threadsafe(coro, loop):
        _ = asyncio.ensure_future(coro, loop=loop)

    with patch(
        "asyncio.run_coroutine_threadsafe", side_effect=mock_run_coroutine_threadsafe
    ):
        bridge._handle_hub_message({"bridge_client_id": ws_id, "data": "back"})
        await asyncio.sleep(0.01)

    assert mock_websocket.sent_messages == [
        '{"bridge_client_id": "' + ws_id + '", "data": "back"}'
    ]

    # hit the failure branch for _handle_hub_message
    class ErrorWebsocket:
        async def send(self, msg):
            raise RuntimeError("Fail")

    bridge.client_id_to_ws[ws_id] = ErrorWebsocket()
    with patch(
        "asyncio.run_coroutine_threadsafe", side_effect=mock_run_coroutine_threadsafe
    ):
        bridge._handle_hub_message({"bridge_client_id": ws_id, "data": "back"})
        await asyncio.sleep(0.01)


@patch("nerve.bridge.WEBSOCKETS_AVAILABLE", False)
def test_bridge_start_no_websockets(mock_nexus_client):
    bridge = NerveBridge()
    bridge.start()
    mock_nexus_client.connect.assert_not_called()


@patch("nerve.bridge._probe_hub", return_value=False)
def test_bridge_start_no_hub(mock_probe_hub, mock_nexus_client):
    bridge = NerveBridge()
    bridge.start()
    mock_nexus_client.connect.assert_not_called()


def test_probe_hub_windows():
    with (
        patch("platform.system", return_value="Windows"),
        patch("socket.socket") as mock_sock,
    ):
        mock_instance = mock_sock.return_value
        mock_instance.connect.side_effect = OSError()
        assert not nerve.bridge._probe_hub()
        mock_instance.close.side_effect = OSError()
        assert not nerve.bridge._probe_hub()


def test_probe_hub_unix():
    with patch("platform.system", return_value="Linux"), patch("socket.socket"):
        assert nerve.bridge._probe_hub()


def test_run_bridge():
    with patch("nerve.bridge.NerveBridge") as mock_bridge_class:
        mock_instance = mock_bridge_class.return_value
        nerve.bridge.run_bridge(host="10.1.1.1", port=9999)
        mock_bridge_class.assert_called_once_with(host="10.1.1.1", port=9999)
        mock_instance.start.assert_called_once()
