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
Persistent peer registry for Nerve LAN V1.

Frozen requirement: Decision #4 — Peer Registry, connect, and Connection Lifetime.

A peer is identified by a stable peer_id, not by its IP address.
The IP address (last_address) is metadata that may change (DHCP).

Storage decision (Implementation Proposal):
    The existing repository has no established persistent data directory.
    nerve.config is the only existing persistence, and it is explicitly
    excluded by Decision #4: "must not casually overload nerve.config into
    an unstructured peer database if a separate Nerve-managed registry is
    architecturally cleaner."

    Therefore a new directory is strictly necessary. Location selected:
        Linux / macOS: ~/.nerve/peers.json
        Windows:       %APPDATA%\\Nerve\\peers.json

    Rationale:
    - ~/.nerve/ is consistent with the dotfile convention for user-specific
      application data on Unix.
    - %APPDATA%\\Nerve\\ is the Windows standard for per-user application data.
    - Both are cross-platform standard locations.
    - Neither conflicts with nerve.config (which lives in the working directory).
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nerve.lan.util import atomic_json_write

# ---------------------------------------------------------------------------
# Peer data model
# ---------------------------------------------------------------------------


@dataclass
class Peer:
    """
    Represents a known Nerve LAN peer.

    peer_id      Stable unique identifier (does not change with IP changes).
    name         Human-readable label for the peer (may be user-defined).
    hostname     OS hostname reported by the peer.
    platform     OS platform reported by the peer (e.g., "Linux", "Windows").
    last_address Last known IP:port address of the peer's LAN control plane.
    last_seen    Unix timestamp of the last successful contact.
    """

    peer_id: str
    name: str
    hostname: str
    platform: str
    last_address: str
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Peer:
        return cls(
            peer_id=data["peer_id"],
            name=data["name"],
            hostname=data["hostname"],
            platform=data["platform"],
            last_address=data["last_address"],
            last_seen=float(data.get("last_seen", time.time())),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _registry_path() -> Path:
    """
    Return the platform-appropriate path for peers.json.

    Linux / macOS: ~/.nerve/peers.json
    Windows:       %APPDATA%\\Nerve\\peers.json

    This is an Implementation Proposal — no path is frozen in the spec.
    The existing repository has no established persistent data directory.
    """
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Nerve" / "peers.json"
        return Path.home() / "Nerve" / "peers.json"
    return Path.home() / ".nerve" / "peers.json"


class PeerRegistry:
    """
    Manages the persistent registry of known Nerve LAN peers.

    Peers are stored as JSON at the platform-appropriate location.
    The registry is loaded on instantiation and saved explicitly.
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._path: Path = (
            registry_path if registry_path is not None else _registry_path()
        )
        self._peers: dict[str, Peer] = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load peers from disk. Silently no-ops if the file does not exist."""
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            peers_list = data.get("peers", [])
            self._peers = {
                entry["peer_id"]: Peer.from_dict(entry) for entry in peers_list
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            # Corrupted registry: preserve evidence, do not overwrite silently.
            backup_name = f"{self._path.name}.corrupt.{int(time.time())}"
            backup_path = self._path.with_name(backup_name)
            try:
                os.replace(self._path, backup_path)
                print(
                    f"[WARNING] Local peer registry was corrupt. Preserved as {backup_name}"
                )
            except OSError:
                pass
            self._peers = {}

    def save(self) -> None:
        """Persist the current registry to disk."""
        data = {"peers": [p.to_dict() for p in self._peers.values()]}
        atomic_json_write(self._path, data)

    # ------------------------------------------------------------------
    # Peer operations
    # ------------------------------------------------------------------

    def add_or_update(self, peer: Peer) -> None:
        """
        Add a new peer or update an existing one by peer_id.

        After calling this method, call save() to persist the change.
        """
        self._peers[peer.peer_id] = peer

    def get(self, peer_id_or_name: str) -> Peer | None:
        """
        Retrieve a peer by peer_id (exact match) or by name (case-insensitive).

        Returns None if no match is found, or if the name match is ambiguous.
        """
        # Exact peer_id match first
        if peer_id_or_name in self._peers:
            return self._peers[peer_id_or_name]

        # Fallback: case-insensitive name match
        matches = self.find_by_name(peer_id_or_name)
        if len(matches) == 1:
            return matches[0]
        # If 0 or >1 matches, return None (ambiguous or not found)
        return None

    def find_by_name(self, name: str) -> list[Peer]:
        """
        Find all peers matching the given name (case-insensitive).
        Returns a list of matching peers.
        """
        needle = name.lower()
        return [p for p in self._peers.values() if p.name.lower() == needle]

    def list_peers(self) -> list[Peer]:
        """Return all known peers, sorted by last_seen descending."""
        return sorted(self._peers.values(), key=lambda p: p.last_seen, reverse=True)

    def remove(self, peer_id_or_name: str) -> bool:
        """
        Remove a peer by peer_id or name.

        Returns True if a peer was removed, False if not found.
        After calling this method, call save() to persist the change.
        """
        peer = self.get(peer_id_or_name)
        if peer is None:
            return False
        del self._peers[peer.peer_id]
        return True


# ---------------------------------------------------------------------------
# Helper: build a Peer from a connect handshake response
# ---------------------------------------------------------------------------


def peer_from_handshake(
    handshake: dict,
    address: str,
    name: str | None = None,
) -> Peer:
    """
    Construct a Peer from the data received during a connect handshake.

    handshake  dict with keys: peer_id, hostname, platform (from nerve host hello)
    address    IP:port string of the remote LAN control plane
    name       optional human label; defaults to handshake hostname
    """
    peer_id = handshake["peer_id"]
    hostname = handshake.get("hostname", socket.gethostname())
    peer_platform = handshake.get("platform", "unknown")
    return Peer(
        peer_id=peer_id,
        name=name if name else hostname,
        hostname=hostname,
        platform=peer_platform,
        last_address=address,
        last_seen=time.time(),
    )
