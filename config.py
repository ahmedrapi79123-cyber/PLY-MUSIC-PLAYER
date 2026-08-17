"""Configuration management for the PLY music player.

Handles directory creation, path setup, and logger initialization.
Uses XDG Base Directory specification for proper Linux/Flatpak compatibility.
"""

import logging
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# XDG Base Directory paths (Flatpak-safe)
# ---------------------------------------------------------------------------
_XDG_DATA_HOME   = Path(os.environ.get("XDG_DATA_HOME",   Path.home() / ".local" / "share"))
_XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
_XDG_CACHE_HOME  = Path(os.environ.get("XDG_CACHE_HOME",  Path.home() / ".cache"))

# Code directory (where this file lives — used to detect development mode)
CODE_DIR = Path(__file__).resolve().parent


def _is_writable(path: Path) -> bool:
    """Returns True if the given directory is writable."""
    try:
        test_file = path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
# In development (running from source): use ~/.local/share/ply so we don't
# litter the source tree with data files.
# In installed/Flatpak mode: XDG paths are already set correctly by the runtime.
BASE_DIR   = _XDG_DATA_HOME / "ply"
CONFIG_DIR = _XDG_CONFIG_HOME / "ply"
CACHE_DIR  = _XDG_CACHE_HOME / "ply"

DATA_DIR   = BASE_DIR / "data"
LOGS_DIR   = BASE_DIR / "logs"
TEMP_DIR   = CACHE_DIR / "covers"  # Cover art cache goes in XDG_CACHE_HOME

# Assets: prefer installed path, fall back to source-tree assets/
_INSTALLED_ASSETS = Path("/app/share/ply/assets")  # Flatpak install path
_SOURCE_ASSETS    = CODE_DIR / "assets"

if _INSTALLED_ASSETS.exists():
    ASSETS_DIR = _INSTALLED_ASSETS
elif _SOURCE_ASSETS.exists():
    ASSETS_DIR = _SOURCE_ASSETS
else:
    ASSETS_DIR = BASE_DIR / "assets"

# Ensure all writable runtime directories exist.
# ASSETS_DIR may point to a read-only /app path in Flatpak — skip it.
for _dir in [DATA_DIR, LOGS_DIR, TEMP_DIR, CONFIG_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
# Only create ASSETS_DIR if it's not already an installed (read-only) path
if not _INSTALLED_ASSETS.exists():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SETTINGS_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE  = DATA_DIR   / "history.json"
LOG_FILE      = LOGS_DIR   / "ply.log"

# ---------------------------------------------------------------------------
# Supported audio extensions
# GStreamer's playbin handles all of these natively.
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {
    ".mp3",   # MPEG Audio Layer III
    ".wav",   # Waveform Audio
    ".ogg",   # Ogg Vorbis
    ".flac",  # Free Lossless Audio Codec
    ".opus",  # Opus (in Ogg container)
    ".m4a",   # MPEG-4 Audio (AAC)
    ".aac",   # Advanced Audio Coding (raw)
}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    # Reduce noise from third-party libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("mutagen").setLevel(logging.WARNING)


def disable_console_logging() -> None:
    """Removes StreamHandler from the root logger to prevent console corruption in TUI."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            root_logger.removeHandler(handler)


# Initialise logging immediately on import
setup_logging()
logger = logging.getLogger("PLY")
logger.info("PLY configuration initialised. BASE_DIR=%s", BASE_DIR)
