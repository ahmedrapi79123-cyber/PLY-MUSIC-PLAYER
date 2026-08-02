"""Audio playback engine for the PLY music player.

Uses GStreamer playbin - the same backend as Rhythmbox, Banshee, and GNOME Music.
Supports any audio format (MP3, OGG, FLAC, WebM/Opus, M4A/AAC, WAV) regardless
of the file extension, with full seek, pause, resume, and volume control.
"""

import time
import threading
from typing import Optional, Callable
from pathlib import Path

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    GST_AVAILABLE = True
except Exception:
    GST_AVAILABLE = False

from config import logger
from library import Song


class Player:
    """Controls audio playback using GStreamer playbin (same engine as Rhythmbox)."""

    def __init__(self, on_song_end_callback: Optional[Callable[[], None]] = None) -> None:
        self.current_song: Optional[Song] = None
        self.state: str = "stopped"   # "playing", "paused", "stopped"
        self.volume: int = 70
        self.on_song_end_callback = on_song_end_callback
        self.is_initialized = False
        self._playbin = None
        self._bus_thread: Optional[threading.Thread] = None
        self._stop_bus = threading.Event()

        self._play_lock = threading.Lock()
        self.playback_token = 0

        if not GST_AVAILABLE:
            logger.error("GStreamer (python3-gi) is not available. Cannot initialize player.")
            return

        try:
            self._playbin = Gst.ElementFactory.make('playbin', 'ply-playbin')
            if self._playbin is None:
                raise RuntimeError("Failed to create GStreamer playbin element.")
            # Set initial volume
            self._playbin.set_property('volume', self.volume / 100.0)
            self.is_initialized = True
            logger.info("GStreamer playbin initialized successfully.")
            # Start bus monitoring thread
            self._bus_thread = threading.Thread(target=self._bus_loop, daemon=True)
            self._bus_thread.start()
        except Exception as e:
            logger.error("Failed to initialize GStreamer playbin: %s", e)

    def set_on_song_end(self, callback: Callable[[], None]) -> None:
        """Sets the callback to trigger when a song finishes."""
        self.on_song_end_callback = callback

    def play(self, song: Song, start_pos: float = 0.0) -> bool:
        """Plays a Song using GStreamer. Handles any audio format automatically.

        Returns True on success, False on failure.
        """
        if not self.is_initialized or self._playbin is None:
            logger.warning("Player not initialized. Cannot play: %s", song)
            return False

        with self._play_lock:
            self.playback_token += 1
            current_token = self.playback_token

            try:
                # Stop any current playback
                self._playbin.set_state(Gst.State.NULL)

                # Set URI
                filepath = Path(song.filepath).resolve()
                uri = filepath.as_uri()
                self._playbin.set_property('uri', uri)

                # Start playback
                ret = self._playbin.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    logger.error("GStreamer failed to set PLAYING state for: %s", song.filepath)
                    self.state = "stopped"
                    return False

                # Wait briefly for state transition
                state_ret, _cur, _pend = self._playbin.get_state(timeout=Gst.SECOND * 3)
                if state_ret == Gst.StateChangeReturn.FAILURE:
                    logger.error("GStreamer state transition failed for: %s", song.filepath)
                    self._playbin.set_state(Gst.State.NULL)
                    self.state = "stopped"
                    return False

                # Seek to start_pos if needed
                if start_pos > 0.0:
                    self._playbin.seek_simple(
                        Gst.Format.TIME,
                        Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                        int(start_pos * Gst.SECOND)
                    )

                self.current_song = song
                self.state = "playing"
                logger.info("GStreamer playing: %s (from %.1fs)", song, start_pos)
                return True

            except Exception as e:
                logger.error("GStreamer play error for %s: %s", song.filepath, e)
                self.state = "stopped"
                return False

    def pause(self) -> None:
        """Pauses current playback."""
        with self._play_lock:
            if not self.is_initialized or self.state != "playing":
                return
            try:
                self._playbin.set_state(Gst.State.PAUSED)
                self.state = "paused"
                logger.info("Playback paused.")
            except Exception as e:
                logger.error("Failed to pause: %s", e)

    def resume(self) -> None:
        """Resumes paused playback."""
        with self._play_lock:
            if not self.is_initialized or self.state != "paused":
                return
            try:
                self._playbin.set_state(Gst.State.PLAYING)
                self.state = "playing"
                logger.info("Playback resumed.")
            except Exception as e:
                logger.error("Failed to resume: %s", e)

    def stop(self) -> None:
        """Stops playback completely."""
        with self._play_lock:
            if not self.is_initialized:
                return
            try:
                self.playback_token += 1
                self._playbin.set_state(Gst.State.NULL)
                self.state = "stopped"
                self.current_song = None
                logger.info("Playback stopped.")
            except Exception as e:
                logger.error("Failed to stop: %s", e)

    def seek(self, position: float) -> None:
        """Seeks to the given position in seconds."""
        if not self.is_initialized or not self.current_song:
            return
        duration = self.current_song.duration
        if duration > 0:
            position = max(0.0, min(position, duration))
        try:
            self._playbin.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                int(position * Gst.SECOND)
            )
            logger.info("Seeked to %.1f seconds.", position)
        except Exception as e:
            logger.error("Failed to seek to %.1f: %s", position, e)

    def set_volume(self, volume: int) -> None:
        """Sets the playback volume (0 to 100)."""
        self.volume = max(0, min(volume, 100))
        if self.is_initialized and self._playbin:
            try:
                self._playbin.set_property('volume', self.volume / 100.0)
            except Exception as e:
                logger.error("Failed to set volume: %s", e)

    def get_elapsed_time(self) -> float:
        """Gets the current elapsed playback position in seconds."""
        if not self.is_initialized or self.state == "stopped" or not self._playbin:
            return 0.0
        try:
            success, pos_ns = self._playbin.query_position(Gst.Format.TIME)
            if success and pos_ns >= 0:
                return pos_ns / Gst.SECOND
        except Exception:
            pass
        return 0.0

    def _bus_loop(self) -> None:
        """Background thread: monitors GStreamer bus for EOS and ERROR messages."""
        if not self._playbin:
            return
        bus = self._playbin.get_bus()
        while not self._stop_bus.is_set():
            msg = bus.timed_pop_filtered(
                100 * Gst.MSECOND,
                Gst.MessageType.EOS | Gst.MessageType.ERROR
            )
            if msg is None:
                continue
            
            with self._play_lock:
                if self.state != "playing":
                    continue
                
                if msg.type == Gst.MessageType.EOS:
                    logger.info("Song finished playing naturally (GStreamer EOS).")
                    self.state = "stopped"
                    self.playback_token += 1
                    if self.on_song_end_callback:
                        threading.Thread(target=self.on_song_end_callback, daemon=True).start()
                
                elif msg.type == Gst.MessageType.ERROR:
                    err, debug = msg.parse_error()
                    logger.error("GStreamer error: %s | debug: %s", err, debug)
                    self.state = "stopped"
                    self.playback_token += 1
                    if self.on_song_end_callback:
                        threading.Thread(target=self.on_song_end_callback, daemon=True).start()

    def close(self) -> None:
        """Cleans up GStreamer resources."""
        self._stop_bus.set()
        if self.is_initialized and self._playbin:
            try:
                self._playbin.set_state(Gst.State.NULL)
                logger.info("GStreamer player closed.")
            except Exception as e:
                logger.error("Error closing GStreamer player: %s", e)
