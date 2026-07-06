# Alenia Nerve - Cliente de Python y CLI Hub

Esta es la biblioteca de cliente oficial de Python y la Interfaz de Línea de Comandos (CLI) para Alenia Nerve, el motor de comunicación entre procesos (IPC) local y ultrarrápido.

## El Hub CLI de Nerve

El paquete de Python incluye la herramienta de línea de comandos central (`nerve`) utilizada para iniciar y administrar el Hub de enrutamiento IPC principal.

![Consola del Hub de Nerve](../../assets/python_client.svg)

### Ejecutando el Hub

Una vez instalado, puedes iniciar el hub central desde cualquier terminal:

```bash
nerve start
```

Para ver detalles detallados del enrutamiento de paquetes en tiempo real, ejecuta el hub en modo detallado (verbose):

```bash
nerve start --verbose
```

---

## Instalación del Cliente

Instala el paquete a través de pip:

```bash
pip install alenia-nerve
```

O instálalo globalmente omitiendo las restricciones de paquetes del sistema si es necesario (por ejemplo, dentro de contenedores Docker):

```bash
pip install alenia-nerve --break-system-packages
```

---

## Ejemplo de Integración

### 1. Inicializar el Cliente
Conéctate al hub local registrando un ID de cliente único.

```python
from nerve import NexusClient

client = NexusClient()
client.connect("my_python_node")
```

### 2. Enviar mensajes
Envía una carga útil JSON a otro nodo registrado:

```python
payload = {"status": "processing", "progress": 45}
client.send("renderer_node", payload)
```

### 3. Transmisión de mensajes (Broadcast)
Transmite una carga útil a todos los demás nodos conectados actualmente al Hub:

```python
client.broadcast({"event": "reload_assets"})
```

### 4. Escuchar transmisiones
Registra una función de callback para escuchar flujos de datos en tiempo real:

```python
def handle_incoming(data):
    print(f"Received: {data}")

client.listen(handle_incoming)
```

---

## Licencia

Este software se distribuye bajo la Licencia Pública General de GNU v3 (GPL v3).
