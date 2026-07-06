# Plan de Desarrollo y Seguimiento de Tareas — alenia-nerve

Este archivo registra el progreso de la reestructuración y el desarrollo del monorepo de Alenia Nerve.

## Fase 1: Estructuración del Monorepo y CI/CD

- [x] Crear estructura de directorios para clientes en `clients/` (python, javascript, rust, go).
- [x] Migrar el código del cliente y hub de Python a `clients/python/`.
- [x] Crear stubs y proyectos de base para los nuevos clientes:
  - [x] JavaScript: `package.json`, `index.js`, `index.d.ts`, pruebas en `test.js`.
  - [x] Rust: `Cargo.toml`, `src/lib.rs` con pruebas de integración.
  - [x] Go: `go.mod`, `client.go`, pruebas unitarias en `client_test.go`.
- [x] Configurar el flujo de integración continua en `.github/workflows/ci.yml` (linters y pruebas multilingüe).

## Fase 2: Documentación Oficial (Bilingüe)

- [x] Actualizar y distribuir insignias en `README.md` y `README.es.md` global.
- [x] Traducir y homogeneizar toda la documentación del repositorio (ES/EN):
  - [x] `README.md` y `README.es.md` en la raíz.
  - [x] `CONTRIBUTING.md` y `CONTRIBUTING.es.md`.
  - [x] `CODE_OF_CONDUCT.md` y `CODE_OF_CONDUCT.es.md`.
  - [x] `SECURITY.md` y `SECURITY.es.md`.
  - [x] `CONTRIBUTORS.md` y `CONTRIBUTORS.es.md`.
- [x] Crear y actualizar los registros de cambios (`CHANGELOG.md` y `CHANGELOG.es.md`) para cada cliente.
- [x] Incrustar la imagen de consola `nerve_hub.jpg` en los READMEs de Python y global.

## Fase 3: Implementación de Clientes

- [x] Cliente de JavaScript / TypeScript:
  - [x] Implementar conexión UDS y TCP fallback en Node.js.
  - [x] Serialización/deserialización JSON delimitada por líneas.
  - [x] Soporte para `connect`, `send`, `broadcast`, `listen` y `listClients`.
  - [x] Reconexión automática con callbacks.
  - [x] Tipos TypeScript en `index.d.ts`.
  - [x] `package.json` completo con todos los campos npm requeridos.
- [x] Cliente de Rust:
  - [x] Implementar API asíncrona (`NexusClient`) y síncrona (`SyncNexusClient`).
  - [x] Soporte UDS (Linux/macOS) y TCP (Windows).
  - [x] Reconexión automática con loop de retención.
  - [x] Tests de integración con puertos dinámicos (sin colisiones).
  - [x] Clippy limpio (`-D warnings`), `cargo fmt` aplicado.
  - [x] `Cargo.toml` con `categories`, `documentation` y `exclude`.
- [x] Cliente de Go:
  - [x] Implementar `NexusClient` real con UDS/TCP usando `net.Dial`.
  - [x] API: `Connect`, `Disconnect`, `Send`, `Broadcast`, `Listen`, `OnReconnect`.
  - [x] Reconexión automática con goroutine de lectura.
  - [x] Tests con servidor mock TCP (3 tests: Connect, Send, Listen).
  - [x] `go vet` limpio, `-race` detector sin issues.

## Fase 4: Publicación Oficial y CI/CD de Release

- [x] Configurar publicación a PyPI (`publish.yml`) con validación tag vs versión.
- [x] Configurar publicación a npm (`publish-npm.yml`) con provenance y validación.
- [x] Configurar publicación a crates.io (`publish-rust.yml`) con clippy, fmt y tests.
- [x] Actualizar CI con matrix de Node.js (18/20/22), `cargo clippy`, `go vet` y `-race`.
- [x] Crear cuenta y token en crates.io → agregar secreto `CRATES_IO_TOKEN` en GitHub.
- [x] Crear token en npm → agregar secreto `NPM_TOKEN` en GitHub.
- [x] Realizar el release tag `v1.3.8` y verificar que los workflows de publicación completan exitosamente.

## Fase 5: Robustez y Seguridad Avanzada

- [x] Soporte TLS/SSL para conexiones TCP en todos los clientes.
- [x] Rotación de tokens de autenticación dinámicos en el Hub.
- [x] Rate limiting y cuotas de transferencia por cliente.

## Fase 6: Herramientas del Ecosistema y CLI

- [x] CLI global `nerve-cli monitor` para monitoreo del Hub en tiempo real.
- [x] Dashboard web ligero (local) para visualizar conexiones y latencia.
- [x] Visor gráfico de topología de la red de procesos (Nexus Topology View).

## Fase 7: Ampliación de Clientes y Puentes

- [x] Cliente de C++ nativo para integraciones con motores de juegos.
- [x] Cliente de C# / .NET para aplicaciones de escritorio y Unity.
- [x] Puente HTTP-a-Nerve con WebSockets fallback para navegadores web.

## Fase 8: Pruebas de Integración Cruzada

- [x] Suite de pruebas cruzadas (Python ↔ JS, Python ↔ Go, JS ↔ Rust).
- [x] Benchmark de latencia sub-milisegundo entre clientes en local.
- [x] Entorno de integración continua con hub real en el pipeline de GitHub Actions.
