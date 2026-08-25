# HANDOFF — Video Analyzer
Updated: 2026-08-25 SGT

## What this project is
A command-line tool that takes a YouTube link, downloads the video, and saves
screenshots taken at even intervals through it — each named with the exact second
it came from — plus a `manifest.json` listing every frame and its timestamp. The
frames are meant to be fed to Claude's vision API and matched against a
separately generated timestamped transcript.

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

Not yet done: Galvin has not run it himself, and it has never been pointed at one
of his own videos (all testing used a 19s public clip and a synthetic 200s file).

## Last commit
`479888c` — feat(extract): add YouTube frame extractor with timestamped manifest
(pushed: **no** — repo is local only, no GitHub remote created yet)

## How to launch
```
python extract.py <youtube_url>
```
Output lands in `frames/<N> - <Title> - <D-M-YYYY>/`. There is a sample run left
in place at `frames/1 - Me at the zoo - 25-8-2026/` to look at.

Optional: `--interval N` (only 1 2 3 5 10 30 60), `--outdir PATH`, `--no-keep-video`.

## In progress / next steps
1. **Ask Galvin whether to create a GitHub repo** under `gosubay` and push. Nothing
   is backed up off this machine right now.
2. Galvin to run it on one of his own videos and confirm the folder naming reads
   the way he wants in Explorer.
3. Build the transcript step — it must emit timestamps in seconds as floats to
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
- Videos over 30 minutes produce more than 30 frames (60s is the top of the
  ladder). Accepted — Galvin said he mostly analyses short videos. A `--max-frames`
  cap is the obvious fix if that ever bites.

Safe to close the window — everything is committed locally and the full spec is in
CLAUDE.md.
