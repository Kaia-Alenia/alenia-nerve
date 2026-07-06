from rich.console import Console
from rich.text import Text
import time

console = Console(record=True, width=80)
console.print("[green]➜[/green] [bold cyan]nerve[/bold cyan] run hub --port 5000")
console.print("[bold yellow]NexusHub[/bold yellow] Initializing Nerve Nexus on port 5000...")
time.sleep(0.1)
console.print("[dim]Listening for IPC connections on uds:///tmp/nerve.sock[/dim]")
console.print("[dim]Listening for TCP connections on 127.0.0.1:5000[/dim]")
console.print("[bold green]✔ NexusHub Ready.[/bold green]")
console.print("Client [cyan]rust-client-1[/cyan] connected.")
console.print("Client [cyan]js-client-2[/cyan] connected.")

console.save_svg("hub_terminal.svg", title="Nerve Hub")
