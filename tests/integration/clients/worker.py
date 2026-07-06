import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../clients/python/src')))
from nerve.core import NexusClient

client = NexusClient()
client.connect("python_worker")

def handle_incoming(msg):
    # msg is the full message: {"type": ..., "from": ..., "payload": {...}}
    data = msg.get("payload") if isinstance(msg, dict) else None
    if not isinstance(data, dict):
        return
    if data.get("type") != "process_task":
        return

    task_id = data.get("task_id")
    file_payload = data.get("payload")
    ops = data.get("operations")

    print(f"\n[Python Worker] Recibi peticion (ID: {task_id}).")
    print(f"  -> Archivo: {file_payload}")
    print(f"  -> Operaciones solicitadas: {ops}")
    print(f"  -> Simulando inferencia de IA/Carga pesada...")

    # Simulate heavy processing (e.g. an AI model processing an image)
    time.sleep(2)

    print(f"[Python Worker] Inferencia completada. Devolviendo resultado.")

    # Send response back to the gateway
    response = {
        "type": "task_result",
        "task_id": task_id,
        "result": {
            "status": "success",
            "output_file": f"processed_{file_payload}",
            "confidence": 0.98,
        },
    }
    client.send("api_gateway", response)

client.listen(handle_incoming)
print("[Python Worker] Local AI engine ready and waiting for frontend tasks...")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n[Python Worker] Apagando motor...")
finally:
    client.disconnect()
