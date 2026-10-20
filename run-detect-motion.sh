#!/usr/bin/env bash
# =====================================================================
# detect-motion Linux/macOS Runner
# Runs detect-motion in a Docker container with mounted video folders
# =====================================================================

set -euo pipefail

# Usage:
#   ./run-detect-motion.sh [INPUT_FOLDER] [OUTPUT_FOLDER] [QUARANTINE_FOLDER] [DETECT_MOTION_ARGS...]
#
# Examples:
#   ./run-detect-motion.sh "/home/user/videos" "/home/user/kept"
#   ./run-detect-motion.sh "/home/user/videos" "/home/user/kept" --profile balanced --progress
#   ./run-detect-motion.sh --help

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_INPUT="${SCRIPT_DIR}/videos"
DEFAULT_OUTPUT="${SCRIPT_DIR}/videos-keep"
DEFAULT_QUARANTINE="${SCRIPT_DIR}/videos-quarantine"

IMAGE_NAME="detect-motion:latest"

# Parse arguments
INPUT_FOLDER=""
OUTPUT_FOLDER=""
QUARANTINE_FOLDER=""
DETECT_ARGS=()

ARG_COUNT=0
for arg in "$@"; do
    if [[ "$arg" == -* ]]; then
        DETECT_ARGS+=("$arg")
    elif [[ $ARG_COUNT -eq 0 ]]; then
        INPUT_FOLDER="$(realpath -m "$arg")"
        ARG_COUNT=$((ARG_COUNT + 1))
    elif [[ $ARG_COUNT -eq 1 ]]; then
        OUTPUT_FOLDER="$(realpath -m "$arg")"
        ARG_COUNT=$((ARG_COUNT + 1))
    elif [[ $ARG_COUNT -eq 2 ]]; then
        QUARANTINE_FOLDER="$(realpath -m "$arg")"
        ARG_COUNT=$((ARG_COUNT + 1))
    else
        DETECT_ARGS+=("$arg")
    fi
done

# Use defaults if not provided
INPUT_FOLDER="${INPUT_FOLDER:-$DEFAULT_INPUT}"
OUTPUT_FOLDER="${OUTPUT_FOLDER:-$DEFAULT_OUTPUT}"
QUARANTINE_FOLDER="${QUARANTINE_FOLDER:-$DEFAULT_QUARANTINE}"

# Create host directories if they don't exist
mkdir -p "$INPUT_FOLDER" "$OUTPUT_FOLDER" "$QUARANTINE_FOLDER"

# Build docker run command
DOCKER_CMD=(
    docker run --rm
    -v "${INPUT_FOLDER}:/data/video"
    -v "${OUTPUT_FOLDER}:/data/keep"
    -v "${QUARANTINE_FOLDER}:/data/quarantine"
    "$IMAGE_NAME"
)

# Add default input/output dirs if not overridden by user args
if ! printf '%s\n' "${DETECT_ARGS[@]}" | grep -q -- '--input-dir'; then
    DOCKER_CMD+=(--input-dir /data/video)
fi

if ! printf '%s\n' "${DETECT_ARGS[@]}" | grep -q -- '--output-dir'; then
    DOCKER_CMD+=(--output-dir /data/keep)
fi

if ! printf '%s\n' "${DETECT_ARGS[@]}" | grep -q -- '--quarantine-dir'; then
    DOCKER_CMD+=(--quarantine-dir /data/quarantine)
fi

# Append user arguments
DOCKER_CMD+=("${DETECT_ARGS[@]}")

# Show what we're doing
echo "====================================================================="
echo "Starting detect-motion container"
echo "====================================================================="
echo "Input folder:     $INPUT_FOLDER"
echo "Output folder:    $OUTPUT_FOLDER"
echo "Quarantine folder: $QUARANTINE_FOLDER"
echo "Docker command:   ${DOCKER_CMD[*]}"
echo "====================================================================="
echo

# Execute
exec "${DOCKER_CMD[@]}"