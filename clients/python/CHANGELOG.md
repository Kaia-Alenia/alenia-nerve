# Changelog — alenia-nerve

All notable changes to this project will be documented in this file.

## [1.5.5] — 2026-07-31
### Fixed
- **Core** (`core.py`): Fixed critical bug in `NexusHub.start()` where `raise OSError` for "address already in use" was caught by its own `except` block, causing the socket to always be removed even when an active hub was listening.
- **Bridge** (`bridge.py`): Fixed infinite hang in `NerveBridge.start()` when hub is not running. Implemented real message routing in `_handle_hub_message` using `asyncio.run_coroutine_threadsafe`. Fixed `KeyError` in `_ws_handler` cleanup by using `discard()` and `.pop()` instead of `remove()` and `del`.
- **CLI Monitor** (`cli_monitor.py`): `nerve dashboard` and `nerve monitor` no longer hang indefinitely when the hub is not active. Both commands now display a clear error and exit immediately.

## [1.5.3] — 2026-07-28
- Added Secure Data Packing (`.nrv`) with AES-256-GCM and Argon2id.
- Enhanced CLI with `pack` and `unpack` commands for End-to-End file encryption.
- Added `nerve open` command for interactive extraction with up to 3 password retry attempts.
- Added `nerve associate` and `unassociate` commands to register `.nrv` files with the OS and provide custom icons for Windows/macOS/Linux.
- Added `nerve genpass` for generating secure passwords (random) and passphrases (Diceware).
- Added interactive password prompts with native GUI fallbacks (osascript, Tkinter, Zenity) when not in a TTY.
- Improved extraction safety by gracefully skipping unsafe absolute symlinks and hardlinks with a warning instead of aborting.

## [1.5.1] — 2026-07-20

### Fixed
- `nerve dashboard`: `index.html` was missing from the published wheel because
  `[tool.setuptools.package-data]` did not declare `dashboard/index.html`.
  Users who installed via `pip install alenia-nerve` received a 404 when opening
  the dashboard. The file is now explicitly included under the `nerve` package.

---

## [1.3.5] — 2026-06-15

### Changed
- Bumped version to ensure clean PyPI publication and description synchronization.

---

## [1.3.4] — 2026-06-15

### Changed
- Updated README badges layout to use unified purple palette and HTML GitGem badge for PyPI synchronization.

---

## [1.3.3] — 2026-06-15

### Fixed
- `NexusClient`: Resolved socket and file descriptor leaks by closing sockets on failed connection attempts.
- `NexusClient`: Solved a critical race condition in `list_clients()` by routing responses through the listener thread.
- `NexusClient`: Prevented infinite reconnect loops on explicit disconnection.
- `NexusHub`: Prevented thread and socket leaks on stop by closing all active client sockets.
- `NexusHub`: Protected Unix socket creation via umask to ensure secure permissions.
- `NexusHub`: Replaced busy sleep in heartbeats with Event synchronization.

### Changed
- Removed emojis from `README.md` to adhere to clean presentation guidelines.
- Added GitGem verification badge to `README.md`.

---

## [1.3.2] — 2026-05-16

### Added
- `CHANGELOG.md` — full version history now tracked.
- `CONTRIBUTORS.md` — contributor recognition file.
- Python 3.13 classifier added to `pyproject.toml`.

### Fixed
- `cli.py`: `nerve` with no arguments now exits with code `0` (informational, not error).
- `SECURITY.md`: corrected supported version table (was listing Python versions < 3.10 which are unsupported).
- `README.md`: updated changelog section title from v1.2.0 to v1.3.1; added missing `broadcast()`, `list_clients()` API documentation.

---


## [1.3.1] — 2026-05-15

### Changed
- Improved `NexusHub._handle_client` error recovery path for unregistered connections.
- `cli.py`: `nerve` with no arguments now exits with code `0` instead of `1` (informational usage, not an error).
- Added `Python 3.13` classifier to `pyproject.toml`.
- README: Added documentation for `broadcast()` and `list_clients()` client API methods.

---

## [1.3.0] — 2026-05-10

### Added
- `on_connect` and `on_disconnect` hooks on `NexusHub` for lifecycle event monitoring.
- `NexusClient.list_clients()` — query all registered nodes from any client.
- `NexusHub.broadcast()` public method for server-side broadcasting.
- Configurable `heartbeat_interval` parameter on `NexusHub`.

### Fixed
- Race condition in `NexusHub._remove_client` where a client could be removed twice under rapid disconnect.
- Heartbeat thread now stops cleanly when `hub.stop()` is called.

---

## [1.2.0] — 2026-04-20

### Added
- Auto-reconnection loop in `NexusClient.listen()` with configurable `retry_interval`.
- `on_reconnect` callback support in `NexusClient.listen()`.
- Colored ANSI console output for hub logs.
- `--verbose` / `-v` flag for the `nerve start` CLI command.
- External `nerve.config` file support (JSON and key=value formats).
- `NexusHub.connected_clients` property for real-time client registry inspection.

### Changed
- Windows now uses `AF_INET` TCP fallback automatically; Unix/macOS uses `AF_UNIX`.

---

## [1.1.0] — 2026-03-15

### Added
- Initial `nerve start` CLI command.
- Line-based JSON framing (`\n` delimiter) for reliable message boundaries.
- Background daemon thread per client connection in the hub.

---

## [1.0.0] — 2026-02-28

### Added
- Initial release of `alenia-nerve`.
- `NexusHub` — central routing hub via Unix Domain Socket or TCP.
- `NexusClient` — lightweight IPC client with `connect`, `send`, `broadcast`, and `listen` API.
- Cross-platform support: Linux, macOS, Windows.
