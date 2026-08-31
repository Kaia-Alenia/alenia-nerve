import importlib.resources
import logging
import os
import platform
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)


def get_python_exe() -> str:
    """Gets the path to the python executable."""
    return sys.executable


def associate() -> bool:
    system = platform.system()
    if system == "Windows":
        return _associate_windows()
    elif system == "Darwin":
        return _associate_macos()
    elif system == "Linux":
        return _associate_linux()
    else:
        logger.error(f"Unsupported platform: {system}")
        return False


def unassociate() -> bool:
    system = platform.system()
    if system == "Windows":
        return _unassociate_windows()
    elif system == "Darwin":
        return _unassociate_macos()
    elif system == "Linux":
        return _unassociate_linux()
    else:
        logger.error(f"Unsupported platform: {system}")
        return False


def _associate_windows() -> bool:
    try:
        import ctypes
        import winreg

        # Paths
        ico_path = str(
            importlib.resources.files("nerve.icons").joinpath("nrv-icon.ico")
        )
        python_exe = get_python_exe()
        command = f'"{python_exe}" -m nerve.cli open "%1"'

        # Register .nrv
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\.nrv"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "NerveFile")

        # Register NerveFile
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\NerveFile"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "Nerve Secure Container")

        # DefaultIcon
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\NerveFile\DefaultIcon"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f'"{ico_path}"')

        # Command
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\NerveFile\shell\open\command"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, command)

        # SHChangeNotify to refresh icons
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception as e:
            logger.warning(f"Could not refresh icons: {e}")

        return True
    except Exception as e:
        logger.error(f"Windows association failed: {e}")
        return False


def _unassociate_windows() -> bool:
    try:
        import ctypes
        import winreg

        def delete_key_recursively(root, subkey):
            try:
                with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
                    info = winreg.QueryInfoKey(key)
                    for i in range(info[0]):
                        sub = winreg.EnumKey(key, 0)
                        delete_key_recursively(key, sub)
                winreg.DeleteKey(root, subkey)
            except OSError:
                pass

        delete_key_recursively(winreg.HKEY_CURRENT_USER, r"Software\Classes\.nrv")
        delete_key_recursively(winreg.HKEY_CURRENT_USER, r"Software\Classes\NerveFile")

        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"Windows unassociation failed: {e}")
        return False


def _associate_macos() -> bool:
    try:
        home = os.path.expanduser("~")
        app_dir = os.path.join(home, "Applications", "Nerve.app")
        contents_dir = os.path.join(app_dir, "Contents")
        macos_dir = os.path.join(contents_dir, "MacOS")
        resources_dir = os.path.join(contents_dir, "Resources")

        os.makedirs(macos_dir, exist_ok=True)
        os.makedirs(resources_dir, exist_ok=True)

        # Copy icon
        icns_src = importlib.resources.files("nerve.icons").joinpath("nrv-icon.icns")
        icns_dest = os.path.join(resources_dir, "nrv-icon.icns")
        if hasattr(icns_src, "read_bytes"):
            with open(icns_dest, "wb") as f:
                f.write(icns_src.read_bytes())

        # Create executable wrapper
        python_exe = get_python_exe()
        wrapper_path = os.path.join(macos_dir, "Nerve")
        wrapper_content = f"""#!/bin/bash
if [ "$#" -eq 0 ]; then
    exit 0
fi
if [[ "$1" == -psn* ]]; then
    exit 0
fi
"{python_exe}" -m nerve.cli open "$1"
"""
        with open(wrapper_path, "w", encoding="utf-8") as f:
            f.write(wrapper_content)
        os.chmod(wrapper_path, 0o755)

        # Write Info.plist
        plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Nerve</string>
    <key>CFBundleDisplayName</key>
    <string>Nerve</string>
    <key>CFBundleIdentifier</key>
    <string>com.aleniastudios.nrv</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>Nerve</string>
    <key>CFBundleIconFile</key>
    <string>nrv-icon.icns</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.10</string>
    <key>LSUIElement</key>
    <true/>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array>
                <string>nrv</string>
            </array>
            <key>CFBundleTypeIconFile</key>
            <string>nrv-icon.icns</string>
            <key>CFBundleTypeName</key>
            <string>Nerve Secure Container</string>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
            <key>LSHandlerRank</key>
            <string>Owner</string>
        </dict>
    </array>
</dict>
</plist>
"""
        with open(os.path.join(contents_dir, "Info.plist"), "w", encoding="utf-8") as f:
            f.write(plist_content)

        # Remove quarantine (Gatekeeper)
        try:
            subprocess.run(
                ["xattr", "-d", "com.apple.quarantine", app_dir],
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

        # Register with Launch Services
        lsregister = "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
        if os.path.exists(lsregister):
            subprocess.run([lsregister, "-f", app_dir], check=False)

        return True
    except Exception as e:
        logger.error(f"macOS association failed: {e}")
        return False


def _unassociate_macos() -> bool:
    try:
        home = os.path.expanduser("~")
        app_dir = os.path.join(home, "Applications", "Nerve.app")

        lsregister = "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
        if os.path.exists(lsregister) and os.path.exists(app_dir):
            subprocess.run([lsregister, "-u", app_dir], check=False)

        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)

        return True
    except Exception as e:
        logger.error(f"macOS unassociation failed: {e}")
        return False


def _associate_linux() -> bool:
    try:
        home = os.path.expanduser("~")

        # Create MIME type
        mime_dir = os.path.join(home, ".local", "share", "mime", "packages")
        os.makedirs(mime_dir, exist_ok=True)

        mime_xml = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
    <mime-type type="application/x-nerve">
        <comment>Nerve Secure Container</comment>
        <glob pattern="*.nrv"/>
        <icon name="application-x-nerve"/>
    </mime-type>
</mime-info>
"""
        with open(os.path.join(mime_dir, "nerve.xml"), "w", encoding="utf-8") as f:
            f.write(mime_xml)

        # Copy icons
        icons_pkg_dir = importlib.resources.files("nerve.icons")
        sizes = [16, 32, 64, 128, 256]
        for size in sizes:
            icon_dir = os.path.join(
                home,
                ".local",
                "share",
                "icons",
                "hicolor",
                f"{size}x{size}",
                "mimetypes",
            )
            os.makedirs(icon_dir, exist_ok=True)

            src_png = icons_pkg_dir.joinpath(f"nrv-icon-{size}x{size}.png")
            dest_png = os.path.join(icon_dir, "application-x-nerve.png")

            if hasattr(src_png, "read_bytes"):
                with open(dest_png, "wb") as f:
                    f.write(src_png.read_bytes())

        # Create .desktop file
        apps_dir = os.path.join(home, ".local", "share", "applications")
        os.makedirs(apps_dir, exist_ok=True)

        python_exe = get_python_exe()
        desktop_content = f"""[Desktop Entry]
Name=Nerve
Exec="{python_exe}" -m nerve.cli open %f
Icon=application-x-nerve
Terminal=false
Type=Application
MimeType=application/x-nerve;
NoDisplay=true
"""
        with open(os.path.join(apps_dir, "nerve.desktop"), "w", encoding="utf-8") as f:
            f.write(desktop_content)

        # Update caches
        try:
            subprocess.run(
                ["update-mime-database", os.path.join(home, ".local", "share", "mime")],
                check=False,
            )
        except Exception:
            pass

        try:
            subprocess.run(
                [
                    "gtk-update-icon-cache",
                    "-f",
                    "-t",
                    os.path.join(home, ".local", "share", "icons", "hicolor"),
                ],
                check=False,
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["xdg-mime", "default", "nerve.desktop", "application/x-nerve"],
                check=False,
            )
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"Linux association failed: {e}")
        return False


def _unassociate_linux() -> bool:
    try:
        home = os.path.expanduser("~")

        # Remove MIME type
        mime_file = os.path.join(
            home, ".local", "share", "mime", "packages", "nerve.xml"
        )
        if os.path.exists(mime_file):
            os.remove(mime_file)

        # Remove icons
        sizes = [16, 32, 64, 128, 256]
        for size in sizes:
            icon_file = os.path.join(
                home,
                ".local",
                "share",
                "icons",
                "hicolor",
                f"{size}x{size}",
                "mimetypes",
                "application-x-nerve.png",
            )
            if os.path.exists(icon_file):
                os.remove(icon_file)

        # Remove .desktop file
        desktop_file = os.path.join(
            home, ".local", "share", "applications", "nerve.desktop"
        )
        if os.path.exists(desktop_file):
            os.remove(desktop_file)

        # Update caches
        try:
            subprocess.run(
                ["update-mime-database", os.path.join(home, ".local", "share", "mime")],
                check=False,
            )
        except Exception:
            pass

        try:
            subprocess.run(
                [
                    "gtk-update-icon-cache",
                    "-f",
                    "-t",
                    os.path.join(home, ".local", "share", "icons", "hicolor"),
                ],
                check=False,
            )
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"Linux unassociation failed: {e}")
        return False
