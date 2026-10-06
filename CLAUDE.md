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

## The shareable release (added 2026-08-25)

### 13. How it is packaged
`build_exe.bat` -> PyInstaller (`VideoAnalyzer.spec`) -> `release/make_zip.py`.
Output: `release/VideoAnalyzer-v1.1-windows.zip`, about 278 MB (v1.0 was 184 MB;
the difference is the transcript engine). The version number lives in
`release/make_zip.py`. Published as a GitHub release on the private repo.

**One-folder, never one-file.** A one-file build re-extracts ~450 MB of FFmpeg
into a temp folder on every launch, which reads as a frozen app.

**FFmpeg and ffprobe are bundled** so the recipient installs nothing. They go in
via `datas`, not `binaries` - they are self-contained executables and letting
PyInstaller scan them for dependencies is slow and pointless.

The two binaries are ~217 MB each because the winget `full_build` is statically
linked. A `full-shared` build (tiny exes plus shared DLLs) would cut the release
to roughly a third. Swap by dropping `ffmpeg.exe`/`ffprobe.exe` and their DLLs
into `bin/` next to the spec - it prefers that folder over the PATH.

### 14. Frozen vs source paths
Two different roots, and mixing them up is the classic packaging bug:

- `core.app_dir()` - the .exe's own folder. Things the user must be able to
  find: `frames/`, `debug.log`, the bundled `bin/`.
- `core.resource_dir()` - PyInstaller's unpack folder (`_internal`). Read-only
  things we ship: `ui/`, `assets/`.

`core.tool_path()` checks both, so ffmpeg is found wherever it ends up.

### 15. What the recipient needs
Nothing. Verified by running the built exe with FFmpeg stripped out of `PATH`:
it found its own copy and completed a full download and extraction.

Two caveats that are not bugs:
- **SmartScreen** shows "Windows protected your PC" for any unsigned exe. Fixing
  that needs a code-signing certificate (a few hundred dollars a year). The
  bundled `README.txt` explains the More info -> Run anyway click.
- **Edge WebView2** is required. Windows 11 always has it; a stale Windows 10
  might not. `app.py` checks the registry at startup and shows a message box
  with the Microsoft download link rather than failing silently.

### 15a. Transcripts inside the release (added 2026-10-06)
The shared .exe ships faster-whisper, **CPU only**.

- The NVIDIA CUDA DLLs are **not** bundled: they are ~1.8 GB, which would push
  the zip past what GitHub accepts for one release file (2 GB). A friend's PC
  transcribes on the processor (`int8`); `core.transcribe()` already falls back
  on its own. Running from source on Galvin's machine still uses the GPU.
- The `medium` model (~1.5 GB) is **not** bundled either - it downloads on the
  first transcript, per section 17. `release/README.txt` warns about the wait.
- The spec uses `collect_data_files` + `collect_dynamic_libs` for
  faster_whisper / ctranslate2 / onnxruntime / av / tokenizers. **Not
  `collect_all`** - that pulled in transformers, cv2, llvmlite and pyarrow from
  other projects on the build machine and produced a 1.2 GB folder.
- `pkg_resources` must stay in `excludes` alongside `setuptools`. With only
  setuptools excluded PyInstaller still adds its pkg_resources startup hook and
  the exe dies at launch with `No module named 'jaraco'`.
- **Close every running `Video Analyzer.exe` before rebuilding.** A running copy
  locks `dist/`, the build stops half-way without an obvious error, and the
  result fails with `No module named 'encodings'`.

Verified 2026-10-06 on the built exe with FFmpeg and Python stripped from PATH
and an empty model cache: frames + transcript (model downloaded, `device: cpu`)
and download-only + transcript both completed.

---

## Download-only mode (added 2026-08-25)

### 16. "Just download the video"
A second mode, chosen with a toggle at the top of the paste card, that
downloads the video as-is and skips frame extraction entirely.

- **Accepted links**: YouTube (same as frame mode) plus **Instagram, Facebook
  and TikTok** — yt-dlp already supports all four, so no extra dependency.
  Host allowlist lives in `core._DOWNLOAD_HOSTS`; validated by
  `core.validate_download_url()`, kept separate from `validate_url()` so frame
  extraction stays YouTube-only.
- **Folder naming, sequence numbering and title-cleaning are unchanged** —
  reuses `safe_title()` and `next_sequence_number()` so Recent history stays
  one consistent list regardless of mode.
- **Manifest is different on purpose**: `{"mode": "video_only", "video_id",
  "title", "url", "uploader", "extracted_on", "duration_seconds",
  "frame_width", "frame_height", "source_video"}`. No `frames` array, no
  `interval_seconds`, no `frame_count` — a transcript matcher has nothing to
  match against a video with no extracted frames.
- **The "Keep the video file" checkbox does not apply to this mode** — the
  whole point is the video, so it is always kept. The UI hides that checkbox
  and the interval selector when this mode is active.
- Implemented as `core.download_only()`, a sibling to `core.process()` — not
  a branch inside it, because the frame-extraction path has cancellation and
  cleanup logic (`extract_frames`, `plan_timestamps`) that download-only never
  touches.
- CLI: `python extract.py <link> --video-only`.
- A queue can mix both modes in one run — each queued item carries its own
  `mode`, decided by the toggle at the moment it was added.

---

## Transcripts (added 2026-09-05)

### 17. "Also get the script"
A checkbox in the setup view that adds a spoken-word transcript to a run. It
works with **both** modes - frames and "just download the video" - because a
transcript is almost always wanted *alongside* the frames, not instead of them.

Decided by Galvin on 2026-09-05: model `medium`, a checkbox (not a third mode),
and the model downloads on first use rather than shipping inside the .exe.

**Engine: faster-whisper, model `medium`.**
`faster-whisper` is the CTranslate2 build of OpenAI's Whisper. Chosen over
YouTube's own auto-captions because auto-captions have no punctuation and no
sentence boundaries, which makes them poor input for a vision+text analysis.

**YouTube captions are the fallback, not the default.** If Whisper cannot run
(library missing, or the model is not cached and there is no network), we fall
back to yt-dlp's caption track so the run still produces something. The
`source` field in `transcript.json` records which one was used.

### 18. GPU, and the DLL trap
`medium` runs on the GPU when one is usable, and falls back to CPU `int8`
otherwise. Verified on Galvin's RTX 5060 Ti at ~10x realtime on a cold 19s clip
(warm runs on longer videos are far faster).

**The trap:** CTranslate2 loads `cublas64_12.dll` and cuDNN *lazily*, with a
plain `LoadLibrary`. Those DLLs ship inside the `nvidia-cublas-cu12` and
`nvidia-cudnn-cu12` pip packages, in `site-packages/nvidia/*/bin`, which is not
on the DLL search path. Symptom is a load that appears to succeed followed by
`RuntimeError: Library cublas64_12.dll is not found or cannot be loaded` at the
first encode.

`os.add_dll_directory()` does **not** fix it - a plain `LoadLibrary` ignores it.
The fix is to prepend those folders to `os.environ["PATH"]` *before* the first
transcribe, which is what `core._enable_cuda_dlls()` does. Do not "clean this
up" into `add_dll_directory`; it was tried and it does not work.

The model is loaded **once per process** and cached in `core._WHISPER_CACHE`, so
a queue of ten videos pays the ~3 s load once.

### 19. transcript.json
Written into the run folder beside `manifest.json`. Same float discipline as the
manifest, for the same reason - a matcher depends on it.

```json
{
  "source": "whisper",
  "model": "medium",
  "device": "cuda",
  "language": "en",
  "duration_seconds": 19.014,
  "segment_count": 2,
  "text": "the whole transcript as one string",
  "segments": [
    { "index": 0, "start": 1.02, "end": 13.82, "text": "Alright, so here we are..." }
  ]
}
```

- `start` and `end` are **always JSON floats**, seconds from the start of the
  video, never `MM:SS` and never strings. Enforced with `float(round(x, 2))`.
- `index` is contiguous from 0.
- `segments` is **segment-level, not word-level.** Whisper is still *run* with
  `word_timestamps=True`, because that measurably improves where the segment
  boundaries land, but the per-word list is discarded before writing. A 30
  minute video at word level is a quarter of a megabyte of JSON and burns
  context for no analytical gain.
- `source` is `"whisper"` or `"captions"`. `device` is `"cuda"` or `"cpu"`.
- UTF-8, `ensure_ascii=False`, like the manifest.

`transcript.txt` is written next to it - the same content as `[M:SS] line`
text, for reading and for pasting straight into a chat.

`manifest.json` gains a `"transcript"` key: `"transcript.json"` when one was
made, `null` when it was not. This is additive; every existing reader keeps
working.

### 20. Rules that must not drift
- **Cancelling still leaves nothing behind.** Transcription happens *before*
  the manifest is written, and a cancel during it deletes the part-finished
  folder exactly like a cancel during frame extraction.
- **A failed transcript never fails the run.** If Whisper falls over, the
  frames are still correct and still worth keeping - the run finishes, the
  manifest records `"transcript": null`, and the reason is put in
  `"transcript_error"`. Losing 30 frames because the audio was silent would be
  absurd.
- **Frame timestamps and transcript timestamps are the same clock** - seconds
  from the start of the same `source.mp4`. That is the whole point; nothing may
  offset one and not the other.
- CLI: `python extract.py <link> --transcript` (works with `--video-only` too).

## Dependencies
- Python 3.13
- `yt-dlp` (pip)
- `pywebview` (pip) — only needed for the app window, not the CLI
- FFmpeg — `ffmpeg` and `ffprobe` must both be on PATH. Called via `subprocess`,
  deliberately not the `ffmpeg-python` wrapper, to keep dependencies minimal.
- Pillow (pip) — only to regenerate the icon, not needed to run anything
- `faster-whisper` (pip) — only for transcripts. Pulls in `ctranslate2` and
  `av`. For GPU also `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` (see 18).
  Not needed for frames or plain downloads.

## Not built yet
- Sending frames to the vision API
- Deleting individual frames from a finished run (deliberately skipped: it would
  renumber `index` and force a manifest rewrite, which risks the timestamp
  guarantee. Whole runs can be deleted from the Recent list.)
