#!/usr/bin/env bash
# Entrypoint for detect-motion container

set -euo pipefail

# Ensure data directories exist
mkdir -p /data/video /data/keep /data/quarantine

# If no arguments provided, show help
if [ $# -eq 0 ]; then
    exec detect-motion --help
fi

# Run detect-motion with all passed arguments
exec detect-motion "$@"
