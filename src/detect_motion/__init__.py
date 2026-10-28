"""detect-motion: Detect which videos contain real movement, using OpenCV."""

__version__ = "2.0.0"

from .cli import main
from .detector import VideoResult, analyse_video

__all__ = ["__version__", "main", "VideoResult", "analyse_video"]
