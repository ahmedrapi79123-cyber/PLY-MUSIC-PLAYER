"""Configuration management for the PLY music player.

Handles directory creation, path setup, and logger initialization.
"""

import logging
import os
from pathlib import Path

# Base directories
CODE_DIR = Path(__file__).resolve().parent

def _is_writable(path: Path) -> bool:
    try:
        test_file = path / ".write_test"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        return False

# If the code directory is writable and looks like a development workspace, use it.
# Otherwise, fall back to a user-specific home directory (~/.ply) to avoid permission errors.
if _is_writable(CODE_DIR) and (CODE_DIR / "main.py").exists():
    BASE_DIR = CODE_DIR
else:
    BASE_DIR = Path.home() / ".ply"

DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
ASSETS_DIR = BASE_DIR / "assets"
TEMP_DIR = DATA_DIR / "temp"

# Ensure directories exist
for directory in [DATA_DIR, LOGS_DIR, ASSETS_DIR, TEMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# File paths
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"
LOG_FILE = LOGS_DIR / "ply.log"

# Supported audio extensions
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg"}

# Setup Logging
def setup_logging() -> None:
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    # Reduce noise from third-party libraries
    logging.getLogger("pygame").setLevel(logging.WARNING)

def disable_console_logging() -> None:
    """Removes StreamHandler from the root logger to prevent console corruption in TUI."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)

# Initialize logging immediately on import
setup_logging()
logger = logging.getLogger("PLY")
logger.info("PLY configurations initialized.")
