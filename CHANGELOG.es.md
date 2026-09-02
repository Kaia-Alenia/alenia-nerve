# Registro de Cambios — alenia-nerve

Todos los cambios notables en este proyecto serán documentados en este archivo.

## [1.6.10] — 2026-09-02
### Agregado
- **LAN** (`api.py`): Añadido el parámetro `target_ip` a `scan()` (y al CLI `nerve scan <IP>`) para descubrimiento unicast. Esto evita el aislamiento de AP (AP Isolation) en routers Wi-Fi restrictivos donde se bloquea el broadcast UDP.
- **Nerve LAN Fase 1**: Introducida la Comunicación Directa entre Dispositivos sin necesidad de un hub central (a partir de la versión 1.6.0).
- **CLI**: Añadido `nerve host` para iniciar un host persistente de igual a igual (peer-to-peer).
- **CLI**: Añadido `nerve scan` para descubrir dispositivos Nerve en la red local mediante broadcast UDP (puerto 50511).
- **Seguridad**: Autenticación robusta usando `auth_token` para conexiones LAN.

### Solucionado
- **LAN** (`host.py`): El enlace (bind) de descubrimiento UDP en el puerto 50511 ahora es no fatal. Resuelve `WinError 10013` en entornos CI de Windows y firewalls estrictos, permitiendo que el plano de datos TCP siga funcionando.
- **LAN** (`api.py`): Solucionados problemas de enrutamiento multi-homed en Windows haciendo broadcast explícito a las direcciones de subred en lugar de depender solo del `<broadcast>` global.
- **Cliente Python**: `__version__` ahora usa correctamente `importlib.metadata` para resolución dinámica de versiones, evitando discrepancias de versión.
- **LAN** (`host.py`): Solucionada una condición de carrera de hilos huérfanos en macOS durante `stop()`.

## [1.5.9] — 2026-08-31
### Solucionado
- **CI** (`ci.yml`): Fijado `ruff` a la versión `0.15.20` para evitar fallos en cascada del linter en entornos CI que usan `pip install ruff` (última versión).
- **CI** (Python): Resueltos errores de `ruff check` — ordenación de imports (`I001`), directivas `noqa` sin uso (`RUF100`), concatenación de listas (`RUF005`), `asyncio.ensure_future` sin captura (`RUF006`) y anidamiento de sentencias `with` (`SIM117`) en los archivos de prueba.
- **CI** (Go): Eliminadas dos declaraciones de función `TestListClientsError` duplicadas en `client_test.go` que causaban que `go vet` fallara.
- **CI** (Rust / `crates.io`): Se vuelve a publicar la corrección `1.5.8` de `client_tests.rs` — la corrección de `cargo fmt --check` estaba en `main` pero la etiqueta `v1.5.8` era anterior a ella. Esta versión asegura que `crates.io` reciba la versión formateada correctamente.

## [1.5.8] — 2026-08-31
### Agregado
- **Core** (`core.py`): Extraído `_process_message()` de `_handle_client()` — la lógica de despacho de mensajes ahora vive en su propio método, reduciendo la complejidad de la función y facilitando las pruebas.
- **Core** (`core.py`): Añadida constante `MAX_BUFFER_SIZE` (10 MB) para limitar los búferes de lectura de socket sin límite y prevenir agotamiento de memoria bajo entrada adversarial.
- **Core** (`core.py`): `broadcast()` ahora registra métricas de `total_bytes_sent` y `total_messages_sent`, manteniendo las estadísticas coherentes con los envíos directos.
- **Bridge** (`bridge.py`): Añadido parámetro `allowed_origins` a `NerveBridge` — rechaza conexiones WebSocket cuyo encabezado `Origin` no esté en la lista permitida (por defecto limita al propio `host:port`). Cierra un vector de ataque CSRF/cross-origin.
- **Tests** (Rust): Tests unitarios para `load_external_config` (JSON, key=value y ruta inexistente). Añadida dependencia de desarrollo `tempfile`.
- **Tests** (JavaScript): Suite de tests migrada de una función procedural `runTests()` a bloques BDD `describe/it` de `mocha`. Añadido `mocha ^10.8.2` como dependencia de desarrollo.
- **Tests** (Go): Ampliada la cobertura de `client_test.go` con 301 líneas de nuevos casos de prueba.
- **Tests** (Python): Añadidos `test_bridge.py` y `test_cli_monitor.py` a la suite de pytest; extendido `test_core.py` con 37 aserciones adicionales.

### Corregido
- **Core** (`core.py`): Eliminado `import hmac` no utilizado (Ruff F401).
- **CLI Monitor** (`cli_monitor.py`): Corregido `format_bytes()` — los valores negativos y los límites exactos de kilobyte se redondeaban incorrectamente. Ahora maneja `abs(b) < 1024` de forma separada antes de entrar al bucle de unidades.
- **CLI Monitor** (`cli_monitor.py`): Eliminado el encabezado permisivo `Access-Control-Allow-Origin: *` del endpoint de métricas `/api/metrics` del dashboard.

### Cambiado
- Versión sincronizada a `1.5.8` en todos los paquetes cliente (Python, JavaScript/npm, Rust/crates.io).

## [1.5.7] — 2026-07-31
### Corregido
- **Bridge** (`bridge.py`): Resuelto error de lint Ruff S110 — reemplazado `except Exception: pass` silencioso en `_handle_hub_message._send()` por `logger.debug(...)` para registrar la excepción en lugar de ignorarla.

## [1.5.6] — 2026-07-31
### Corregido
- **Core** (`core.py`): Corregido bug crítico en `NexusHub.start()` donde el `raise OSError` de "dirección ya en uso" era atrapado por su propio bloque `except OSError`, haciendo que el hub siempre intentara eliminar el socket incluso si había una instancia activa escuchando.
- **Bridge** (`bridge.py`): Corregido bloqueo infinito en `NerveBridge.start()` — ahora verifica la disponibilidad del hub antes de conectar. Completado `_handle_hub_message` con `asyncio.run_coroutine_threadsafe` para routing real hacia clientes WebSocket. Corregido `KeyError` en `_ws_handler.finally` usando `discard()` y `.pop()` en lugar de `remove()` y `del`.
- **CLI Monitor** (`cli_monitor.py`): Corregido bloqueo indefinido en `nerve dashboard` y `nerve monitor` cuando el hub no estaba corriendo. Ahora fallan inmediatamente con mensaje de error claro usando un probe de socket previo.
### Cambiado
- Versión sincronizada a `1.5.6` en todos los paquetes cliente (Python, JavaScript/npm, Rust/crates.io).

## [1.5.4] — 2026-07-28
### Modificado
- **Core**: Forzada la extensión `.nrv` automáticamente al empaquetar si no se provee.
- **UI**: Corregido bug en Linux donde cancelar el diálogo de contraseña abría una ventana secundaria.
- **Assets**: Ajustado el padding interno del logo `.nrv` para proporciones correctas en file managers.


## [1.5.3] — 2026-07-28
- Agregado Empaquetado Seguro de Datos (`.nrv`) con AES-256-GCM y Argon2id.
- Interfaz CLI mejorada con comandos `pack` y `unpack` para encriptación de archivos de extremo a extremo.
- Agregado comando `nerve genpass` y generación interactiva de contraseñas seguras durante el empaquetado `.nrv`, usando generador de passphrase tipo diceware con lista de EFF.

## [1.5.1] — 2026-07-20

### Corregido
- Python: `nerve dashboard` devolvía 404 porque `dashboard/index.html` no estaba
  incluido en el wheel publicado. Corregido declarando el archivo en
  `[tool.setuptools.package-data]` dentro de `pyproject.toml`.

---

## [1.3.5] — 2026-06-15

### Cambiado
- Incrementada la versión para asegurar una publicación limpia en PyPI y sincronización de descripción.

---

## [1.3.4] — 2026-06-15

### Cambiado
- Actualizado el diseño de las insignias del README para usar una paleta púrpura unificada y la insignia GitGem en HTML para la sincronización con PyPI.

---

## [1.3.3] — 2026-06-15

### Corregido
- `NexusClient`: Se resolvieron fugas de sockets y descriptores de archivos cerrando los sockets en intentos de conexión fallidos.
- `NexusClient`: Se solucionó una condición de carrera crítica en `list_clients()` enrutando las respuestas a través del hilo del oyente.
- `NexusClient`: Se previno bucles de reconexión infinita tras una desconexión explícita.
- `NexusHub`: Se previnieron fugas de hilos y sockets al detener cerrando todos los sockets de clientes activos.
- `NexusHub`: Se protegió la creación de sockets Unix mediante umask para asegurar permisos seguros.
- `NexusHub`: Se reemplazó el sleep activo en los latidos (heartbeats) por sincronización de eventos.

### Cambiado
- Se eliminaron los emojis de `README.md` para cumplir con las pautas de presentación limpia.
- Se agregó la insignia de verificación de GitGem a `README.md`.

---

## [1.3.2] — 2026-05-16

### Agregado
- `CHANGELOG.md` — ahora se realiza el seguimiento del historial de versiones completo.
- `CONTRIBUTORS.md` — archivo de reconocimiento a los contribuidores.
- Se agregó el clasificador de Python 3.13 a `pyproject.toml`.

### Corregido
- `cli.py`: Ejecutar `nerve` sin argumentos ahora sale con código `0` (información, no error).
- `SECURITY.md`: Corregida la tabla de versiones soportadas (se listaban versiones de Python < 3.10 que no tienen soporte).
- `README.md`: Actualizada la sección del registro de cambios de v1.2.0 a v1.3.1; agregada la documentación faltante para los métodos `broadcast()` y `list_clients()`.

---


## [1.3.1] — 2026-05-15

### Cambiado
- Mejorado el flujo de recuperación de errores en `NexusHub._handle_client` para conexiones no registradas.
- `cli.py`: Ejecutar `nerve` sin argumentos ahora sale con código `0` en lugar de `1` (uso informativo, no error).
- Se agregó el clasificador de `Python 3.13` a `pyproject.toml`.
- README: Añadida la documentación para los métodos de la API del cliente `broadcast()` y `list_clients()`.

---

## [1.3.0] — 2026-05-10

### Agregado
- Hooks `on_connect` y `on_disconnect` en `NexusHub` para el monitoreo de eventos del ciclo de vida.
- `NexusClient.list_clients()` — consulta todos los nodos registrados desde cualquier cliente.
- Método público `NexusHub.broadcast()` para transmisión en el servidor.
- Parámetro configurable `heartbeat_interval` en `NexusHub`.

### Corregido
- Condición de carrera en `NexusHub._remove_client` donde un cliente podía ser eliminado dos veces bajo una desconexión rápida.
- El hilo de latido ahora se detiene limpiamente cuando se llama a `hub.stop()`.

---

## [1.2.0] — 2026-04-20

### Agregado
- Bucle de reconexión automática en `NexusClient.listen()` con `retry_interval` configurable.
- Soporte para callback `on_reconnect` en `NexusClient.listen()`.
- Salida en consola con colores ANSI para los logs del hub.
- Bandera `--verbose` / `-v` para el comando CLI `nerve start`.
- Soporte para archivo de configuración externo `nerve.config` (formatos JSON y key=value).
- Propiedad `NexusHub.connected_clients` para inspección del registro de clientes en tiempo real.

### Cambiado
- Windows ahora usa automáticamente la alternativa TCP `AF_INET`; Unix/macOS usa `AF_UNIX`.

---

## [1.1.0] — 2026-03-15

### Agregado
- Comando CLI inicial `nerve start`.
- Delimitación JSON basada en líneas (delimitador `\n`) para límites de mensajes confiables.
- Hilo de demonio en segundo plano por conexión de cliente en el hub.

---

## [1.0.0] — 2026-02-28

### Agregado
- Lanzamiento inicial de `alenia-nerve`.
- `NexusHub` — hub de enrutamiento central a través de Socket de Dominio Unix o TCP.
- `NexusClient` — cliente IPC ligero con API para `connect`, `send`, `broadcast` y `listen`.
- Soporte multiplataforma: Linux, macOS, Windows.
