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
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from nerve import __version__
from nerve.core import NexusClient
from nerve.lan.api import NerveLAN
from nerve.lan.rest_server import handle_lan_get, handle_lan_post

LATEST_DATA: dict[str, Any] = {"metrics": {}, "clients": [], "hub_connected": False}
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")


class DashboardHandler(BaseHTTPRequestHandler):
    lan_api: NerveLAN | None = None

    def _get_lan_api(self) -> NerveLAN:
        if self.lan_api is None:
            type(self).lan_api = NerveLAN()
        return self.lan_api

    def _send_json(self, data: dict[str, Any], status_code: int = 200) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/metrics":
            self._send_json(LATEST_DATA)
            return
        if path == "/" or path == "/index.html":
            index_path = os.path.join(DASHBOARD_DIR, "index.html")
            if not os.path.exists(index_path):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Dashboard index.html not found.")
                return

            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
            return

        lan_res = handle_lan_get(self._get_lan_api(), path, parsed.query)
        if lan_res is not None:
            status_code, payload = lan_res
            self._send_json(payload, status_code=status_code)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        )
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, status_code=400)
            return

        try:
            lan_res = handle_lan_post(self._get_lan_api(), parsed.path, data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status_code=500)
            return

        if lan_res is not None:
            status_code, payload = lan_res
            self._send_json(payload, status_code=status_code)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def data_fetcher_loop(client: NexusClient):
    while True:
        try:
            metrics = client.get_metrics()
            clients = client.list_clients()
            LATEST_DATA["metrics"] = metrics
            LATEST_DATA["clients"] = clients
            LATEST_DATA["hub_connected"] = True
        except Exception:
            LATEST_DATA["hub_connected"] = False
        time.sleep(1.0)


def _probe_hub(timeout: float = 2.0) -> bool:
    """Return True if a Nerve Hub appears reachable; False otherwise."""
    import platform
    import socket as _socket

    from nerve.core import load_external_config

    config = load_external_config()
    is_windows = platform.system() == "Windows"
    if is_windows:
        host = str(config.get("host", "127.0.0.1"))
        port = int(config.get("port", 50505))
        address: tuple | str = (host, port)
        family = _socket.AF_INET
    else:
        address = str(config.get("socket_path", "/tmp/nerve.sock"))
        family = _socket.AF_UNIX

    sock = _socket.socket(family, _socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(address)
        sock.close()
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def run_dashboard(port: int = 8080, require_hub: bool = True):
    print(f"\033[95m[NERVE CLI]\033[0m Starting Dashboard on http://localhost:{port}")

    hub_available = _probe_hub()
    if not hub_available and require_hub:
        print(
            "\033[91m[NERVE CLI]\033[0m Could not connect to Hub: hub is not running or unreachable."
        )
        print("Is the Nerve Hub running? Run 'nerve start' in another terminal.")
        sys.exit(1)

    client: NexusClient | None = None
    if hub_available:
        client = NexusClient()
        client.connect("nerve-dashboard")
        LATEST_DATA["hub_connected"] = True
        fetcher_thread = threading.Thread(
            target=data_fetcher_loop, args=(client,), daemon=True
        )
        fetcher_thread.start()
    else:
        LATEST_DATA["hub_connected"] = False
        print(
            "\033[93m[NERVE CLI]\033[0m IPC Hub offline — running Web UI in standalone LAN/NRV mode."
        )

    lan_instance = NerveLAN()

    class UnifiedDashboardHandler(DashboardHandler):
        lan_api = lan_instance

    try:
        server = HTTPServer(("0.0.0.0", port), UnifiedDashboardHandler)
        print("\033[92m[NERVE CLI]\033[0m Dashboard running. Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[95m[NERVE CLI]\033[0m Stopping dashboard...")
    except Exception as e:
        print(f"\033[91m[NERVE CLI]\033[0m Server error: {e}")
    finally:
        if client is not None:
            client.disconnect()
        if lan_instance.status.running:
            lan_instance.stop()


def format_bytes(b: int) -> str:
    if abs(b) < 1024:
        return f"{int(b)} B"

    b_float = float(b)
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(b_float) < 1024.0:
            if unit == "B":
                return f"{int(b_float)} B"
            return f"{b_float:.1f} {unit}"
        b_float /= 1024.0
    return f"{b_float:.1f} TB"


def run_monitor():
    if not _probe_hub():
        print(
            "\033[91m[NERVE CLI]\033[0m Could not connect to Hub: hub is not running or unreachable."
        )
        print("Is the Nerve Hub running? Run 'nerve start' in another terminal.")
        sys.exit(1)

    client = NexusClient()
    client.connect("nerve-monitor")

    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    lines_printed = 0
    try:
        while True:
            metrics = client.get_metrics()
            clients = client.list_clients()

            uptime = metrics.get("uptime", 0.0)
            hours, rem = divmod(uptime, 3600)
            mins, secs = divmod(rem, 60)
            uptime_str = f"{int(hours):02d}:{int(mins):02d}:{int(secs):02d}"

            if lines_printed > 0:
                sys.stdout.write(f"\033[{lines_printed}A\033[0J")

            output = [
                f"\033[95m=== NERVE HUB MONITOR ===\033[0m  (v{__version__})",
                f"Uptime: \033[92m{uptime_str}\033[0m",
                "-" * 40,
                f"Clients Connected : \033[93m{metrics.get('clients', 0)}\033[0m",
                f"Messages Sent     : \033[96m{metrics.get('total_messages_sent', 0)}\033[0m",
                f"Messages Received : \033[96m{metrics.get('total_messages_received', 0)}\033[0m",
                f"Bytes Sent        : \033[96m{format_bytes(metrics.get('total_bytes_sent', 0))}\033[0m",
                f"Bytes Received    : \033[96m{format_bytes(metrics.get('total_bytes_received', 0))}\033[0m",
                "-" * 40,
                "\033[95mActive Client Nodes:\033[0m",
            ]

            for cid in clients:
                output.append(f"  \033[92m•\033[0m {cid}")

            if not clients:
                output.append("  \033[90m(no clients connected)\033[0m")

            output.append("-" * 40)
            output.append("\033[90mPress Ctrl+C to exit\033[0m")

            text = "\n".join(output) + "\n"
            sys.stdout.write(text)
            sys.stdout.flush()
            lines_printed = len(output)

            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        client.disconnect()
