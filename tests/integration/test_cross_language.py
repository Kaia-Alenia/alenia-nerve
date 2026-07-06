import asyncio
import subprocess
import time
import json
import os
import socket
import pytest
from nerve.core import NexusClient

TEST_TIMEOUT = 15
HUB_STARTUP_RETRIES = 20
HUB_RETRY_INTERVAL = 0.25


def _wait_for_hub(socket_path: str = "/tmp/nerve.sock", retries: int = HUB_STARTUP_RETRIES) -> bool:
    """Probe the hub socket until it accepts connections or the retry limit is reached."""
    for _ in range(retries):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(socket_path)
            s.close()
            return True
        except OSError:
            time.sleep(HUB_RETRY_INTERVAL)
    return False


@pytest.fixture(scope="module")
def nerve_hub():
    """Start the Nerve Hub locally for all tests in this module."""
    hub_proc = subprocess.Popen(
        ["python3", "-m", "nerve.cli", "start"],
        stdout=None,
        stderr=None,
    )
    ready = _wait_for_hub()
    if not ready:
        hub_proc.terminate()
        hub_proc.wait()
        pytest.fail("Nerve hub did not become ready in time.")
    yield hub_proc
    hub_proc.terminate()
    hub_proc.wait()


@pytest.mark.asyncio
async def test_cross_language_latency(nerve_hub):
    """
    Start secondary clients in multiple languages, broadcast a ping from the
    Python master, and measure the round-trip latency (pong) of each one.
    """
    # 1. Configure master client in Python
    master_client = NexusClient()
    master_client.connect("master_tester")

    master_timestamp = [0.0]
    received_pongs: dict = {}

    def on_message(msg: dict):
        """
        Called for every incoming message. The hub delivers:
            {"type": "broadcast", "from": "<sender>", "payload": {...}}
        """
        if not isinstance(msg, dict):
            return
        payload = msg.get("payload")
        if not isinstance(payload, dict):
            return
        if payload.get("event") != "pong":
            return
        sender = payload.get("from") or msg.get("from")
        sent_time = payload.get("timestamp", 0.0)
        # Handle float precision across languages
        if abs(sent_time - master_timestamp[0]) > 0.1:
            return
        recv_time = time.time()
        latency_ms = (recv_time - master_timestamp[0]) * 1000
        received_pongs[sender] = latency_ms

    master_client.listen(on_message)
    # Give the listener thread a moment to start.
    time.sleep(0.3)

    # 2. Start secondary clients
    clients_dir = os.path.join(os.path.dirname(__file__), "clients")

    procs = []
    # JavaScript
    js_client_path = os.path.join(clients_dir, "ping_pong.js")
    if os.path.exists(js_client_path):
        p = subprocess.Popen(["node", "ping_pong.js"], cwd=clients_dir)
        procs.append(("js_client", p))

    # Go — build first, then run
    go_client_path = os.path.join(clients_dir, "ping_pong.go")
    if os.path.exists(go_client_path):
        subprocess.run(
            ["go", "build", "-o", "ping_pong_go", "ping_pong.go"],
            cwd=clients_dir,
            check=True,
        )
        p = subprocess.Popen(["./ping_pong_go"], cwd=clients_dir)
        procs.append(("go_client", p))

    # Python
    py_client_path = os.path.join(clients_dir, "ping_pong.py")
    if os.path.exists(py_client_path):
        p = subprocess.Popen(["python3", "ping_pong.py"], cwd=clients_dir)
        procs.append(("py_client", p))

    # Rust — build first, then run with the correct config path
    rust_client_path = os.path.join(clients_dir, "rust_client")
    if os.path.exists(rust_client_path):
        subprocess.run(["cargo", "build", "-q"], cwd=rust_client_path, check=True)
        binary_path = os.path.join(rust_client_path, "target", "debug", "rust_client")
        project_root = os.path.abspath(os.path.join(clients_dir, "../../../"))
        nerve_config = os.path.join(project_root, "nerve.config")
        env = os.environ.copy()
        env["NERVE_CONFIG"] = nerve_config
        p = subprocess.Popen([binary_path], cwd=rust_client_path, env=env)
        procs.append(("rs_client", p))

    try:
        # Allow all secondary clients time to connect and register.
        time.sleep(3)

        # 3. Send ping — timestamp in seconds (float) for precise latency math.
        master_timestamp[0] = time.time()
        master_client.broadcast({
            "event": "ping",
            "timestamp": master_timestamp[0],
        })

        # 4. Wait for pongs from all clients
        expected = len(procs)
        start_wait = time.time()
        while len(received_pongs) < expected and (time.time() - start_wait) < TEST_TIMEOUT:
            await asyncio.sleep(0.1)

        # 5. Evaluate
        missing = [name for name, _ in procs if name not in received_pongs]
        assert len(received_pongs) == expected, (
            f"Missing pongs from: {missing}. "
            f"Received {len(received_pongs)}/{expected}."
        )

        print("\n--- Latency Report ---")
        latencies = list(received_pongs.values())
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        report = {
            "clients": received_pongs,
            "metrics": {
                "avg_ms": round(avg_latency, 3),
                "max_ms": round(max_latency, 3),
                "p99_ms": round(max_latency, 3),
            },
        }
        print(json.dumps(report, indent=2))

        # Average latency must be under 50ms (CI) / ideally <1ms locally.
        assert avg_latency < 50.0, f"Latency too high: {avg_latency:.3f}ms"

    finally:
        for _name, p in procs:
            p.terminate()
            p.wait()
        master_client.disconnect()
