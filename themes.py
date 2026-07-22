"""Theme configurations for the PLY music player.

Provides color schemes for GUI (Tkinter) and Rich styles for CLI.
"""

from typing import Dict, Any

# GUI Colors
GUI_THEMES = {
    "dark": {
        "bg": "#121214",
        "container_bg": "#1e1e24",
        "fg": "#f1f2f6",
        "muted_fg": "#a4b0be",
        "accent": "#6c5ce7",        # Modern purple accent
        "accent_hover": "#8073e6",
        "accent_active": "#5b4bc4",
        "selection_bg": "#2f3542",
        "selection_fg": "#ffffff",
        "border": "#2f3542",
        "slider_bg": "#2f3542",
        "slider_trough": "#121214",
        "btn_bg": "#2f3542",
        "btn_fg": "#f1f2f6"
    },
    "light": {
        "bg": "#f5f6fa",
        "container_bg": "#ffffff",
        "fg": "#2f3542",
        "muted_fg": "#747d8c",
        "accent": "#6c5ce7",
        "accent_hover": "#5b4bc4",
        "accent_active": "#4834d4",
        "selection_bg": "#dfe4ea",
        "selection_fg": "#2f3542",
        "border": "#dfe4ea",
        "slider_bg": "#dfe4ea",
        "slider_trough": "#f5f6fa",
        "btn_bg": "#dfe4ea",
        "btn_fg": "#2f3542"
    }
}

# CLI Rich Styles
CLI_THEMES = {
    "dark": {
        "logo": "bold rgb(108,92,231)",
        "song": "bold white",
        "artist": "italic cyan",
        "album": "italic magenta",
        "status_play": "bold green",
        "status_pause": "bold yellow",
        "status_stop": "bold red",
        "progress_bar": "rgb(108,92,231)",
        "volume": "bold cyan",
        "metadata": "bold white",
        "border": "rgb(108,92,231)",
        "border_muted": "rgb(47,53,66)",
        "highlight": "bold rgb(108,92,231)",
        "muted": "dim white",
        "shortcut_key": "bold cyan",
        "shortcut_desc": "dim white",
        "active_row": "bold white on rgb(108,92,231)",
        "inactive_row": "white"
    },
    "light": {
        "logo": "bold rgb(108,92,231)",
        "song": "bold black",
        "artist": "italic blue",
        "album": "italic dark_magenta",
        "status_play": "bold green",
        "status_pause": "bold gold3",
        "status_stop": "bold red",
        "progress_bar": "rgb(108,92,231)",
        "volume": "bold blue",
        "metadata": "bold black",
        "border": "rgb(108,92,231)",
        "border_muted": "rgb(223,228,234)",
        "highlight": "bold rgb(108,92,231)",
        "muted": "dim black",
        "shortcut_key": "bold blue",
        "shortcut_desc": "dim black",
        "active_row": "bold white on rgb(108,92,231)",
        "inactive_row": "black"
    }
}

class ThemeManager:
    """Manages the current active theme for the application."""

    def __init__(self, dark_mode: bool = True) -> None:
        self.dark_mode = dark_mode

    def toggle_theme(self) -> None:
        """Toggles the dark mode state."""
        self.dark_mode = not self.dark_mode

    @property
    def mode_name(self) -> str:
        """Returns the name of the current mode."""
        return "dark" if self.dark_mode else "light"

    def get_gui_theme(self) -> Dict[str, str]:
        """Gets color palette for current GUI theme."""
        return GUI_THEMES[self.mode_name]

    def get_cli_theme(self) -> Dict[str, str]:
        """Gets Rich styles for current CLI theme."""
        return CLI_THEMES[self.mode_name]
