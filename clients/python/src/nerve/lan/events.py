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

from collections import defaultdict
from collections.abc import Callable
from typing import Any

# Host lifecycle
HOST_STARTING = "HOST_STARTING"
HOST_STARTED = "HOST_STARTED"
HOST_STOPPING = "HOST_STOPPING"
HOST_STOPPED = "HOST_STOPPED"

# Peer lifecycle
PEER_DISCOVERED = "PEER_DISCOVERED"
PEER_CONNECTED = "PEER_CONNECTED"
PEER_DISCONNECTED = "PEER_DISCONNECTED"

# Transfer lifecycle
TRANSFER_REQUESTED = "TRANSFER_REQUESTED"
TRANSFER_ACCEPTED = "TRANSFER_ACCEPTED"
TRANSFER_REJECTED = "TRANSFER_REJECTED"

TRANSFER_PREPARING = "TRANSFER_PREPARING"
TRANSFER_STARTED = "TRANSFER_STARTED"
TRANSFER_PROGRESS = "TRANSFER_PROGRESS"
TRANSFER_VERIFYING = "TRANSFER_VERIFYING"
TRANSFER_COMPLETED = "TRANSFER_COMPLETED"
TRANSFER_FAILED = "TRANSFER_FAILED"
TRANSFER_CANCELLED = "TRANSFER_CANCELLED"


class EventDispatcher:
    """
    Structured event dispatcher for Nerve LAN.
    Provides a simple pub/sub model for the LAN service boundary.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., None]]] = defaultdict(list)

    def on(self, event_name: str, callback: Callable[..., None]) -> None:
        """Subscribe to a specific event."""
        self._subscribers[event_name].append(callback)

    def off(self, event_name: str, callback: Callable[..., None]) -> None:
        """Unsubscribe from a specific event."""
        if callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event with structured data to all subscribers."""
        import logging as _logging
        _log = _logging.getLogger("nerve.lan.events")
        for callback in self._subscribers[event_name]:
            try:
                callback(*args, **kwargs)
            except Exception as exc:
                # Dispatcher must not propagate callback errors; report via logger
                _log.warning(
                    "Error in event callback for %s: %s",
                    event_name,
                    exc,
                    exc_info=True,
                )
