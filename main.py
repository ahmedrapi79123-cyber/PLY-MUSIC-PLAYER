"""Entry point for the PLY music player.

Parses command line arguments and routes to either the CLI or GUI.
"""

import sys
import argparse
from pathlib import Path
from config import logger, setup_logging, SUPPORTED_EXTENSIONS
from settings import Settings
from library import Library, Song
from playlist import Playlist
from player import Player
from cli import CLI
from gui import GUI

def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="PLY - A professional, modern command-line and graphical music player."
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

    # Initialize Settings
    settings = Settings()

    # Override settings with CLI flags if provided
    if args.shuffle:
        settings.set("shuffle", True)
    if args.repeat:
        settings.set("repeat", True)
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
        input_path = Path(args.path).resolve()
        if not input_path.exists():
            print(f"Error: Path '{args.path}' does not exist.")
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

    # Determine execution mode: CLI or GUI
    # If --gui flag is set or no path is provided, run GUI mode.
    # Otherwise run CLI mode.
    run_gui = args.gui or (len(sys.argv) == 1)

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
                    on_raise_window = lambda: app.root.after(0, app.show_window),
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
