import sys
from nerve.core import NexusHub

PURPLE = "\033[95m"
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

ASCII_ART = r"""
 _   _  _____ ______ _   _ _____ 
| \ | ||  ___|| ___ \ | | |  ___|
|  \| || |__  | |_/ / | | | |__  
| . ` ||  __| |    /| | | |  __| 
| |\  || |___ | |\ \ \_/ /| |___ 
\_| \_/\____/ \_| \_|\___/\____/ 
   Local Communication Engine v1.2.0"""

BANNER = f"{PURPLE}{ASCII_ART}{RESET}\n"

def print_help():
    print(BANNER)
    print(f"""=== {PURPLE}NERVE CLI{RESET} ===
Local Communication Engine by Alenia Studios

Usage:
  nerve start [--verbose]  Starts the Nerve Hub server (optional verbose mode)
  nerve --help             Displays this help message
""")

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    command = sys.argv[1]
    
    if command == "start":
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        
        print(BANNER)
        print(f"{PURPLE}[NERVE CLI] Initializing Nerve Hub...{RESET}")
        if verbose:
            print(f"{PURPLE}[NERVE CLI] Verbose logging mode activated.{RESET}")
            
        hub = NexusHub(verbose=verbose)
        try:
            hub.start()
        except KeyboardInterrupt:
            print(f"\n{PURPLE}[NERVE CLI] Server stopped by user.{RESET}")
            sys.exit(0)
        except Exception as e:
            print(f"{RED}[NERVE CLI] Critical system error: {e}{RESET}")
            sys.exit(1)
    elif command in ("--help", "-h", "help"):
        print_help()
        sys.exit(0)
    else:
        print(f"{RED}[NERVE CLI] Unrecognized command: '{command}'{RESET}")
        print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
