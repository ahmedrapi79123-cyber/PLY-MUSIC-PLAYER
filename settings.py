"""Settings manager for the PLY music player.

Provides persistent settings management by loading/saving JSON configurations.
"""

import json
from typing import Any, Dict
from config import SETTINGS_FILE, logger

class Settings:
    """Manages the application settings and persistence."""

    def __init__(self) -> None:
        self.defaults: Dict[str, Any] = {
            "last_volume": 70,
            "last_folder": None,
            "dark_mode": True,
            "shuffle": False,
            "repeat": False,
            "last_song": None,
            "last_playlist": None,
            "tray_icon_size": 64
        }
        self.settings: Dict[str, Any] = self.defaults.copy()
        self.load()

    def load(self) -> None:
        """Loads settings from settings.json or initializes them with defaults."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all keys are present
                    for key, val in self.defaults.items():
                        self.settings[key] = loaded.get(key, val)
                logger.info("Settings loaded successfully.")
            except Exception as e:
                logger.error("Failed to load settings: %s. Using defaults.", e)
                self.settings = self.defaults.copy()
        else:
            self.settings = self.defaults.copy()
            self.save()

    def save(self) -> None:
        """Saves current settings to settings.json."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            logger.info("Settings saved successfully.")
        except Exception as e:
            logger.error("Failed to save settings: %s", e)

    def get(self, key: str) -> Any:
        """Gets a setting value by key."""
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key: str, value: Any) -> None:
        """Sets a setting value and saves the settings file."""
        self.settings[key] = value
        self.save()
