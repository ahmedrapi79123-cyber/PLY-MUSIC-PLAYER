"""Library and song data models for the PLY music player.

Handles scanning directories, loading metadata, and managing history.
"""

from pathlib import Path
import json
import time
from typing import List, Dict, Any, Optional
from config import SUPPORTED_EXTENSIONS, HISTORY_FILE, logger
from utils import extract_metadata, get_album_cover

class Song:
    """Represents an audio track with its metadata."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = Path(filepath).resolve()
        self.title: str = ""
        self.artist: str = ""
        self.album: str = ""
        self.year: str = ""
        self.duration: float = 0.0
        self.has_cover: bool = False
        self.cover_path: Optional[Path] = None
        self.load_metadata()

    def load_metadata(self) -> None:
        """Reads metadata from the audio file using utility functions."""
        meta = extract_metadata(self.filepath)
        self.title = meta["title"]
        self.artist = meta["artist"]
        self.album = meta["album"]
        self.year = meta["year"]
        self.duration = meta["duration"]
        self.has_cover = meta["has_cover"]

    def load_cover(self) -> Optional[Path]:
        """Loads and caches the cover image, returning its path."""
        if self.has_cover and not self.cover_path:
            self.cover_path = get_album_cover(self.filepath)
        return self.cover_path

    def to_dict(self) -> Dict[str, Any]:
        """Serializes song metadata into a dictionary."""
        return {
            "filepath": str(self.filepath),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "duration": self.duration
        }

    def __str__(self) -> str:
        return f"{self.title} - {self.artist}"

class Library:
    """Manages the music library collection and play history."""

    def __init__(self) -> None:
        self.songs: List[Song] = []
        self.history: List[Dict[str, Any]] = []
        self.load_history()

    def scan_directory(self, dir_path: Path) -> List[Song]:
        """Recursively scans a directory for supported audio formats.

        Populates the library songs list.
        """
        logger.info("Scanning directory: %s", dir_path)
        path = Path(dir_path)
        scanned_songs: List[Song] = []

        if not path.exists() or not path.is_dir():
            logger.warning("Scan directory does not exist or is not a folder: %s", dir_path)
            return scanned_songs

        # Scan recursively
        try:
            for filepath in path.rglob("*"):
                if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
                    try:
                        song = Song(filepath)
                        scanned_songs.append(song)
                    except Exception as e:
                        logger.error("Failed to load song %s: %s", filepath, e)
        except Exception as e:
            logger.error("Error during recursive folder scanning: %s", e)

        # Sort songs alphabetically by title
        scanned_songs.sort(key=lambda s: s.title.lower())
        self.songs = scanned_songs
        logger.info("Scan completed. Found %d songs.", len(self.songs))
        return self.songs

    def load_history(self) -> None:
        """Loads play history from history.json."""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.info("Play history loaded: %d entries.", len(self.history))
            except Exception as e:
                logger.error("Failed to load history: %s", e)
                self.history = []
        else:
            self.history = []

    def save_history(self) -> None:
        """Saves current play history to history.json."""
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=4, ensure_ascii=False)
            logger.debug("Play history saved.")
        except Exception as e:
            logger.error("Failed to save history: %s", e)

    def add_to_history(self, song: Song) -> None:
        """Adds a song to play history (limited to last 100 played songs)."""
        entry = {
            "filepath": str(song.filepath),
            "title": song.title,
            "artist": song.artist,
            "timestamp": time.time()
        }
        # Prepend to make it latest first
        self.history.insert(0, entry)
        # Limit to 100 items
        self.history = self.history[:100]
        self.save_history()
