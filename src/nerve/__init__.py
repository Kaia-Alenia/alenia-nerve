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

from .core import NexusClient, NexusHub, load_external_config

__version__ = "1.3.2"
__author__ = "Alenia Studios"
__license__ = "ALENIA STUDIOS TOOL LICENSE Version 1.0"
__email__ = "contact.aleniastudios@gmail.com"
__all__ = ["NexusHub", "NexusClient", "load_external_config"]
