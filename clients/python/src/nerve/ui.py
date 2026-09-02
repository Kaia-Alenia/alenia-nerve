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
import platform
import subprocess
import sys

_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_RESET = "\033[0m"


def _colored(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def print_warning(message: str) -> None:
    print(_colored(f"[WARN] {message}", _YELLOW))


def print_info(message: str) -> None:
    print(_colored(f"[INFO] {message}", _CYAN))


def print_success(message: str) -> None:
    print(_colored(f"[ OK ] {message}", _GREEN))


def is_tty() -> bool:
    return sys.stdin.isatty()


def print_warning(message: str) -> None:
    if is_tty():
        print(f"\033[93m[WARNING] {message}\033[0m", file=sys.stderr)
    else:
        print(f"[WARNING] {message}", file=sys.stderr)


def print_info(message: str) -> None:
    print(message)


def show_error(message: str) -> None:
    if is_tty():
        print(f"[ERROR] {message}", file=sys.stderr)
        return

    system = platform.system()
    if system == "Darwin":
        try:
            escaped_msg = message.replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'display alert "{escaped_msg}" as critical'],
                check=False,
            )
        except Exception:
            pass
    elif system == "Windows":
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showerror("Error", message, parent=root)
            root.destroy()
        except ImportError:
            pass
    elif system == "Linux":
        try:
            result = subprocess.run(
                ["zenity", "--error", "--text", message, "--title", "Error"],
                check=False,
            )
            if result.returncode in (0, 1, 5):
                return
        except FileNotFoundError:
            pass

        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showerror("Error", message, parent=root)
            root.destroy()
        except ImportError:
            pass


def prompt_password(prompt: str, error: str | None = None) -> str:
    if error:
        show_error(error)

    if is_tty():
        return getpass.getpass(prompt)

    system = platform.system()
    if system == "Darwin":
        try:
            escaped_prompt = prompt.replace('"', '\\"')
            script = f'set T to text returned of (display dialog "{escaped_prompt}" with hidden answer default answer "")'
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, check=True
            )
            return result.stdout.strip("\n\r")
        except Exception:
            return ""
    elif system == "Windows":
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            password = simpledialog.askstring("Nerve", prompt, parent=root, show="*")
            root.destroy()
            return password or ""
        except ImportError:
            return ""
    elif system == "Linux":
        try:
            result = subprocess.run(
                ["zenity", "--password", "--title", "Nerve"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip("\n\r")
            elif result.returncode in (1, 5):
                return ""
        except FileNotFoundError:
            try:
                import tkinter as tk
                from tkinter import simpledialog

                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                password = simpledialog.askstring(
                    "Nerve", prompt, parent=root, show="*"
                )
                root.destroy()
                return password or ""
            except ImportError:
                return ""

    return ""
