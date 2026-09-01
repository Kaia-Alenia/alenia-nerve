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

import time
from typing import Any

from nerve.lan.api import NerveLAN
from nerve.lan.events import HOST_STARTED, HOST_STARTING, HOST_STOPPED, HOST_STOPPING


def test_lan_event_dispatcher() -> None:
    lan = NerveLAN()
    
    events_fired = []
    
    def on_starting(*args: Any, **kwargs: Any) -> None:
        events_fired.append("starting")
        
    def on_started(*args: Any, **kwargs: Any) -> None:
        events_fired.append("started")
        
    def on_stopping(*args: Any, **kwargs: Any) -> None:
        events_fired.append("stopping")
        
    def on_stopped(*args: Any, **kwargs: Any) -> None:
        events_fired.append("stopped")

    lan.on(HOST_STARTING, on_starting)
    lan.on(HOST_STARTED, on_started)
    lan.on(HOST_STOPPING, on_stopping)
    lan.on(HOST_STOPPED, on_stopped)
    
    # We monkeypatch the underlying _host to prevent actual socket binding in simple unit tests
    # Wait, NerveHost by default attempts to bind. We will just test the events fire properly.
    
    # Actually, we can just test the dispatcher manually
    lan.events.dispatch(HOST_STARTING)
    assert "starting" in events_fired
    
    lan.events.dispatch(HOST_STARTED)
    assert "started" in events_fired
    
    lan.events.dispatch(HOST_STOPPING)
    assert "stopping" in events_fired
    
    lan.events.dispatch(HOST_STOPPED)
    assert "stopped" in events_fired

    lan.off(HOST_STARTING, on_starting)
    lan.events.dispatch(HOST_STARTING)
    # The count of "starting" shouldn't increase
    assert events_fired.count("starting") == 1

def test_lan_api_stubs() -> None:
    lan = NerveLAN()
    
    # Test scan stub
    scan_res = lan.scan()
    assert isinstance(scan_res, list)
    assert len(scan_res) == 0
    
    # Test send stub
    send_res = lan.send("some/path", to="192.168.1.10")
    assert not send_res.success
    assert "Not implemented" in str(send_res.error)
    
    # Test get_transfers stub
    transfers = lan.get_transfers()
    assert isinstance(transfers, list)
    assert len(transfers) == 0
