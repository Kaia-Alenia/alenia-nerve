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
import socket
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

from nerve.lan.host import NerveHost


def test_discovery_loop() -> None:
    host = NerveHost(lan_port=50507, verbose=False)
    host._running = True

    mock_udp = MagicMock()
    host._udp_server = mock_udp

    # We will simulate a recvfrom that returns a valid discovery, then an invalid one, then raises OSError to exit the loop
    mock_udp.recvfrom.side_effect = [
        (b"NERVE_DISCOVERY\nversion=1\nnonce=123", ("192.168.1.50", 12345)),
        (b"RANDOM_JUNK", ("192.168.1.60", 54321)),
        OSError("Socket closed"),
    ]

    # Run the loop directly (it will exit on OSError)
    host._discovery_loop()

    # Assert sendto was called exactly once for the valid discovery
    assert mock_udp.sendto.call_count == 1
    call_args = mock_udp.sendto.call_args[0]
    data_sent = call_args[0]
    addr_sent = call_args[1]

    assert addr_sent == ("192.168.1.50", 12345)

    parsed = json.loads(data_sent.decode("utf-8"))
    assert parsed["type"] == "nerve_discovery_response"
    assert parsed["control_port"] == 50507
    assert parsed["transfer_port"] == 50510
