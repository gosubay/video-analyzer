# HANDOFF — Video Analyzer
Updated: 2026-08-25 SGT (session 1)

## What this project is
A Windows app that takes a YouTube link, downloads the video, and saves
screenshots taken at even intervals through it — each named with the exact second
it came from — plus a `manifest.json` listing every frame and its timestamp. The
frames are meant to be fed to Claude's vision API and matched against a
separately generated timestamped transcript.

There are two front ends over one engine (`core.py`): a desktop window
(`app.py` + `server.py` + `ui/`) and the original command line (`extract.py`).

## Current status
v1 works end to end and has been run and verified in this session.

Proven:
- Real download + extraction against a live YouTube video (`Me at the zoo`, 19s).
- **Timestamp accuracy verified visually** against a purpose-built 200s test video
  with the time burned into every frame — `frame_0000.0s`, `frame_0090.0s` and
  `frame_0190.0s` contained exactly `t = 0.000000 s`, `t = 90.000000 s` and
  `t = 190.000000 s`.
- Interval ladder across 17 durations from 10s to 1 hour.
- Manifest integrity: floats not ints, filename agrees with timestamp, contiguous
  indexes, alphabetical order == chronological order, every listed file exists.
- Error paths: non-YouTube host, dead video ID, missing argument, off-ladder
  `--interval` — all print one plain sentence and exit 1.
- Folder sequence numbering (`1 - ...` then `2 - ...`), `youtu.be` short links,
  `--interval` and `--no-keep-video` flags.

**Galvin has run it himself** — `frames/2 - What Is Simping 🤔 - 25-8-2026`, a 40s
video with an emoji and a `?` in the title. Folder name, manifest and all 20
frames came out correct.

The app window is also proven, driven end to end through its own API in this
session:
- full run: inspect → queue → download → extract → results, frames visible
- cancel mid-extraction: stops, and leaves **no** part-finished folder behind
- a queue of two where the second video is dead: the good one still finishes,
  the dead one is marked failed with a plain sentence
- bad input (Vimeo link, gibberish, deleted video) rejected before queueing
- window verified open, visible, 1180x820, with the app icon applied

Not yet done: Galvin has not clicked around the new window himself.

## Last commit
`fb02383` — feat(ui): add desktop app window with queue, cancel and frame grid
(pushed: **yes** — https://github.com/gosubay/video-analyzer, **private**, branch `main`)

## How to launch
Double-click **Video Analyzer.lnk** in the project folder (purple film icon). It
checks Python/FFmpeg/packages, then opens the app window and closes itself.

To see the UI in a browser while working on it (no window, live reload by hand):
```
python server.py 8730      then open http://127.0.0.1:8730/
```
To screenshot the UI without a visible browser pane:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --window-size=1180,820 --screenshot=out.png http://127.0.0.1:8730/
```
Command line still works and is unchanged:
```
python extract.py <youtube_url_or_video_file>
```
Output lands in `frames/<N> - <Title> - <D-M-YYYY>/`. There is a sample run left
in place at `frames/1 - Me at the zoo - 25-8-2026/` to look at.

Optional: `--interval N` (only 1 2 3 5 10 30 60), `--outdir PATH`, `--no-keep-video`.

## In progress / next steps
1. Galvin to open the new window and say what he wants changed.
2. Ask whether the repo should be flipped to public — it was created private
   because he did not say which he wanted.
3. Package as a .exe for friends (the `exe-release` skill) — pywebview bundles
   with PyInstaller, but FFmpeg still has to be found or shipped alongside.
4. Build the transcript step — it must emit timestamps in seconds as floats to
   match `manifest.json`. The downloaded `source.mp4` is kept beside the frames
   specifically so this step doesn't re-download.
4. Then the vision step: glob `frame_*.jpg` (already in time order), pair each with
   the transcript line covering its timestamp.

## Decisions made this session (don't re-litigate)
- Interval ladder `1 2 3 5 10 30 60`, smallest value keeping the video ≤30 frames —
  Galvin's call, replaces an earlier 1–3s clamp.
- Folder name `N - Title - D-M-YYYY` — Galvin's format, no ID, no slug.
- Date uses `-` not `/` — Windows treats `/` as a path separator, so `25/8/2026`
  would silently create nested folders. Not negotiable, Galvin was told.
- 720p download cap — vision API downsizes anything bigger anyway.
- Keep `source.mp4` beside the frames — saves a second download at transcript time.
- Per-frame `-ss` seeking, never the `fps=1/n` filter. See Gotchas.
- Date format `25-8-2026` confirmed acceptable by Galvin after the `/` problem
  was explained.
- Repo created **private** under `gosubay` — he asked for a repo but not which
  visibility, so the safe default was taken.
- UI is a local web page in a native window (pywebview / Edge WebView2), not
  tkinter — tkinter cannot do the soft-pastel look he picked.
- Look: **cute pastel with a mascot**, chosen by Galvin from four options. The
  mascot is a clapperboard with idle / working / done / error moods.
- All four optional features were requested and built: queue, cancel, copy-for-
  Claude, local video files.
- Deleting individual frames was deliberately NOT built — it would renumber
  `index` and force a manifest rewrite. Whole runs can be deleted from Recent.

## Gotchas
- **Never switch frame extraction to `ffmpeg -vf fps=1/n` as an optimisation.** It
  looks correct and is faster, but it emits the *last* frame of each interval
  bucket, putting frames up to half an interval late — a frame labelled 90.0s held
  the 94.97s picture. The reproduction recipe for the timecode test video is in
  CLAUDE.md section 5; run it before trusting any rewrite of that code.
- `round(0 * 1, 1)` in Python returns int `0`, not `0.0`, which silently wrote
  `"timestamp": 0` into the manifest. Fixed with an explicit `float()`. Any change
  to manifest construction needs the float check re-run.
- The last planned timestamp can land past the final decodable picture (a 19.014s
  video has no frame at 19.0s). This is handled — it logs and stops — but it means
  `frame_count` can be one less than a naive `duration / interval` calculation.
- Printing emoji titles breaks with a `UnicodeEncodeError` if stdout is redirected
  to a file on Windows. `main()` reconfigures stdout to UTF-8 to handle it; calling
  the module's functions directly from `python -c` bypasses that guard.
- The `.lnk` shortcut is gitignored on purpose — it hard-codes
  `C:\Claude\Code\Video Analyzer`, so a clone on another machine needs
  `assets/make_shortcut.ps1` re-run rather than the file copied.
- `assets/icon.ico` is generated by `assets/make_icon.py` (needs Pillow). Never
  hand-edit the .ico; change the script and re-run it.
- Testing the .bat from bash or PowerShell is painful because of quote handling
  around the space in the filename. What works: write a one-line wrapper .bat
  that `call`s it by full path, then pipe the URL into that wrapper.
- **Never read the clipboard with ctypes.** The first version did and segfaulted
  the entire app — `GetClipboardData` returns a 64-bit handle, ctypes defaults
  return types to 32-bit int, and locking the truncated handle killed Python. A
  segfault cannot be caught, so the window just vanished. It shells out to
  PowerShell now. Any ctypes call anywhere needs explicit `argtypes`/`restype`;
  `set_window_icon()` in app.py is the pattern to copy.
- **`Video Analyzer.bat` must stay pure ASCII.** cmd.exe reads a .bat by byte
  offset; one non-ASCII character (an em dash in a comment was enough) shifts
  that offset and cmd resumes parsing mid-word. It then ran fragments like
  '001' and 'yzer' as commands and took every branch at once, telling the user
  Python and FFmpeg were both missing when neither was. Check with
  `grep -c '[^ -~]' "Video Analyzer.bat"` - it must print 0.
- `[hidden] { display: none !important; }` at the top of style.css is load-
  bearing. Without it every `display: flex` rule beats the `hidden` attribute and
  the lightbox covers the whole app on load.
- The frame-count shown before a run comes from yt-dlp's duration (a whole
  number); the run itself uses ffprobe (exact). So the estimate can be one out —
  19 vs 20 on the test clip. Output is correct either way.
- The dev server must be run as `python server.py` (it serves in the main
  thread). An earlier version parked the main thread on an Event and the harness
  killed it as a segfault.
- Videos over 30 minutes produce more than 30 frames (60s is the top of the
  ladder). Accepted — Galvin said he mostly analyses short videos. A `--max-frames`
  cap is the obvious fix if that ever bites.

Safe to close the window — everything is committed and pushed to GitHub, and the
full spec is in CLAUDE.md.
