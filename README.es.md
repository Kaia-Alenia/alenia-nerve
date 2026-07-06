# Nerve — Sistema Nervioso Descentralizado para Sockets Locales

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-darkviolet.svg?style=for-the-badge)](https://github.com/Kaia-Alenia/alenia-nerve) <a href="https://gitgem.org/github/Kaia-Alenia/alenia-nerve"><img src="https://gitgem.org/api/badge/github/Kaia-Alenia/alenia-nerve.svg" alt="GitGem"></a>


> **Soberanía, Velocidad y Privacidad Absoluta.** Nerve es el motor de comunicación entre procesos (IPC) local y multiplataforma diseñado por Alenia Studios para orquestar herramientas de desarrollo de videojuegos localmente, requiriendo cero dependencias en la nube.

---

## ¿Para qué sirve Nerve?

Nerve está diseñado para desarrolladores que necesitan conectar múltiples programas, scripts o microservicios locales para intercambiar datos en tiempo real con latencia de submilisegundos. En lugar de ejecutar un servidor web local pesado (como Flask o FastAPI) que abre puertos públicos, o escribir en archivos compartidos propensos a bloqueos, Nerve crea un bus de comunicación local seguro y ultrarrápido.

### Casos de Uso Principales:
* **Microservicios Locales y Aplicaciones de Escritorio:** Vincula un frontend moderno (Electron, Tauri, Flutter) con un backend pesado en Python o un modelo de IA local.
* **Pipelines de Datos en Tiempo Real e IA:** Transmite datos (audio, video, texto) entre nodos de procesamiento. Si un nodo de IA falla, Nerve lo reconecta automáticamente.
* **Automatización y Orquestación de Scripts:** Coordina tareas en segundo plano (colectores de logs, scripts de respaldo automático, scrapers) y agrega sus salidas.
* **Comunicación Políglota:** Conecta programas escritos en diferentes lenguajes (Python, Rust, C++, Go) utilizando JSON simple delimitado por líneas sobre sockets locales estándar.

---

## El Concepto: Redes Locales Soberanas

En el desarrollo de videojuegos moderno, la privacidad de tus recursos, código fuente y metadatos es primordial. Nerve actúa como un bus de datos local ultrarrápido, permitiendo que procesos independientes (como cortadores de sprites, renderizadores de gifs y monitores de sistema) se sincronicen en tiempo real con latencia de submilisegundos, sin enviar un solo byte fuera de tu estación de trabajo física.

---

## Núcleo Nativo Multiplataforma (UDS y TCP)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blueviolet.svg?style=for-the-badge)](#)

Nerve es totalmente multiplataforma y se adapta dinámicamente al sistema operativo anfitrión para ofrecer la mejor latencia local posible:
* **Linux y macOS:** Utiliza Unix Domain Sockets (UDS) nativos a través de `socket.AF_UNIX` en `/tmp/nerve.sock` para tuberías de memoria directa de alto rendimiento.
* **Windows:** Alterna dinámicamente a una conexión TCP local especializada a través de `socket.AF_INET` en `127.0.0.1:50505`, garantizando compatibilidad al 100% en estaciones de trabajo de desarrollo sin modificar una sola línea de la lógica de tus herramientas.

---

## Estructura del Monorepo y Clientes Soportados

Nerve está estructurado como un Monorepo que contiene el Hub central y las bibliotecas de cliente oficiales para varios lenguajes de programación:

```
alenia-nerve/
├── clients/
│   ├── python/        # Cliente oficial de Python y CLI Hub
│   ├── javascript/    # Cliente de Node.js y Navegador
│   ├── rust/          # Biblioteca de cliente en Rust
│   └── go/            # Biblioteca de cliente en Go
```

Consulta el subdirectorio de cada cliente para obtener instrucciones específicas de instalación y uso.

## Instalación (Cliente de Python y CLI Hub)
[![PyPI Version](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet)](https://pypi.org/project/alenia-nerve/) [![Python](https://img.shields.io/badge/Python-3.10%2B-indigo.svg?style=for-the-badge)](#)

Recomendamos instalar esta herramienta dentro de un entorno virtual aislado para cumplir con los estándares de seguridad de los sistemas operativos modernos (PEP 668) y evitar conflictos de dependencias.

```bash
python3 -m venv alenia_env

source alenia_env/bin/activate

pip install alenia-nerve
```

Nota para instalación global: Si prefieres una instalación en todo el sistema (por ejemplo, dentro de Docker o pipelines de CI/CD específicos) y eres consciente de los riesgos, puedes omitir la restricción del sistema operativo:

```bash
pip install alenia-nerve --break-system-packages
```

---

## Interfaz de Línea de Comandos (CLI) y el Hub Principal

Una vez que tengas la biblioteca `alenia-nerve` instalada globalmente o en tu entorno virtual, no necesitas escribir un script de Python personalizado para iniciar el servidor. Puedes abrir cualquier terminal y escribir:

```bash
nerve start
```

Este comando inicia instantáneamente el NexusHub (el servidor principal). Al hacer esto:
1. **Configuración Cero:** Este terminal se ejecutará en segundo plano y actuará como el cerebro central o enrutador para toda tu red local.
2. **Descubrimiento Automático:** Cualquier otra herramienta, script o aplicación que use el NexusClient se descubrirá y conectará automáticamente a este Hub para comenzar a enviar y recibir mensajes sin problemas.

Si deseas ver exactamente qué mensajes se están transmitiendo entre tus aplicaciones en tiempo real (útil para depuración), puedes usar:
```bash
nerve start --verbose
```

### Menú de Ayuda:
```bash
nerve --help
```

---

## Ejemplo Simple de Integración (Python)

### 1. Inicializar el Cliente
Conéctate al hub local registrando un ID de cliente único.

```python
from nerve import NexusClient

client = NexusClient()
client.connect("my_tool_id")
```

### 2. Enviar Mensaje a un Nodo Específico
Envía cualquier carga útil serializable en JSON directamente a otro nodo registrado:

```python
payload = {"progress": 100, "status": "COMPLETED"}
client.send("other_tool_id", payload)
```

### 3. Transmisión a Todos los Nodos (Broadcast)
Transmite cualquier carga útil a todos los demás clientes actualmente conectados al hub:

```python
client.broadcast({"event": "asset_ready", "path": "/assets/knight.png"})
```

### 4. Escuchar el Flujo Entrante
Registra una función de devolución de llamada (callback) asíncrona para escuchar flujos de datos en tiempo real:

```python
def handle_incoming(data):
    print(f"Received: {data}")

client.listen(handle_incoming)
```

### 5. Listar Nodos Conectados
Consulta al hub por todos los IDs de clientes registrados actualmente:

```python
nodes = client.list_clients()
print(nodes)  # ['renderer', 'monitor', 'logger']
```

Para ver una implementación completamente funcional y lista para producción de Nerve trabajando junto con Zenith en herramientas como Framegrid y Giftly, visita el repositorio [zenith-nerve-tools](https://github.com/Kaia-Alenia/zenith-nerve-tools).

---

## Contribuidores

Queremos expresar nuestro más profundo agradecimiento a todos los que contribuyen a Nerve. Tu trabajo, revisiones y reportes de errores hacen posible este proyecto.

* **Alenia Studios** - Mantenedor Principal y Publicador

¿Quieres aparecer aquí? Consulta nuestra guía CONTRIBUTING.md y envía una solicitud de extracción (Pull Request). Consulta CONTRIBUTORS.md para ver la lista completa.

Consulta CHANGELOG.md para ver el historial completo de versiones.

---

## Licencia
[![License](https://img.shields.io/badge/License-GPLv3-8a2be2.svg?style=for-the-badge)](LICENSE)

Este software se distribuye bajo la Licencia Pública General de GNU v3 (GPL v3). Consulta el archivo LICENSE para más detalles.

---
*Diseñado con pasión por Alenia Studios para empoderar a creadores de juegos soberanos.*
