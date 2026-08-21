"""Entry point for the PLY music player.

Parses command line arguments and routes to either the CLI or GUI.
"""

import sys
import os
import fcntl
import argparse
from pathlib import Path
from config import logger, setup_logging, SUPPORTED_EXTENSIONS, CACHE_DIR
from settings import Settings
from library import Library, Song
from playlist import Playlist
from player import Player
from cli import CLI
from gui import GUI

# ---------------------------------------------------------------------------
# Single-instance lock
# ---------------------------------------------------------------------------
_LOCK_FILE = None   # kept open so the lock persists for the process lifetime

def _acquire_single_instance_lock() -> bool:
    """Try to acquire an exclusive flock on a runtime lock file.

    Returns True if this is the first (and only) instance.
    Returns False if another instance is already running.
    """
    global _LOCK_FILE
    # Prefer XDG_RUNTIME_DIR (per-session temp dir, works inside Flatpak)
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", str(CACHE_DIR)))
    lock_path = runtime_dir / "ply.lock"

    try:
        # Open (or create) the lock file — intentionally NOT closed so the
        # lock is held until this process exits.
        _LOCK_FILE = open(lock_path, "w")
        fcntl.flock(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FILE.write(str(os.getpid()))
        _LOCK_FILE.flush()
        return True   # we got the lock — we are the only instance
    except BlockingIOError:
        return False  # another instance holds the lock


def _raise_existing_instance() -> None:
    """Ask the running PLY instance to raise its window via MPRIS D-Bus."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.mpris.MediaPlayer2.ply",          # bus name
            "/org/mpris/MediaPlayer2",              # object path
            "org.mpris.MediaPlayer2",               # interface
            "Raise",                                # method
            None, None,
            Gio.DBusCallFlags.NONE,
            2000, None,
        )
        print("PLY is already running — bringing it to the front.")
    except Exception:
        print("PLY is already running.")  # graceful fallback

def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="PLY - A professional, modern command-line and graphical music player.",
        epilog="""Examples:
  ply ~/Music
      Play music from a directory using CLI mode.

  ply --gui
      Launch the graphical interface.

  ply --gui ~/Music
      Launch the GUI and scan ~/Music.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER
      Launch PLY GUI through Flatpak.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER ~/Music
      Play ~/Music through Flatpak CLI mode.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER --gui
      Launch the PLY GUI through Flatpak.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER --shuffle ~/Music
      Play music with shuffle enabled.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER --repeat ~/Music
      Play music with repeat enabled.

  flatpak run io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER --volume 50 ~/Music
      Start playback at 50% volume.""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "path", nargs="?", type=str, default=None,
        help="Path to an audio file (MP3, WAV, OGG) or a directory of music to play."
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Force launch the graphical user interface."
    )
    parser.add_argument(
        "--shuffle", action="store_true",
        help="Enable shuffle mode for playback."
    )
    parser.add_argument(
        "--repeat", action="store_true",
        help="Enable repeat mode for playback."
    )
    parser.add_argument(
        "--volume", type=int, default=None,
        help="Set the initial volume (0 to 100)."
    )
    return parser.parse_args()

def main() -> None:
    """Main execution function."""
    args = parse_arguments()

    # Determine execution mode early (needed for single-instance check)
    run_gui = args.gui or (len(sys.argv) == 1)

    # ── Single-instance guard (GUI mode only) ────────────────────────────
    if run_gui:
        if not _acquire_single_instance_lock():
            _raise_existing_instance()
            sys.exit(0)
    # ─────────────────────────────────────────────────────────────────────

    # Initialize Settings
    settings = Settings()

    # Override settings with CLI flags if provided
    if args.shuffle:
        settings.set("shuffle", True)
    if args.repeat:
        settings.set("repeat", "all")
    if args.volume is not None:
        # Clamp volume between 0 and 100
        vol = max(0, min(args.volume, 100))
        settings.set("last_volume", vol)

    # Initialize components
    library = Library()
    playlist = Playlist()
    player = Player()

    # Handle path argument if provided
    input_path = None
    if args.path:
        import urllib.parse
        p_str = args.path
        if p_str.startswith("file://"):
            p_str = urllib.parse.unquote(p_str[7:])
        input_path = Path(p_str).resolve()
        if not input_path.exists():
            print(f"Error: Path '{p_str}' does not exist.")
            sys.exit(1)

        # Update last folder settings
        if input_path.is_dir():
            settings.set("last_folder", str(input_path))
            songs = library.scan_directory(input_path)
            for song in songs:
                playlist.add_song(song)
        elif input_path.is_file() and input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            settings.set("last_folder", str(input_path.parent))
            song = Song(input_path)
            playlist.add_song(song)
            settings.set("last_song", str(input_path))
        else:
            print(f"Error: Unsupported file format or not a directory: {args.path}")
            sys.exit(1)


    if run_gui:
        logger.info("Starting PLY in GUI mode...")
        try:
            app = GUI(player, playlist, library, settings)

            # Start MPRIS2 D-Bus service
            try:
                from mpris import MPRISController
                mpris = MPRISController()
                started = mpris.start(
                    on_play      = lambda: app.root.after(0, app._toggle_play_pause),
                    on_pause     = lambda: app.root.after(0, app._pause_song),
                    on_stop      = lambda: app.root.after(0, app._stop_song),
                    on_next      = lambda: app.root.after(0, app._next_song),
                    on_previous  = lambda: app.root.after(0, app._prev_song),
                    on_seek      = lambda pos: app.root.after(0, lambda: player.seek(pos)),
                    on_open_uri  = lambda path: app.root.after(0, lambda: app._open_uri(path)),
                    on_raise_window = lambda: app.root.after(0, app.show_window),
                    get_loop_status = lambda: playlist.repeat_mode,
                    get_shuffle     = lambda: playlist.shuffle,
                )
                if started:
                    app.mpris = mpris
                    logger.info("MPRIS2 service connected to GUI.")
            except Exception as mpris_err:
                logger.warning("MPRIS2 could not start: %s", mpris_err)

            app.run()
        except Exception as e:
            logger.critical("Failed to run GUI: %s", e, exc_info=True)
            print(f"Failed to start GUI: {e}. Falling back to CLI mode...")
            app = CLI(player, playlist, library, settings)
            app.run()
    else:
        logger.info("Starting PLY in CLI mode...")
        # In CLI, if no path was provided, notify the user or load history/last played
        if not playlist.songs:
            # Try to load last folder if available
            last_f = settings.get("last_folder")
            if last_f and Path(last_f).exists():
                logger.info("Loading last scanned folder: %s", last_f)
                songs = library.scan_directory(Path(last_f))
                for song in songs:
                    playlist.add_song(song)
            else:
                print("Error: No audio files or folder specified. Usage: ply <file_or_folder>")
                sys.exit(1)

        # Autoplay first song in CLI
        if playlist.songs:
            # Match last song if possible, or play first
            last_s = settings.get("last_song")
            start_song = playlist.songs[0]
            if last_s and Path(last_s).exists():
                last_s_path = Path(last_s)
                for s in playlist.songs:
                    if s.filepath == last_s_path:
                        start_song = s
                        break
            
            playlist.set_current_by_song(start_song)
            player.play(start_song)
            library.add_to_history(start_song)
            settings.set("last_song", str(start_song.filepath))

        app = CLI(player, playlist, library, settings)
        app.run()

if __name__ == "__main__":
    main()
