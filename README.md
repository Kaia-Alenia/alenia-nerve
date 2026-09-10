<div align="center">
  <h1>Nerve</h1>
  <p><b>The Ultimate LAN Transfer & IPC Streaming Engine</b></p>
  
  [![PyPI Version](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet)](https://pypi.org/project/alenia-nerve/)
  [![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-darkviolet.svg)](https://github.com/Kaia-Alenia/alenia-nerve)
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
  [![Ko-fi](https://img.shields.io/badge/Support_us-Ko--fi-FF5E5B.svg?logo=ko-fi&logoColor=white)](https://ko-fi.com/aleniastudios)

  <br>
  <p><b>Sovereignty, Speed, and Complete Privacy.</b> Nerve is a cross-platform command-line engine designed to securely pack and transfer massive datasets, compiled binaries, and stream data between Windows, Linux, macOS, and Android through Termux. <b>No cloud or Internet access is required.</b></p>
</div>

---

## What is Nerve?

Forget about uploading 20GB of massive databases or heavy compiled binaries to cloud storage just to send them to a server across the room.

Nerve turns your local network into a high-speed, peer-to-peer data bus. It separates traffic into two professional layers:
1. **The Control Plane:** For discovering devices on your LAN (`nerve scan`), secure token authentication, and sending real-time lightweight JSON messages between polyglot microservices (Python, Rust, Go, JS).
2. **The Data Plane:** A raw binary streaming transport built to move massive packed `.nrv` files via chunking without ever choking your RAM.

### No Internet does not mean no local network

Nerve does not contact external servers to discover, authenticate, or transfer files. All LAN traffic is direct between devices:

`nerve scan` sends a UDP discovery query, `nerve host` responds, the TCP control plane authenticates with the token, and the TCP data plane transfers the file.

To work without Internet access, Wi-Fi or Ethernet must remain connected to a common local network. You can turn off the router's WAN/Internet connection while keeping its LAN active, use a local hotspot, Wi-Fi Direct, or a direct Ethernet cable. If the network adapter itself is disabled, there is no IP route and no application can connect the devices.

### The Nerve Experience

Transferring gigabytes securely across operating systems requires packing your assets and providing your secure auth token:

```bash
# 1. On your Windows workstation (pack your heavy directory)
$ nerve pack D:\HeavyDatasets\Project project.nrv

# 2. On your Linux machine (configure auth_token in nerve.config)
$ nerve host --receive-dir ~/received_data

# 3. On your Windows workstation (Discover and Send)
$ nerve scan
> Found: linux-server (192.168.1.10)
$ nerve connect 192.168.1.10 --token "my-secure-password"
$ nerve send project.nrv --to linux-server
```

The same flow works in every direction: Linux to Windows, Windows to Linux, Windows to Windows, and macOS to any of them. The host receives files; `send` starts a transfer from the device that owns the file.

### Android through Termux

Android can participate in the same LAN by running Nerve's Python client inside [Termux](https://termux.dev/). No special Android application or Internet connection is required during the transfer.

```bash
# In Termux
pkg update
pkg install python git
termux-setup-storage
git clone https://github.com/Kaia-Alenia/alenia-nerve.git
cd alenia-nerve/clients/python
pip install .
```

To receive files on Android:

```bash
export NERVE_AUTH_TOKEN="my-local-token"
nerve host --receive-dir ~/storage/downloads
```

From Windows or Linux, find Android's IP and connect directly:

```bash
nerve diagnose 192.168.1.50
nerve connect 192.168.1.50 --token "my-local-token"
nerve send archive.zip --to 192.168.1.50
```

To send from Android to Windows or Linux, start `nerve host` on the destination and run `nerve send` from Termux using the file path. Keep Termux active during transfers; Android may suspend background processes when the screen is locked.

---

## Firewall and Port Requirements (Windows / Linux)

When using `nerve host` and `nerve scan` for Direct Device-to-Device communication, ensure your OS firewall allows traffic on the following ports:

| Port | Protocol | Purpose |
|--------|-----------|-----------|
| `50511` | UDP | Discovery (broadcasts from `nerve scan`) |
| `50507` | TCP | Control Plane (authentication and handshake; configurable) |
| `50510` | TCP | Data Plane (file transfers and large payloads) |

**Windows Firewall Solution:**
If `nerve scan` fails to find a Windows machine, the Windows Firewall is likely blocking incoming UDP 50511. Open **PowerShell as Administrator** and run:
```powershell
New-NetFirewallRule -DisplayName "Nerve LAN Discovery" -Direction Inbound -Protocol UDP -LocalPort 50511 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Control" -Direction Inbound -Protocol TCP -LocalPort 50507 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Data" -Direction Inbound -Protocol TCP -LocalPort 50510 -Action Allow -Profile Any
```

**AP Isolation (Wi-Fi Routers):**
If your router isolates Wi-Fi clients (blocking UDP broadcasts), `nerve scan` will fail. You can bypass this by scanning the exact IP directly (unicast):
```bash
nerve scan 192.168.1.50
```

**Linux Firewall Solution (UFW):**
If you are running a strict firewall on Linux (like Ubuntu), incoming UDP broadcasts might be dropped. Allow the ports via UFW:
```bash
sudo ufw allow 50511/udp
sudo ufw allow 50507/tcp
sudo ufw allow 50510/tcp
```

**Fallback: Direct Connection**
If discovery continues to fail due to strict router configurations, you can bypass `nerve scan` entirely and connect directly to the host's IP address:
```bash
$ nerve connect 192.168.1.50 --token "my-secure-password"
```
To find your local IP address:

```powershell
# Windows
ipconfig
```

```bash
# Linux / macOS / Termux
ip addr
# If ip is unavailable in Termux:
ifconfig
```

Use the private IPv4 address of the adapter that connects both devices, such as `192.168.1.50`, `10.0.0.25`, or `172.20.10.4`. Do not use `127.0.0.1`; that address only works inside the same device.

---

## Core Features

* **Terminal-Native Transfers:** Direct `Linux <-> Windows` and `Windows <-> Windows` transfers out of the box.
* **Dual-Architecture Engine:** Uses ultra-low latency **Unix Domain Sockets (UDS)** for local IPC, and dynamically pivots to **TCP Binary Streams** when reaching out to the LAN.
* **True Streaming (No Memory Bloat):** Massive files are broken into `.nrv` binary chunks on the fly. Nerve will not load a 10GB file into your RAM.
* **Secure by Default:** LAN connections require an auth token configured in `nerve.config` or `NERVE_AUTH_TOKEN`; `nerve connect` also accepts `--token`. LAN mode is strictly opt-in. Unless you run `nerve host`, Nerve remains completely silent and isolated.
* **Polyglot SDKs:** Need to wire a Rust backend to a Python data pipeline locally? Nerve provides official clients to orchestrate local microservices with auto-reconnection and background heartbeats.

---

##  Supported Clients & Integration

Nerve is structured as a Monorepo containing the main Hub and official client libraries. Below you can find the installation and a simple integration example for each supported language.

### Python Client & CLI Hub

[![Python](https://img.shields.io/badge/Python-3.10%2B-indigo.svg?logo=python&logoColor=white)](#)
[![PyPI](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet&label=PyPI)](https://pypi.org/project/alenia-nerve/)
[![Downloads](https://img.shields.io/pypi/dm/alenia-nerve.svg?color=blueviolet&label=Downloads%2Fmo)](https://pypi.org/project/alenia-nerve/)

✓ **Installation:**
```bash
python3 -m venv alenia_env
source alenia_env/bin/activate   # Windows: alenia_env\Scripts\activate
pip install alenia-nerve
```

✓ **Simple Integration Example:**
```python
from nerve import NexusClient

client = NexusClient()
client.connect("my_python_tool")

# Send to a specific node
client.send("renderer", {"progress": 100, "status": "DONE"})

# Listen for incoming messages
def on_message(data):
    print(f"Received: {data}")

client.listen(on_message)
```

---

### Rust Client

[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange.svg?logo=rust&logoColor=white)](#)
[![crates.io](https://img.shields.io/crates/v/alenia-nerve.svg?color=orange&label=crates.io)](https://crates.io/crates/alenia-nerve)
[![docs.rs](https://img.shields.io/docsrs/alenia-nerve.svg?color=blue&label=docs.rs)](https://docs.rs/alenia-nerve)

✓ **Installation:**
```bash
cargo add alenia-nerve
```

✓ **Simple Integration Example:**
```rust
use alenia_nerve::{NexusClient, ConnectionAddress};
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut client = NexusClient::new(Duration::from_secs(1), "", None);
    client.connect("my_rust_tool").await?;

    client.send("renderer", serde_json::json!({"status": "ready"}))?;

    client.listen(|msg| println!("Received: {}", msg), None).await;
    Ok(())
}
```

---

### JavaScript / Node.js Client

[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933.svg?logo=nodedotjs&logoColor=white)](#)
[![npm](https://img.shields.io/npm/v/alenia-nerve.svg?color=cb3837&label=npm)](https://www.npmjs.com/package/alenia-nerve)
[![Downloads](https://img.shields.io/npm/dm/alenia-nerve.svg?color=cb3837&label=Downloads%2Fmo)](https://www.npmjs.com/package/alenia-nerve)

✓ **Installation:**
```bash
npm install alenia-nerve
```

✓ **Simple Integration Example:**
```javascript
const { NexusClient } = require("alenia-nerve");

const client = new NexusClient();
await client.connect("my_js_tool");

client.send("renderer", { progress: 100, status: "DONE" });

client.listen((data) => {
    console.log("Received:", data);
});
```

---

### Go Client

[![Go](https://img.shields.io/badge/Go-1.21%2B-00ADD8.svg?logo=go&logoColor=white)](#)
[![pkg.go.dev](https://pkg.go.dev/badge/github.com/Kaia-Alenia/alenia-nerve/clients/go.svg)](https://pkg.go.dev/github.com/Kaia-Alenia/alenia-nerve/clients/go)

✓ **Installation:**
```bash
go get github.com/Kaia-Alenia/alenia-nerve/clients/go
```

✓ **Simple Integration Example:**
```go
package main

import (
    "fmt"
    nerve "github.com/Kaia-Alenia/alenia-nerve/clients/go"
)

func main() {
    client := nerve.NewClient()
    client.Connect("my_go_tool")

    client.Send("renderer", map[string]interface{}{"status": "ready"})

    client.Listen(func(data map[string]interface{}) {
        fmt.Println("Received:", data)
    })
}
```

---

For a fully functional, production-ready implementation of Nerve working alongside Zenith in tools like Framegrid and Giftly, visit the [zenith-nerve-tools](https://github.com/Kaia-Alenia/zenith-nerve-tools) repository.

---

### Secure Data Packing (.nrv)

Nerve includes a high-performance streaming cryptographic packer designed for sharing offline resources. It uses AES-256-GCM and Argon2id to secure folders or files in `.nrv` containers.

For maximum security, avoid passing the password as an argument; use the `NERVE_NRV_PASSWORD` environment variable:
```bash
NERVE_NRV_PASSWORD="my_secure_password" nerve pack ./my_game my_game.nrv
NERVE_NRV_PASSWORD="my_secure_password" nerve unpack my_game.nrv ./output
```
If the environment variable is not set, the CLI will prompt for the password interactively. If you don't have a password, the CLI will offer to generate a highly secure passphrase for you (using Diceware with the EFF wordlist). You can also generate standalone secure passwords using the `nerve genpass` command.

##  Command Line Interface (CLI) & The Main Hub

Once installed, the `nerve` command provides a suite of tools for managing your local IPC network and securing files.

### Available Commands

* **`nerve start`**: Spins up the **NexusHub** — the central message router for your local network. It runs immediately with zero configuration and listens for incoming connections. Use `nerve start --verbose` to trace every packet routed in real-time.
* **`nerve monitor`**: Launches a terminal-based live dashboard showing all connected clients, uptime, message counts, and traffic stats at a glance.
* **`nerve dashboard`**: Starts a lightweight local web interface on `http://localhost:8080` that renders a live **Network Topology View** of all connected nodes.
* **`nerve bridge`**: Starts an HTTP/WebSocket proxy on port 50506. This allows web browsers and WebSocket clients to connect and talk directly to the Nerve IPC network. (Requires `websockets` package).
* **`nerve host`**: Spawns a persistent peer-to-peer host for Direct Device Communication. This allows other devices to discover this machine on the local network.
* **`nerve scan [IP]`**: Scans the local network for other Nerve devices running `nerve host`. Uses UDP broadcast, or unicast if a specific IP is provided (useful for bypassing AP Isolation on strict routers).
* **`nerve pack <src> <out.nrv>`**: Securely encrypts and packs a file or directory into a `.nrv` container using AES-256-GCM.
* **`nerve unpack <nrv> <out>`**: Decrypts and extracts a `.nrv` container to the specified output directory.
* **`nerve open <file.nrv>`**: Interactively opens a `.nrv` container, handling password prompts via TTY or native GUI dialogs (Zenity/Tkinter/macOS osascript) with up to 3 retry attempts.
* **`nerve associate`**: Registers the `.nrv` file extension with your operating system (Windows/macOS/Linux) and associates it with the `nerve open` command and a custom icon, enabling double-click extraction.
* **`nerve unassociate`**: Removes the `.nrv` file extension association from your operating system.
* **`nerve genpass`**: Generates a highly secure password or passphrase. Use `--mode random` (default length 20) or `--mode passphrase` (default 5 words).

### Starting the Hub

```bash
nerve start
```

<div align="center">
  <img src="assets/images/nerve-start.png" alt="nerve start — Hub initializing and active via Unix Socket" width="90%">
  <br><sub>The Hub initializes instantly and listens for client connections via Unix Domain Socket.</sub>
</div>

<br>

### Help Menu:
```bash
nerve --help
```

---

##  Ecosystem Tools: CLI Monitor & Web Dashboard

Nerve ships with two powerful built-in tools to observe your local network in real-time — no external services required.

### Global CLI Monitor (`nerve-monitor`)

A terminal-based live dashboard that shows all connected clients, uptime, message counts, and traffic stats at a glance.

<p align="center">
  <img src="assets/images/cli-monitor-clients.png" alt="CLI Monitor showing 6 clients: py_client, js_client, go_client, rs_client, nerve-monitor, nerve-dashboard" width="48%">
  &nbsp;
  <img src="assets/images/cli-monitor-giftly.png" alt="CLI Monitor showing Giftly and Framegrid connected alongside nerve-monitor and nerve-dashboard" width="48%">
</p>

*Left: All four official language clients connected simultaneously. Right: Real-world tools [Giftly and Framegrid](https://github.com/Kaia-Alenia/zenith-nerve-tools) connected invisibly — fully visible in the Hub.*

---

### Hub Logs (`nerve start`)

The Hub terminal logs every registration, message route, and disconnection event with colored output. This is what the server sees when clients connect.

<p align="center">
  <img src="assets/images/hub-logs-clients.png" alt="Hub logs showing the NERVE ASCII banner and all 6 clients registering" width="48%">
  &nbsp;
  <img src="assets/images/hub-logs-giftly.png" alt="Hub logs showing Giftly and Framegrid registering alongside nerve-monitor and nerve-dashboard" width="48%">
</p>

*Left: Hub boot sequence with all language clients registering (py, js, go, rs). Right: Giftly and Framegrid registering as native Nerve nodes.*

---

### Web Dashboard (`nerve-dashboard`)

A lightweight local web interface that renders a live **Network Topology View** — a graph of every connected node — plus uptime, total traffic, and message counters.

<p align="center">
  <img src="assets/images/dashboard-topology.png" alt="Nexus Topology View — graph showing Nerve Hub at center with go_client, rs_client, js_client, py_client, nerve-monitor and nerve-dashboard as nodes" width="48%">
  &nbsp;
  <img src="assets/images/dashboard-full.png" alt="Full Web Dashboard — sidebar with connected nodes list (nerve-monitor, nerve-dashboard, py_client, js_client, go_client, rs_client), uptime 00:04:32, total traffic 18.25 KB, messages processed 1003" width="48%">
</p>

*Left: Pure topology graph — the Nerve Hub at center, all nodes orbiting it. Right: Full dashboard with live metrics sidebar showing uptime, traffic (18.25 KB), and 1003 messages processed.*

*(Check out our [zenith-nerve-tools monorepo](https://github.com/Kaia-Alenia/zenith-nerve-tools) for practical real-world tools built on top of Nerve.)*

---



##  Configuration File (`nerve.config`)

Place a `nerve.config` file in your project root or user home directory to customize socket paths, TCP ports, and authentication without changing code.

**JSON format:**
```json
{
  "socket_path": "/tmp/nerve.sock",
  "port": 50505,
  "host": "127.0.0.1",
  "auth_token": "my_secure_token",
  "lan_port": 50507
}
```

**Simple key-value format:**
```text
socket_path=/tmp/nerve.sock
port=50505
auth_token=my_secure_token
lan_port=50507
```

---

##  LAN Discovery & Firewall (Windows / Linux)

When using `nerve host` and `nerve scan` for Direct Device Communication across multiple computers, ensure your firewall permits traffic on the following ports:

| Port | Protocol | Purpose |
|------|----------|---------|
| `50511` | UDP | Discovery (`nerve scan` broadcasts) |
| `50507` | TCP | Control Plane (authentication & handshake; configurable with `lan_port`) |
| `50510` | TCP | Data Plane (file transfer & large payloads) |

**Windows Firewall Fix:**
If `nerve scan` cannot find a Windows machine running `nerve host`, it is usually because Windows Firewall blocks inbound UDP 50511 by default. Open an **Administrator PowerShell** and run:
```powershell
New-NetFirewallRule -DisplayName "Nerve LAN Discovery" -Direction Inbound -Protocol UDP -LocalPort 50511 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Control" -Direction Inbound -Protocol TCP -LocalPort 50507 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Data" -Direction Inbound -Protocol TCP -LocalPort 50510 -Action Allow -Profile Any
```

**AP Isolation (Wi-Fi Routers):**
If your router isolates Wi-Fi clients (blocking broadcast packets), `nerve scan` will fail. You can bypass this by scanning the exact IP directly (unicast):
```bash
nerve scan 192.168.1.50
```

### Finding local IP addresses

Use the private IPv4 address of the adapter connected to the same LAN as the other device. Do not use `127.0.0.1`, which only represents the current device.

```powershell
# Windows
ipconfig
```

```bash
# Linux and macOS
ip addr

# Android / Termux
ip addr
# Fallback if ip is unavailable:
ifconfig
```

Valid examples include `192.168.1.50`, `10.0.0.25`, and `172.20.10.4`. To verify the local interface and remote host:

```bash
nerve diagnose 192.168.1.50
```

If the diagnostic reports a local interface but TCP fails, check the firewall, confirm both devices are on the same subnet, and disable client isolation on the router. If no IPv4 interface is detected, the computer has been fully disconnected from the LAN: turning off Internet access is compatible with Nerve, but disabling Wi-Fi/Ethernet is not.

### Configurable ports

The default `nerve host` control port is `50507`. If you set another value with `lan_port` or `--port`, open that TCP port and include it when connecting, for example `nerve connect 192.168.1.50:4432`. The data port remains `50510` and discovery uses UDP `50511`.

---

##  Contributors

We want to express our deepest gratitude to everyone who contributes to Nerve! Your work, reviews, and bug reports make this project possible.

* **Alenia Studios** - Lead Maintainer and Publisher

Want to appear here? Check our [CONTRIBUTING.md](CONTRIBUTING.md) guide and submit a Pull Request! See [CONTRIBUTORS.md](CONTRIBUTORS.md) for the full list.

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

##  License

[![License](https://img.shields.io/badge/License-GPLv3-8a2be2.svg)](LICENSE)

This software is distributed under the **GNU General Public License v3 (GPL v3)**. See [LICENSE](LICENSE) for more details.

---
*Crafted with passion by Alenia Studios to power sovereign software engineers and creators.*
