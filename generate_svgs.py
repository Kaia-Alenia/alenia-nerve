import os
from rich.console import Console

os.makedirs("assets", exist_ok=True)

def create_svg(filename, lines, title):
    console = Console(record=True, width=80)
    for line in lines:
        console.print(line)
    console.save_svg(os.path.join("assets", filename), title=title)

# Hub
create_svg("nerve_hub.svg", [
    "[green]➜[/green] [bold cyan]nerve[/bold cyan] run hub --port 5000",
    "[bold yellow]NexusHub[/bold yellow] Initializing Nerve Nexus on port 5000...",
    "[dim]Listening for IPC connections on uds:///tmp/nerve.sock[/dim]",
    "[dim]Listening for TCP connections on 127.0.0.1:5000[/dim]",
    "[bold green]✔ NexusHub Ready.[/bold green]",
    "Client [cyan]rust-client-1[/cyan] connected.",
    "Client [cyan]js-client-2[/cyan] connected.",
    "Client [cyan]python-monitor[/cyan] connected."
], "Nerve Hub")

# Python
create_svg("python_client.svg", [
    "[green]➜[/green] [bold cyan]python[/bold cyan] ping_pong.py",
    "[bold yellow]NerveClient[/bold yellow] Connecting to Hub at /tmp/nerve.sock...",
    "[bold green]✔ Connected as python_ping_pong_1[/bold green]",
    "Sent [magenta]ping[/magenta] event...",
    "Received [magenta]pong[/magenta] from [cyan]rust-client-1[/cyan] (latency: 0.12ms)"
], "Python Client")

# JS
create_svg("js_client.svg", [
    "[green]➜[/green] [bold cyan]node[/bold cyan] index.js",
    "[bold yellow]NerveClient[/bold yellow] Connecting to IPC socket...",
    "[bold green]✔ Connected![/bold green] (Client ID: js_client_2)",
    "Subscribed to topic: 'system.metrics'",
    "Received event: { cpu_usage: 4.2, mem: '1.2GB' }"
], "JavaScript Client")

# Rust
create_svg("rust_client.svg", [
    "[green]➜[/green] [bold cyan]cargo[/bold cyan] run --example basic",
    "[bold yellow]NexusClient[/bold yellow] Attempting UDS connection to /tmp/nerve.sock",
    "[bold green]✔ Connection established[/bold green]",
    "Broadcasting 1000 messages...",
    "[bold green]✔ Broadcast complete (0.85ms)[/bold green]"
], "Rust Client")

# Go
create_svg("go_client.svg", [
    "[green]➜[/green] [bold cyan]go[/bold cyan] run main.go",
    "[bold yellow]NerveClient[/bold yellow] Dialing unix:///tmp/nerve.sock",
    "[bold green]✔ Connected.[/bold green] Starting listener goroutine...",
    "Listening for 'status.update'...",
    "Received status update from 'hub': OK"
], "Go Client")

# C++
create_svg("cpp_client.svg", [
    "[green]➜[/green] [bold cyan]./build/nerve_demo[/bold cyan]",
    "[bold yellow]NexusClient::Connect()[/bold yellow] Using UDS...",
    "[bold green]✔ Connected to Nerve IPC.[/bold green]",
    "Sending telemetry data...",
    "Telemetry sent. Bytes: 1024"
], "C++ Client")

# C#
create_svg("csharp_client.svg", [
    "[green]➜[/green] [bold cyan]dotnet[/bold cyan] run",
    "[bold yellow]NexusClient[/bold yellow] Initializing TCP connection to 127.0.0.1:5000",
    "[bold green]✔ Connected![/bold green]",
    "Listening for 'game.state' updates...",
    "game.state update received! (Entities: 42)"
], "C# Client")

print("Created SVGs.")
