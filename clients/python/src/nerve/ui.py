import getpass
import platform
import subprocess
import sys


def is_tty() -> bool:
    return sys.stdin.isatty()


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
        except Exception:  # noqa: BLE001, S110
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
        except Exception:  # noqa: BLE001
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
                check=True,
            )
            return result.stdout.strip("\n\r")
        except (FileNotFoundError, subprocess.CalledProcessError):
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
