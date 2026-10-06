#!/usr/bin/env python3
"""
Zip the built folder into the file Galvin actually sends people.

Run by build_exe.bat after PyInstaller finishes. Writes
release/VideoAnalyzer-v<VERSION>-windows.zip
"""

import sys
import time
import zipfile
from pathlib import Path

VERSION = "1.1"

HERE = Path(__file__).parent.resolve()
ROOT = HERE.parent
DIST = ROOT / "dist" / "Video Analyzer"
TARGET = HERE / f"VideoAnalyzer-v{VERSION}-windows.zip"


def main():
    if not DIST.is_dir():
        print(f"Nothing to zip - {DIST} does not exist. Run the build first.")
        return 1

    files = [p for p in DIST.rglob("*") if p.is_file()]
    raw = sum(p.stat().st_size for p in files)
    print(f"  zipping {len(files)} files, {raw / 1048576:.0f} MB raw...")

    started = time.time()
    if TARGET.exists():
        TARGET.unlink()

    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for index, path in enumerate(files, 1):
            # Everything sits under one folder so unzipping never sprays files
            # across the user's Downloads.
            bundle.write(path, Path("Video Analyzer") / path.relative_to(DIST))
            if index % 200 == 0:
                print(f"    {index}/{len(files)}...", flush=True)

    size = TARGET.stat().st_size / 1048576
    print(f"  wrote {TARGET.name} - {size:.0f} MB in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
