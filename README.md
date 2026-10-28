# detect-motion

A simple motion detector that scans videos and classifies each clip as containing movement or not, using OpenCV.

## Installation

```bash
uv sync
```

The Docker-based runners need Docker Desktop (Windows/macOS) or Docker Engine (Linux).

## Usage

### On Windows

Copy your videos into `D:\videos`, then run `build-and-run.bat`.
It builds the `detect-motion:latest` Docker image, smoke-tests it by printing the version, and starts the container on that folder.
Clips containing movement are moved to `D:\videos-keep`, clips without movement go to `D:\videos-drop`, and the JSON report is written to `D:\videos-keep\motion-report.json`.
Progress is printed as each clip finishes, and because `--move` is the default, the input folder is emptied during the run rather than only at the end.

### Command line

```bash
# Scan default input directory
uv run detect-motion

# Scan specific files with progress meter
uv run detect-motion /data/video/MOVI0000.AVI --progress

# Keep moving videos, delete the rest
uv run detect-motion --output-dir /data/keep --move --delete --yes

# Dry run (analyse only, no filesystem changes)
uv run detect-motion --dry-run

# Show version
uv run detect-motion --version
```

## CLI

```
videos              video files, globs or directories
--input-dir         folder scanned when no file given (default: /data/video)
--profile           filter preset: noisy, balanced, sensitive
--method            mog2 (background model) or diff (frame differencing)
--width             working width in pixels (profile default)
--frame-stride      analyse every Nth frame
--min-area-ratio    min moving area as a fraction of the frame
--exclude           ignore a region (X,Y,W,H fractions), repeatable
--output-dir        copy/move kept videos here
--move              move instead of copy
--delete            delete videos with no movement (requires --yes)
--yes               confirm irreversible operations
--drop-dir          move rejected videos instead of deleting
--dry-run           analyse only, never modify files
--report            write JSON report ('-' for stdout)
--workers           number of parallel worker processes
--progress / -p     show progress meter [i/N] p%
--quiet             suppress progress output
--version           show version and exit
```

Each clip is moved (or copied/deleted) as soon as its own analysis finishes,
so the input folder drains during the run instead of at the very end. The
report is written once, after the last clip.

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run formatter
uv run ruff format src tests

# Run linter
uv run ruff check src tests

# Run type checker
uv run mypy src

# Run tests
uv run pytest
```

## Project layout

```
.
├── pyproject.toml          # project metadata & tool config
├── README.md               # this file
├── build-and-run.bat       # Windows: build the image, then scan a folder
├── run-detect-motion.bat   # Windows: run the image on a folder
├── run-detect-motion.sh    # Linux/macOS: run the image on a folder
├── .devcontainer/          # Dockerfile, entrypoint, devcontainer config
├── src/
│   └── detect_motion/
│       ├── __init__.py     # public API & version
│       ├── __main__.py     # python -m detect_motion entry
│       ├── cli.py          # argument parsing, main()
│       └── detector.py     # analysis engine (analyse_video + VideoResult)
└── tests/                  # pytest suite
    ├── conftest.py         # shared fixtures
    ├── test_cli.py         # CLI tests
    └── test_detector.py    # engine tests
```
