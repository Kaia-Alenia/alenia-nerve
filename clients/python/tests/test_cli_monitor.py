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

from unittest.mock import MagicMock, patch

import pytest

from nerve.cli_monitor import LATEST_DATA, data_fetcher_loop, format_bytes


@pytest.mark.parametrize(
    "b, expected",
    [
        (0, "0 B"),
        (500, "500 B"),
        (-500, "-500 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (int(1024 * 1024 * 2.5), "2.5 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
        (int(1024 * 1024 * 1024 * 3.7), "3.7 GB"),
        (1024 * 1024 * 1024 * 1024, "1.0 TB"),
        (1024 * 1024 * 1024 * 1024 * 5, "5.0 TB"),
        (1024 * 1024 * 1024 * 1024 * 1024, "1024.0 TB"),
    ],
)
def test_format_bytes(b, expected):
    assert format_bytes(b) == expected


def test_data_fetcher_loop_success():
    # Note: the issue description shows current_dashboard_data,
    # but the actual implementation uses LATEST_DATA and get_metrics().
    # We prioritize writing tests that pass against the real, existing codebase.
    client_mock = MagicMock()

    mock_metrics = {"uptime": 100.0}
    mock_clients = ["client1", "client2"]

    client_mock.get_metrics.return_value = mock_metrics
    client_mock.list_clients.return_value = mock_clients

    with patch("nerve.cli_monitor.time.sleep", side_effect=StopIteration):
        try:
            data_fetcher_loop(client_mock)
        except StopIteration:
            pass

    assert LATEST_DATA["metrics"] == mock_metrics
    assert LATEST_DATA["clients"] == mock_clients


def test_data_fetcher_loop_exception():
    client_mock = MagicMock()

    client_mock.get_metrics.side_effect = Exception("Failed to get metrics")

    with patch("nerve.cli_monitor.time.sleep", side_effect=StopIteration) as sleep_mock:
        try:
            data_fetcher_loop(client_mock)
        except StopIteration:
            pass

    sleep_mock.assert_called_once_with(1.0)


def test_dashboard_handler_serves_lan_and_nrv_endpoints(tmp_path, monkeypatch):
    """DashboardHandler exposes unified /api/lan/* and /api/nrv/* endpoints."""
    import json
    import socket
    import threading
    import urllib.request
    from http.server import HTTPServer

    from nerve.cli_monitor import DashboardHandler
    from nerve.lan.api import NerveLAN

    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr("nerve.lan.util.default_audit_log_path", lambda: audit_path)

    lan = NerveLAN(verbose=False)
    lan._audit_log_path = audit_path

    class TestHandler(DashboardHandler):
        lan_api = lan

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = HTTPServer(("127.0.0.1", port), TestHandler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f"http://127.0.0.1:{port}"

        with opener.open(f"{base}/api/lan/status", timeout=3) as resp:
            status_body = json.loads(resp.read().decode("utf-8"))
        assert status_body["running"] is False
        assert status_body["status"] == "stopped"

        gen_req = urllib.request.Request(
            f"{base}/api/nrv/genpass",
            data=json.dumps({"mode": "passphrase", "words": 4}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(gen_req, timeout=3) as resp:
            gen_body = json.loads(resp.read().decode("utf-8"))
        assert len(gen_body["password"].split("-")) == 4
        assert gen_body["entropy"] > 0

        with opener.open(f"{base}/", timeout=3) as resp:
            html = resp.read().decode("utf-8")
        assert "view-lan" in html
        assert "view-vault" in html
        assert "view-audit" in html
    finally:
        server.shutdown()
        server.server_close()
        th.join(timeout=2)
