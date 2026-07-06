# Registro de Cambios — alenia-nerve

Todos los cambios notables en este proyecto serán documentados en este archivo.

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
