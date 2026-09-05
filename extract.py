#!/usr/bin/env python3
"""
Video Analyzer - command line.

Usage:  python extract.py <youtube_url_or_video_file> [--interval N] [--outdir PATH]
                         [--no-keep-video] [--video-only] [--transcript]

This is a thin wrapper. All the real work - and the locked spec for the interval
ladder, folder naming, manifest schema and per-frame seeking - lives in core.py
and is documented in CLAUDE.md.
"""

import argparse
import sys

import core


def log(msg=""):
    print(msg, flush=True)


def run(args):
    state = {"stage": None, "last_pct": -1, "last_tr": -1}

    def on_stage(stage, data):
        if stage == "download":
            percent = data.get("percent", 0.0)
            if percent >= state["last_pct"] + 10:
                state["last_pct"] = percent
                total = data.get("total_bytes")
                size = f"  ({total / 1024 / 1024:.1f} MB)" if total else ""
                log(f"  downloading... {int(percent)}%{size}")
        elif stage == "metadata":
            if state["stage"] != "metadata":
                state["stage"] = "metadata"
                log(f"  got it: {data.get('title')}")
        elif stage == "extract":
            done, total = data.get("done", 0), data.get("total", 0)
            if done == 0:
                log("")
                log(f"Extracting {total} frames...")
            else:
                log(f"  extracting frame {done} of {total}...")
        elif stage == "transcribe":
            percent = data.get("percent", 0.0)
            if state["stage"] != "transcribe":
                state["stage"] = "transcribe"
                log("")
                log("Listening for the script...")
            elif percent >= state["last_tr"] + 20:
                state["last_tr"] = percent
                log(f"  transcribing... {int(percent)}%")
        elif stage == "saving":
            log("  writing manifest...")

    log("Working...")

    if args.video_only:
        result = core.download_only(
            args.source, out_root=args.outdir,
            transcript=args.transcript, on_stage=on_stage,
        )
        log("")
        log("Done. Video saved to:")
        log(f"  {result['folder']}")
        report_transcript(result)
        return 0

    result = core.process(
        args.source,
        out_root=args.outdir,
        interval=args.interval,
        keep_video=args.keep_video,
        transcript=args.transcript,
        on_stage=on_stage,
    )

    log("")
    log(f"Done. {result['frame_count']} frames written to:")
    log(f"  {result['folder']}")
    log("  manifest: manifest.json")
    report_transcript(result)
    return 0


def report_transcript(result):
    """One line about the script, whether it worked or not."""
    if result.get("transcript"):
        log(f"  transcript: {result['transcript']} (and transcript.txt)")
    elif result.get("transcript_error"):
        log(f"  no transcript: {result['transcript_error']}")


def main():
    if hasattr(sys.stdout, "reconfigure"):           # emoji-safe output on Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Turn a YouTube video into timestamped frames for vision analysis."
    )
    parser.add_argument("source", help="YouTube video URL, or a path to a video file")
    parser.add_argument(
        "--interval", type=int, choices=core.INTERVAL_LADDER, default=None,
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
    parser.add_argument(
        "--video-only", action="store_true",
        help="Just download the video - no frames. Also accepts Instagram, Facebook and TikTok links.",
    )
    parser.add_argument(
        "--transcript", action="store_true",
        help="Also write transcript.json and transcript.txt - the spoken words with timings.",
    )
    parser.set_defaults(keep_video=True)
    args = parser.parse_args()

    try:
        return run(args)
    except core.ExtractError as exc:
        log("")
        log(f"ERROR: {exc}")
        return 1
    except core.Cancelled:
        log("\nCancelled.")
        return 130
    except KeyboardInterrupt:
        log("\nCancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
