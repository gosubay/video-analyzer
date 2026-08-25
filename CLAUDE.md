# Video Analyzer — project rules

Purpose: turn a YouTube URL into a folder of timestamped JPG frames plus a
`manifest.json`, ready to be fed to Claude's vision API alongside a separately
generated timestamped transcript.

Galvin's global rules in `C:\Users\Admin\.claude\CLAUDE.md` also apply.

---

## Locked decisions

These were decided by Galvin on 2026-08-25. Do not change them without asking.

### 1. Frame interval — the ladder
Frame spacing is **snapped to one of these values only**, never anything in between:

```
1s, 2s, 3s, 5s, 10s, 30s, 60s
```

Rule: pick the **smallest ladder value that keeps the video at or under ~30 frames**.

```python
INTERVAL_LADDER = [1, 2, 3, 5, 10, 30, 60]
TARGET_FRAMES = 30
ideal = duration / TARGET_FRAMES
interval = first ladder value >= ideal   (fall back to 60 if none)
```

Resulting behaviour:

| Duration | Interval | Frames |
|---------:|---------:|-------:|
| 20s      | 1s       | 20 |
| 30s      | 1s       | 30 |
| 60s      | 2s       | 30 |
| 90s      | 3s       | 30 |
| 2 min    | 5s       | 24 |
| 5 min    | 10s      | 30 |
| 15 min   | 30s      | 30 |
| 30 min   | 60s      | 30 |
| 1 hour   | 60s      | 60 |

Anything up to 30 minutes lands at 30 frames or fewer. Past 30 minutes the count
grows, because 60s is the top of the ladder. Galvin has said he mostly analyses
short videos, so this is accepted.

`--interval N` forces a value, but **only a value on the ladder** — argparse
rejects anything else.

### 2. Folder naming
```
<sequence number> - <Video Title> - <D-M-YYYY>
```
Example: `1 - The Man Who Cheated With Invisible Ink 😬 - 25-8-2026`

- **Sequence number** counts up across every video ever processed. It is derived
  by scanning the output root for existing `N - ` folders and taking the highest
  plus one. Not zero-padded — Windows Explorer sorts numbers naturally.
- **Date** is the date the frames were extracted, not the video's upload date.
- **Date separator is `-`, not `/`.** Windows treats `/` as a path separator, so
  `25/8/2026` would silently create nested folders. This is non-negotiable.
- **Title** has the Windows-illegal characters `< > : " / \ | ? *` replaced with a
  space, control characters dropped, whitespace collapsed, and is truncated to 90
  characters so the full path stays clear of the Windows 260-character limit.
  Emoji and accented characters are kept.
- The **unmodified original title** is stored in `manifest.json` under `title`.
- A collision (same video twice in one day) gets ` (2)`, ` (3)` appended.

### 3. Frame file naming
```
frame_<seconds, 4 integer digits, always 1 decimal>s.jpg
```
Examples: `frame_0000.0s.jpg`, `frame_0003.0s.jpg`, `frame_0190.0s.jpg`

**Always exactly one decimal place**, even for whole seconds. Zero-padded to four
integer digits so that alphabetical order equals chronological order — code that
globs the folder gets the frames in time order without sorting logic.

### 4. manifest.json
```json
{
  "video_id": "jNQXAC9IVRw",
  "title": "Me at the zoo",
  "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
  "uploader": "jawed",
  "extracted_on": "2026-08-25",
  "duration_seconds": 19.014,
  "interval_seconds": 1.0,
  "frame_count": 19,
  "frame_width": 320,
  "frame_height": 240,
  "source_video": "source.mp4",
  "frames": [
    { "index": 0, "filename": "frame_0000.0s.jpg", "timestamp": 0.0 }
  ]
}
```

Hard rules for the manifest, because a transcript matcher depends on them:

- `timestamp` is **always a JSON float**, never an int and never a string.
  `0.0`, not `0`. Same for `interval_seconds`. Enforced with `float()` at the
  point of construction — Python's `round(0 * 1, 1)` returns int `0` otherwise.
- `timestamp` is **seconds from the start of the video**. Never `MM:SS`, never a
  formatted string.
- `filename` always agrees with `timestamp`: `f"frame_{timestamp:06.1f}s.jpg"`.
- `index` is contiguous from 0.
- Written UTF-8 with `ensure_ascii=False` so emoji titles stay readable.

### 5. Frame extraction method — do not "optimise" this
Frames are extracted with **one accurate `ffmpeg -ss` seek per frame**, not with
the `fps=1/n` video filter.

The `fps` filter was tried first and is **wrong for this use case**. It buckets
input frames onto an output grid and emits the *last* frame of each bucket, so on
a 200s test video the frame labelled `90.0s` actually contained the picture from
**94.97s** — nearly 5 seconds late. Verified with a burned-in timecode video.

Per-frame seeking was verified against the same timecode video: `frame_0000.0s`,
`frame_0090.0s` and `frame_0190.0s` contained exactly `t = 0.000000 s`,
`t = 90.000000 s` and `t = 190.000000 s`.

If frame extraction is ever rewritten, re-run that timecode test before trusting it:

```bash
ffmpeg -f lavfi -i "testsrc2=size=640x360:rate=30:duration=200" -vf "drawtext=fontfile='C\:/Windows/Fonts/arialbd.ttf':text='t = %{pts\:flt} s':fontsize=54:fontcolor=white:box=1:boxcolor=black:boxborderw=14:x=(w-text_w)/2:y=(h-text_h)/2" -c:v libx264 -pix_fmt yuv420p timecode.mp4
```

### 6. Download settings
- Cap at **720p** (`MAX_HEIGHT = 720`). Claude's vision API downsizes anything
  larger, so a higher resolution costs time and bandwidth for no analysis gain.
- The downloaded video is **kept** beside the frames as `source.mp4`, so the
  transcript step does not need to download it again. `--no-keep-video` opts out.
- JPEG quality is ffmpeg `-q:v 2` (high).

### 7. Error handling
Every failure must print **one plain sentence**, never a Python traceback, and
exit with code 1. yt-dlp's own console output is silenced with a null logger so
only our message appears. Add new cases to the `friendly_download_error` table —
the generic `"unavailable"` catch-all must stay **below** the specific reasons.

---

## The app window (added 2026-08-25)

### 8. Shape of the code
```
core.py      the engine - download, probe, plan, extract, manifest, history
extract.py   command line, a thin wrapper over core
server.py    local HTTP server: serves ui/ + frames/ and a small JSON API
app.py       opens the desktop window (pywebview / Edge WebView2) onto that server
ui/          index.html, style.css, app.js - the page itself
```

**`core.py` is the only place that touches ffmpeg, yt-dlp or the manifest.** The
CLI and the window are both just front ends. Any rule from sections 1-7 above is
enforced once, in core, and must never be reimplemented in the UI.

The UI mirrors two things in JavaScript for instant feedback — the interval
ladder and the frame-count estimate. Those are *display only*. The server always
recalculates from `core.py` before doing any work.

### 9. Why a local web page instead of tkinter
The window is Edge WebView2, which ships with Windows 11, driven by pywebview.
It looks like a normal app - no address bar, own taskbar button and icon. The
alternative (tkinter) cannot produce the soft-pastel look Galvin asked for
without a fight. The server binds to **127.0.0.1 only** and picks a random free
port, so nothing is reachable from outside the machine.

### 10. Locked UI decisions
- **Cute pastel with a mascot.** Cream background, lavender/mint/peach accents,
  fat rounded corners. The mascot is a clapperboard with four moods — `idle`
  (dozing, z z z), `working` (clapping, tongue out), `done` (happy eyes,
  confetti), `error` (worried, sweat drop). Driven by
  `data-state` on `#mascot-wrap`; every mood is plain SVG + CSS, no images.
- **The app never forces you to close it.** After a run it shows results and
  offers "Do another one". This was the specific complaint that prompted the UI.
- **Confirm before downloading.** Adding a link calls `/api/inspect`, which reads
  the title, channel, duration and thumbnail *without* downloading, and shows
  how many frames the run will produce.
- **Queue** runs items one at a time. One item failing must not stop the rest;
  it is marked `failed` with its plain-sentence reason and the run continues.
- **Cancelling must leave nothing behind.** `core.process` deletes the
  part-finished folder on both `Cancelled` and `ExtractError`.
- Results show a clickable frame grid; clicking opens a lightbox with arrow-key
  navigation.
- "Copy for Claude" puts the folder path, manifest path and a one-line summary
  on the clipboard.

### 11. Do not use ctypes for the clipboard
An earlier version read the clipboard with the Win32 API through `ctypes` and
**segfaulted the whole app**: `GetClipboardData` returns a 64-bit handle, ctypes
defaults return types to 32-bit `int`, and locking the truncated handle killed
Python. A segfault cannot be caught by `try/except`, so the app just vanished.

Clipboard access now shells out to PowerShell. It costs a few hundred
milliseconds once at startup and it cannot take the app down. If you ever
reintroduce ctypes here, declare `argtypes` and `restype` on **every** call —
see `set_window_icon()` in app.py for the pattern.

### 12. Debug logging
`app.py` writes to `debug.log` beside itself (gitignored). Startup failures also
raise a Windows message box rather than dying silently. Check that file first
when the window will not open.

---

## Dependencies
- Python 3.13
- `yt-dlp` (pip)
- `pywebview` (pip) — only needed for the app window, not the CLI
- FFmpeg — `ffmpeg` and `ffprobe` must both be on PATH. Called via `subprocess`,
  deliberately not the `ffmpeg-python` wrapper, to keep dependencies minimal.
- Pillow (pip) — only to regenerate the icon, not needed to run anything

## Not built yet
- Transcript generation (separate step, will be matched to these timestamps)
- Sending frames to the vision API
- Deleting individual frames from a finished run (deliberately skipped: it would
  renumber `index` and force a manifest rewrite, which risks the timestamp
  guarantee. Whole runs can be deleted from the Recent list.)
