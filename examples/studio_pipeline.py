import time
import threading
from nerve import NexusClient

def run_giftly_renderer():
    giftly = NexusClient()
    try:
        giftly.connect("Giftly_Engine")
        
        def auto_render_gif(data):
            path = data['folder_path']
            frames = data['frame_count']
            w, h = data['dimensions']['w'], data['dimensions']['h']
            
            print("\n[Giftly] >>> Received signal from FrameGrid!")
            print(f"[Giftly] Loading {frames} frames from: {path}")
            print(f"[Giftly] Configuring Render Settings: {w}x{h}px | 12 FPS | Scale 2x")
            
            for percent in [10, 50, 90, 100]:
                time.sleep(0.3)
                bar = "█" * (percent // 10) + "░" * (10 - (percent // 10))
                print(f"[Giftly] Rendering GIF... [{bar}] {percent}%")
            print("[Giftly] Success! 'knight_attack.gif' has been successfully rendered and saved! 🌌")

        giftly.listen(auto_render_gif)
        print("[Giftly] Engine initialized. Awaiting rendering triggers from the pipeline...")
        time.sleep(6)
    except Exception as e:
        print(f"[Giftly] Error: {e}")

def run_framegrid_engine():
    time.sleep(1.5)
    framegrid = NexusClient()
    try:
        framegrid.connect("FrameGrid_Engine")
        print("\n[FrameGrid] Slicing spritesheet: 'knight_attack.png'...")
        time.sleep(2)
        
        job_data = {
            "tool_origin": "FrameGrid",
            "folder_path": "/home/user/assets/knight_attack/",
            "frame_count": 8,
            "dimensions": {"w": 64, "h": 64},
            "status": "READY_FOR_RENDER"
        }
        
        print("[FrameGrid] Slicing complete! Broadcasting job parameters to Giftly...")
        framegrid.send("Giftly_Engine", job_data)
        
    except Exception as e:
        print(f"[FrameGrid] Error: {e}")

if __name__ == "__main__":
    print("=== ALENIA STUDIOS: SOVEREIGN PIPELINE PROTOCOL ===")
    print("Demonstrating Nerve Inter-Process Sync for Indie Game Dev Pipelines.\n")
    
    giftly_thread = threading.Thread(target=run_giftly_renderer)
    framegrid_thread = threading.Thread(target=run_framegrid_engine)
    
    giftly_thread.start()
    framegrid_thread.start()
    
    giftly_thread.join()
    framegrid_thread.join()
    
    print("\n=== Studio Pipeline Run Complete ===")
