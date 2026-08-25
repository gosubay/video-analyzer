# Video Analyzer

Give it a YouTube link. It gives you back a folder of screenshots taken at even
intervals through the video, each one named with the exact second it came from,
plus a `manifest.json` listing them all.

The point: you can hand those frames to Claude's vision API and line them up
against a timestamped transcript, because the picture named `frame_0090.0s.jpg`
really is the picture at 90 seconds.

## One-time setup

1. Install FFmpeg (if `ffmpeg -version` in a terminal errors, you don't have it):
   ```bash
   winget install Gyan.FFmpeg
   ```
   Close and reopen your terminal afterwards.

2. Install the two Python bits:
   ```bash
   pip install yt-dlp pywebview
   ```

The launcher checks for all of this and offers to fix it, so you can skip step 2
and let it do the work the first time you open the app.

## Using it

**Double-click Video Analyzer** — the shortcut with the purple film icon. A proper
app window opens.

- Paste a link and press **Add**. It looks the video up and shows you the title,
  the channel, how long it is and how many frames it's about to make — *before*
  downloading anything.
- Add more links if you want. They run one after another.
- Press **Let's go**. Watch the progress, or press **Stop** if you change your mind.
- When it's done you get a grid of every frame it grabbed. Click one to see it
  full size, arrow keys to flick through.
- **It stays open.** Press "Do another one" and go again.

Past runs are listed down the left. Click one to open its folder.

If the shortcut is missing — it isn't stored in the repo, because a shortcut
remembers the exact folder it was made in — recreate it:

```bash
powershell -ExecutionPolicy Bypass -File assets\make_shortcut.ps1 -Desktop
```

Leave off `-Desktop` if you don't want a copy on your desktop.

### From a terminal instead

The command line still works and does exactly the same thing:

```bash
python extract.py https://www.youtube.com/watch?v=jNQXAC9IVRw
```

| Option | What it does |
|---|---|
| `--interval N` | Force the gap between frames. Only `1 2 3 5 10 30 60` are allowed. |
| `--outdir PATH` | Put the video folders somewhere other than `./frames`. |
| `--no-keep-video` | Don't save the downloaded video next to the frames. |

## What you get

```
frames/
  1 - Me at the zoo - 25-8-2026/
      frame_0000.0s.jpg
      frame_0001.0s.jpg
      frame_0002.0s.jpg
      ...
      manifest.json
      source.mp4
```

The number in front of the folder counts up every time you run it, so your videos
stay in the order you processed them.

## How many frames you get

It aims for about 30 frames per video and picks the gap from a fixed list —
1, 2, 3, 5, 10, 30 or 60 seconds:

| Video length | Gap | Frames |
|---:|---:|---:|
| 30 seconds | 1s | 30 |
| 1 minute | 2s | 30 |
| 90 seconds | 3s | 30 |
| 5 minutes | 10s | 30 |
| 15 minutes | 30s | 30 |
| 30 minutes | 60s | 30 |
| 1 hour | 60s | 60 |

Anything up to half an hour gives you 30 frames or fewer. Longer than that and
the count climbs, because 60 seconds is the biggest gap available. You can always
override it with the dropdown next to the Go button.

## The icon

`assets/icon.ico` is generated, not hand-drawn. To change it, edit
`assets/make_icon.py` and run:

```bash
python assets/make_icon.py
```

That needs Pillow (`pip install Pillow`). It writes the `.ico` at every size
Windows asks for, plus `icon-preview.png` so you can see it large.

## If something goes wrong

The app tells you in one plain sentence — private video, deleted video, no
internet, and so on. A failed video in a queue doesn't stop the others.

If the window won't open at all, look at **debug.log** in this folder. It records
every startup, so it will usually say what stopped it.

## How it's put together

| File | What it is |
|---|---|
| `core.py` | The engine. Downloading, frame extraction, the manifest. |
| `extract.py` | The command line, a thin wrapper over `core.py`. |
| `server.py` | A tiny web server on your own machine that the window talks to. |
| `app.py` | Opens the app window. |
| `ui/` | The page itself — layout, styling, mascot. |

Full technical spec and the rules that must not be broken: [CLAUDE.md](CLAUDE.md)
