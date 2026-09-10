<div align="center">
  <h1>Nerve</h1>
  <p><b>El Motor Definitivo de Transferencia LAN y Streaming IPC</b></p>
  
  [![PyPI Version](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet)](https://pypi.org/project/alenia-nerve/)
  [![GitHub Repository](https://img.shields.io/badge/GitHub-Repositorio-darkviolet.svg)](https://github.com/Kaia-Alenia/alenia-nerve)
  [![License: GPL v3](https://img.shields.io/badge/Licencia-GPLv3-blue.svg)](LICENSE)
  [![Ko-fi](https://img.shields.io/badge/Apóyanos-Ko--fi-FF5E5B.svg?logo=ko-fi&logoColor=white)](https://ko-fi.com/aleniastudios)

  <br>
  <p><b>Soberanía, Velocidad y Privacidad Absoluta.</b> Nerve es un motor de línea de comandos multiplataforma diseñado para empaquetar y transferir de forma segura bases de datos masivas, binarios pesados y transmitir datos entre Windows, Linux, macOS y Android mediante Termux. <b>No necesita nube ni acceso a Internet.</b></p>
</div>

---

## ¿Qué es Nerve?

Olvídate de subir 20GB de bases de datos o binarios pesados a la nube solo para pasarlos al servidor que está al otro lado de la habitación.

Nerve convierte tu red local en un bus de datos peer-to-peer de alta velocidad. Separa el tráfico en dos capas profesionales:
1. **El Plano de Control:** Para descubrir dispositivos en tu LAN (`nerve scan`), autenticación segura mediante tokens, y envío de mensajes JSON ligeros en tiempo real entre microservicios políglotas (Python, Rust, Go, JS).
2. **El Plano de Datos:** Un transporte de transmisión binaria pura construido para mover archivos masivos `.nrv` empaquetados mediante fragmentación (chunking) sin saturar jamás tu memoria RAM.

### Sin Internet no significa sin red local

Nerve no contacta servidores externos para descubrir, autenticar o transferir archivos. Todo el tráfico LAN usa conexiones directas entre dispositivos:

`nerve scan` envía una consulta UDP, `nerve host` responde, el plano de control TCP autentica con el token y el plano de datos TCP transfiere el archivo.

Para trabajar sin Internet, el Wi-Fi o Ethernet debe seguir conectado a una red local común. Puedes apagar la conexión WAN del router y mantener su LAN activa, usar un hotspot local, Wi-Fi Direct o un cable Ethernet directo. Si se desactiva por completo el adaptador de red, no existe una ruta IP y ningún programa puede conectar los dispositivos.

### La Experiencia Nerve

Transferir gigabytes de forma segura entre sistemas operativos requiere empaquetar tus archivos y usar un token de autenticación:

```bash
# 1. En tu estación de trabajo Windows (empaqueta tu directorio pesado)
$ nerve pack D:\BasesDeDatos\Proyecto proyecto.nrv

# 2. En tu máquina Linux (configura auth_token en nerve.config)
$ nerve host --receive-dir ~/datos_recibidos

# 3. En tu estación de trabajo Windows (Descubre y Envía)
$ nerve scan
> Found: linux-server (192.168.1.10)
$ nerve connect 192.168.1.10 --token "mi-contraseña-segura"
$ nerve send proyecto.nrv --to linux-server
```

El mismo flujo funciona en cualquier dirección: Linux a Windows, Windows a Linux, Windows a Windows y macOS a cualquiera de ellos. El host recibe archivos; el comando `send` inicia la transferencia desde el dispositivo que contiene el archivo.

### Android mediante Termux

Android puede participar en la misma LAN ejecutando el cliente Python de Nerve dentro de [Termux](https://termux.dev/). No requiere una aplicación Android especial ni Internet durante la transferencia.

```bash
# En Termux
pkg update
pkg install python git
termux-setup-storage
git clone https://github.com/Kaia-Alenia/alenia-nerve.git
cd alenia-nerve/clients/python
pip install .
```

Para recibir archivos en Android:

```bash
export NERVE_AUTH_TOKEN="mi-token-local"
nerve host --receive-dir ~/storage/downloads
```

Desde Windows o Linux, consulta la IP de Android y conecta directamente:

```bash
nerve diagnose 192.168.1.50
nerve connect 192.168.1.50 --token "mi-token-local"
nerve send archivo.zip --to 192.168.1.50
```

Para enviar desde Android hacia Windows o Linux, inicia `nerve host` en el equipo destino y ejecuta `nerve send` desde Termux usando la ruta del archivo. Mantén Termux activo durante la transferencia; Android puede suspender procesos en segundo plano si se bloquea la pantalla.

---

## Requisitos de Puertos y Firewall (Windows / Linux)

Cuando uses `nerve host` y `nerve scan` para Comunicación Directa entre Dispositivos, asegúrate de que tu firewall permita el tráfico en los siguientes puertos:

| Puerto | Protocolo | Propósito |
|--------|-----------|-----------|
| `50511` | UDP | Descubrimiento (broadcasts de `nerve scan`) |
| `50507` | TCP | Plano de Control (autenticación y handshake; configurable) |
| `50510` | TCP | Plano de Datos (transferencia de archivos y cargas grandes) |

**Solución para el Firewall de Windows:**
Si `nerve scan` no puede encontrar una máquina Windows ejecutando `nerve host`, generalmente es porque el Firewall de Windows bloquea el puerto UDP 50511 de entrada. Abre un **PowerShell como Administrador** y ejecuta:
```powershell
New-NetFirewallRule -DisplayName "Nerve LAN Discovery" -Direction Inbound -Protocol UDP -LocalPort 50511 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Control" -Direction Inbound -Protocol TCP -LocalPort 50507 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Data" -Direction Inbound -Protocol TCP -LocalPort 50510 -Action Allow -Profile Any
```

**Aislamiento AP (Routers Wi-Fi):**
Si tu router aísla a los clientes Wi-Fi (bloqueando paquetes broadcast UDP), `nerve scan` fallará. Puedes evitar esto escaneando la IP exacta directamente (unicast):
```bash
nerve scan 192.168.1.50
```

**Solución para el Firewall de Linux (UFW):**
Si estás usando un firewall estricto en Linux (como Ubuntu), los paquetes UDP entrantes podrían ser descartados. Permite los puertos usando UFW:
```bash
sudo ufw allow 50511/udp
sudo ufw allow 50507/tcp
sudo ufw allow 50510/tcp
```

**Plan B: Conexión Directa**
Si el escaneo sigue fallando debido a configuraciones de red o routers estrictos, puedes saltarte `nerve scan` por completo y conectarte directamente a la dirección IP del host:
```bash
$ nerve connect 192.168.1.50 --token "mi-contraseña-segura"
```
Para saber cuál es tu IP local:

```powershell
# Windows
ipconfig
```

```bash
# Linux / macOS / Termux
ip addr
# Si el comando ip no está disponible en Termux:
ifconfig
```

Busca la dirección IPv4 privada del adaptador que realmente conecta ambos equipos, por ejemplo `192.168.1.50`, `10.0.0.25` o `172.20.10.4`. No uses `127.0.0.1`: esa dirección solo funciona dentro del mismo dispositivo.

---

## Características Principales

* **Transferencias Nativas en Terminal:** Transferencias directas `Linux <-> Windows` y `Windows <-> Windows` listas para usar.
* **Motor de Doble Arquitectura:** Utiliza **Unix Domain Sockets (UDS)** de latencia ultrabaja para IPC local, y pivota dinámicamente a **Flujos Binarios TCP** al salir a la red LAN.
* **Streaming Real (Sin Inflar Memoria):** Los archivos masivos se dividen en fragmentos binarios `.nrv` sobre la marcha. Nerve no cargará un archivo de 10GB en tu memoria RAM.
* **Seguro por Defecto:** Las conexiones LAN requieren un token de autenticación configurado en `nerve.config` o `NERVE_AUTH_TOKEN`; `nerve connect` también acepta `--token`. A menos que ejecutes `nerve host`, Nerve permanece completamente silencioso y aislado.
* **SDKs Políglotas:** ¿Necesitas conectar un backend en Rust a un pipeline de datos en Python localmente? Nerve proporciona clientes oficiales para orquestar microservicios locales con reconexión automática y latidos en segundo plano.

---

##  Clientes Soportados e Integración

Nerve está estructurado como un Monorepo que contiene el Hub principal y las bibliotecas de cliente oficiales. A continuación puedes encontrar la instalación y un ejemplo simple de integración para cada lenguaje soportado.

### Cliente Python y Hub CLI

[![Python](https://img.shields.io/badge/Python-3.10%2B-indigo.svg?logo=python&logoColor=white)](#)
[![PyPI](https://img.shields.io/pypi/v/alenia-nerve.svg?color=blueviolet&label=PyPI)](https://pypi.org/project/alenia-nerve/)
[![Descargas](https://img.shields.io/pypi/dm/alenia-nerve.svg?color=blueviolet&label=Descargas%2Fmes)](https://pypi.org/project/alenia-nerve/)

✓ **Instalación:**
```bash
python3 -m venv alenia_env
source alenia_env/bin/activate   # En Windows: alenia_env\Scriptsctivate
pip install alenia-nerve
```

✓ **Ejemplo Simple de Integración:**
```python
from nerve import NexusClient

client = NexusClient()
client.connect("mi_herramienta_python")

# Enviar a un nodo específico
client.send("renderer", {"progress": 100, "status": "DONE"})

# Escuchar mensajes entrantes
def on_message(data):
    print(f"Recibido: {data}")

client.listen(on_message)
```

---

### Cliente Rust

[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange.svg?logo=rust&logoColor=white)](#)
[![crates.io](https://img.shields.io/crates/v/alenia-nerve.svg?color=orange&label=crates.io)](https://crates.io/crates/alenia-nerve)
[![docs.rs](https://img.shields.io/docsrs/alenia-nerve.svg?color=blue&label=docs.rs)](https://docs.rs/alenia-nerve)

✓ **Instalación:**
```bash
cargo add alenia-nerve
```

✓ **Ejemplo Simple de Integración:**
```rust
use alenia_nerve::{NexusClient, ConnectionAddress};
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mut client = NexusClient::new(Duration::from_secs(1), "", None);
    client.connect("mi_herramienta_rust").await?;

    client.send("renderer", serde_json::json!({"status": "ready"}))?;

    client.listen(|msg| println!("Recibido: {}", msg), None).await;
    Ok(())
}
```

---

### Cliente JavaScript / Node.js

[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933.svg?logo=nodedotjs&logoColor=white)](#)
[![npm](https://img.shields.io/npm/v/alenia-nerve.svg?color=cb3837&label=npm)](https://www.npmjs.com/package/alenia-nerve)
[![Descargas](https://img.shields.io/npm/dm/alenia-nerve.svg?color=cb3837&label=Descargas%2Fmes)](https://www.npmjs.com/package/alenia-nerve)

✓ **Instalación:**
```bash
npm install alenia-nerve
```

✓ **Ejemplo Simple de Integración:**
```javascript
const { NexusClient } = require("alenia-nerve");

const client = new NexusClient();
await client.connect("mi_herramienta_js");

client.send("renderer", { progress: 100, status: "DONE" });

client.listen((data) => {
    console.log("Recibido:", data);
});
```

---

### Cliente Go

[![Go](https://img.shields.io/badge/Go-1.21%2B-00ADD8.svg?logo=go&logoColor=white)](#)
[![pkg.go.dev](https://pkg.go.dev/badge/github.com/Kaia-Alenia/alenia-nerve/clients/go.svg)](https://pkg.go.dev/github.com/Kaia-Alenia/alenia-nerve/clients/go)

✓ **Instalación:**
```bash
go get github.com/Kaia-Alenia/alenia-nerve/clients/go
```

✓ **Ejemplo Simple de Integración:**
```go
package main

import (
    "fmt"
    nerve "github.com/Kaia-Alenia/alenia-nerve/clients/go"
)

func main() {
    client := nerve.NewClient()
    client.Connect("mi_herramienta_go")

    client.Send("renderer", map[string]interface{}{"status": "ready"})

    client.Listen(func(data map[string]interface{}) {
        fmt.Println("Recibido:", data)
    })
}
```

---

### Empaquetado Seguro (.nrv)

Nerve incluye un empaquetador criptográfico de alto rendimiento por streaming diseñado para compartir recursos offline. Utiliza AES-256-GCM y Argon2id para asegurar carpetas o archivos en contenedores `.nrv`.

Para máxima seguridad, evita pasar la contraseña como argumento; usa la variable de entorno `NERVE_NRV_PASSWORD`:
```bash
NERVE_NRV_PASSWORD="mi_contraseña_segura" nerve pack ./mi_juego mi_juego.nrv
NERVE_NRV_PASSWORD="mi_contraseña_segura" nerve unpack mi_juego.nrv ./output
```
Si no se define la variable de entorno, la CLI solicitará la contraseña de forma interactiva. Si no tienes una contraseña, la CLI te ofrecerá generar una frase de contraseña altamente segura (usando Diceware con la lista EFF). También puedes generar contraseñas seguras independientes usando el comando `nerve genpass`.

---

##  Interfaz de Línea de Comandos (CLI) y el Hub Principal

Una vez instalado, el comando `nerve` proporciona un conjunto de herramientas para administrar tu red IPC local y asegurar archivos.

### Comandos Disponibles

* **`nerve start`**: Inicia el **NexusHub** — el enrutador central de mensajes para tu red local. Se ejecuta de inmediato sin necesidad de configuración y escucha las conexiones entrantes. Usa `nerve start --verbose` para rastrear en tiempo real cada paquete enrutado.
* **`nerve monitor`**: Lanza un panel interactivo en terminal que muestra todos los clientes conectados, tiempo de actividad, conteo de mensajes y estadísticas de tráfico en un solo vistazo.
* **`nerve dashboard`**: Inicia una interfaz web local ligera en `http://localhost:8080` que renderiza una **Vista de Topología de Red** en vivo con todos los nodos conectados.
* **`nerve bridge`**: Inicia un proxy HTTP/WebSocket en el puerto 50506. Esto permite que navegadores web y clientes WebSocket se conecten y hablen directamente con la red IPC de Nerve. (Requiere el paquete `websockets`).
* **`nerve host`**: Inicia un host persistente de igual a igual (peer-to-peer) para la Comunicación Directa entre Dispositivos. Esto permite que otros dispositivos descubran esta máquina en la red local.
* **`nerve scan [IP]`**: Escanea la red local en busca de otros dispositivos Nerve ejecutando `nerve host`. Usa broadcast UDP, o unicast si se proporciona una IP específica (útil para eludir el aislamiento AP en routers estrictos).
* **`nerve pack <origen> <salida.nrv>`**: Encripta de forma segura y empaqueta un archivo o directorio en un contenedor `.nrv` usando AES-256-GCM.
* **`nerve unpack <nrv> <salida>`**: Desencripta y extrae un contenedor `.nrv` en el directorio de salida especificado.
* **`nerve open <archivo.nrv>`**: Abre de forma interactiva un contenedor `.nrv`, manejando las solicitudes de contraseña mediante TTY o diálogos de interfaz gráfica nativos (Zenity/Tkinter/macOS osascript) con hasta 3 intentos de reintento.
* **`nerve associate`**: Registra la extensión de archivo `.nrv` en tu sistema operativo (Windows/macOS/Linux) y la asocia con el comando `nerve open` y un ícono personalizado, habilitando la extracción con doble clic.
* **`nerve unassociate`**: Elimina la asociación de la extensión de archivo `.nrv` de tu sistema operativo.
* **`nerve genpass`**: Genera una contraseña o frase de contraseña altamente segura. Usa `--mode random` (longitud por defecto 20) o `--mode passphrase` (por defecto 5 palabras).

### Iniciando el Hub

```bash
nerve start
```

<div align="center">
  <img src="assets/images/nerve-start.png" alt="nerve start — Hub initializing and active via Unix Socket" width="90%">
  <br><sub>El Hub se inicializa instantáneamente y escucha conexiones de clientes vía Unix Domain Socket.</sub>
</div>

<br>

### Menú de Ayuda:
```bash
nerve --help
```

---

##  Herramientas de Monitoreo: CLI y Web Dashboard

Nerve incluye potentes herramientas integradas para observar tu red local en tiempo real — sin requerir servicios externos en la nube.

### CLI Monitor Global (`nerve-monitor`)

Un panel interactivo basado en terminal que muestra todos los clientes conectados, tiempo de actividad (uptime), conteo de mensajes y estadísticas de tráfico en un solo vistazo.

<p align="center">
  <img src="assets/images/cli-monitor-clients.png" alt="CLI Monitor mostrando clientes conectados" width="48%">
  &nbsp;
  <img src="assets/images/cli-monitor-giftly.png" alt="CLI Monitor mostrando tráfico en vivo" width="48%">
</p>

*Monitoreo en tiempo real de clientes de múltiples lenguajes y aplicaciones de producción conectadas simultáneamente.*

---

### Logs del Hub (`nerve start`)

Los registros del terminal del Hub muestran cada evento de registro, ruta de mensaje y desconexión con una salida a color. Esto es lo que el servidor ve cuando las aplicaciones cliente se conectan.

<p align="center">
  <img src="assets/images/hub-logs-clients.png" alt="Logs del Hub mostrando el banner ASCII y registro de clientes" width="48%">
  &nbsp;
  <img src="assets/images/hub-logs-giftly.png" alt="Logs del Hub mostrando el tráfico de red local" width="48%">
</p>

*Secuencia de arranque del Hub y registro transparente de eventos y reconexiones automáticas.*

---

### Web Dashboard (`nerve-dashboard`)

Una interfaz web local ligera que renderiza una **Vista de Topología de Red** en vivo — un grafo de cada nodo conectado — además del tiempo de actividad, tráfico total y contadores de mensajes.

<p align="center">
  <img src="assets/images/dashboard-topology.png" alt="Vista de Topología de Nexus — grafo mostrando al Hub de Nerve al centro con los nodos conectados" width="48%">
  &nbsp;
  <img src="assets/images/dashboard-full.png" alt="Dashboard Completo en la Web — barra lateral con la lista de nodos, tiempo de actividad y mensajes procesados" width="48%">
</p>

*Izquierda: Grafo de topología de los nodos interconectados. Derecha: Panel completo con la barra lateral de métricas en vivo mostrando el tráfico (ej. 18.25 KB) y mensajes procesados.*

---

##  Casos de Uso Reales en Producción

Nerve fue construido para operar en entornos exigentes. Actualmente, orquesta el ecosistema de herramientas de **Alenia Studios**, sirviendo como el puente de comunicación en tiempo real para aplicaciones pesadas de escritorio:

* **Framegrid:** Herramienta avanzada de procesamiento de imágenes y hojas de sprites.
* **Giftly:** Renderizador de exportaciones y automatización de GIFs.

*(Echa un vistazo a nuestro monorepo [zenith-nerve-tools](https://github.com/Kaia-Alenia/zenith-nerve-tools) para ver la implementación de estas herramientas de producción construidas enteramente sobre la arquitectura de Nerve).*

---



##  Archivo de Configuración (`nerve.config`)

Coloca un archivo `nerve.config` en la raíz de tu proyecto o en el directorio de usuario (home) para personalizar las rutas de socket, los puertos TCP y la autenticación sin cambiar el código:

**Formato JSON:**
```json
{
  "socket_path": "/tmp/nerve.sock",
  "port": 50505,
  "host": "127.0.0.1",
  "auth_token": "mi_token_seguro",
  "lan_port": 50507
}
```

**Formato clave-valor simple:**
```text
socket_path=/tmp/nerve.sock
port=50505
auth_token=mi_token_seguro
lan_port=50507
```

---

##  Descubrimiento LAN y Firewall (Windows / Linux)

Cuando uses `nerve host` y `nerve scan` para Comunicación Directa entre Dispositivos a través de múltiples computadoras, asegúrate de que tu firewall permita el tráfico en los siguientes puertos:

| Puerto | Protocolo | Propósito |
|--------|-----------|-----------|
| `50511` | UDP | Descubrimiento (broadcasts de `nerve scan`) |
| `50507` | TCP | Plano de Control (autenticación y handshake; configurable con `lan_port`) |
| `50510` | TCP | Plano de Datos (transferencia de archivos y cargas grandes) |

**Solución para el Firewall de Windows:**
Si `nerve scan` no puede encontrar una máquina Windows ejecutando `nerve host`, generalmente es porque el Firewall de Windows bloquea el puerto UDP 50511 de entrada por defecto. Abre un **PowerShell como Administrador** y ejecuta:
```powershell
New-NetFirewallRule -DisplayName "Nerve LAN Discovery" -Direction Inbound -Protocol UDP -LocalPort 50511 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Control" -Direction Inbound -Protocol TCP -LocalPort 50507 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Nerve LAN Data" -Direction Inbound -Protocol TCP -LocalPort 50510 -Action Allow -Profile Any
```

**Aislamiento AP (Routers Wi-Fi):**
Si tu router aísla a los clientes Wi-Fi (bloqueando paquetes broadcast), `nerve scan` fallará. Puedes evitar esto escaneando la IP exacta directamente (unicast):
```bash
nerve scan 192.168.1.50
```

### Cómo consultar las IP locales

La IP que debes usar es la IPv4 privada del adaptador conectado a la misma LAN que el otro dispositivo. No uses `127.0.0.1`, porque solo representa el propio equipo.

```powershell
# Windows
ipconfig
```

```bash
# Linux y macOS
ip addr

# Android / Termux
ip addr
# Alternativa si no está disponible:
ifconfig
```

Ejemplos válidos son `192.168.1.50`, `10.0.0.25` o `172.20.10.4`. Si solo quieres verificar el estado de la red y del host remoto:

```bash
nerve diagnose 192.168.1.50
```

Si el diagnóstico muestra una interfaz local disponible pero la conexión TCP falla, revisa el firewall, que ambos dispositivos estén en la misma subred y que el router no tenga activado el aislamiento de clientes. Si no hay una interfaz IPv4 activa, la PC fue desconectada completamente de la LAN: apagar Internet es compatible con Nerve, apagar el enlace Wi-Fi/Ethernet no lo es.

### Nota sobre los puertos configurables

El puerto de control predeterminado de `nerve host` es `50507`. Si defines otro valor con `lan_port` o `--port`, debes abrir ese mismo puerto TCP y usarlo al conectar, por ejemplo `nerve connect 192.168.1.50:4432`. El puerto de datos permanece en `50510` y el descubrimiento usa UDP `50511`.

---

##  Contribuidores

¡Queremos expresar nuestro más profundo agradecimiento a todas las personas que contribuyen a Nerve! Su trabajo, revisiones y reportes de errores hacen que este proyecto sea posible.

* **Alenia Studios** - Mantenedor Principal y Publicador

¿Quieres aparecer aquí? Revisa nuestra guía [CONTRIBUTING.md](CONTRIBUTING.md) y envía un Pull Request. Visita [CONTRIBUTORS.md](CONTRIBUTORS.md) para ver la lista completa.

Consulta [CHANGELOG.md](CHANGELOG.md) para ver el historial completo de versiones.

---

##  Licencia

[![Licencia](https://img.shields.io/badge/Licencia-GPLv3-8a2be2.svg)](LICENSE)

Este software se distribuye bajo la **Licencia Pública General de GNU v3 (GPL v3)**. Consulta [LICENSE](LICENSE) para más detalles.

---
*Elaborado con pasión por Alenia Studios para impulsar a creadores e ingenieros de software soberano.*
