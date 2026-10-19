# detect-motion

A simple motion detector that scans videos and classifies each clip as containing movement or not, using OpenCV.

## Installation

```bash
uv sync
```

## Usage

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
--quarantine-dir    move rejected videos instead of deleting
--dry-run           analyse only, never modify files
--report            write JSON report ('-' for stdout)
--workers           number of parallel worker processes
--progress / -p     show progress meter [i/N] p%
--quiet             suppress progress output
--version           show version and exit
```

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
src/                      # project root
├── pyproject.toml        # project metadata & tool config
├── README.md             # this file
├── src/                  # source package (src layout)
│   └── detect_motion/
│       ├── __init__.py   # public API & version
│       ├── __main__.py   # python -m detect_motion entry
│       ├── cli.py        # argument parsing, main()
│       └── detector.py   # analysis engine (analyse_video + VideoResult)
└── tests/                # pytest suite
    ├── conftest.py       # shared fixtures
    ├── test_cli.py       # CLI tests
    └── test_detector.py  # engine tests
```
