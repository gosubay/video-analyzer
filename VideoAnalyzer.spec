# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller recipe for the shareable Windows release.

Build with:  build_exe.bat        (or: pyinstaller VideoAnalyzer.spec --noconfirm)

One-folder build, not one-file. One-file would re-extract ~450 MB of FFmpeg into
a temp folder on every single launch, which looks like the app has frozen.

FFmpeg and ffprobe are copied in as plain data, not as `binaries`. They are
self-contained executables - letting PyInstaller scan them for dependencies is
slow and pointless.
"""

import shutil
from pathlib import Path

APP_NAME = "Video Analyzer"
HERE = Path(SPECPATH)


def ffmpeg_pair():
    """Find ffmpeg and ffprobe to ship. Prefer a local bin/, else the PATH."""
    found = []
    for name in ("ffmpeg", "ffprobe"):
        local = HERE / "bin" / f"{name}.exe"
        source = str(local) if local.is_file() else shutil.which(name)
        if not source:
            raise SystemExit(
                f"Cannot find {name}.exe. Install FFmpeg (winget install Gyan.FFmpeg) "
                f"or drop {name}.exe into a bin\\ folder next to this spec."
            )
        found.append((source, "bin"))
    return found


datas = [
    (str(HERE / "ui"), "ui"),
    (str(HERE / "assets" / "icon.ico"), "assets"),
    (str(HERE / "assets" / "icon-preview.png"), "assets"),
    *ffmpeg_pair(),
]

hiddenimports = [
    # pywebview picks its Windows backend at runtime, so PyInstaller cannot see it
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr_loader",
    "clr_loader.netfx",
    "pythonnet",
    # yt-dlp loads extractors dynamically
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.compat",
]

excludes = [
    "tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL",
    "pytest", "IPython", "notebook", "setuptools", "pip",
]

a = Analysis(
    ["app.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX mangles the FFmpeg binaries
    console=False,             # no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
