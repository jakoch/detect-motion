"""Command-line interface for detect-motion."""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .detector import VideoResult, analyse_video

DEFAULT_INPUT_DIR = "/data/video"
DEFAULT_PATTERN = "*"
DEFAULT_REPORT = "motion-report.json"
VIDEO_SUFFIXES = {
    ".avi",
    ".mp4",
    ".mov",
    ".mkv",
    ".m4v",
    ".wmv",
    ".mpg",
    ".mpeg",
    ".webm",
}

# Filter presets. Every preset value can be overridden on the command line.
#   noisy     - grainy low-light footage: rejects sensor grain hard
#   balanced  - middle ground: keeps more detail, tolerates more noise
#   sensitive - small and faint objects, at the cost of false alarms
PROFILES: dict[str, dict[str, object]] = {
    "noisy": {
        "width": 320,
        "blur": 15,
        "open": 9,
        "dilate": 3,
        "min_area_ratio": 0.005,
        "min_motion_ratio": 0.002,
        "mog_var_threshold": 96.0,
        "temporal": 1,
    },
    "balanced": {
        "width": 480,
        "blur": 11,
        "open": 7,
        "dilate": 3,
        "min_area_ratio": 0.003,
        "min_motion_ratio": 0.0015,
        "mog_var_threshold": 64.0,
        "temporal": 1,
    },
    "sensitive": {
        "width": 640,
        "blur": 9,
        "open": 5,
        "dilate": 3,
        "min_area_ratio": 0.0015,
        "min_motion_ratio": 0.001,
        "mog_var_threshold": 32.0,
        "temporal": 1,
    },
}
# --min-area was removed from the CLI: --min-area-ratio (fraction of frame) is
# the resolution-independent control. The pixel floor was already dominated by
# the ratio at every practical working width.


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    p = argparse.ArgumentParser(
        description="Detect videos containing movement and optionally keep them.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "videos",
        nargs="*",
        help="video files, globs or directories (default: all videos in --input-dir)",
    )
    p.add_argument(
        "--input-dir",
        default=DEFAULT_INPUT_DIR,
        help="folder scanned when no file given",
    )

    g = p.add_argument_group("detection")
    g.add_argument(
        "--profile",
        choices=tuple(PROFILES),
        default="noisy",
        help="filter preset: noisy (grainy footage, fewest false alarms), "
        "balanced, sensitive (small/faint objects, more false alarms). "
        "Explicit flags always override the preset",
    )
    g.add_argument(
        "--method",
        choices=("mog2", "diff"),
        default="mog2",
        help="mog2: learned background model (sensitive to slow motion, "
        "slower); diff: frame differencing (faster). MOG2 is "
        "high-accuracy/low-speed; diff is better when throughput matters",
    )
    g.add_argument(
        "--width",
        type=int,
        default=None,
        help="working width in pixels (profile default)",
    )
    g.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="analyse every Nth frame",
    )
    g.add_argument(
        "--min-area-ratio",
        type=float,
        default=None,
        help="min moving area as a fraction of the frame",
    )
    g.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help="ignore a region, as fractions of width/height (0-1). Repeatable. "
        "Useful for fixed cameras: burned-in clocks, trees, rain",
    )

    o = p.add_argument_group("output")
    o.add_argument("--output-dir", help="copy/move kept videos here")
    o.add_argument("--move", action="store_true", help="move instead of copy")
    o.add_argument(
        "--delete",
        action="store_true",
        help="DELETE videos classified as having no movement "
        "(irreversible, requires --yes). Prefer --drop-dir",
    )
    o.add_argument(
        "--yes",
        action="store_true",
        help="confirm the irreversible parts of the run (required by --delete)",
    )
    o.add_argument(
        "--drop-dir",
        help="move rejected videos here instead of deleting them; the "
        "recoverable alternative to --delete",
    )
    o.add_argument(
        "--dry-run",
        action="store_true",
        help="analyse and report only: never move, copy, delete",
    )
    o.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        help="write a JSON report ('-' for stdout)",
    )
    o.add_argument(
        "--workers",
        type=int,
        default=min(8, (os.cpu_count() or 2)),
    )
    o.add_argument(
        "--progress",
        "-p",
        action="store_true",
        help="show a simple progress meter [i/N] p%% for each video",
    )
    o.add_argument("--quiet", action="store_true")
    o.add_argument(
        "--version",
        action="store_true",
        help="show version information and exit",
    )
    return p


def apply_profile(args: argparse.Namespace) -> None:
    """Fill unset preset-tunable flags from the selected profile."""
    for key, value in PROFILES[args.profile].items():
        if getattr(args, key, None) is None:
            setattr(args, key, value)


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject nonsensical values at parse time."""

    def at_least(name: str, minimum: int | float) -> None:
        value = getattr(args, name, None)
        if value is None:
            return
        if value < minimum:
            parser.error(f"--{name.replace('_', '-')} must be >= {minimum} (got {value})")

    def within(name: str, low: float, high: float) -> None:
        value = getattr(args, name, None)
        if value is None:
            return
        if not (low <= value <= high):
            parser.error(
                f"--{name.replace('_', '-')} must be between {low} and {high} (got {value})"
            )

    at_least("frame_stride", 1)
    at_least("width", 16)
    at_least("min_area_ratio", 0.0)
    at_least("workers", 1)
    within("min_motion_fraction", 0.0, 1.0)
    within("max_motion_fraction", 0.0, 1.0)


def collect_videos(paths: list[str], input_dir: str, pattern: str) -> list[str]:
    """Collect video files from paths, globs, directories, or the input dir."""
    found: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            found += sorted(glob.glob(os.path.join(p, pattern)))
        elif any(ch in p for ch in "*?["):
            found += sorted(glob.glob(p))
        else:
            found.append(p)
    if not paths:
        found += sorted(glob.glob(os.path.join(input_dir, pattern)))
    # De-dup, keep order.
    seen: set[str] = set()
    out: list[str] = []
    for f in found:
        if f in seen:
            continue
        if Path(f).suffix.lower() in VIDEO_SUFFIXES and os.path.isfile(f):
            seen.add(f)
            out.append(f)
    return out


def select_videos(
    files: list[str],
    sort_key: str = "mtime",
    newest_first: bool = False,
    limit: int = 0,
) -> list[str]:
    """Order files by timestamp and cut the list down to ``limit`` entries."""
    if sort_key == "name":
        key = lambda f: (Path(f).name, f)  # noqa: E731
    else:
        getter = {"mtime": os.path.getmtime, "ctime": os.path.getctime}.get(
            sort_key, os.path.getmtime
        )

        def key(f: str):  # noqa: E306
            try:
                stamp = getter(f)
            except OSError:
                stamp = 0.0
            return (stamp, Path(f).name, f)

    ordered = sorted(files, key=key)
    if newest_first:
        ordered.reverse()
    return ordered[:limit] if limit > 0 else ordered


def place_file(src: str, out_dir: Path, move: bool) -> str:
    """Copy or move ``src`` into ``out_dir``, handling name collisions."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / Path(src).name
    i = 1
    while dest.exists():
        dest = out_dir / f"{Path(src).stem}_{i}{Path(src).suffix}"
        i += 1
    if move:
        shutil.move(src, dest)
    else:
        shutil.copy2(src, dest)
    return str(dest)


def apply_defaults(args: argparse.Namespace) -> None:
    """Fill non-profile defaults for flags removed from the CLI.

    Motion-ratio and morphology values are intentionally absent: they come from
    the profile via apply_profile(), so setting them here would mask the preset.
    """
    args.pattern = DEFAULT_PATTERN
    args.limit = 0
    args.sort_key = "mtime"
    args.newest = False
    args.adaptive = True
    args.min_motion_frames = 10
    args.min_motion_fraction = 0.01
    args.max_motion_fraction = 0.60


def apply_result(res: VideoResult, args: argparse.Namespace) -> tuple[str, int]:
    """Act on one finished video immediately.

    Returns ``(tag, bytes_freed)``: a short label for the progress line and the
    size of a deleted file. Acting per clip means the input folder drains as the
    scan proceeds instead of only after every clip has been analysed.
    """
    if args.dry_run or res.status == "error":
        return "", 0
    try:
        if res.status == "keep":
            if not args.output_dir:
                return "", 0
            res.moved_to = place_file(res.path, Path(args.output_dir), args.move)
            return ("moved to keep" if args.move else "copied to keep"), 0
        if args.drop_dir:
            place_file(res.path, Path(args.drop_dir), move=True)
            return "moved to drop", 0
        if args.delete:
            size = os.path.getsize(res.path)
            os.remove(res.path)
            res.deleted = True
            return "deleted", size
    except OSError as exc:
        # Keep scanning: one unreadable/locked file must not abort the batch.
        res.reason = f"{res.reason}; action failed: {exc}".lstrip("; ")
        return "action failed", 0
    return "", 0


def main(argv: list[str] | None = None) -> int:
    """Run the detect-motion CLI.

    Returns an exit code: 0 always (unless --delete with no --yes returns 2).
    """
    parser = build_parser()

    # Docker attaches stdout through a pipe, which Python block-buffers. Force
    # line buffering so progress lines appear while the scan is running.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    args = parser.parse_args(argv)

    if args.version:
        from detect_motion import __version__

        print(f"Simple Motion Detector v{__version__}")
        print("Copyright (c) 2025-2026 Jens A. Koch")
        return 0

    # Tier 2: sensible defaults for flags removed from the CLI.
    # Profile-specific values (blur, open, dilate, temporal, mog_var_threshold,
    # min_area_ratio, min_motion_ratio) are filled in by apply_profile().
    apply_defaults(args)
    apply_profile(args)
    validate_args(parser, args)
    found = collect_videos(args.videos, args.input_dir, args.pattern)
    if not found:
        print(
            f"no videos found in {args.input_dir} matching {args.pattern}",
            file=sys.stderr,
        )
        return 1
    videos = select_videos(found, args.sort_key, args.newest, args.limit)

    # --delete is irreversible: require explicit confirmation, and point at the
    # recoverable alternative.
    if args.delete and not args.yes:
        print(
            "--delete is irreversible. Re-run with --yes to confirm, or use "
            "--drop-dir DIR to move rejected videos somewhere recoverable.",
            file=sys.stderr,
        )
        return 2

    # When --report writes JSON to stdout, progress goes to stderr so it is
    # not polluted.
    progress = sys.stderr if args.report == "-" else sys.stdout
    if not args.quiet:
        scope = f"{len(videos)} of {len(found)} video(s), oldest first by mtime"
        print(
            f"scanning {scope} with {args.workers} worker(s), "
            f"method={args.method}, adaptive={args.adaptive}",
            file=progress,
        )

    started = time.time()
    results: list[VideoResult] = []
    total = len(videos)
    done = 0
    deleted_bytes = 0

    if args.dry_run:
        args.output_dir = None
        args.delete = args.drop_dir = False
        if not args.quiet:
            print(
                "dry run: nothing will be moved, copied or deleted",
                file=progress,
            )

    def _record(res: VideoResult) -> None:
        """Act on a finished clip, then print its progress line."""
        nonlocal done, deleted_bytes
        tag, freed = apply_result(res, args)
        deleted_bytes += freed
        done += 1
        suffix = f"  -> {tag}" if tag else ""
        if args.progress and not args.quiet:
            pct = done * 100 // total
            print(
                f"  [{done}/{total}] {pct:3d}% {Path(res.path).name:20s} {res.summary()}{suffix}",
                file=progress,
            )
        elif not args.quiet:
            print(f"  {Path(res.path).name:20s} {res.summary()}{suffix}", file=progress)

    if args.workers > 1 and len(videos) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            # Report and act on each clip as soon as it finishes: with ordered
            # results a single long clip at the head of the queue hides all
            # progress (and delays every move behind it).
            futures = {pool.submit(analyse_video, v, args): v for v in videos}
            for future in as_completed(futures):
                res = future.result()
                results.append(res)
                _record(res)
        # Completion order is arbitrary; restore the oldest-first input order.
        position = {path: index for index, path in enumerate(videos)}
        results.sort(key=lambda r: position.get(r.path, len(videos)))
    else:
        for v in videos:
            res = analyse_video(v, args)
            results.append(res)
            _record(res)

    kept = [r for r in results if r.status == "keep"]
    dropped = [r for r in results if r.status == "drop"]
    errors = [r for r in results if r.status == "error"]

    elapsed = time.time() - started
    report = {
        "settings": dict(vars(args)),
        "summary": {
            "scanned": len(results),
            "kept": len(kept),
            "dropped": len(dropped),
            "errors": len(errors),
            "frames_processed": sum(r.frames_total for r in results),
            "throughput_fps": round(sum(r.frames_total for r in results) / max(elapsed, 1e-9), 1),
            "deleted": sum(1 for r in results if r.deleted),
            "deleted_bytes": deleted_bytes,
            "elapsed_s": round(elapsed, 2),
        },
        "kept": [Path(r.path).name for r in kept],
        "deleted": [Path(r.path).name for r in results if r.deleted],
        "results": [vars(r) for r in results],
    }
    if args.report == "-":
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2)

    if not args.quiet:
        print(
            f"\nkept {len(kept)}/{len(results)} video(s): "
            f"{', '.join(Path(r.path).name for r in kept) or '-'}",
            file=progress,
        )
        for r in errors:
            print(f"  !! {Path(r.path).name}: {r.reason}", file=progress)
        print(
            f"report: {args.report}  ({report['summary']['elapsed_s']}s)",
            file=progress,
        )

    return 0
