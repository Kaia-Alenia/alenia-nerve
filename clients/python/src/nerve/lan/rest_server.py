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
from typing import Any
from urllib.parse import parse_qs, urlparse

from nerve.lan.api import NerveLAN

logger = logging.getLogger(__name__)


def handle_lan_get(
    lan_api: NerveLAN, path: str, query: str = ""
) -> tuple[int, dict[str, Any]] | None:
    """Dispatch shared LAN/NRV GET routes; returns (status, payload) or None."""
    if path == "/api/lan/status":
        st = lan_api.status
        return 200, {
            "status": "running" if st.running else "stopped",
            "running": st.running,
            "port": st.port,
            "error": st.error,
        }
    if path == "/api/lan/peers":
        peers = [p.__dict__ for p in lan_api.get_peers()]
        return 200, {"peers": peers}
    if path == "/api/lan/transfers":
        transfers = [t.__dict__ for t in lan_api.get_transfers()]
        return 200, {"transfers": transfers}
    if path == "/api/lan/audit":
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        return 200, {"audit": lan_api.get_audit_log(limit=limit)}
    if path == "/api/lan/network_info":
        return 200, lan_api.network_info()
    return None


def handle_lan_post(
    lan_api: NerveLAN, path: str, data: dict[str, Any]
) -> tuple[int, dict[str, Any]] | None:
    """Dispatch shared LAN/NRV POST routes; returns (status, payload) or None."""
    if path == "/api/lan/start":
        st = lan_api.start()
        return 200, {"success": st.running, "status": st.__dict__}
    if path == "/api/lan/stop":
        st = lan_api.stop()
        return 200, {"success": not st.running, "status": st.__dict__}
    if path == "/api/lan/scan":
        target_ip = data.get("target_ip")
        timeout = float(data.get("timeout", 2.0))
        subnet_fallback = bool(data.get("subnet_fallback", False))
        peers = lan_api.scan(
            timeout=timeout, target_ip=target_ip, subnet_fallback=subnet_fallback
        )
        return 200, {"peers": [p.__dict__ for p in peers]}
    if path == "/api/lan/connect":
        ip = data.get("ip")
        if not ip:
            return 400, {"error": "Missing 'ip'"}
        res = lan_api.connect(ip, name=data.get("name"), token=data.get("token"))
        return 200, {"peer": res.__dict__, "success": res.success}
    if path == "/api/lan/send":
        to = data.get("to")
        file_path = data.get("file_path")
        if not to or not file_path:
            return 400, {"error": "Missing 'to' or 'file_path'"}
        t_status = lan_api.send(file_path, to)
        return 200, {"transfer": t_status.__dict__, "success": t_status.success}
    if path == "/api/nrv/pack":
        source_path = data.get("source_path")
        output_path = data.get("output_path")
        password = data.get("password")
        if not source_path or not output_path or not password:
            return 400, {"error": "Missing 'source_path', 'output_path', or 'password'"}
        return 200, lan_api.pack_container(source_path, output_path, password)
    if path == "/api/nrv/unpack":
        nrv_path = data.get("nrv_path")
        output_dir = data.get("output_dir")
        password = data.get("password")
        if not nrv_path or not output_dir or not password:
            return 400, {"error": "Missing 'nrv_path', 'output_dir', or 'password'"}
        return 200, lan_api.unpack_container(nrv_path, output_dir, password)
    if path == "/api/nrv/genpass":
        mode = data.get("mode", "passphrase")
        if mode == "random":
            from nerve.genpass import generate_random_password

            length = int(data.get("length", 20))
            pwd, ent = generate_random_password(length=length)
        else:
            from nerve.genpass import generate_passphrase

            words = int(data.get("words", 5))
            pwd, ent = generate_passphrase(words=words)
        return 200, {"password": pwd, "entropy": ent, "mode": mode}
    return None


class LANRestHandler(BaseHTTPRequestHandler):
    """HTTP Handler for LAN API requests."""

    lan_api: NerveLAN = None  # type: ignore

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        result = handle_lan_get(self.lan_api, parsed.path, parsed.query)
        if result is None:
            self.send_error(404, "Not Found")
            return
        status_code, payload = result
        self._send_json(payload, status_code=status_code)

    def do_POST(self):
        parsed = urlparse(self.path)
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
            result = handle_lan_post(self.lan_api, parsed.path, data)
            if result is None:
                self.send_error(404, "Not Found")
                return
            status_code, payload = result
            self._send_json(payload, status_code=status_code)
        except Exception as e:
            logger.error("REST API Error: %s", e, exc_info=True)
            self.send_error(500, str(e))

    def _send_json(self, data: dict, status_code: int = 200):
        self.send_response(status_code)
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
