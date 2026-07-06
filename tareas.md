# Plan de Desarrollo y Seguimiento de Tareas — alenia-nerve

Este archivo registra el progreso de la reestructuración y el desarrollo del monorepo de Alenia Nerve. Se actualiza después de completar cada hito.

## Fase 1: Estructuración del Monorepo y CI/CD

- [x] Crear estructura de directorios para clientes en `clients/` (python, javascript, rust, go).
- [x] Migrar el código del cliente y hub de Python a `clients/python/`.
- [x] Crear stubs y proyectos de base para los nuevos clientes:
  - [x] JavaScript: `package.json`, `index.js`, pruebas básicas en `test.js`.
  - [x] Rust: `Cargo.toml`, `src/lib.rs` con pruebas integradas.
  - [x] Go: `go.mod`, `client.go`, pruebas unitarias en `client_test.go`.
- [x] Configurar el flujo de integración continua en `.github/workflows/ci.yml` para validar de forma multilingüe (linters y pruebas de cada cliente).

## Fase 2: Documentación Oficial (Bilingüe)

- [x] Actualizar y distribuir insignias (badges) de forma profesional a lo largo del `README.md` y `README.es.md` global.
- [x] Traducir y homogeneizar toda la documentación en la raíz del repositorio (ES/EN, libre de emojis):
  - [x] `README.md` y `README.es.md` (incluyendo enlace a `zenith-nerve-tools` en la sección de ejemplos).
  - [x] `CONTRIBUTING.md` y `CONTRIBUTING.es.md` (actualizando comandos de instalación editable).
  - [x] `CODE_OF_CONDUCT.md` y `CODE_OF_CONDUCT.es.md`.
  - [x] `SECURITY.md` y `SECURITY.es.md`.
  - [x] `CONTRIBUTORS.md` y `CONTRIBUTORS.es.md`.
- [x] Crear y actualizar los registros de cambios (`CHANGELOG.md` y `CHANGELOG.es.md`) para cada cliente en sus directorios.
- [x] Incrustar la imagen de consola `nerve_hub.jpg` en los READMEs de Python y global.

## Fase 3: Implementación de Clientes Pendientes

- [ ] Cliente de JavaScript / TypeScript:
  - [ ] Implementar conexión UDS y TCP TCP fallback en Node.js.
  - [ ] Implementar serialización/deserialización JSON delimitada por líneas (`\n`).
  - [ ] Implementar soporte para `connect`, `send`, `broadcast` y `listen`.
- [ ] Cliente de Rust:
  - [ ] Implementar la API usando sockets UDS/TCP nativos.
  - [ ] Asegurar soporte para entornos asíncronos y síncronos.
- [ ] Cliente de Go:
  - [ ] Implementar soporte con goroutines para la recepción asíncrona de mensajes.
  - [ ] Validar conector socket local.

## Fase 4: Pruebas de Integración Cruzada e Hitos Finales

- [ ] Crear suite de pruebas de integración cruzada (por ejemplo, nodo de Python enviando mensajes a nodo de Go/JS).
- [ ] Validar rendimiento y latencia sub-milisegundo entre diferentes clientes en local.
- [ ] Preparar paquetes para publicación oficial (npm, crates.io, go registry, PyPI).
