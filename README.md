# Nerve — Decentralized Nervous System for Local Sockets

[![License](https://img.shields.io/badge/License-Alenia%20Studios%20Tool%201.0-8a2be2.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blueviolet.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.7%2B-darkviolet.svg)](#)

> **Sovereignty, Speed, and Complete Privacy.** Nerve is the cross-platform local inter-process communication engine designed by **Alenia Studios** to orchestrate game development tools locally, requiring zero cloud dependency.

---

## The Concept: Sovereign Local Networks

In modern game development, the privacy of your assets, source code, and metadata is paramount. **Nerve** acts as an ultra-fast local data bus, allowing independent processes (such as sprite slicers, gif renderers, and system monitors) to sync in real-time with sub-millisecond latency, without sending a single byte outside your physical workstation.

---

## Multi-Platform Native Core (UDS & TCP)

Nerve is fully cross-platform and dynamically adapts to the host operating system to deliver the best local latency possible:
* **Linux & macOS**: Utilizes native **Unix Domain Sockets (UDS)** via `socket.AF_UNIX` at `/tmp/nerve.sock` for high-performance direct memory piping.
* **Windows**: Dynamically falls back to a specialized **local TCP connection** via `socket.AF_INET` at `127.0.0.1:50505`, ensuring 100% compatibility across developer workstations without modifying a single line of your tools' logic.

---

## v1.2.0 Stability & Identity Updates

Nerve has been heavily upgraded to offer production-grade resilience and studio identity:
* **Industrial Auto-Reconnection**: `NexusClient` features automatic background reconnection loops. If the connection drops or the Hub restarts, the client attempts connection every 2 seconds indefinitely, preserving the host application from crashes and registering back smoothly as soon as the Hub comes online.
* **Resilient JSON Validation**: The Hub evaluates incoming packets robustly. If corrupted or invalid payloads are sent, it registers an `[NERVE] Invalid Payload` error and proceeds without dropping the client socket or crashing the system.
* **Background Heartbeats (Latido)**: The Hub broadcasts verification ping packets (`{"type": "ping"}`) every 5 seconds to actively monitor and purge stale, dead or silently dropped connections, freeing up system sockets.
* **Aesthetic Colored Console**: Enhanced interactive experience featuring beautiful Alenia purple banners, success green logs, warning orange, and failure red errors using standard ANSI colors.
* **Verbose Mode**: Run the server with `--verbose` or `-v` flags to print a detailed, colored trace of every single message routed through the Hub.
* **External Configuration Support**: Easily configure ports and socket paths without altering code. Create a `nerve.config` file in your root folder as JSON or simple key-value text.

---

## Configuration File (`nerve.config`)

To customize socket paths or TCP ports globally, place a `nerve.config` file in your project's working directory.

**Option A (JSON Format):**
```json
{
  "socket_path": "/tmp/nerve.sock",
  "port": 50505,
  "host": "127.0.0.1"
}
```

**Option B (Simple Text Format):**
```text
socket_path=/tmp/nerve.sock
port=50505
```

---

## Key Features

* **Cross-Platform**: Zero configuration required; runs out-of-the-box on Windows, Linux, and macOS.
* **Line-Based Framing**: Robust packet handling using newline delimiters (`\n`) to prevent data collision or buffer merging under heavy throughput.
* **Hub-Client Architecture**: A single central coordinator (`NexusHub`) directs intelligent message routing to specific registered nodes (`NexusClient`).
* **Console Command Interface (CLI)**: Spawn and manage the hub globally from any terminal with a simple command.

---

## Official Installation

Install the official package from PyPI:

```bash
pip install alenia-nerve
```

*(If you are using a modern Linux distribution with PEP 668 PEP-managed packages, append the `--break-system-packages` flag or run inside a virtual environment)*:

```bash
pip install alenia-nerve --break-system-packages
```

---

## Command Line Interface (CLI)

Once installed, you can start the Nerve Hub globally from any terminal shell:

```bash
nerve start
```

For detailed message routing traces, run:
```bash
nerve start --verbose
```

### Help Menu:
```bash
nerve --help
```

---

## Simple Integration Example

### 1. Initialize the Client
Connect to the local hub by registering a unique client ID.

```python
from nerve import NexusClient

client = NexusClient()
client.connect("my_tool_id")
```

### 2. Send Message to a Specific Node
Send any JSON-serializable payload directly to another registered node:

```python
payload = {"progress": 100, "status": "COMPLETED"}
client.send("other_tool_id", payload)
```

### 3. Listen for Incoming Stream
Register an asynchronous callback function to listen to data streams in real-time:

```python
def handle_incoming(data):
    print(f"Received: {data}")

client.listen(handle_incoming)
```

---

## License and Intellectual Property

This software is distributed under the **ALENIA STUDIOS TOOL LICENSE Version 1.0**.

* **For the Indie Community**: 100% free for both commercial and non-commercial game development.
* **No AI Training**: Standalone scraping, training, or inclusion of this codebase in Artificial Intelligence datasets is strictly prohibited.

---
*Crafted with passion by Alenia Studios to power sovereign game creators.*
