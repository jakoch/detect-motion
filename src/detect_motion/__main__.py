"""Allow running the package as ``python -m detect_motion``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
