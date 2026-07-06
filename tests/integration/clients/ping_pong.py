import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../clients/python/src')))
from nerve.core import NexusClient

client = NexusClient()
client.connect("py_client")

def handle(msg):
    # msg is the full message dict: {"type": ..., "payload": ..., "from": ...}
    payload = msg.get("payload") if isinstance(msg, dict) else None
    if not isinstance(payload, dict):
        return
    if payload.get("event") == "ping":
        client.broadcast({
            "event": "pong",
            "from": "py_client",
            "timestamp": payload.get("timestamp"),
        })

client.listen(handle)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    client.disconnect()
