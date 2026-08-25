#!/usr/bin/env python3
"""
Video Analyzer - frame extractor.

Downloads a YouTube video, extracts frames on a fixed interval, and writes a
manifest.json mapping every frame file to its exact timestamp in seconds.

Usage:  python extract.py <youtube_url> [--interval N] [--outdir PATH] [--no-keep-video]

The full spec (interval ladder, folder naming, manifest schema) lives in CLAUDE.md.
"""

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- spec constants
# Frame spacing is snapped to one of these values - never anything in between.
INTERVAL_LADDER = [1, 2, 3, 5, 10, 30, 60]
TARGET_FRAMES = 30
MAX_HEIGHT = 720          # download cap; Claude's vision API downsizes above this anyway
JPEG_QUALITY = 2          # ffmpeg -q:v, 2 = high quality
MAX_TITLE_CHARS = 90      # keeps the full path clear of the Windows 260-char limit

# Characters Windows forbids in a file or folder name.
_ILLEGAL = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ExtractError(Exception):
    """Any failure we can explain to the user in one plain sentence."""


# ---------------------------------------------------------------- small helpers
def log(msg=""):
    print(msg, flush=True)


def which_or_die(name, install_hint):
    path = shutil.which(name)
    if not path:
        raise ExtractError(f"{name} is not installed or not on your PATH.\n  Fix: {install_hint}")
    return path


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


def validate_url(url):
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    host_match = re.match(r"^https?://([^/]+)", url, re.I)
    host = host_match.group(1).lower() if host_match else ""
    host = host.split("@")[-1].split(":")[0]
    allowed = ("youtube.com", "youtu.be", "youtube-nocookie.com")
    if not any(host == d or host.endswith("." + d) for d in allowed):
        raise ExtractError(
            f"That does not look like a YouTube link (host: {host or 'none'}).\n"
            f"  Expected something like: https://www.youtube.com/watch?v=XXXXXXXXXXX"
        )
    return url


# ---------------------------------------------------------------- step 1: download
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


def download(url, workdir):
    """Fetch the video at <=MAX_HEIGHT. Returns (file_path, info_dict)."""
    try:
        import yt_dlp
    except ImportError:
        raise ExtractError("yt-dlp is not installed.\n  Fix: run  pip install yt-dlp")

    class _Silent:
        """Swallow yt-dlp's own console output so only our plain message is shown."""
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    state = {"last_pct": -1}

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            if total:
                pct = int(done * 100 / total)
                if pct >= state["last_pct"] + 10:
                    state["last_pct"] = pct
                    mb = total / 1024 / 1024
                    log(f"  downloading... {pct}%  ({mb:.1f} MB)")
        elif d["status"] == "finished":
            state["last_pct"] = -1
            log("  download complete, preparing file...")

    opts = {
        "format": (
            f"bestvideo[height<={MAX_HEIGHT}]+bestaudio/"
            f"best[height<={MAX_HEIGHT}]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(Path(workdir) / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "noplaylist": True,
        "retries": 3,
        "logger": _Silent(),
        "no_color": True,
    }

    log("Downloading video...")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:                       # yt_dlp raises several exception types
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


# ---------------------------------------------------------------- step 2: duration
def probe_duration(ffprobe, video_path):
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        duration = float(out)
    except (subprocess.CalledProcessError, ValueError):
        raise ExtractError("ffprobe could not read the video's duration - the file may be corrupt.")
    if duration <= 0:
        raise ExtractError("The video reports a duration of zero seconds - nothing to extract.")
    return duration


def probe_dimensions(ffprobe, video_path):
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        width, height = (int(v) for v in out.split("x")[:2])
        return width, height
    except Exception:
        return None, None


# ---------------------------------------------------------------- step 3: frames
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


def extract_frames(ffmpeg, video_path, timestamps, out_dir):
    """
    One accurate seek per timestamp.

    Deliberately NOT the ffmpeg `fps=1/n` filter: that filter buckets input
    frames onto an output grid and emits the LAST frame of each bucket, so a
    frame labelled 90s actually held the picture from ~95s. Seeking per frame
    lands on the real picture at that instant, which is what the transcript
    matching depends on.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(timestamps)
    written = []

    for position, ts in enumerate(timestamps, start=1):
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        ok = result.returncode == 0 and dest.exists() and dest.stat().st_size > 0

        if not ok:
            if dest.exists():
                dest.unlink()
            # The final timestamp can land past the last decodable picture.
            if position == total and written:
                log(f"  no picture available at {ts:.1f}s - stopping there")
                break
            detail = (result.stderr or "").strip().splitlines()
            hint = detail[-1] if detail else "unknown ffmpeg error"
            raise ExtractError(f"ffmpeg failed extracting the frame at {ts:.1f}s: {hint}")

        log(f"  extracting frame {position} of {total}...")
        written.append({"index": len(written), "filename": filename, "timestamp": ts})

    if not written:
        raise ExtractError("No frames could be extracted - the file may have no usable video stream.")
    return written


# ---------------------------------------------------------------- main
def run(args):
    ffmpeg = which_or_die("ffmpeg", "install FFmpeg, then reopen your terminal")
    ffprobe = which_or_die("ffprobe", "install FFmpeg, then reopen your terminal")

    url = validate_url(args.url)
    out_root = Path(args.outdir).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video_analyzer_") as workdir:
        video_path, info = download(url, workdir)

        title = info.get("title") or info.get("id") or "untitled"
        video_id = info.get("id") or "unknown"
        duration = probe_duration(ffprobe, video_path)
        width, height = probe_dimensions(ffprobe, video_path)

        interval = args.interval or choose_interval(duration)
        timestamps = plan_timestamps(duration, interval)

        log("")
        log(f"Title:    {title}")
        log(f"Duration: {duration:.1f}s")
        log(f"Interval: {interval}s  ->  {len(timestamps)} frames")
        log("")

        # Folder:  "N - Title - D-M-YYYY"
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

        log("Extracting frames...")
        manifest_frames = extract_frames(ffmpeg, video_path, timestamps, out_dir)

        kept_video = None
        if args.keep_video:
            kept_video = f"source{video_path.suffix}"
            shutil.move(str(video_path), str(out_dir / kept_video))

        manifest = {
            "video_id": video_id,
            "title": title,
            "url": info.get("webpage_url") or url,
            "uploader": info.get("uploader"),
            "extracted_on": today.isoformat(),
            "duration_seconds": round(duration, 3),
            "interval_seconds": float(interval),
            "frame_count": len(manifest_frames),
            "frame_width": width,
            "frame_height": height,
            "source_video": kept_video,
            "frames": manifest_frames,
        }
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    log("")
    log(f"Done. {len(manifest_frames)} frames written to:")
    log(f"  {out_dir}")
    log(f"  manifest: {manifest_path.name}")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):           # emoji-safe output on Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download a YouTube video and extract timestamped frames for vision analysis."
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--interval", type=int, choices=INTERVAL_LADDER, default=None,
        help="Force a frame interval in seconds instead of choosing automatically.",
    )
    parser.add_argument(
        "--outdir", default="frames",
        help="Where video folders are created (default: ./frames)",
    )
    parser.add_argument(
        "--no-keep-video", dest="keep_video", action="store_false",
        help="Delete the downloaded video instead of saving it beside the frames.",
    )
    parser.set_defaults(keep_video=True)
    args = parser.parse_args()

    try:
        return run(args)
    except ExtractError as exc:
        log("")
        log(f"ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        log("\nCancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
