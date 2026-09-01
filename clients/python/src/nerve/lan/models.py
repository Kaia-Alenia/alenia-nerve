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
from typing import Optional


@dataclass
class ConnectionResult:
    success: bool
    error: Optional[str] = None
    peer_id: Optional[str] = None
    peer_name: Optional[str] = None
    address: Optional[str] = None


@dataclass
class DiscoveryResult:
    peer_id: str
    peer_name: str
    address: str
    platform: str


@dataclass
class TransferResult:
    success: bool
    transfer_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class HostStatus:
    running: bool
    address: Optional[str] = None
    port: Optional[int] = None
    error: Optional[str] = None


@dataclass
class ProgressEvent:
    transfer_id: str
    percent: float
    transferred_bytes: int
    total_bytes: int
    current_file: Optional[str] = None
