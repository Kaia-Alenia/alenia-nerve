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
import asyncio
import json
import logging
import platform
import socket
from typing import Any

try:
    import websockets
    import websockets.exceptions

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from .core import NexusClient, load_external_config

logger = logging.getLogger(__name__)


def _probe_hub(timeout: float = 2.0) -> bool:
    """Return True if a Nerve Hub appears reachable; False otherwise."""
    config = load_external_config()
    is_windows = platform.system() == "Windows"
    if is_windows:
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 50505))
        address: tuple | str = (host, port)
        family = socket.AF_INET
    else:
        address = str(config.get("socket_path", "/tmp/nerve.sock"))
        family = socket.AF_UNIX

    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(address)
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


class NerveBridge:
    """
    HTTP/WebSockets to Nerve Hub Bridge.
    Allows web browsers and other WebSocket clients to connect to the Nerve IPC network.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50506,
        hub_config: dict[str, Any] | None = None,
    ):
        self.host = host
        self.port = port
        self.hub_config = hub_config or {}

        # We use a single NexusClient for the bridge to communicate with the Hub.
        # But we could also create a virtual client ID for each WS connection.
        self.nerve_client = NexusClient(**self.hub_config)
        self.active_websockets: set[Any] = set()
        self.ws_to_client_id: dict[Any, str] = {}
        self.client_id_to_ws: dict[str, Any] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self):
        if not WEBSOCKETS_AVAILABLE:
            logger.error(
                "The 'websockets' package is not installed. Run 'pip install websockets' to use the Bridge."
            )
            return

        if not _probe_hub():
            logger.error(
                "Nerve Hub is not running or unreachable. "
                "Start the hub first with 'nerve start'."
            )
            return

        self.nerve_client.connect("nerve_bridge_node")

        # Listen for messages from the Hub and route them back to the correct WS client.
        self.nerve_client.listen(self._handle_hub_message)

        logger.info(
            f"Starting Nerve Bridge WebSocket server on ws://{self.host}:{self.port}"
        )

        async def serve():
            self._loop = asyncio.get_running_loop()
            async with websockets.serve(self._ws_handler, self.host, self.port):
                await asyncio.Future()  # run forever

        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            logger.info("Bridge stopped.")
        finally:
            self.nerve_client.disconnect()

    def _handle_hub_message(self, payload: dict):
        """Route a message from the Nerve Hub to the correct WebSocket client."""
        target = payload.get("bridge_client_id")
        if target and target in self.client_id_to_ws and self._loop is not None:
            ws = self.client_id_to_ws[target]

            async def _send():
                try:
                    await ws.send(json.dumps(payload))
                except Exception:  # noqa: BLE001
                    pass

            asyncio.run_coroutine_threadsafe(_send(), self._loop)

    async def _ws_handler(self, websocket, *args, **kwargs):
        self.active_websockets.add(websocket)
        ws_id = f"ws_{id(websocket)}"
        self.ws_to_client_id[websocket] = ws_id
        self.client_id_to_ws[ws_id] = websocket

        logger.info(f"WebSocket client connected: {ws_id}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Bridge acts as a proxy: forward the WS message into the Nerve network.
                    self.nerve_client.send(
                        to=data.get("to", "hub"),
                        payload={"ws_id": ws_id, "data": data.get("payload", {})},
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Error processing WS message: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.active_websockets.discard(websocket)
            self.ws_to_client_id.pop(websocket, None)
            self.client_id_to_ws.pop(ws_id, None)
            logger.info(f"WebSocket client disconnected: {ws_id}")


def run_bridge(host="127.0.0.1", port=50506):
    bridge = NerveBridge(host=host, port=port)
    bridge.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bridge()
