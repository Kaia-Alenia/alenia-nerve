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
"""Nerve — Decentralized Nervous System for Local Sockets.

Nerve is a cross-platform, zero-dependency local inter-process communication
(IPC) engine built by Alenia Studios.  It provides a lightweight hub-client
architecture for routing JSON messages between independent processes running on
the same machine, with no cloud dependency and sub-millisecond latency.

Typical usage::

    from nerve import NexusHub, NexusClient

    hub = NexusHub()
    hub.start()  # run in a separate process or thread

    client = NexusClient()
    client.connect("my_tool")
    client.send("other_tool", {"status": "ready"})
"""

import importlib.metadata

from .core import NexusClient, NexusHub, load_external_config
from .nrv import pack_nrv, unpack_nrv

try:
    __version__ = importlib.metadata.version("alenia-nerve")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"
__author__ = "Alenia Studios"
__license__ = "GNU General Public License v3 (GPL v3)"
__email__ = "contact.aleniastudios@gmail.com"
__all__ = ["NexusClient", "NexusHub", "load_external_config", "pack_nrv", "unpack_nrv"]

# pack_nrv: Packs a file or directory into a secure encrypted .nrv container
# unpack_nrv: Decrypts and extracts a .nrv container safely
