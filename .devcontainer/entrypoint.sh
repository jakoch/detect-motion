#!/usr/bin/env bash
# Entrypoint for detect-motion container

set -euo pipefail

# Ensure data directories exist
mkdir -p /data/video /data/keep /data/drop

# A dev container starts this image with a keep-alive command instead of a
# detect-motion invocation. Forward such commands untouched.
if [ "${DETECT_MOTION_PASSTHROUGH:-0}" = "1" ]; then
    exec "$@"
fi

# If no arguments provided, show help
if [ $# -eq 0 ]; then
    exec detect-motion --help
fi

# Run detect-motion with all passed arguments
exec detect-motion "$@"
