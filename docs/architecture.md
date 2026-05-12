# Architecture

Nerve utilizes a centralized local architecture designed for sub-millisecond inter-process data piping.

## Core Components

1. **NexusHub**: The orchestration server routing incoming and outgoing JSON payloads. It binds dynamically depending on the host platform (using Unix Domain Sockets on macOS/Linux and a localized TCP interface on Windows).
2. **NexusClient**: The lightweight socket interface embedded within your pipeline applications. It manages connections, automatic background reconnection threads, and socket health pings.

## Communication Protocol

Data is serialized as single-line JSON structures and framed using newline characters (`\n`). This deliberate framing protocol prevents data collisions, package merging, and buffer distortion under high-frequency stream operations.
