import time
import threading
from nerve import NexusClient

def run_receiver():
    receiver = NexusClient()
    try:
        receiver.connect("receiver_node")
        
        def on_message_received(payload):
            print(f"[RECEIVER] Received message: {payload}")

        receiver.listen(on_message_received)
        print("[RECEIVER] Connected and listening for messages...")
        time.sleep(5)
    except Exception as e:
        print(f"[RECEIVER] Error: {e}")

def run_sender():
    time.sleep(1)
    sender = NexusClient()
    try:
        sender.connect("sender_node")
        print("[SENDER] Connected to Nerve Hub. Sending test messages...")
        
        for i in range(1, 4):
            payload = {"msg_id": i, "content": f"Hello from Nerve! Packet #{i}"}
            print(f"[SENDER] Sending packet #{i} to receiver_node...")
            sender.send("receiver_node", payload)
            time.sleep(1)
            
    except Exception as e:
        print(f"[SENDER] Error: {e}")

if __name__ == "__main__":
    print("=== NERVE: BASIC USAGE EXAMPLE ===")
    print("Make sure Nerve Hub is running ('nerve start') before running this script.\n")
    
    receiver_thread = threading.Thread(target=run_receiver)
    sender_thread = threading.Thread(target=run_sender)
    
    receiver_thread.start()
    sender_thread.start()
    
    receiver_thread.join()
    sender_thread.join()
    
    print("\n=== Demo finished successfully! ===")
