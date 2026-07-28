# Alenia Nerve — Python Client & CLI Hub

[![PyPI Version](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet&label=PyPI)](https://pypi.org/project/alenia-nerve/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/alenia-nerve.svg?color=blueviolet&label=Downloads%2Fmo)](https://pypi.org/project/alenia-nerve/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-indigo.svg)](#)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-blueviolet.svg)](#)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](../../LICENSE)
[![Ko-fi](https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B.svg)](https://ko-fi.com/aleniastudios)

This is the official Python client library and Command Line Interface (CLI) for Alenia Nerve, the ultra-fast local inter-process communication (IPC) engine.

## The Nerve CLI Hub

The Python package includes the central CLI tool (`nerve`) used to boot and manage the central IPC routing Hub.

<div align="center">
  <img src="../../assets/python_client.svg" alt="Nerve Hub Console" width="100%">
</div>

### CLI Commands Reference

Nerve provides a comprehensive suite of commands to manage the IPC Hub, monitor traffic, and securely pack/unpack data.

#### Hub & Monitoring
- **`nerve start`**: Starts the central Nerve Hub (blocking process). Use `--verbose` for detailed real-time message routing logs.
- **`nerve monitor`**: Launches an interactive, terminal-based UI to view real-time hub statistics, connected nodes, and message throughput.
- **`nerve dashboard`**: Starts a visual web dashboard accessible at `http://localhost:8080` to monitor the local Nerve network.
- **`nerve bridge`**: Starts the HTTP/WebSocket bridge (default port `50506`) to allow external applications (e.g., browsers, remote clients) to securely communicate with the local Nerve IPC network.

#### Secure Containers (.nrv)
Nerve includes a high-security encrypted container format (`.nrv`) protected with AES-GCM and Argon2id.

- **`nerve pack <src> <out.nrv>`**: Packs a file or directory into a secure `.nrv` container. It will prompt for a password or use the `NERVE_NRV_PASSWORD` environment variable.
- **`nerve unpack <file.nrv> <out_dir>`**: Decrypts and unpacks a `.nrv` container into the specified output directory.
- **`nerve open <file.nrv>`**: Interactive command to open a `.nrv` container. It handles up to 3 password retries and uses native GUI prompts if run outside a terminal.
- **`nerve associate`**: Registers the `.nrv` file extension with your Operating System (Windows/macOS/Linux) and sets Nerve as the default application to open them.
- **`nerve unassociate`**: Removes the `.nrv` file association from your system.
- **`nerve genpass [--mode random|passphrase] [--length N] [--words N]`**: Generates a cryptographically secure random password or memorable passphrase.

---

## Client Installation

Install the package via pip:

```bash
pip install alenia-nerve
```

Or install it globally bypassing system package restrictions if needed (e.g., inside containers):

```bash
pip install alenia-nerve --break-system-packages
```

---

## Integration Example

### 1. Initialize Client
Connect to the local hub by registering a unique client ID.

```python
from nerve import NexusClient

client = NexusClient()
client.connect("my_python_node")
```

### 2. Send messages
Send a JSON-serializable payload directly to another registered node:

```python
payload = {"status": "processing", "progress": 45}
client.send("renderer_node", payload)
```

### 3. Broadcast messages
Broadcast a payload to every other node currently connected to the Hub:

```python
client.broadcast({"event": "reload_assets"})
```

### 4. Listen for streams
Register a callback function to listen to data streams in real-time:

```python
def handle_incoming(data):
    print(f"Received: {data}")

client.listen(handle_incoming)
```

---

## License

This software is distributed under the GNU General Public License v3 (GPL v3).

## Credits

The secure password generator uses the [EFF Large Wordlist](https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt) created by the Electronic Frontier Foundation, distributed under the [Creative Commons Attribution 3.0 License (CC BY 3.0)](https://creativecommons.org/licenses/by/3.0/).
