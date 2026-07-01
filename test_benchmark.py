import time
import json
import socket
from unittest.mock import MagicMock
from src.nerve.core import NexusHub

def benchmark_heartbeat_current():
    conn = MagicMock()
    # Dummy sendall to avoid mock overhead in tight loop
    def dummy_sendall(data):
        pass
    conn.sendall = dummy_sendall
    
    start_time = time.perf_counter()
    for _ in range(1000000):
        # Current implementation
        conn.sendall((json.dumps({"type": "ping"}) + "\n").encode("utf-8"))
    
    end_time = time.perf_counter()
    return end_time - start_time

def benchmark_heartbeat_optimized():
    conn = MagicMock()
    # Dummy sendall to avoid mock overhead in tight loop
    def dummy_sendall(data):
        pass
    conn.sendall = dummy_sendall
    
    start_time = time.perf_counter()
    # Pre-computed payload
    ping_payload = b'{"type": "ping"}\n'
    
    for _ in range(1000000):
        # Optimized implementation
        conn.sendall(ping_payload)
    
    end_time = time.perf_counter()
    return end_time - start_time

if __name__ == "__main__":
    current = benchmark_heartbeat_current()
    print(f"Current approach: {current:.4f} seconds")
    
    optimized = benchmark_heartbeat_optimized()
    print(f"Optimized approach: {optimized:.4f} seconds")
    
    if optimized < current:
        improvement = (current - optimized) / current * 100
        print(f"Improvement: {improvement:.2f}% faster")
