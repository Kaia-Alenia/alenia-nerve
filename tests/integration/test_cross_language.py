import asyncio
import subprocess
import time
import json
import os
import socket
import pytest
from nerve.core import NexusClient

TEST_TIMEOUT = 10

@pytest.fixture(scope="module")
def nerve_hub():
    """Levanta el Hub de Nerve de forma local para todas las pruebas."""
    hub_proc = subprocess.Popen(
        ["python3", "-m", "nerve.cli", "start"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1) # Esperar a que el hub esté listo
    yield hub_proc
    hub_proc.terminate()
    hub_proc.wait()

@pytest.mark.asyncio
async def test_cross_language_latency(nerve_hub):
    """
    Inicia clientes en múltiples lenguajes, realiza un broadcast de ping y 
    mide el tiempo de respuesta (pong) de cada uno para calcular latencia.
    """
    # 1. Configurar cliente maestro en Python
    master_client = NexusClient()
    master_client.connect("master_tester")
    
    received_pongs = {}
    
    def on_pong(payload):
        if isinstance(payload, dict) and payload.get("event") == "pong":
            client = payload.get("from")
            sent_time = payload.get("timestamp")
            recv_time = time.time()
            latency_ms = (recv_time - sent_time) * 1000
            received_pongs[client] = latency_ms

    master_client.listen(on_pong)
    time.sleep(0.5)
    
    # 2. Iniciar clientes secundarios
    clients_dir = os.path.join(os.path.dirname(__file__), "clients")
    
    procs = []
    # JS
    js_client_path = os.path.join(clients_dir, "ping_pong.js")
    if os.path.exists(js_client_path):
        p = subprocess.Popen(["node", "ping_pong.js"], cwd=clients_dir)
        procs.append(p)
    # Go
    go_client_path = os.path.join(clients_dir, "ping_pong.go")
    if os.path.exists(go_client_path):
        p = subprocess.Popen(["go", "run", "ping_pong.go"], cwd=clients_dir)
        procs.append(p)
        
    # Dar tiempo a que se conecten
    time.sleep(2)
    
    # 3. Enviar ping
    timestamp = time.time()
    master_client.broadcast({"event": "ping", "timestamp": timestamp})
    
    # 4. Esperar pongs
    start_wait = time.time()
    while len(received_pongs) < len(procs) and (time.time() - start_wait) < TEST_TIMEOUT:
        await asyncio.sleep(0.1)
        
    # Cleanup
    for p in procs:
        p.terminate()
        p.wait()
    master_client.disconnect()
    
    # Evaluar
    assert len(received_pongs) > 0, "No se recibieron pongs de ningún cliente"
    
    print("\n--- Latency Report ---")
    latencies = list(received_pongs.values())
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    
    report = {
        "clients": received_pongs,
        "metrics": {
            "avg_ms": round(avg_latency, 3),
            "max_ms": round(max_latency, 3),
            "p99_ms": round(max_latency, 3) 
        }
    }
    print(json.dumps(report, indent=2))
    
    # Verificar que la latencia media sea aceptable (< 50ms en CI, ideal <1ms local)
    assert avg_latency < 50.0, f"Latencia demasiado alta: {avg_latency}ms"
