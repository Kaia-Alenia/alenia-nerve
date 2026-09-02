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

from dataclasses import dataclass
from enum import Enum


class TransferState(str, Enum):
    """Structured transfer lifecycle states (arch §77.7, §79.4)."""

    PREPARING = "PREPARING"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ConnectionResult:
    success: bool
    error: str | None = None
    peer_id: str | None = None
    peer_name: str | None = None
    address: str | None = None


@dataclass
class DiscoveryResult:
    peer_id: str
    peer_name: str
    address: str
    platform: str


@dataclass
class TransferResult:
    success: bool
    transfer_id: str | None = None
    error: str | None = None


@dataclass
class HostStatus:
    running: bool
    address: str | None = None
    port: int | None = None
    error: str | None = None


@dataclass
class ProgressEvent:
    transfer_id: str
    percent: float
    transferred_bytes: int
    total_bytes: int
    current_file: str | None = None
