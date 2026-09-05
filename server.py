#!/usr/bin/env python3
"""
Video Analyzer - the local server behind the app window.

Serves the UI (ui/), serves the extracted frames so the app can show thumbnails,
and exposes a small JSON API that the page talks to. Nothing here is reachable
from outside this computer: it binds to 127.0.0.1 only.
"""

import json
import mimetypes
import os
import re
import subprocess
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import core

# Read-only files we ship come out of the bundle; everything the user should be
# able to find sits next to the .exe. In a source checkout these are the same
# folder, which is why this only matters once packaged.
RESOURCES = core.resource_dir().resolve()
ROOT = core.app_dir().resolve()
UI_DIR = RESOURCES / "ui"
ASSET_DIR = RESOURCES / "assets"
OUT_ROOT = ROOT / "frames"

# app.py sets this so the "Choose a video file" button can open a real Windows
# file dialog. Left as None when the UI is opened in a plain browser.
FILE_PICKER = None


# ---------------------------------------------------------------- clipboard
# PowerShell rather than the Win32 clipboard API on purpose. The ctypes version
# of this crashed the whole app: GetClipboardData returns a 64-bit handle, ctypes
# defaults its return type to a 32-bit int, and the truncated handle segfaulted
# Python the moment it was locked. A subprocess costs a few hundred milliseconds
# once at startup, which nobody notices, and it cannot take the app down.
_PS = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]

# Keeps a console window from flashing up behind the app on every call. This
# used to live only in core.py, so the two functions below raised NameError,
# the blanket `except` swallowed it, and the clipboard silently did nothing.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _clipboard_read():
    try:
        result = subprocess.run(
            _PS + ["Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=6, creationflags=_NO_WINDOW,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _clipboard_write(text):
    try:
        result = subprocess.run(
            _PS + ["$input | Set-Clipboard"],
            input=str(text), capture_output=True, text=True,
            timeout=6, creationflags=_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- app state
class AppState:
    """Everything the UI needs to draw itself, guarded by one lock."""

    def __init__(self):
        self.lock = threading.RLock()
        self.job = None
        self.worker = None
        self.reset()

    def reset(self):
        with self.lock:
            self.phase = "idle"          # idle | working | done | error | cancelled
            self.queue = []
            self.current = -1
            self.stage = None            # download | extract | transcribe | saving
            self.percent = 0.0
            self.frames_done = 0
            self.frames_total = 0
            self.message = ""
            self.transcript = False
            self.results = []
            self.error = None

    def snapshot(self):
        with self.lock:
            return {
                "phase": self.phase,
                "queue": list(self.queue),
                "current": self.current,
                "stage": self.stage,
                "percent": round(self.percent, 1),
                "frames_done": self.frames_done,
                "frames_total": self.frames_total,
                "message": self.message,
                "transcript": self.transcript,
                "results": list(self.results),
                "error": self.error,
                "busy": self.phase == "working",
            }


STATE = AppState()


def frame_url(folder_name, filename):
    quote = urllib.parse.quote
    return f"/frames/{quote(folder_name)}/{quote(filename)}"


def _run_queue(items, interval, keep_video, transcript):
    """Worker thread: process every queued item in order."""
    job = STATE.job

    for position, item in enumerate(items):
        if job.cancelled:
            break

        mode = item.get("mode") or "frames"

        with STATE.lock:
            STATE.current = position
            STATE.stage = "download" if item.get("kind") != "file" else "extract"
            STATE.percent = 0.0
            STATE.frames_done = 0
            STATE.frames_total = item.get("frame_count") or 0
            STATE.message = ""
            STATE.queue[position]["status"] = "working"

        def on_stage(stage, data, _pos=position):
            with STATE.lock:
                STATE.stage = stage
                if stage == "download":
                    STATE.percent = float(data.get("percent", 0.0))
                elif stage == "extract":
                    STATE.frames_done = int(data.get("done", 0))
                    STATE.frames_total = int(data.get("total", 0)) or STATE.frames_total
                elif stage == "transcribe":
                    STATE.percent = float(data.get("percent", 0.0))
                elif stage == "metadata":
                    if data.get("title"):
                        STATE.queue[_pos]["title"] = data["title"]

        try:
            if mode == "video":
                result = core.download_only(
                    item["source"],
                    out_root=OUT_ROOT,
                    transcript=transcript,
                    on_stage=on_stage,
                    job=job,
                )
            else:
                result = core.process(
                    item["source"],
                    out_root=OUT_ROOT,
                    interval=interval,
                    keep_video=keep_video,
                    transcript=transcript,
                    on_stage=on_stage,
                    job=job,
                )
        except core.Cancelled:
            with STATE.lock:
                STATE.queue[position]["status"] = "cancelled"
            break
        except core.ExtractError as exc:
            with STATE.lock:
                STATE.queue[position]["status"] = "failed"
                STATE.queue[position]["error"] = str(exc)
            continue
        except Exception:
            with STATE.lock:
                STATE.queue[position]["status"] = "failed"
                STATE.queue[position]["error"] = (
                    "Something went wrong that I did not expect. "
                    "The details were written to the log."
                )
            traceback.print_exc()
            continue

        folder_name = result["folder_name"]
        with STATE.lock:
            STATE.queue[position]["status"] = "done"
            entry = {
                "folder": result["folder"],
                "folder_name": folder_name,
                "title": result["title"],
                "mode": mode,
                "duration_pretty": core.pretty_duration(result["duration_seconds"]),
                "manifest": str(Path(result["folder"]) / "manifest.json"),
                "transcript": (
                    str(Path(result["folder"]) / result["transcript"])
                    if result.get("transcript") else None
                ),
                "transcript_txt": (
                    str(Path(result["folder"]) / core.TRANSCRIPT_TXT)
                    if result.get("transcript") else None
                ),
                "transcript_error": result.get("transcript_error"),
            }
            if mode == "video":
                entry["source_video"] = str(Path(result["folder"]) / result["source_video"])
            else:
                entry.update({
                    "frame_count": result["frame_count"],
                    "interval_seconds": result["interval_seconds"],
                    "frames": [
                        {
                            "filename": f["filename"],
                            "timestamp": f["timestamp"],
                            "label": core.pretty_duration(f["timestamp"]),
                            "url": frame_url(folder_name, f["filename"]),
                        }
                        for f in result["frames"]
                    ],
                })
            STATE.results.append(entry)

    with STATE.lock:
        failed = [q for q in STATE.queue if q.get("status") == "failed"]
        if job.cancelled:
            STATE.phase = "cancelled"
        elif failed and not STATE.results:
            STATE.phase = "error"
            STATE.error = failed[0].get("error") or "That did not work."
        else:
            STATE.phase = "done"
        STATE.stage = None


# ---------------------------------------------------------------- API
def api_inspect(payload):
    source = payload.get("source", "")
    interval = payload.get("interval") or None
    mode = payload.get("mode") or "frames"
    info = core.inspect_source(source, interval=interval, mode=mode)
    return info


def api_start(payload):
    with STATE.lock:
        if STATE.phase == "working":
            raise core.ExtractError("Something is already running.")

    items = payload.get("items") or []
    if not items:
        raise core.ExtractError("There is nothing in the queue.")
    interval = payload.get("interval") or None
    keep_video = bool(payload.get("keep_video", True))
    transcript = bool(payload.get("transcript", False))

    prepared = [
        {
            "source": item.get("source"),
            "title": item.get("title") or item.get("source"),
            "thumbnail": item.get("thumbnail"),
            "kind": item.get("kind"),
            "mode": item.get("mode") or "frames",
            "frame_count": item.get("frame_count"),
            "duration_pretty": item.get("duration_pretty"),
            "status": "waiting",
            "error": None,
        }
        for item in items
    ]

    STATE.reset()
    with STATE.lock:
        STATE.phase = "working"
        STATE.queue = prepared
        STATE.current = 0
        STATE.transcript = transcript
    STATE.job = core.Job()
    STATE.worker = threading.Thread(
        target=_run_queue, args=(prepared, interval, keep_video, transcript),
        daemon=True
    )
    STATE.worker.start()
    return {"ok": True}


def api_cancel(_payload):
    with STATE.lock:
        job = STATE.job
    if job:
        job.cancel()
    return {"ok": True}


def api_open(payload):
    target = Path(payload.get("path", "")).expanduser()
    if not target.exists():
        raise core.ExtractError("That folder is not there any more.")
    os.startfile(str(target))            # noqa: S606 - Windows shell open, by design
    return {"ok": True}


def api_reveal(payload):
    target = Path(payload.get("path", "")).expanduser()
    if not target.exists():
        raise core.ExtractError("That file is not there any more.")
    subprocess.Popen(["explorer", "/select,", str(target)])
    return {"ok": True}


def api_copy(payload):
    text = payload.get("text", "")
    return {"ok": _clipboard_write(text)}


def api_clipboard(payload):
    text = (_clipboard_read() or "").strip()
    mode = payload.get("mode") or "frames"
    is_match = core.is_download_url(text) if mode == "video" else core.is_youtube_url(text)
    return {"text": text if is_match else ""}


def api_pick_file(_payload):
    if FILE_PICKER is None:
        raise core.ExtractError(
            "The file picker only works in the app window, not in a browser tab."
        )
    chosen = FILE_PICKER()
    return {"path": chosen or ""}


def api_history(_payload):
    return {"items": core.read_history(OUT_ROOT)}


def api_delete(payload):
    """Remove a whole run folder. Used by the history list's little x."""
    import shutil as _shutil
    target = Path(payload.get("path", "")).expanduser().resolve()
    if OUT_ROOT.resolve() not in target.parents:
        raise core.ExtractError("That folder is not one of mine, so I will not touch it.")
    if not re.match(r"^\d+ - ", target.name):
        raise core.ExtractError("That folder is not one of mine, so I will not touch it.")
    _shutil.rmtree(target, ignore_errors=True)
    return {"ok": True}


def api_health(_payload):
    return {
        "ok": True,
        "missing_tools": core.missing_tools(),
        "out_root": str(OUT_ROOT),
        "has_picker": FILE_PICKER is not None,
        "can_transcribe": core.whisper_available(),
    }


ROUTES = {
    "/api/inspect": api_inspect,
    "/api/start": api_start,
    "/api/cancel": api_cancel,
    "/api/open": api_open,
    "/api/reveal": api_reveal,
    "/api/copy": api_copy,
    "/api/clipboard": api_clipboard,
    "/api/pick": api_pick_file,
    "/api/history": api_history,
    "/api/delete": api_delete,
    "/api/health": api_health,
}


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "VideoAnalyzer"

    def log_message(self, *_args):
        pass                              # keep the console clean

    # -- helpers -----------------------------------------------------------
    def _send(self, code, body, content_type="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False))

    def _serve_file(self, path):
        if not path.is_file():
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        guessed = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if guessed.startswith("text/") or guessed == "application/javascript":
            guessed += "; charset=utf-8"
        self._send(200, path.read_bytes(), guessed)

    def _resolve_static(self, url_path):
        """Map a URL onto a file, refusing anything that escapes its folder."""
        clean = urllib.parse.unquote(url_path.split("?", 1)[0])
        if clean in ("/", "/index.html"):
            return UI_DIR / "index.html"
        for prefix, base in (("/ui/", UI_DIR), ("/frames/", OUT_ROOT), ("/assets/", ASSET_DIR)):
            if clean.startswith(prefix):
                candidate = (base / clean[len(prefix):]).resolve()
                if base.resolve() == candidate or base.resolve() in candidate.parents:
                    return candidate
                return None
        return None

    # -- verbs -------------------------------------------------------------
    def do_GET(self):
        if self.path.split("?")[0] == "/api/state":
            self._json(STATE.snapshot())
            return
        target = self._resolve_static(self.path)
        if target is None:
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        self._serve_file(target)

    def do_POST(self):
        route = ROUTES.get(self.path.split("?")[0])
        if not route:
            self._send(404, json.dumps({"error": "no such endpoint"}))
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._json({"error": "That request did not make sense."}, 400)
            return

        try:
            self._json(route(payload))
        except core.ExtractError as exc:
            self._json({"error": str(exc)}, 400)
        except core.Cancelled:
            self._json({"error": "Cancelled."}, 400)
        except Exception:
            traceback.print_exc()
            self._json({"error": "Something went wrong that I did not expect."}, 500)


def start(port=0):
    """Start the server on localhost. Returns (httpd, url)."""
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def serve_forever(port=8730):
    """Run the server in the foreground. Used for developing the UI in a browser."""
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    print(f"Video Analyzer UI running at http://127.0.0.1:{port}/", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import sys as _sys
    serve_forever(int(_sys.argv[1]) if len(_sys.argv) > 1 else 8730)
