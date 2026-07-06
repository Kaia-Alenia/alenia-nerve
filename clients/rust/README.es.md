# Alenia Nerve — Cliente Rust

[![crates.io](https://img.shields.io/crates/v/alenia-nerve.svg?color=orange&label=crates.io)](https://crates.io/crates/alenia-nerve)
[![crates.io Downloads](https://img.shields.io/crates/d/alenia-nerve.svg?color=orange&label=Descargas)](https://crates.io/crates/alenia-nerve)
[![docs.rs](https://img.shields.io/docsrs/alenia-nerve.svg?color=blue&label=docs.rs)](https://docs.rs/alenia-nerve)
[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange.svg)](#)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-blueviolet.svg)](#)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPLv3-blue.svg)](../../LICENSE)
[![Ko-fi](https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B.svg)](https://ko-fi.com/aleniastudios)

<div align="center">
  <img src="../../assets/rust_client.svg" alt="Rust Client" width="100%">
</div>

Biblioteca de cliente Rust para el motor IPC local [Alenia Nerve](https://github.com/Kaia-Alenia/alenia-nerve).
Proporciona una API asíncrona (`NexusClient`) y bloqueante/síncrona (`SyncNexusClient`) a través de Sockets de Dominio Unix (Linux/macOS) o TCP (Windows).

## Instalación

Instala el paquete (crate) usando `cargo`:

```bash
cargo add alenia-nerve
```

Alternativamente, añádelo manualmente a tu `Cargo.toml`:

```toml
[dependencies]
alenia-nerve = "1.4.5"
```

## Inicio Rápido

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
            |msg| println!("Recibido: {}", msg),
            None,
        )
        .await;

    Ok(())
}
```

## Licencia

Licencia Pública General de GNU v3.0 — consulta [LICENSE](../../LICENSE) para más detalles.

Construido por **Alenia Studios** — contact.aleniastudios@gmail.com
