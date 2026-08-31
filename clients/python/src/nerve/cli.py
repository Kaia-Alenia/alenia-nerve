# -----------------------------------------------------------------------------
# This file is part of Nerve.
#
# Nerve is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Nerve is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nerve. If not, see <https://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------
import getpass
import os
import sys

from nerve import __version__
from nerve.cli_monitor import run_dashboard, run_monitor
from nerve.core import NexusHub
from nerve.ui import is_tty

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
  nerve monitor           View real-time hub statistics in the terminal
  nerve dashboard         Start the web dashboard on http://localhost:8080
  nerve bridge            Start the HTTP/WebSocket bridge on port 50506
  nerve pack <src> <out>          Pack a file into a secure .nrv container
  nerve unpack <nrv> <out>        Unpack a .nrv container
  nerve open <file.nrv>           Open a .nrv container (handles password retries)
  nerve associate                 Register .nrv extension with the OS
  nerve unassociate               Unregister .nrv extension
  nerve genpass [--mode random|passphrase] [--length N] [--words N]
                          Generate a secure password or passphrase
  nerve --help            Show this help message
  nerve --version         Print the installed version

{PURPLE}Configuration:{RESET}
  Place a {GREEN}nerve.config{RESET} file in your working directory to customise the
  socket path or TCP port without changing any code.

{PURPLE}Examples:{RESET}
  nerve start
  nerve monitor
  nerve dashboard
  NERVE_NRV_PASSWORD="mysecret" nerve pack ./my_game my_game.nrv
  NERVE_NRV_PASSWORD="mysecret" nerve unpack my_game.nrv ./output
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

    elif args[0] == "monitor":
        run_monitor()
        sys.exit(0)

    elif args[0] == "dashboard":
        port = 8080
        if "--port" in args:
            idx = args.index("--port")
            if len(args) > idx + 1:
                port = int(args[idx + 1])
        run_dashboard(port=port)
        sys.exit(0)

    elif args[0] == "bridge":
        try:
            from nerve.bridge import run_bridge
        except ImportError:
            print(
                f"{RED}[NERVE CLI] 'websockets' not installed. Install with 'pip install websockets' to use bridge.{RESET}"
            )
            sys.exit(1)
        port = 50506
        if "--port" in args:
            idx = args.index("--port")
            if len(args) > idx + 1:
                port = int(args[idx + 1])
        run_bridge(port=port)
        sys.exit(0)

    elif args[0] == "pack":
        if len(args) < 3:
            print(f"{RED}[NERVE CLI] Usage: nerve pack <source> <output.nrv>{RESET}")
            sys.exit(1)
        source = args[1]
        output = args[2]

        password = os.environ.get("NERVE_NRV_PASSWORD")
        confirm = None
        if not password:
            print(
                f"{PURPLE}[NERVE CLI] No password provided via environment variable.{RESET}"
            )
            gen_option = (
                input(
                    f"{YELLOW}[NERVE CLI] Would you like Nerve to generate a secure password for you? (y/N): {RESET}"
                )
                .strip()
                .lower()
            )
            if gen_option == "y":
                from nerve.genpass import generate_passphrase

                passphrase, entropy = generate_passphrase(words=5)
                print(f"\n{GREEN}--- GENERATED PASSWORD ---{RESET}")
                print(f"{PURPLE}Password:{RESET} {passphrase}")
                print(f"{PURPLE}Estimated entropy:{RESET} {entropy:.2f} bits")
                print(
                    f"\n{RED}> IMPORTANT: Save this password now. It will not be shown again.{RESET}\n"
                )

                saved_confirm = (
                    input("Have you saved the password? (type 'yes' to continue): ")
                    .strip()
                    .lower()
                )
                if saved_confirm == "yes":
                    password = passphrase
                    confirm = passphrase
                else:
                    print(
                        f"{YELLOW}[NERVE CLI] Generation cancelled. Falling back to manual input.{RESET}"
                    )

            if not password:
                password = getpass.getpass(
                    f"{PURPLE}[NERVE CLI] Enter password to pack: {RESET}"
                )
                confirm = getpass.getpass(
                    f"{PURPLE}[NERVE CLI] Confirm password: {RESET}"
                )
            if password != confirm:
                print(f"{RED}[NERVE CLI] Passwords do not match.{RESET}")
                sys.exit(1)

        if not password:
            print(f"{RED}[NERVE CLI] Password cannot be empty.{RESET}")
            sys.exit(1)

        from nerve.nrv import pack_nrv

        try:
            pack_nrv(source, output, password)
            print(f"{GREEN}[NERVE CLI] Pack successful: {output}{RESET}")
        except FileNotFoundError as exc:
            print(f"{RED}[NERVE CLI] Error: File or directory not found - {exc}{RESET}")
            sys.exit(1)
        except ValueError as exc:
            print(f"{RED}[NERVE CLI] Error: Invalid operation - {exc}{RESET}")
            sys.exit(1)
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Error packing: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "unpack":
        if len(args) < 3:
            print(f"{RED}[NERVE CLI] Usage: nerve unpack <nrv_file> <out_dir>{RESET}")
            sys.exit(1)
        nrv_file = args[1]
        out_dir = args[2]

        password = os.environ.get("NERVE_NRV_PASSWORD")
        if not password:
            password = getpass.getpass(
                f"{PURPLE}[NERVE CLI] Enter password to unpack: {RESET}"
            )

        if not password:
            print(f"{RED}[NERVE CLI] Password cannot be empty.{RESET}")
            sys.exit(1)

        from nerve.nrv import unpack_nrv

        try:
            unpack_nrv(nrv_file, out_dir, password)
            print(f"{GREEN}[NERVE CLI] Unpack successful at: {out_dir}{RESET}")
        except FileNotFoundError as exc:
            print(f"{RED}[NERVE CLI] Error: File not found - {exc}{RESET}")
            sys.exit(1)
        except ValueError as exc:
            print(f"{RED}[NERVE CLI] Error: Invalid operation - {exc}{RESET}")
            sys.exit(1)
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Error unpacking: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "open":
        if len(args) < 2:
            print(f"{RED}[NERVE CLI] Usage: nerve open <file.nrv>{RESET}")
            sys.exit(1)
        nrv_file = args[1]

        from nerve.nrv import unpack_nrv
        from nerve.ui import prompt_password, show_error

        base, _ = os.path.splitext(nrv_file)
        out_dir = f"{base}_unpacked"

        attempts = 3
        while attempts > 0:
            password = os.environ.get("NERVE_NRV_PASSWORD")
            if not password:
                password = prompt_password(
                    f"Enter password to unpack {os.path.basename(nrv_file)}:"
                )

            if not password:
                # If they cancelled or entered empty password, just exit cleanly without an error popup.
                if is_tty():
                    print(f"{RED}[NERVE CLI] Password cannot be empty.{RESET}")
                sys.exit(1)

            try:
                unpack_nrv(nrv_file, out_dir, password)
                sys.exit(0)
            except ValueError as exc:
                if "Incorrect password" in str(exc):
                    attempts -= 1
                    if attempts > 0:
                        show_error(
                            f"Incorrect password. You have {attempts} attempts left."
                        )
                        if "NERVE_NRV_PASSWORD" in os.environ:
                            del os.environ["NERVE_NRV_PASSWORD"]
                    else:
                        show_error("Incorrect password. No attempts left.")
                        sys.exit(1)
                else:
                    show_error(f"Error unpacking: {exc}")
                    sys.exit(1)
            except Exception as exc:
                show_error(f"Error unpacking: {exc}")
                sys.exit(1)

    elif args[0] == "associate":
        from nerve.associate import associate

        try:
            associate()
            print(
                f"{GREEN}[NERVE CLI] Successfully associated .nrv files with Nerve.{RESET}"
            )
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Failed to associate .nrv files: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "unassociate":
        from nerve.associate import unassociate

        try:
            unassociate()
            print(
                f"{GREEN}[NERVE CLI] Successfully removed .nrv file association.{RESET}"
            )
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Failed to unassociate .nrv files: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "genpass":
        import argparse

        parser = argparse.ArgumentParser(
            prog="nerve genpass", description="Generate a secure password/passphrase"
        )
        parser.add_argument(
            "--mode",
            choices=["random", "passphrase"],
            default="passphrase",
            help="Generation mode (default: passphrase)",
        )
        parser.add_argument(
            "--length",
            type=int,
            default=20,
            help="Length for random mode (default: 20)",
        )
        parser.add_argument(
            "--words",
            type=int,
            default=5,
            help="Number of words for passphrase mode (default: 5)",
        )
        # Parse specifically sys.argv[2:] (after `nerve genpass`)
        parsed_args = parser.parse_args(args[1:])

        if parsed_args.mode == "random":
            from nerve.genpass import generate_random_password

            pwd, ent = generate_random_password(length=parsed_args.length)
            print(f"{GREEN}Password:{RESET} {pwd}")
            print(f"{YELLOW}Entropy:{RESET} {ent:.2f} bits")
        else:
            from nerve.genpass import generate_passphrase

            pwd, ent = generate_passphrase(words=parsed_args.words)
            print(f"{GREEN}Passphrase:{RESET} {pwd}")
            print(f"{YELLOW}Entropy:{RESET} {ent:.2f} bits")
        sys.exit(0)

    else:
        print(f"{RED}[NERVE CLI] Unrecognized command: '{args[0]}'{RESET}")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
