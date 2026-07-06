import asyncio
import json
import logging
from typing import Set, Dict, Any

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from .core import NexusClient

logger = logging.getLogger(__name__)

class NerveBridge:
    """
    HTTP/WebSockets to Nerve Hub Bridge.
    Allows web browsers and other WebSocket clients to connect to the Nerve IPC network.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 50506, hub_config: Dict[str, Any] = None):
        self.host = host
        self.port = port
        self.hub_config = hub_config or {}
        
        # We use a single NexusClient for the bridge to communicate with the Hub.
        # But we could also create a virtual client ID for each WS connection.
        self.nerve_client = NexusClient(**self.hub_config)
        self.active_websockets: Set[Any] = set()
        self.ws_to_client_id: Dict[Any, str] = {}
        self.client_id_to_ws: Dict[str, Any] = {}
        
    def start(self):
        if not WEBSOCKETS_AVAILABLE:
            logger.error("The 'websockets' package is not installed. Run 'pip install websockets' to use the Bridge.")
            return

        # Connect the bridge itself to Nerve Hub
        self.nerve_client.connect("nerve_bridge_node")
        
        # We need to listen to all broadcast messages and route messages back to the correct WS client.
        # In a full implementation, we'd intercept specific messages. For now we broadcast all to all WS clients,
        # or handle targeted messages if the payload specifies a 'target_ws_id'.
        
        self.nerve_client.on("bridge_response", self._handle_hub_message)
        
        # Start WebSocket server
        logger.info(f"Starting Nerve Bridge WebSocket server on ws://{self.host}:{self.port}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        start_server = websockets.serve(self._ws_handler, self.host, self.port)
        
        try:
            loop.run_until_complete(start_server)
            loop.run_forever()
        except KeyboardInterrupt:
            logger.info("Bridge stopped.")
        finally:
            self.nerve_client.disconnect()

    def _handle_hub_message(self, type: str, payload: dict):
        target = payload.get("bridge_client_id")
        if target and target in self.client_id_to_ws:
            # Must run thread-safe in asyncio loop, but for simplicity:
            # We can't await here directly since it's called from nerve_client thread.
            # We would use asyncio.run_coroutine_threadsafe.
            # This is just a stub for the architecture.
            pass

    async def _ws_handler(self, websocket, path):
        self.active_websockets.add(websocket)
        # Assign a unique ID
        ws_id = f"ws_{id(websocket)}"
        self.ws_to_client_id[websocket] = ws_id
        self.client_id_to_ws[ws_id] = websocket
        
        logger.info(f"WebSocket client connected: {ws_id}")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Forward to Nerve Hub
                    # For simplicity, bridge acts as a proxy
                    self.nerve_client.send(
                        to=data.get("to", "hub"), 
                        payload={"ws_id": ws_id, "data": data.get("payload", {})}
                    )
                except Exception as e:
                    logger.error(f"Error processing WS message: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.active_websockets.remove(websocket)
            del self.ws_to_client_id[websocket]
            del self.client_id_to_ws[ws_id]
            logger.info(f"WebSocket client disconnected: {ws_id}")

def run_bridge(host="127.0.0.1", port=50506):
    bridge = NerveBridge(host=host, port=port)
    bridge.start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bridge()
