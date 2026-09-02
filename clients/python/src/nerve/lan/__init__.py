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
nerve.lan — Nerve LAN V1 direct device-to-device communication.

This subpackage implements the Nerve LAN V1 architecture as defined in
NERVE_LAN_ARCHITECTURE_v1_FINAL_AUDITED.md.

Existing local IPC (NexusHub, NexusClient, nerve start) is not modified
by this subpackage.

Public API is intentionally minimal at Phase 1. Exports will be extended
as each implementation phase is completed and reviewed.
"""

from nerve.lan.api import NerveLAN
from nerve.lan.events import (
    HOST_STARTED,
    HOST_STARTING,
    HOST_STOPPED,
    HOST_STOPPING,
    PEER_CONNECTED,
    PEER_DISCONNECTED,
    PEER_DISCOVERED,
    TRANSFER_ACCEPTED,
    TRANSFER_CANCELLED,
    TRANSFER_COMPLETED,
    TRANSFER_FAILED,
    TRANSFER_PREPARING,
    TRANSFER_PROGRESS,
    TRANSFER_REJECTED,
    TRANSFER_REQUESTED,
    TRANSFER_STARTED,
    TRANSFER_VERIFYING,
)
from nerve.lan.models import (
    ConnectionResult,
    DiscoveryResult,
    HostStatus,
    ProgressEvent,
    TransferResult,
)

__all__ = [
    # Events
    "HOST_STARTED",
    "HOST_STARTING",
    "HOST_STOPPED",
    "HOST_STOPPING",
    "PEER_CONNECTED",
    "PEER_DISCONNECTED",
    "PEER_DISCOVERED",
    "TRANSFER_ACCEPTED",
    "TRANSFER_CANCELLED",
    "TRANSFER_COMPLETED",
    "TRANSFER_FAILED",
    "TRANSFER_PREPARING",
    "TRANSFER_PROGRESS",
    "TRANSFER_REJECTED",
    "TRANSFER_REQUESTED",
    "TRANSFER_STARTED",
    "TRANSFER_VERIFYING",
    # Models
    "ConnectionResult",
    "DiscoveryResult",
    "HostStatus",
    "NerveLAN",
    "ProgressEvent",
    "TransferResult",
]
