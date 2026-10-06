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

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

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

# Transcripts: faster-whisper and the native libraries under it. Each one
# carries DLLs or data files (the VAD model, CTranslate2's runtime) that
# PyInstaller's import scan alone does not pick up. Not collect_all - that also
# drags in their optional converter/tooling imports (transformers, cv2, ...)
# and triples the size of the release.
#
# The NVIDIA CUDA DLLs (nvidia-cublas-cu12 / nvidia-cudnn-cu12, ~1.8 GB) are
# deliberately NOT shipped - the release would not fit a GitHub upload. The
# built app transcribes on the CPU; core.transcribe() falls back by itself.
# The Whisper model is not shipped either, it downloads on first use.
binaries = []
for package in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers"):
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)
hiddenimports += ["faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers"]

excludes = [
    "tkinter", "matplotlib", "pandas", "scipy", "PIL",
    "pytest", "IPython", "notebook", "setuptools", "pkg_resources", "pip",
    # installed on the build machine for other projects - never needed here
    "torch", "torchaudio", "torchvision", "tensorflow", "nvidia",
    "transformers", "cv2", "llvmlite", "numba", "pyarrow", "sklearn", "sympy",
    "librosa", "soundfile", "tiktoken", "sentencepiece", "datasets", "onnx",
    "pydantic", "pydantic_core", "uvicorn", "fastapi", "watchfiles", "lxml",
    "pycountry", "whisper", "win32com", "pythonwin",
]

a = Analysis(
    ["app.py"],
    pathex=[str(HERE)],
    binaries=binaries,
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
