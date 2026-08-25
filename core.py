#!/usr/bin/env python3
"""
Video Analyzer - the engine.

Everything that actually does work lives here so that both the command line
(extract.py) and the app window (app.py) share one implementation and one set
of rules. The locked spec - interval ladder, folder naming, manifest schema,
per-frame seeking - is documented in CLAUDE.md. Do not diverge from it here.
"""

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- spec constants
# Frame spacing is snapped to one of these values - never anything in between.
INTERVAL_LADDER = [1, 2, 3, 5, 10, 30, 60]
TARGET_FRAMES = 30
MAX_HEIGHT = 720          # download cap; Claude's vision API downsizes above this anyway
JPEG_QUALITY = 2          # ffmpeg -q:v, 2 = high quality
MAX_TITLE_CHARS = 90      # keeps the full path clear of the Windows 260-char limit

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}

# Characters Windows forbids in a file or folder name.
_ILLEGAL = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Hide the console window that subprocess would otherwise flash on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ExtractError(Exception):
    """Any failure we can explain to the user in one plain sentence."""


class Cancelled(Exception):
    """Raised when the user asks to stop. Never shown as an error."""


class Job:
    """A cancel switch that can be flipped from another thread."""

    def __init__(self):
        self._flag = threading.Event()

    def cancel(self):
        self._flag.set()

    @property
    def cancelled(self):
        return self._flag.is_set()

    def check(self):
        if self._flag.is_set():
            raise Cancelled()


_NULL_JOB = Job()


# ---------------------------------------------------------------- finding ffmpeg
def app_dir():
    """
    The folder the app lives in - the .exe's folder in a built release, or this
    source folder otherwise. Used for things the user should be able to see:
    the bundled ffmpeg, the frames output, the log.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def resource_dir():
    """
    Where read-only files we ship (ui/, assets/) actually sit. PyInstaller
    unpacks those somewhere of its own choosing, which is NOT app_dir().
    """
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else Path(__file__).parent


def tool_path(name):
    """
    Locate ffmpeg or ffprobe: our own bundled copy first, then the machine's.

    A packaged release ships both binaries in bin/ next to the .exe, so a friend
    who has never heard of FFmpeg does not have to install anything.
    """
    exe = f"{name}.exe" if os.name == "nt" else name
    places = (
        app_dir() / "bin" / exe,        # sitting beside the .exe
        app_dir() / exe,
        resource_dir() / "bin" / exe,   # tucked inside the bundle
        resource_dir() / exe,
    )
    for candidate in places:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def ffmpeg_dir():
    """The folder holding ffmpeg, for handing to yt-dlp so it can merge audio."""
    found = tool_path("ffmpeg")
    return str(Path(found).parent) if found else None


# ---------------------------------------------------------------- small helpers
def which_or_die(name, install_hint):
    path = tool_path(name)
    if not path:
        raise ExtractError(f"{name} is not installed or not on your PATH. {install_hint}")
    return path


def missing_tools():
    """Names of required programs that are not installed. Empty list means good."""
    return [name for name in ("ffmpeg", "ffprobe") if not tool_path(name)]


def choose_interval(duration):
    """Smallest ladder value that keeps the video at or under TARGET_FRAMES frames."""
    ideal = duration / TARGET_FRAMES
    for step in INTERVAL_LADDER:
        if step >= ideal:
            return step
    return INTERVAL_LADDER[-1]


def safe_title(title):
    """Strip characters Windows rejects, keep everything else (emoji included)."""
    cleaned = "".join(
        " " if ch in _ILLEGAL else ch
        for ch in title
        if unicodedata.category(ch) != "Cc"      # drop control characters
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > MAX_TITLE_CHARS:
        cleaned = cleaned[:MAX_TITLE_CHARS].rstrip(" .") + "..."
    if cleaned.split(".")[0].upper() in _RESERVED_NAMES:
        cleaned = "_" + cleaned
    return cleaned or "untitled"


def next_sequence_number(root):
    """Highest existing 'N - ...' folder number under root, plus one."""
    highest = 0
    root = Path(root)
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir():
                match = re.match(r"^(\d+) - ", child.name)
                if match:
                    highest = max(highest, int(match.group(1)))
    return highest + 1


def format_timestamp(seconds):
    """0.0 -> '0000.0', 3.5 -> '0003.5'. Zero-padded so filenames sort chronologically."""
    return f"{seconds:06.1f}"


def pretty_duration(seconds):
    """90.4 -> '1:30'. For display only, never for filenames."""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def looks_like_url(text):
    return bool(re.match(r"^\s*(https?://|www\.)", str(text or ""), re.I))


def validate_url(url):
    url = str(url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    host_match = re.match(r"^https?://([^/]+)", url, re.I)
    host = host_match.group(1).lower() if host_match else ""
    host = host.split("@")[-1].split(":")[0]
    allowed = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    if not any(host == d or host.endswith("." + d) for d in allowed):
        raise ExtractError(
            f"That does not look like a YouTube link (host: {host or 'none'}). "
            f"Expected something like https://www.youtube.com/watch?v=XXXXXXXXXXX"
        )
    return url


def is_youtube_url(text):
    try:
        validate_url(text)
        return True
    except ExtractError:
        return False


# ---------------------------------------------------------------- errors
def friendly_download_error(raw):
    """Turn yt-dlp's noisy output into one sentence a human can act on."""
    text = str(raw).lower()
    table = [
        ("private video", "That video is private, so it cannot be downloaded."),
        ("members-only", "That video is members-only and cannot be downloaded."),
        ("removed by the uploader", "That video was removed by the uploader."),
        ("sign in to confirm your age", "That video is age-restricted and cannot be downloaded without signing in."),
        ("age-restricted", "That video is age-restricted and cannot be downloaded without signing in."),
        ("not available in your country", "That video is blocked in your country."),
        ("confirm you", "YouTube is asking for a bot check. Try again shortly, or use browser cookies."),
        ("is not a valid url", "That is not a valid URL."),
        ("unsupported url", "That link is not a video page."),
        ("incomplete youtube id", "That YouTube link looks truncated - check you copied the whole URL."),
        ("requested format is not available", f"No version of that video is available at {MAX_HEIGHT}p or below."),
        ("no video formats", "That page has no downloadable video (is it a livestream that has not started?)."),
        ("this live event will begin", "That is a scheduled livestream that has not started yet."),
        # generic catch-all - must stay below the specific reasons above
        ("unavailable", "That video is unavailable - it may have been deleted, private or region-blocked."),
        ("getaddrinfo", "No internet connection could be made - check your network."),
        ("failed to resolve", "No internet connection could be made - check your network."),
        ("urlopen error", "Network error while contacting YouTube - check your connection."),
        ("timed out", "The connection to YouTube timed out - check your connection and try again."),
    ]
    for needle, message in table:
        if needle in text:
            return message
    first_line = str(raw).strip().splitlines()[0] if str(raw).strip() else "unknown error"
    return f"Download failed: {first_line}"


class _SilentLogger:
    """Swallow yt-dlp's own console output so only our plain message is shown."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _import_ytdlp():
    try:
        import yt_dlp
    except ImportError:
        raise ExtractError("yt-dlp is not installed. Run:  pip install yt-dlp")
    return yt_dlp


# ---------------------------------------------------------------- probing
def probe_duration(video_path):
    ffprobe = which_or_die("ffprobe", "Install FFmpeg and reopen the app.")
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True, creationflags=_NO_WINDOW
        ).stdout.strip()
        duration = float(out)
    except (subprocess.CalledProcessError, ValueError):
        raise ExtractError("Could not read that video's duration - the file may be corrupt.")
    if duration <= 0:
        raise ExtractError("That video reports a duration of zero seconds - nothing to extract.")
    return duration


def probe_dimensions(video_path):
    ffprobe = tool_path("ffprobe")
    if not ffprobe:
        return None, None
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(video_path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True, creationflags=_NO_WINDOW
        ).stdout.strip()
        width, height = (int(v) for v in out.split("x")[:2])
        return width, height
    except Exception:
        return None, None


def inspect_source(source, interval=None):
    """
    Look at a YouTube link or a local file WITHOUT downloading it, and work out
    what a run would produce. Feeds the confirm-before-you-download screen.
    """
    source = str(source or "").strip().strip('"')

    if Path(source).expanduser().is_file():
        path = Path(source).expanduser().resolve()
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            raise ExtractError(f"{path.suffix or 'That file type'} is not a video file I can read.")
        duration = probe_duration(path)
        info = {
            "kind": "file",
            "source": str(path),
            "video_id": None,
            "title": path.stem,
            "uploader": None,
            "thumbnail": None,
            "url": None,
        }
    else:
        url = validate_url(source)
        yt_dlp = _import_ytdlp()
        opts = {
            "quiet": True, "no_warnings": True, "noplaylist": True,
            "skip_download": True, "logger": _SilentLogger(), "no_color": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                meta = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise ExtractError(friendly_download_error(exc))

        if meta.get("_type") == "playlist":
            entries = [e for e in (meta.get("entries") or []) if e]
            if not entries:
                raise ExtractError("That link is a playlist with no playable videos.")
            meta = entries[0]

        duration = meta.get("duration")
        if not duration:
            raise ExtractError("That video has no duration - it may be a livestream.")
        duration = float(duration)
        info = {
            "kind": "youtube",
            "source": url,
            "video_id": meta.get("id"),
            "title": meta.get("title") or meta.get("id") or "untitled",
            "uploader": meta.get("uploader"),
            "thumbnail": meta.get("thumbnail"),
            "url": meta.get("webpage_url") or url,
        }

    chosen = int(interval) if interval else choose_interval(duration)
    stamps = plan_timestamps(duration, chosen)
    info.update({
        "duration_seconds": round(duration, 3),
        "duration_pretty": pretty_duration(duration),
        "interval_seconds": chosen,
        "interval_auto": not bool(interval),
        "frame_count": len(stamps),
    })
    return info


# ---------------------------------------------------------------- download
def download(url, workdir, on_progress=None, job=_NULL_JOB):
    """Fetch the video at <=MAX_HEIGHT. Returns (file_path, info_dict)."""
    yt_dlp = _import_ytdlp()
    state = {"last": -1}

    def hook(d):
        if job.cancelled:
            raise Cancelled()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            if total and on_progress:
                percent = done * 100 / total
                if percent >= state["last"] + 1:
                    state["last"] = percent
                    on_progress(percent, total)
        elif d["status"] == "finished":
            state["last"] = -1
            if on_progress:
                on_progress(100.0, d.get("total_bytes"))

    opts = {
        "format": f"bestvideo[height<={MAX_HEIGHT}]+bestaudio/best[height<={MAX_HEIGHT}]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(Path(workdir) / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "noplaylist": True,
        "retries": 3,
        "logger": _SilentLogger(),
        "no_color": True,
    }
    located = ffmpeg_dir()
    if located:
        opts["ffmpeg_location"] = located

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Cancelled:
        raise
    except Exception as exc:
        if job.cancelled:
            raise Cancelled()
        raise ExtractError(friendly_download_error(exc))

    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise ExtractError("That link is a playlist with no playable videos.")
        info = entries[0]

    files = sorted(Path(workdir).glob("source.*"))
    if not files:
        raise ExtractError("The download finished but no video file was produced.")
    return files[0], info


# ---------------------------------------------------------------- frames
def plan_timestamps(duration, interval):
    """0.0, interval, 2*interval ... up to (but not past) the end of the video."""
    stamps = []
    step = 0
    while True:
        ts = round(step * float(interval), 1)
        if ts >= duration:
            break
        stamps.append(ts)
        step += 1
    return stamps


def extract_frames(video_path, timestamps, out_dir, on_frame=None, job=_NULL_JOB):
    """
    One accurate seek per timestamp.

    Deliberately NOT the ffmpeg `fps=1/n` filter: that filter buckets input
    frames onto an output grid and emits the LAST frame of each bucket, so a
    frame labelled 90s actually held the picture from ~95s. Seeking per frame
    lands on the real picture at that instant, which is what the transcript
    matching depends on. See CLAUDE.md section 5.
    """
    ffmpeg = which_or_die("ffmpeg", "Install FFmpeg and reopen the app.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(timestamps)
    written = []

    for position, ts in enumerate(timestamps, start=1):
        job.check()
        filename = f"frame_{format_timestamp(ts)}s.jpg"
        dest = out_dir / filename
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-ss", f"{ts:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", str(JPEG_QUALITY),
            "-y", str(dest),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, creationflags=_NO_WINDOW
        )
        ok = result.returncode == 0 and dest.exists() and dest.stat().st_size > 0

        if not ok:
            if dest.exists():
                dest.unlink()
            # The final timestamp can land past the last decodable picture.
            if position == total and written:
                break
            detail = (result.stderr or "").strip().splitlines()
            hint = detail[-1] if detail else "unknown ffmpeg error"
            raise ExtractError(f"Could not read the frame at {ts:.1f}s: {hint}")

        written.append({"index": len(written), "filename": filename, "timestamp": ts})
        if on_frame:
            on_frame(position, total)

    if not written:
        raise ExtractError("No frames could be extracted - the file may have no usable video stream.")
    return written


# ---------------------------------------------------------------- the whole run
def process(source, out_root, interval=None, keep_video=True,
            on_stage=None, job=_NULL_JOB):
    """
    Turn one YouTube link or local video file into a finished folder.

    on_stage(stage, data) is called with:
        ("metadata", info)                     once the title/duration are known
        ("download", {"percent": float, ...})  repeatedly while downloading
        ("extract",  {"done": n, "total": n})  once per frame
        ("saving",   {})                       while writing the manifest
    Returns the manifest dict with an extra "folder" key.
    """
    def announce(stage, data=None):
        if on_stage:
            on_stage(stage, data or {})

    which_or_die("ffmpeg", "Install FFmpeg and reopen the app.")
    which_or_die("ffprobe", "Install FFmpeg and reopen the app.")

    out_root = Path(out_root).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    source = str(source).strip().strip('"')
    local = Path(source).expanduser()
    is_local = local.is_file()

    with tempfile.TemporaryDirectory(prefix="video_analyzer_") as workdir:
        job.check()

        if is_local:
            video_path = local.resolve()
            title = video_path.stem
            meta = {"id": None, "uploader": None, "webpage_url": None}
            announce("metadata", {"title": title, "kind": "file"})
        else:
            url = validate_url(source)
            announce("download", {"percent": 0.0})
            video_path, meta = download(
                url, workdir,
                on_progress=lambda pct, total: announce(
                    "download", {"percent": pct, "total_bytes": total}
                ),
                job=job,
            )
            title = meta.get("title") or meta.get("id") or "untitled"
            announce("metadata", {"title": title, "kind": "youtube"})

        job.check()
        duration = probe_duration(video_path)
        width, height = probe_dimensions(video_path)
        chosen = int(interval) if interval else choose_interval(duration)
        timestamps = plan_timestamps(duration, chosen)

        today = _dt.date.today()
        base_name = (
            f"{next_sequence_number(out_root)} - {safe_title(title)} - "
            f"{today.day}-{today.month}-{today.year}"
        )
        out_dir = out_root / base_name
        suffix = 2
        while out_dir.exists():                      # same video twice in one day
            out_dir = out_root / f"{base_name} ({suffix})"
            suffix += 1
        out_dir.mkdir(parents=True)

        announce("extract", {"done": 0, "total": len(timestamps)})
        try:
            frames = extract_frames(
                video_path, timestamps, out_dir,
                on_frame=lambda done, total: announce("extract", {"done": done, "total": total}),
                job=job,
            )
        except (Cancelled, ExtractError):
            shutil.rmtree(out_dir, ignore_errors=True)   # never leave half a folder
            raise

        announce("saving")
        kept_video = None
        if keep_video:
            kept_video = f"source{video_path.suffix}"
            if is_local:
                shutil.copy2(str(video_path), str(out_dir / kept_video))
            else:
                shutil.move(str(video_path), str(out_dir / kept_video))

        manifest = {
            "video_id": meta.get("id"),
            "title": title,
            "url": meta.get("webpage_url") or (None if is_local else source),
            "uploader": meta.get("uploader"),
            "extracted_on": today.isoformat(),
            "duration_seconds": round(duration, 3),
            "interval_seconds": float(chosen),
            "frame_count": len(frames),
            "frame_width": width,
            "frame_height": height,
            "source_video": kept_video,
            "source_file": str(video_path) if is_local else None,
            "frames": frames,
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    result = dict(manifest)
    result["folder"] = str(out_dir)
    result["folder_name"] = out_dir.name
    return result


# ---------------------------------------------------------------- history
def read_history(out_root, limit=60):
    """Every finished folder under out_root, newest sequence number first."""
    out_root = Path(out_root).expanduser().resolve()
    entries = []
    if not out_root.is_dir():
        return entries
    for child in sorted(out_root.iterdir()):
        if not child.is_dir():
            continue
        match = re.match(r"^(\d+) - ", child.name)
        if not match:
            continue
        manifest_path = child / "manifest.json"
        record = {
            "number": int(match.group(1)),
            "folder": str(child),
            "folder_name": child.name,
            "title": child.name,
            "frame_count": len(list(child.glob("frame_*.jpg"))),
            "extracted_on": None,
            "duration_pretty": None,
            "interval_seconds": None,
            "ok": manifest_path.is_file(),
        }
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                record.update({
                    "title": data.get("title") or record["title"],
                    "frame_count": data.get("frame_count", record["frame_count"]),
                    "extracted_on": data.get("extracted_on"),
                    "interval_seconds": data.get("interval_seconds"),
                    "duration_pretty": pretty_duration(data.get("duration_seconds") or 0),
                })
            except (OSError, ValueError):
                record["ok"] = False
        entries.append(record)
    entries.sort(key=lambda r: r["number"], reverse=True)
    return entries[:limit]
