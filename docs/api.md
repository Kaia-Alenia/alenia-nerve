# API Reference

Nerve is structured with a simple and intuitive API. It features two core classes: `NexusHub` (the broker) and `NexusClient` (the tool interface).

---

## NexusHub

The central orchestration server that routes JSON packets between different registered tool client nodes.

### Initialization

```python
from nerve.core import NexusHub

hub = NexusHub(verbose=False)
```

### Methods

#### `hub.start()`
Binds the socket (either Unix Domain Socket `/tmp/nerve.sock` or TCP `127.0.0.1:50505` on Windows) and enters a loop to accept and orchestrate connection streams.

---

## NexusClient

The light wrapper included in your assets tools or pipeline scripts to talk to the Nerve Bus.

### Initialization

```python
from nerve import NexusClient

client = NexusClient()
```

### Methods

#### `client.connect(client_id)`
Establishes a connection to the active `NexusHub` and registers this node under a unique identifier string.
* **`client_id`** *(str)*: A unique name for your tool (e.g. `"FrameGrid_Engine"`).
* **Robustness**: If the Hub is offline, it enters an automatic, non-blocking reconnection loop every 2 seconds.

#### `client.send(to, payload)`
Sends a JSON-serializable dictionary directly to another registered client.
* **`to`** *(str)*: The target client identifier (e.g. `"Giftly_Engine"`).
* **`payload`** *(dict)*: Any data dictionary.
* **Resilience**: If the socket drops during transmission, it automatically triggers a background reconnect.

#### `client.listen(callback)`
Starts an asynchronous background thread listening for incoming messages directed to this client.
* **`callback`** *(function)*: A function to process received payloads (receives a python `dict` as its only parameter).
