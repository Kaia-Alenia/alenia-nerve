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

{PURPLE}Direct device communication (LAN):{RESET}
  nerve host                      Start the LAN host (foreground, blocking)
  nerve host --receive-dir PATH   Set incoming receive directory
  nerve host --port PORT          Set LAN control plane port (default: 50507)
  nerve host --max-transfers N    Override concurrent transfer limit (default: auto)
  nerve host --verbose            Enable verbose peer logging
  nerve connect <IP>              Connect to a remote Nerve host and register peer
  nerve connect <IP> --name NAME  Assign a name to the peer
  nerve connect <IP> --token TOK  Use an explicit auth token
  nerve scan                      Scan local network for Nerve peers
  nerve diagnose [IP]             Run evidence-based network diagnostics
  nerve peers                     List known peers
  nerve peers remove <NAME|ID>    Remove a known peer
  nerve send <PATH> [PATH2 PATH3] --to <IP|NAME>  Send one or more files to a peer
  nerve receive                   Start a temporary receive session
  nerve receive --dir PATH        Temporary receive session with specific dir
  nerve peer-status <IP|NAME>    Show transfer capacity of a remote peer

{PURPLE}Configuration:{RESET}
  Place a {GREEN}nerve.config{RESET} file in your working directory to customise the
  socket path or TCP port without changing any code.

{PURPLE}Examples:{RESET}
  nerve start
  nerve monitor
  nerve dashboard
  nerve host --receive-dir ~/Downloads
  nerve connect 192.168.1.10 --name mi-linux
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

    elif args[0] == "host":
        from nerve.lan.host import NerveHost

        receive_dir = None
        lan_port = None
        verbose = "--verbose" in args or "-v" in args
        max_transfers = None
        if "--receive-dir" in args:
            idx = args.index("--receive-dir")
            if len(args) > idx + 1:
                receive_dir = args[idx + 1]
            else:
                print(
                    f"{RED}[NERVE CLI] --receive-dir requires a path argument.{RESET}"
                )
                sys.exit(1)
        if "--port" in args:
            idx = args.index("--port")
            if len(args) > idx + 1:
                try:
                    lan_port = int(args[idx + 1])
                except ValueError:
                    print(f"{RED}[NERVE CLI] --port requires an integer value.{RESET}")
                    sys.exit(1)
            else:
                print(f"{RED}[NERVE CLI] --port requires a value.{RESET}")
                sys.exit(1)
        if "--max-transfers" in args:
            idx = args.index("--max-transfers")
            if len(args) > idx + 1:
                try:
                    max_transfers = int(args[idx + 1])
                    if max_transfers < 1:
                        raise ValueError
                except ValueError:
                    print(
                        f"{RED}[NERVE CLI] --max-transfers requires a positive integer.{RESET}"
                    )
                    sys.exit(1)
            else:
                print(f"{RED}[NERVE CLI] --max-transfers requires a value.{RESET}")
                sys.exit(1)
        print(BANNER)
        host = NerveHost(
            receive_dir=receive_dir,
            lan_port=lan_port,
            verbose=verbose,
            max_concurrent_transfers=max_transfers,
        )
        try:
            host.start()
        except SystemExit:
            raise
        except OSError as exc:
            print(f"{RED}[NERVE CLI] Network error: {exc}{RESET}")
            sys.exit(1)
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Critical error: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "connect":
        from nerve.lan.connect import (
            LanAuthenticationError,
            LanConnectionError,
            LanProtocolError,
            connect_and_register,
        )

        if len(args) < 2:
            print(
                f"{RED}[NERVE CLI] Usage: nerve connect <IP[:PORT]> [--name NAME] [--token TOKEN]{RESET}"
            )
            sys.exit(1)
        address = args[1]
        name = None
        token = None
        if "--name" in args:
            idx = args.index("--name")
            if len(args) > idx + 1:
                name = args[idx + 1]
        if "--token" in args:
            idx = args.index("--token")
            if len(args) > idx + 1:
                token = args[idx + 1]
        try:
            peer = connect_and_register(address=address, name=name, token=token)
            print(
                f"{GREEN}[NERVE CLI] Peer registered:{RESET}\n"
                f"  Name:     {peer.name}\n"
                f"  Hostname: {peer.hostname}\n"
                f"  Platform: {peer.platform}\n"
                f"  Address:  {peer.last_address}\n"
                f"  ID:       {peer.peer_id}"
            )
        except LanAuthenticationError as exc:
            print(f"{RED}[NERVE CLI] Authentication failed: {exc}{RESET}")
            sys.exit(1)
        except LanConnectionError as exc:
            print(f"{RED}[NERVE CLI] Connection failed: {exc}{RESET}")
            sys.exit(1)
        except LanProtocolError as exc:
            print(f"{RED}[NERVE CLI] Protocol error: {exc}{RESET}")
            sys.exit(1)
        except Exception as exc:
            print(f"{RED}[NERVE CLI] Error: {exc}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args[0] == "peers":
        from nerve.lan.peer_registry import PeerRegistry

        reg = PeerRegistry()
        sub = args[1] if len(args) > 1 else "list"

        if sub == "remove":
            if len(args) < 3:
                print(f"{RED}[NERVE CLI] Usage: nerve peers remove <NAME|ID>{RESET}")
                sys.exit(1)

            target = args[2]
            # Check for ambiguous name
            matches = reg.find_by_name(target)
            if len(matches) > 1 and target not in [p.peer_id for p in matches]:
                print(
                    f"{RED}[NERVE CLI] Error: Ambiguous peer name '{target}'. Matches {len(matches)} peers.{RESET}"
                )
                sys.exit(1)

            removed = reg.remove(target)
            if removed:
                reg.save()
                print(f"{GREEN}[NERVE CLI] Peer '{target}' removed.{RESET}")
            else:
                print(f"{RED}[NERVE CLI] Peer '{target}' not found.{RESET}")
                sys.exit(1)
        else:
            # Default: list peers
            peers = reg.list_peers()
            if not peers:
                print(f"{YELLOW}[NERVE CLI] No known peers.{RESET}")
            else:
                print(f"{PURPLE}Known Nerve peers:{RESET}\n")
                print(f"  {'NAME':<20} {'ADDRESS':<22} {'PLATFORM':<10} LAST SEEN")
                print(f"  {'-' * 68}")
                import time as _time

                for p in peers:
                    age = _time.time() - p.last_seen
                    if age < 60:
                        seen = f"{int(age)}s ago"
                    elif age < 3600:
                        seen = f"{int(age / 60)}m ago"
                    else:
                        seen = f"{int(age / 3600)}h ago"
                    print(
                        f"  {p.name:<20} {p.last_address:<22} {p.platform:<10} {seen}"
                    )
        sys.exit(0)

    elif args[0] == "send":
        from nerve.lan.api import NerveLAN

        if len(args) < 2:
            print(
                f"{RED}[NERVE CLI] Usage: nerve send <PATH> [PATH2 PATH3] --to <IP|NAME>{RESET}"
            )
            sys.exit(1)

        # Collect all paths before --to
        to = None
        paths: list[str] = []
        i = 1
        while i < len(args):
            if args[i] == "--to":
                if i + 1 < len(args):
                    to = args[i + 1]
                i += 2
            else:
                paths.append(args[i])
                i += 1

        if not paths:
            print(f"{RED}[NERVE CLI] At least one file path is required.{RESET}")
            sys.exit(1)
        if not to:
            print(f"{RED}[NERVE CLI] --to <IP|NAME> is required.{RESET}")
            sys.exit(1)
        if len(paths) > 3:
            print(
                f"{YELLOW}[NERVE CLI] Maximum 3 files per command. Sending first 3.{RESET}"
            )
            paths = paths[:3]

        def _progress(label: str):
            import time

            start_time = time.time()

            def _cb(bytes_sent: int, total: int) -> None:
                pct = (bytes_sent / total) * 100 if total > 0 else 0
                elapsed = time.time() - start_time
                speed_mb = (
                    (bytes_sent / (1024 * 1024)) / elapsed if elapsed > 0 else 0.0
                )
                print(
                    f"\r{GREEN}  {label}: {pct:.1f}% ({bytes_sent}/{total} bytes) | {speed_mb:.1f} MB/s{RESET}",
                    end="",
                    flush=True,
                )

            return _cb

        lan = NerveLAN(verbose=True)
        total = len(paths)
        ok = 0
        print(f"{PURPLE}[NERVE CLI] Sending {total} file(s) to '{to}'...{RESET}")
        for i, path in enumerate(paths, 1):
            label = f"[{i}/{total}] {path}"
            print(f"{PURPLE}  → {label}{RESET}")
            res = lan.send(path, to, progress_callback=_progress(label))
            print()  # newline after progress bar
            if res.success:
                print(f"{GREEN}  ✓ Done{RESET}")
                ok += 1
            else:
                print(f"{RED}  ✗ Failed: {res.error}{RESET}")

        print()
        if ok == total:
            print(
                f"{GREEN}[NERVE CLI] All {ok}/{total} file(s) sent successfully.{RESET}"
            )
            sys.exit(0)
        else:
            print(
                f"{YELLOW}[NERVE CLI] {ok}/{total} file(s) sent. Check errors above.{RESET}"
            )
            sys.exit(1 if ok == 0 else 0)

    elif args[0] == "receive":
        from nerve.lan.api import NerveLAN

        receive_dir = None
        if "--dir" in args:
            idx = args.index("--dir")
            if len(args) > idx + 1:
                receive_dir = args[idx + 1]
            else:
                print(f"{RED}[NERVE CLI] --dir requires a path argument.{RESET}")
                sys.exit(1)

        print(f"{PURPLE}[NERVE CLI] Starting temporary receive session...{RESET}")
        lan = NerveLAN(verbose=True)
        lan.receive(receive_dir=receive_dir)
        sys.exit(0)

    elif args[0] == "scan":
        from nerve.lan.api import NerveLAN

        print(f"{PURPLE}[NERVE CLI] Scanning local network...{RESET}")
        lan = NerveLAN()
        peers = lan.scan()
        if not peers:
            print(f"{YELLOW}[NERVE CLI] No Nerve devices found.{RESET}")
        else:
            print(f"{GREEN}Nerve devices found:\n{RESET}")
            for p in peers:
                print(f"{p.peer_name:<20} {p.address:<15} {p.platform}")
        sys.exit(0)

    elif args[0] == "diagnose":
        from nerve.lan.api import NerveLAN

        target = args[1] if len(args) > 1 else None

        print(f"\n{PURPLE}Nerve Diagnostics{RESET}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        lan = NerveLAN()
        rep = lan.diagnose(target_ip=target)

        print(f"\n{PURPLE}Local Device{RESET}")
        print(rep["local"].get("interface", ""))
        print(rep["local"].get("address", ""))

        if target:
            print(f"\n{PURPLE}Target{RESET}")
            print(rep["target"].get("format", ""))

            print(f"\n{PURPLE}Direct Connection{RESET}")
            print(rep["direct"].get("tcp", ""))

            print(f"\n{PURPLE}Nerve Service{RESET}")
            print(rep["service"].get("auth", ""))

            if rep["causes"]:
                print(f"\n{YELLOW}Possible causes{RESET}")
                for c in rep["causes"]:
                    print(c)

                print(f"\n{GREEN}Recommendation{RESET}")
                print("→ Verify that nerve host is running on the target.")
                print("→ Verify both devices are on the same non-guest network.")
                print("→ Verify firewall permissions for Nerve.")
        sys.exit(0)

    elif args[0] == "peer-status":
        from nerve.lan.api import NerveLAN

        if len(args) < 2:
            print(f"{RED}[NERVE CLI] Usage: nerve peer-status <IP|NAME>{RESET}")
            sys.exit(1)
        target = args[1]
        print(f"{PURPLE}[NERVE CLI] Querying capacity of '{target}'...{RESET}")
        lan = NerveLAN()
        result = lan.get_peer_capacity(target)
        if "error" in result:
            print(f"{RED}[NERVE CLI] Could not reach peer: {result['error']}{RESET}")
            sys.exit(1)
        current = result["current"]
        max_cap = result["max"]
        slots_free = max_cap - current
        bar = f"{current}/{max_cap}"
        status_color = GREEN if slots_free > 0 else RED
        status_label = "available" if slots_free > 0 else "BUSY (no free slots)"
        print(
            f"{PURPLE}Peer transfer capacity:{RESET}\n"
            f"  Slots in use : {status_color}{bar}{RESET}\n"
            f"  Free slots   : {status_color}{slots_free}{RESET}\n"
            f"  Status       : {status_color}{status_label}{RESET}"
        )
        sys.exit(0)

    else:
        print(f"{RED}[NERVE CLI] Unrecognized command: '{args[0]}'{RESET}")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
