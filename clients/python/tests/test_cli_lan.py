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

import sys
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from nerve.cli import main


def test_cli_scan() -> None:
    with (
        patch("sys.argv", ["nerve", "scan"]),
        patch("nerve.lan.api.NerveLAN.scan") as mock_scan,
        patch("sys.exit") as mock_exit,
    ):
        mock_scan.return_value = []
        main()
        mock_scan.assert_called_once()
        mock_exit.assert_called_once_with(0)


def test_cli_diagnose() -> None:
    with (
        patch("sys.argv", ["nerve", "diagnose", "127.0.0.1"]),
        patch("nerve.lan.api.NerveLAN.diagnose") as mock_diag,
        patch("sys.exit") as mock_exit,
    ):
        mock_diag.return_value = {
            "local": {"interface": "[CONFIRMED] OK", "address": "[CONFIRMED] OK"},
            "target": {"format": "[CONFIRMED] OK"},
            "direct": {"tcp": "[CONFIRMED] Timeout"},
            "service": {"auth": "[UNKNOWN] No"},
            "causes": ["[POSSIBLE] Firewall"],
        }
        main()
        mock_diag.assert_called_once_with(target_ip="127.0.0.1")
        mock_exit.assert_called_once_with(0)


def test_cli_send() -> None:
    with (
        patch("sys.argv", ["nerve", "send", "some/path", "--to", "10.0.0.1"]),
        patch("nerve.lan.api.NerveLAN.send") as mock_send,
        patch("sys.exit") as mock_exit,
    ):
        mock_res = MagicMock()
        mock_res.success = True
        mock_send.return_value = mock_res

        main()
        mock_send.assert_called_once()
        mock_exit.assert_called_once_with(0)


def test_cli_receive() -> None:
    with (
        patch("sys.argv", ["nerve", "receive", "--dir", "/tmp"]),
        patch("nerve.lan.api.NerveLAN.receive") as mock_recv,
        patch("sys.exit") as mock_exit,
    ):
        main()
        mock_recv.assert_called_once_with(receive_dir="/tmp")
        mock_exit.assert_called_once_with(0)
