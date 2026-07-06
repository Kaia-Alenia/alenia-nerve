# alenia-nerve — Rust Client

[![crates.io](https://img.shields.io/crates/v/alenia-nerve.svg?style=for-the-badge&color=orange)](https://crates.io/crates/alenia-nerve)
[![docs.rs](https://img.shields.io/docsrs/alenia-nerve.svg?style=for-the-badge&color=blue)](https://docs.rs/alenia-nerve)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=for-the-badge)](../../LICENSE)

<div align="center">
  <img src="../../assets/rust_client.svg" alt="Rust Client" width="100%">
</div>

Rust client library for the [Alenia Nerve](https://github.com/Kaia-Alenia/alenia-nerve) local IPC engine.
Provides both an async (`NexusClient`) and a blocking/sync (`SyncNexusClient`) API over Unix Domain Sockets (Linux/macOS) or TCP (Windows).

## Installation

```toml
[dependencies]
alenia-nerve = "1.4.1"
```

## Quick Start

```rust
use alenia_nerve::{NexusClient, ConnectionAddress};
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut client = NexusClient::new(Duration::from_secs(1), "", None);
    client.connect("my-app").await?;

    client.send("other-app", serde_json::json!({"hello": "world"}))?;

    client
        .listen(
            |msg| println!("Received: {}", msg),
            None,
        )
        .await;

    Ok(())
}
```

## License

GNU General Public License v3.0 — see [LICENSE](../../LICENSE) for details.

Built by **Alenia Studios** — contact.aleniastudios@gmail.com
