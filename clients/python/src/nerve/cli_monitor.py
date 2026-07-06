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
import os
import sys
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any

from nerve.core import NexusClient
from nerve import __version__


LATEST_DATA: Dict[str, Any] = {"metrics": {}, "clients": []}
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(LATEST_DATA).encode("utf-8"))
        elif self.path == "/" or self.path == "/index.html":
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
        else:
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
        except Exception:
            pass
        time.sleep(1.0)


def run_dashboard(port: int = 8080):
    print(f"\033[95m[NERVE CLI]\033[0m Starting Dashboard on http://localhost:{port}")

    client = NexusClient()
    try:
        client.connect("nerve-dashboard")
    except Exception as e:
        print(f"\033[91m[NERVE CLI]\033[0m Could not connect to Hub: {e}")
        print("Is the Nerve Hub running? Run 'nerve start' in another terminal.")
        sys.exit(1)

    fetcher_thread = threading.Thread(
        target=data_fetcher_loop, args=(client,), daemon=True
    )
    fetcher_thread.start()

    try:
        server = HTTPServer(("0.0.0.0", port), DashboardHandler)
        print("\033[92m[NERVE CLI]\033[0m Dashboard running. Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[95m[NERVE CLI]\033[0m Stopping dashboard...")
    except Exception as e:
        print(f"\033[91m[NERVE CLI]\033[0m Server error: {e}")
    finally:
        client.disconnect()


def format_bytes(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} TB"


def run_monitor():
    client = NexusClient()
    try:
        client.connect("nerve-monitor")
    except Exception as e:
        print(f"\033[91m[NERVE CLI]\033[0m Could not connect to Hub: {e}")
        print("Is the Nerve Hub running? Run 'nerve start' in another terminal.")
        sys.exit(1)

    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    try:
        while True:
            metrics = client.get_metrics()
            clients = client.list_clients()

            uptime = metrics.get("uptime", 0.0)
            hours, rem = divmod(uptime, 3600)
            mins, secs = divmod(rem, 60)
            uptime_str = f"{int(hours):02d}:{int(mins):02d}:{int(secs):02d}"

            sys.stdout.write("\033[2J\033[H")

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

            sys.stdout.write("\n".join(output) + "\n")
            sys.stdout.flush()

            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        client.disconnect()
