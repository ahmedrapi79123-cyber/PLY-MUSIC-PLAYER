"""Command Line Interface (CLI) for the PLY music player.

Provides an interactive terminal dashboard with playback status and controls.
"""

import os
import sys
import time
import threading
import select
from pathlib import Path
from typing import Optional, List

# Linux specific terminal key capture
try:
    import termios
    import tty
    UNIX_PLATFORM = True
except ImportError:
    UNIX_PLATFORM = False
    try:
        import msvcrt
    except ImportError:
        pass

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.console import Console
from rich.box import ROUNDED

from config import logger, SUPPORTED_EXTENSIONS, disable_console_logging
from settings import Settings
from themes import ThemeManager
from player import Player
from playlist import Playlist
from library import Library, Song
from utils import format_time

class CLI:
    """Terminal User Interface for the PLY music player."""

    def __init__(self, player: Player, playlist: Playlist, library: Library, settings: Settings) -> None:
        # Silence console log streams to keep TUI clean
        disable_console_logging()

        self.player = player
        self.playlist = playlist
        self.library = library
        self.settings = settings
        self.theme_mgr = ThemeManager(dark_mode=settings.get("dark_mode"))
        self.console = Console()
        self.running = True
        self.keyboard_thread: Optional[threading.Thread] = None
        self.live: Optional[Live] = None
        self.layout: Optional[Layout] = None

        # Terminal configuration variables
        self.fd = None
        self.old_settings = None
        self.term_configured = False

        # Setup player end callback
        self.player.set_on_song_end(self._on_song_finished)

        # Register settings states to playlist
        self.playlist.repeat_mode = "all" if self.settings.get("repeat") else "off"
        # We start with shuffle state from settings
        self.playlist.shuffle = self.settings.get("shuffle")
        self.player.set_volume(self.settings.get("last_volume"))

    def _setup_terminal(self) -> None:
        """Puts the terminal in cbreak mode once at startup."""
        if UNIX_PLATFORM:
            try:
                self.fd = sys.stdin.fileno()
                self.old_settings = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
                self.term_configured = True
                logger.info("Terminal configured to cbreak mode successfully.")
            except Exception as e:
                logger.error("Failed to configure terminal to cbreak mode: %s", e)
                self.term_configured = False

    def _restore_terminal(self) -> None:
        """Restores the original terminal settings."""
        if UNIX_PLATFORM and self.term_configured and self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
                logger.info("Terminal settings restored successfully.")
            except Exception as e:
                logger.error("Failed to restore terminal settings: %s", e)

    def _trigger_update(self) -> None:
        """Forces an immediate redraw of the UI dashboard."""
        if self.live and self.running:
            try:
                self.layout = self._generate_layout()
                self.live.update(self.layout)
            except Exception:
                pass

    def _on_song_finished(self) -> None:
        """Callback triggered when the player finishes a song."""
        next_song = self.playlist.next_song()
        if next_song:
            self.player.play(next_song)
            self.library.add_to_history(next_song)
            self.settings.set("last_song", str(next_song.filepath))
        else:
            self.player.stop()
        self._trigger_update()

    def run(self) -> None:
        """Starts the CLI dashboard and the keyboard capture loop."""
        self.console.clear()
        
        # Setup terminal configuration
        self._setup_terminal()

        # Start keyboard reader thread
        self.keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self.keyboard_thread.start()

        # Render dashboard
        try:
            self.layout = self._generate_layout()
            with Live(self.layout, console=self.console, refresh_per_second=10, screen=True) as live:
                self.live = live
                while self.running:
                    self.layout = self._generate_layout()
                    self.live.update(self.layout)
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Cleans up player and terminal settings."""
        self.running = False
        self._restore_terminal()
        self.player.stop()
        self.player.close()
        
        # Save last session folder/volume
        current = self.playlist.current_song
        if current:
            self.settings.set("last_song", str(current.filepath))
        self.settings.set("last_volume", self.player.volume)
        self.settings.set("shuffle", self.playlist.shuffle)
        self.settings.set("repeat", self.playlist.repeat_mode != "off")
        self.live = None
        logger.info("PLY CLI Shutdown complete.")

    def _keyboard_listener(self) -> None:
        """Listens for keyboard input and executes player controls."""
        while self.running:
            key = self._read_key()
            if not key:
                continue

            updated = False
            # Process key bindings
            if key == " ":
                if self.player.state == "playing":
                    self.player.pause()
                elif self.player.state == "paused":
                    self.player.resume()
                elif self.player.state == "stopped" and self.playlist.songs:
                    # Play current song
                    song = self.playlist.current_song
                    if song:
                        self.player.play(song)
                        self.library.add_to_history(song)
                updated = True

            elif key.lower() == "n":
                next_song = self.playlist.next_song()
                if next_song:
                    self.player.play(next_song)
                    self.library.add_to_history(next_song)
                updated = True

            elif key.lower() == "b":
                prev_song = self.playlist.prev_song()
                if prev_song:
                    self.player.play(prev_song)
                    self.library.add_to_history(prev_song)
                updated = True

            elif key.lower() == "s":
                self.player.stop()
                updated = True

            elif key == "+" or key == "=" or key == "\x1b[A": # Up arrow or Plus
                self.player.set_volume(self.player.volume + 5)
                self.settings.set("last_volume", self.player.volume)
                updated = True

            elif key == "-" or key == "\x1b[B": # Down arrow or Minus
                self.player.set_volume(self.player.volume - 5)
                self.settings.set("last_volume", self.player.volume)
                updated = True

            elif key.lower() == "r":
                # Toggle repeat mode
                if self.playlist.repeat_mode == "off":
                    self.playlist.repeat_mode = "all"
                elif self.playlist.repeat_mode == "all":
                    self.playlist.repeat_mode = "single"
                else:
                    self.playlist.repeat_mode = "off"
                self.settings.set("repeat", self.playlist.repeat_mode != "off")
                updated = True

            elif key.lower() == "h":
                self.playlist.shuffle = not self.playlist.shuffle
                self.settings.set("shuffle", self.playlist.shuffle)
                updated = True

            elif key.lower() == "q":
                self.running = False
                break

            if updated:
                self._trigger_update()

    def _read_key(self) -> Optional[str]:
        """Reads a single keypress from standard input in cbreak mode."""
        if UNIX_PLATFORM:
            if not self.term_configured:
                # Fallback to legacy loop if configuration failed
                fd = sys.stdin.fileno()
                try:
                    old_settings = termios.tcgetattr(fd)
                except termios.error:
                    time.sleep(0.05)
                    return None
                try:
                    tty.setraw(fd)
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist:
                        char = sys.stdin.read(1)
                        if char == "\x1b":
                            rlist2, _, _ = select.select([sys.stdin], [], [], 0.02)
                            if rlist2:
                                char += sys.stdin.read(2)
                        return char
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            else:
                try:
                    # Non-blocking check for input (timeout 0.05s)
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist:
                        char = sys.stdin.read(1)
                        if char == "\x1b":
                            # Read the next two characters for escape sequences
                            rlist2, _, _ = select.select([sys.stdin], [], [], 0.02)
                            if rlist2:
                                char += sys.stdin.read(2)
                        return char
                except Exception as e:
                    logger.error("Error reading key in cbreak mode: %s", e)
                    time.sleep(0.05)
        else:
            # Windows fallback
            if msvcrt and msvcrt.kbhit():
                char = msvcrt.getch()
                if char in (b"\x00", b"\xe0"):
                    char2 = msvcrt.getch()
                    if char2 == b"H":  # Up arrow
                        return "\x1b[A"
                    elif char2 == b"P":  # Down arrow
                        return "\x1b[B"
                try:
                    return char.decode("utf-8")
                except UnicodeDecodeError:
                    return None
            time.sleep(0.05)
        return None

    def _generate_layout(self) -> Layout:
        """Generates the Rich Layout rendering of the dashboard."""
        styles = self.theme_mgr.get_cli_theme()
        
        # Responsive Terminal Size Guard
        width = self.console.width
        height = self.console.height
        if width < 75 or height < 20:
            layout = Layout()
            layout.update(
                Panel(
                    Align.center(
                        f"\n[bold red]⚠️ Terminal window is too small![/]\n\n"
                        f"Current: {width}x{height}\n"
                        f"Minimum required: [cyan]75x20[/]\n\n"
                        f"Please resize your terminal window to continue.",
                        vertical="middle"
                    ),
                    border_style="red",
                    box=ROUNDED
                )
            )
            return layout

        # Main container
        layout = Layout()
        layout.split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2)
        )

        # Header ASCII Logo
        logo_text = (
            " ██████╗  ██╗     ██╗   ██╗\n"
            " ██╔══██╗ ██║     ╚██╗ ██╔╝\n"
            " ██████╔╝ ██║      ╚████╔╝ \n"
            " ██╔═══╝  ██║       ╚██╔╝  \n"
            " ██║      ███████╗   ██║   \n"
            " ╚═╝      ╚══════╝   ╚═╝   "
        )
        logo_panel = Panel(
            Align.center(logo_text, style=styles["logo"]),
            border_style=styles["border_muted"],
            box=ROUNDED
        )

        # Song Details & Playback Status
        current_song = self.playlist.current_song
        player_state = self.player.state.upper()
        
        status_icon = "⏹ Stopped"
        status_style = styles["status_stop"]
        if player_state == "PLAYING":
            status_icon = "▶ Playing"
            status_style = styles["status_play"]
        elif player_state == "PAUSED":
            status_icon = "⏸ Paused"
            status_style = styles["status_pause"]

        meta_table = Table.grid(padding=1)
        meta_table.add_column(style=styles["muted"], justify="left", width=12)
        meta_table.add_column(style=styles["metadata"])

        if current_song:
            meta_table.add_row("🎵 Track:", f"[bold]{current_song.title}[/]")
            meta_table.add_row("👤 Artist:", f"[italic cyan]{current_song.artist}[/]")
            meta_table.add_row("💿 Album:", f"[italic magenta]{current_song.album}[/]")
            meta_table.add_row("📅 Year:", f"[yellow]{current_song.year}[/]")
        else:
            meta_table.add_row("🎵 Track:", "No song selected")
            meta_table.add_row("👤 Artist:", "-")
            meta_table.add_row("💿 Album:", "-")
            meta_table.add_row("📅 Year:", "-")

        # Progress bar
        elapsed_sec = self.player.get_elapsed_time()
        duration_sec = current_song.duration if current_song else 0.0
        
        progress_bar = self._draw_progress_bar(elapsed_sec, duration_sec, styles["progress_bar"])
        time_display = f"[bold]{format_time(elapsed_sec)}[/] / [dim]{format_time(duration_sec)}[/]"

        # Status Line (Volume, Repeat, Shuffle)
        rep = self.playlist.repeat_mode.upper()
        shuf = "ON" if self.playlist.shuffle else "OFF"
        
        shuf_style = styles["highlight"] if self.playlist.shuffle else "dim white"
        rep_style = styles["highlight"] if self.playlist.repeat_mode != "off" else "dim white"

        status_grid = Table.grid(padding=2)
        status_grid.add_row(
            self._draw_volume_bar(self.player.volume, styles["volume"]),
            f"🔀 Shuffle: [{shuf_style}]{shuf}[/]",
            f"🔁 Repeat: [{rep_style}]{rep}[/]"
        )

        left_content = Table.grid(padding=1)
        left_content.add_row(logo_panel)
        
        playing_panel_content = Table.grid(padding=1)
        playing_panel_content.add_row(Align.left(f"Status: [{status_style}]{status_icon}[/]"))
        playing_panel_content.add_row(meta_table)
        playing_panel_content.add_row("")
        playing_panel_content.add_row(Align.center(time_display))
        playing_panel_content.add_row(Align.center(progress_bar))
        playing_panel_content.add_row("")
        playing_panel_content.add_row(Align.center(status_grid))

        left_content.add_row(
            Panel(playing_panel_content, title="Now Playing", border_style=styles["border"], box=ROUNDED)
        )
        layout["left"].update(left_content)

        # Right Column: Playlist & Keyboard Help
        playlist_table = Table(box=None, expand=True)
        playlist_table.add_column("Index", width=6, justify="left")
        playlist_table.add_column("Title", style=styles["metadata"])
        playlist_table.add_column("Dur", width=8, justify="right")

        songs_list = self.playlist.songs
        
        # Calculate scroll viewport height dynamically based on terminal height
        visible_slots = max(3, min(12, height - 18))
        half_slots = visible_slots // 2
        start_idx = max(0, self.playlist.current_index - half_slots)
        end_idx = min(len(songs_list), start_idx + visible_slots)
        
        if end_idx - start_idx < visible_slots:
            start_idx = max(0, end_idx - visible_slots)

        for idx in range(start_idx, end_idx):
            song = songs_list[idx]
            is_current = (idx == self.playlist.current_index)
            
            if is_current:
                marker = "▶ 🎵"
                title_text = f"[bold]{song.title}[/]"
                duration_text = f"[bold]{format_time(song.duration)}[/]"
                row_style = styles["active_row"]
            else:
                marker = f"  {idx+1:02d}"
                title_text = song.title
                duration_text = format_time(song.duration)
                row_style = styles["inactive_row"]
            
            playlist_table.add_row(
                marker,
                title_text,
                duration_text,
                style=row_style
            )

        playlist_title = f"Playlist ({len(songs_list)} tracks)"
        playlist_panel = Panel(
            playlist_table,
            title=playlist_title,
            border_style=styles["border"],
            box=ROUNDED,
            expand=True
        )

        help_table = Table.grid(padding=1)
        help_table.add_column(style=styles["shortcut_key"], width=14)
        help_table.add_column(style=styles["shortcut_desc"])
        help_table.add_row(" [Space]", "Play / Pause")
        help_table.add_row(" [N] / [B]", "Next / Previous Track")
        help_table.add_row(" [S]", "Stop Playback")
        help_table.add_row(" [+] / [-]", "Volume Up / Down")
        help_table.add_row(" [H]", "Toggle Shuffle Mode")
        help_table.add_row(" [R]", "Toggle Repeat Mode")
        help_table.add_row(" [Q]", "Quit Application")

        right_content = Layout()
        right_content.split_column(
            Layout(playlist_panel, ratio=3),
            Layout(Panel(help_table, title="Keyboard Shortcuts", border_style=styles["border_muted"], box=ROUNDED), ratio=2)
        )
        layout["right"].update(right_content)

        return layout

    def _draw_progress_bar(self, elapsed: float, duration: float, bar_color: str) -> str:
        """Returns a string representing a progress bar using block elements with sub-character precision."""
        width = 35
        if duration <= 0:
            pct = 0.0
        else:
            pct = min(1.0, max(0.0, elapsed / duration))

        total_blocks = width * pct
        filled_blocks = int(total_blocks)
        fraction = total_blocks - filled_blocks

        # Sub-character block elements for high precision
        sub_blocks = ["", "▕", "▎", "▍", "▌", "▋", "▊", "▉"]
        sub_idx = int(fraction * 8)
        sub_char = sub_blocks[sub_idx] if sub_idx < len(sub_blocks) else ""

        filled = "█" * filled_blocks + sub_char
        empty_len = width - len(filled)
        empty = "░" * max(0, empty_len)

        return f"[{bar_color}]{filled}[/][dim]{empty}[/]"

    def _draw_volume_bar(self, volume: int, volume_color: str) -> str:
        """Returns a string showing a speaker icon and a visual volume block bar."""
        width = 5
        filled_len = int(width * (volume / 100.0))
        empty_len = width - filled_len
        filled = "█" * filled_len
        empty = "░" * empty_len
        
        icon = "🔊" if volume > 50 else ("🔉" if volume > 0 else "🔇")
        return f"{icon} [{volume_color}]{filled}[/][dim]{empty}[/] {volume}%"
