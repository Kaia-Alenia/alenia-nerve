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

import threading
from collections.abc import Callable
from typing import Any, Optional

from nerve.lan.connect import (
    LanAuthenticationError,
    LanConnectionError,
    LanProtocolError,
    connect_and_register,
)
from nerve.lan.events import (
    HOST_STARTED,
    HOST_STARTING,
    HOST_STOPPED,
    HOST_STOPPING,
    EventDispatcher,
)
from nerve.lan.host import NerveHost
from nerve.lan.models import (
    ConnectionResult,
    DiscoveryResult,
    HostStatus,
    TransferResult,
)
from nerve.lan.peer_registry import PeerRegistry


class NerveLAN:
    """
    Headless public API surface for Nerve LAN V1.
    All automation and UI layers should consume this API.
    """

    def __init__(
        self,
        receive_dir: Optional[str] = None,
        port: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        self.receive_dir = receive_dir
        self.port = port
        self.verbose = verbose
        self.events = EventDispatcher()
        self._host: Optional[NerveHost] = None
        self._host_thread: Optional[threading.Thread] = None

    def on(self, event_name: str, callback: Callable[..., None]) -> None:
        """Subscribe to a LAN event."""
        self.events.on(event_name, callback)

    def off(self, event_name: str, callback: Callable[..., None]) -> None:
        """Unsubscribe from a LAN event."""
        self.events.off(event_name, callback)

    def start(self) -> HostStatus:
        """Start the LAN Host in the background."""
        if self._host is not None:
            return HostStatus(running=True, error="Host is already running.")
        
        self.events.dispatch(HOST_STARTING)
        self._host = NerveHost(
            receive_dir=self.receive_dir,
            lan_port=self.port,
            verbose=self.verbose,
        )

        def _run_host() -> None:
            try:
                if self._host:
                    self._host.start()
            except Exception as e:
                if self.verbose:
                    print(f"[NERVE LAN] Host error: {e}")
            finally:
                self.events.dispatch(HOST_STOPPED)

        self._host_thread = threading.Thread(
            target=_run_host, daemon=True, name="nerve-lan-host"
        )
        self._host_thread.start()
        self.events.dispatch(HOST_STARTED)
        
        return HostStatus(running=True, port=self.port)

    def stop(self) -> HostStatus:
        """Stop the LAN Host."""
        if self._host is None:
            return HostStatus(running=False, error="Host is not running.")
        
        self.events.dispatch(HOST_STOPPING)
        try:
            # We assume host has a stop mechanism or it can be interrupted.
            # NerveHost might need to be refactored to support clean programmatic termination.
            if hasattr(self._host, "stop"):
                self._host.stop()
        except Exception as e:
            return HostStatus(running=False, error=str(e))
        finally:
            self._host = None
            self._host_thread = None
            
        return HostStatus(running=False)

    def scan(self) -> list[DiscoveryResult]:
        """Scan for peers on the local network. (Phase 3)"""
        # Stub for Phase 1
        return []

    def connect(
        self, ip: str, name: Optional[str] = None, token: Optional[str] = None
    ) -> ConnectionResult:
        """Connect to a remote LAN peer."""
        try:
            peer = connect_and_register(address=ip, name=name, token=token)
            return ConnectionResult(
                success=True,
                peer_id=peer.peer_id,
                peer_name=peer.name,
                address=peer.last_address,
            )
        except (LanAuthenticationError, LanConnectionError, LanProtocolError) as e:
            return ConnectionResult(success=False, error=str(e))
        except Exception as e:
            return ConnectionResult(success=False, error=f"Unknown error: {e}")

    def send(
        self,
        path: str,
        to: str,
        progress_callback: Optional[Callable[..., None]] = None,
    ) -> TransferResult:
        """Send a file or directory to a remote peer. (Phase 4)"""
        # Stub for Phase 1
        return TransferResult(success=False, error="Not implemented in Phase 1.")

    def receive(self) -> None:
        """Explicitly accept a receive request. (Phase 7)"""
        # Stub for Phase 1
        pass

    def get_peers(self) -> list[Any]:
        """Get a list of known registered peers."""
        reg = PeerRegistry()
        return reg.list_peers()

    def get_transfers(self) -> list[Any]:
        """Get a list of active transfers."""
        # Stub for Phase 1
        return []
