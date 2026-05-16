# Changelog — alenia-nerve

All notable changes to this project will be documented in this file.

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
