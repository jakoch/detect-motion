# detect-motion DevContainer

This directory contains the DevContainer configuration for running detect-motion in a containerized environment.

## Quick Start

### Option 1: VS Code Dev Container (Recommended for Development)

1. Open the project folder (`/src`) in VS Code
2. Press `F1` → "Dev Containers: Reopen in Container"
3. Wait for container to build and start
4. Open terminal in VS Code (`Ctrl+\``)
5. Run detect-motion:
   ```bash
   detect-motion --input-dir /data/video --output-dir /data/keep --progress
   ```

### Option 2: Standalone Docker (Windows)

```cmd
REM Build the image first (one time)
docker build -t detect-motion:latest -f .devcontainer/Dockerfile .

REM Run with your video folders
run-detect-motion.bat "C:\My Videos" "C:\Kept Videos" --profile balanced --progress
```

### Option 3: Standalone Docker (Linux/macOS)

```bash
# Build the image first (one time)
docker build -t detect-motion:latest -f .devcontainer/Dockerfile .

# Run with your video folders
./run-detect-motion.sh "/home/user/videos" "/home/user/kept" --profile balanced --progress
```

### Option 4: Direct Docker Run

```bash
docker run --rm \
  -v /host/videos:/data/video \
  -v /host/kept:/data/keep \
  -v /host/quarantine:/data/quarantine \
  detect-motion:latest \
  --input-dir /data/video \
  --output-dir /data/keep \
  --quarantine-dir /data/quarantine \
  --profile balanced \
  --progress
```

## Folder Structure

```
src/
├── .devcontainer/
│   ├── Dockerfile          # Container definition
│   ├── devcontainer.json   # VS Code DevContainer config
│   ├── entrypoint.sh       # Container entrypoint
│   └── PLAN.md             # This plan document
├── run-detect-motion.bat   # Windows runner script
├── run-detect-motion.sh    # Linux/macOS runner script
├── pyproject.toml          # Project config
└── src/detect_motion/      # Source code
```

## Mounted Volumes

| Container Path | Purpose | Default Host Path |
|----------------|---------|-------------------|
| `/data/video`  | Input videos (scanned for motion) | `./sample-videos` or `$VIDEO_INPUT` |
| `/data/keep`   | Videos with detected motion | `./kept-videos` or `$VIDEO_OUTPUT` |
| `/data/quarantine` | Videos without motion (optional) | `./quarantine` or `$VIDEO_QUARANTINE` |

Override with environment variables:
```bash
export VIDEO_INPUT=/path/to/videos
export VIDEO_OUTPUT=/path/to/kept
export VIDEO_QUARANTINE=/path/to/quarantine
```

## Common Commands

```bash
# Scan videos in default input folder, show progress
detect-motion --progress

# Use balanced profile (better for general footage)
detect-motion --profile balanced --progress

# Move (not copy) videos with motion to output folder
detect-motion --output-dir /data/keep --move --progress

# Delete videos without motion (requires --yes)
detect-motion --delete --yes --progress

# Quarantine instead of delete (safer)
detect-motion --quarantine-dir /data/quarantine --progress

# Dry run - analyze only, no file operations
detect-motion --dry-run --progress

# Process specific files
detect-motion /data/video/clip1.mp4 /data/video/clip2.avi --progress

# Save JSON report
detect-motion --report motion-report.json --progress
```

## Building the Image

```bash
# From src directory
docker build -t detect-motion:latest -f .devcontainer/Dockerfile .
```

## Troubleshooting

### "no videos found" error
- Ensure your video files are in the mounted input folder (`/data/video` in container)
- Check file extensions: .avi, .mp4, .mov, .mkv, .m4v, .wmv, .mpg, .mpeg, .webm

### Permission denied on output
- The container runs as `vscode` user (UID 1000)
- Ensure host directories are writable by UID 1000

### OpenCV errors
- The container includes all necessary OpenCV dependencies
- If you see codec errors, ensure ffmpeg is installed (it is in the image)

### Windows path issues
- Use the provided `run-detect-motion.bat` which handles path conversion
- Or use WSL2 paths: `/mnt/c/Users/...`

## Development

The project is installed in editable mode (`pip install -e .`). Changes to source code in `src/detect_motion/` are immediately available without rebuilding.

To run tests:
```bash
pytest
```

To format/lint:
```bash
ruff format src tests
ruff check src tests
```