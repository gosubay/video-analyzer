#!/usr/bin/env python3
"""
Video Analyzer - the app window.

Starts the local server (server.py) and opens a real desktop window pointed at
it. The window is Edge WebView2, which every Windows 11 machine already has, so
there is no browser tab and no address bar - it looks and behaves like an app.

Run:  pythonw app.py      (no console window)
      python  app.py      (console window, useful while developing)

Anything that goes wrong is written to debug.log next to this file.
"""

import ctypes
import datetime as _dt
import sys
import threading
import traceback
from pathlib import Path

def _app_dir():
    """The .exe's folder once packaged, this folder when run from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


def _resource_dir():
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else Path(__file__).parent.resolve()


ROOT = _app_dir()
LOG = ROOT / "debug.log"

WINDOW_TITLE = "Video Analyzer"
START_WIDTH, START_HEIGHT = 1180, 820
MIN_WIDTH, MIN_HEIGHT = 900, 640


def log(message):
    """Append a line to debug.log. Never allowed to blow up the app."""
    try:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def fatal(message, detail=""):
    """Tell the user in a message box, log it, and stop."""
    log(f"FATAL: {message}\n{detail}")
    try:
        ctypes.windll.user32.MessageBoxW(
            None, f"{message}\n\nDetails were written to:\n{LOG}", WINDOW_TITLE, 0x10
        )
    except Exception:
        print(message, file=sys.stderr)
    sys.exit(1)


def set_window_icon():
    """
    Put our icon on the window and in the taskbar.

    Cosmetic only - every step is guarded, and the argument/return types are
    declared explicitly. Leaving them to ctypes' 32-bit default truncates the
    64-bit handles, which is how a nearly identical block crashed this app once
    already. If anything here looks off, delete the call rather than guessing.
    """
    icon_path = _resource_dir() / "assets" / "icon.ico"
    if not icon_path.is_file():
        return
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.SendMessageW.restype = wintypes.LPARAM

        IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x0010, 0x0080
        ICON_SMALL, ICON_BIG = 0, 1

        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return
        for size, which in ((16, ICON_SMALL), (32, ICON_BIG)):
            handle = user32.LoadImageW(
                None, str(icon_path), IMAGE_ICON, size, size, LR_LOADFROMFILE
            )
            if handle:
                user32.SendMessageW(hwnd, WM_SETICON, which, handle)
        log("window icon set")
    except Exception as exc:
        log(f"could not set the window icon (harmless): {exc}")


def taskbar_identity():
    """Group the window under its own taskbar button instead of Python's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "gosubay.VideoAnalyzer.1"
        )
    except Exception:
        pass


def webview2_missing():
    """
    True when the Edge WebView2 runtime is absent.

    It ships with Windows 11 and with any recent Edge, so this almost never
    fires - but if it does, the window would fail to open with no explanation
    at all, which is the one thing a non-technical user cannot recover from.
    """
    import winreg

    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, path in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + key[len("SOFTWARE"):]),
        (winreg.HKEY_LOCAL_MACHINE, key),
        (winreg.HKEY_CURRENT_USER, key),
    ):
        try:
            with winreg.OpenKey(root, path) as handle:
                version, _ = winreg.QueryValueEx(handle, "pv")
                if version and version != "0.0.0.0":
                    return False
        except OSError:
            continue
    return True


def main():
    taskbar_identity()

    try:
        if webview2_missing():
            fatal(
                "This app needs the Microsoft Edge WebView2 runtime, which is "
                "not on this computer.\n\n"
                "It is a free Microsoft download. Get the "
                '"Evergreen Standalone Installer" from:\n'
                "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
                "Install it, then open Video Analyzer again."
            )
    except Exception as exc:            # a broken registry must not block startup
        log(f"could not check for WebView2 (continuing anyway): {exc}")

    try:
        import webview
    except ImportError:
        fatal(
            "A piece of the app is missing (pywebview).\n\n"
            "Open a terminal in this folder and run:\n    pip install pywebview"
        )

    try:
        import server
    except Exception:
        fatal("The app could not start.", traceback.format_exc())

    try:
        _httpd, url = server.start()
    except Exception:
        fatal("The app could not open its own window.", traceback.format_exc())

    log(f"server up at {url}")

    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=START_WIDTH,
        height=START_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        background_color="#FDF9F3",
        text_select=False,
    )

    def pick_file():
        """Wired into the server so the 'choose a video file' button works."""
        try:
            types = ("Video files (*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v)", "All files (*.*)")
            chosen = window.create_file_dialog(webview.OPEN_DIALOG, file_types=types)
            return chosen[0] if chosen else ""
        except Exception as exc:
            log(f"file picker failed: {exc}")
            return ""

    server.FILE_PICKER = pick_file

    # The window does not exist until webview.start() has run, so wait a moment
    # before reaching for it.
    threading.Timer(1.4, set_window_icon).start()

    log("opening window")
    try:
        webview.start(debug=False)
    except Exception:
        fatal("The app window closed unexpectedly.", traceback.format_exc())
    log("window closed")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        fatal("Something went wrong while starting up.", traceback.format_exc())
