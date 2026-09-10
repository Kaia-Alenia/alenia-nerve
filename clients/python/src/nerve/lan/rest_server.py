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
"""
nerve LAN REST API — HTTP wrapper over the NerveLAN engine.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from nerve.lan.api import NerveLAN

logger = logging.getLogger(__name__)


class LANRestHandler(BaseHTTPRequestHandler):
    """
    HTTP Handler for LAN API requests.
    """

    lan_api: NerveLAN = None  # type: ignore

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/lan/status":
            self._send_json({"status": self.lan_api.status.value})
        elif path == "/api/lan/peers":
            peers = [p.__dict__ for p in self.lan_api.get_peers()]
            self._send_json({"peers": peers})
        elif path == "/api/lan/transfers":
            transfers = [t.__dict__ for t in self.lan_api.get_transfers()]
            self._send_json({"transfers": transfers})
        elif path == "/api/lan/network_info":
            self._send_json(self.lan_api.network_info())
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = (
            self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        )

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        try:
            if path == "/api/lan/start":
                self.lan_api.start()
                self._send_json({"success": True})
            elif path == "/api/lan/stop":
                self.lan_api.stop()
                self._send_json({"success": True})
            elif path == "/api/lan/scan":
                target_ip = data.get("target_ip")
                timeout = data.get("timeout", 2.0)
                peers = self.lan_api.scan(timeout=timeout, target_ip=target_ip)
                self._send_json({"peers": [p.__dict__ for p in peers]})
            elif path == "/api/lan/connect":
                ip = data.get("ip")
                if not ip:
                    self.send_error(400, "Missing 'ip'")
                    return
                peer = self.lan_api.connect(ip)
                self._send_json({"peer": peer.__dict__})
            elif path == "/api/lan/send":
                to = data.get("to")
                file_path = data.get("file_path")
                if not to or not file_path:
                    self.send_error(400, "Missing 'to' or 'file_path'")
                    return
                t_status = self.lan_api.send(to, file_path)
                self._send_json({"transfer": t_status.__dict__})
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            logger.error(f"REST API Error: {e}", exc_info=True)
            self.send_error(500, str(e))

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        # Disable default logging to stderr, rely on python logger if needed
        pass


class NerveLANRestServer:
    def __init__(self, lan_api: NerveLAN, host: str = "127.0.0.1", port: int = 50508):
        self.lan_api = lan_api
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        class Handler(LANRestHandler):
            lan_api = self.lan_api

        self.server = HTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Nerve LAN REST API started on http://{self.host}:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Nerve LAN REST API stopped.")
