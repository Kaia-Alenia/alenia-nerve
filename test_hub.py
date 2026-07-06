import subprocess
import time
config_content = "host=127.0.0.1\nport=5055\n"
with open("nerve.config", "w") as f:
    f.write(config_content)
hub_proc = subprocess.Popen(["python3", "-m", "nerve.cli", "start"])
time.sleep(2)
print("Hub started. Is it running?", hub_proc.poll() is None)
hub_proc.terminate()
