import sys
from nerve import __version__
from nerve.core import NexusHub

PURPLE = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

ASCII_ART = r"""
 _   _  _____ ______ _   _ _____ 
| \ | ||  ___|| ___ \ | | |  ___|
|  \| || |__  | |_/ / | | | |__ 
| . ` ||  __| |    /| | | |  __|
| |\  || |___ | |\ \ \_/ /| |___
\_| \_/\____/ \_| \_|\___/\____/"""

BANNER = f"{PURPLE}{ASCII_ART}\n   Local Communication Engine v{__version__}{RESET}\n"

HELP_TEXT = f"""\
=== {PURPLE}NERVE CLI{RESET} ===
Local IPC Engine by Alenia Studios — v{__version__}
Contact: contact.aleniastudios@gmail.com

{PURPLE}Usage:{RESET}
  nerve start             Start the Nerve Hub (blocking)
  nerve start --verbose   Start with detailed message routing logs
  nerve start -v          Shorthand for --verbose
  nerve --help            Show this help message
  nerve -h                Shorthand for --help
  nerve --version         Print the installed version

{PURPLE}Configuration:{RESET}
  Place a {GREEN}nerve.config{RESET} file in your working directory to customise the
  socket path or TCP port without changing any code.

  JSON format:
    {{
      "socket_path": "/tmp/nerve.sock",
      "port": 50505,
      "host": "127.0.0.1"
    }}

  Key=value format:
    socket_path=/tmp/nerve.sock
    port=50505

{PURPLE}Examples:{RESET}
  nerve start
  nerve start --verbose
"""


def print_help() -> None:
    print(BANNER)
    print(HELP_TEXT)


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "help"):
        print_help()
        sys.exit(0)

    if args[0] in ("--version", "-V"):
        print(f"alenia-nerve {__version__}")
        sys.exit(0)

    if args[0] == "start":
        verbose = "--verbose" in args or "-v" in args
        print(BANNER)
        print(f"{PURPLE}[NERVE CLI] Initializing Nerve Hub...{RESET}")
        if verbose:
            print(f"{YELLOW}[NERVE CLI] Verbose logging activated.{RESET}")

        hub = NexusHub(verbose=verbose)
        try:
            hub.start()
        except KeyboardInterrupt:
            hub.stop()
            print(f"\n{PURPLE}[NERVE CLI] Stopped by user.{RESET}")
            sys.exit(0)
        except OSError as exc:
            print(f"{RED}[NERVE CLI] Socket error: {exc}{RESET}")
            sys.exit(1)
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Critical error: {exc}{RESET}")
            sys.exit(1)

    else:
        print(f"{RED}[NERVE CLI] Unrecognized command: '{args[0]}'{RESET}")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
