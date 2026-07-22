"""Playlist manager for the PLY music player.

Handles song order, play indexes, shuffling, repeat modes, and M3U/M3U8 file formats.
"""

import random
from pathlib import Path
from typing import List, Optional
from config import logger
from library import Song

class Playlist:
    """Manages a list of songs, supporting playback modes like shuffle and repeat."""

    def __init__(self) -> None:
        self.original_songs: List[Song] = []
        self.songs: List[Song] = []
        self.current_index: int = -1
        self._shuffle: bool = False
        # Repeat modes: "off" (stop at end), "all" (loop playlist), "single" (loop current song)
        self.repeat_mode: str = "off"

    @property
    def shuffle(self) -> bool:
        """Returns True if shuffle mode is active."""
        return self._shuffle

    @shuffle.setter
    def shuffle(self, enabled: bool) -> None:
        """Toggles shuffle mode and reorganizes the songs list."""
        if self._shuffle == enabled:
            return

        self._shuffle = enabled
        current_song = self.current_song

        if enabled:
            # Shuffle current play order
            if self.songs:
                # Keep current song at the beginning if playing
                songs_to_shuffle = [s for s in self.songs if s != current_song]
                random.shuffle(songs_to_shuffle)
                if current_song:
                    self.songs = [current_song] + songs_to_shuffle
                    self.current_index = 0
                else:
                    self.songs = songs_to_shuffle
                    self.current_index = 0 if self.songs else -1
        else:
            # Restore original order
            self.songs = list(self.original_songs)
            if current_song in self.songs:
                self.current_index = self.songs.index(current_song)
            else:
                self.current_index = -1

        logger.info("Shuffle set to %s. Current index: %d", enabled, self.current_index)

    @property
    def current_song(self) -> Optional[Song]:
        """Gets the currently selected song."""
        if 0 <= self.current_index < len(self.songs):
            return self.songs[self.current_index]
        return None

    def add_song(self, song: Song) -> None:
        """Appends a song to the playlist."""
        self.original_songs.append(song)
        if self.shuffle:
            # If shuffled, insert at a random position after current index
            insert_pos = self.current_index + 1 if self.current_index >= 0 else 0
            if insert_pos < len(self.songs):
                self.songs.insert(random.randint(insert_pos, len(self.songs)), song)
            else:
                self.songs.append(song)
        else:
            self.songs.append(song)

        if self.current_index == -1 and self.songs:
            self.current_index = 0

    def remove_song(self, index: int) -> None:
        """Removes a song from the active list by index."""
        if 0 <= index < len(self.songs):
            song = self.songs[index]
            self.songs.pop(index)
            if song in self.original_songs:
                self.original_songs.remove(song)

            # Adjust index
            if self.current_index == index:
                if not self.songs:
                    self.current_index = -1
                elif self.current_index >= len(self.songs):
                    self.current_index = 0
            elif self.current_index > index:
                self.current_index -= 1

    def clear(self) -> None:
        """Clears the playlist completely."""
        self.original_songs.clear()
        self.songs.clear()
        self.current_index = -1

    def next_song(self) -> Optional[Song]:
        """Calculates and moves to the next song based on play modes."""
        if not self.songs:
            return None

        if self.repeat_mode == "single":
            # Keep same song
            return self.current_song

        if self.current_index < len(self.songs) - 1:
            self.current_index += 1
        else:
            if self.repeat_mode == "all":
                self.current_index = 0
            else:
                # End of playlist, return None to stop playback
                return None

        return self.current_song

    def prev_song(self) -> Optional[Song]:
        """Moves to the previous song in the list."""
        if not self.songs:
            return None

        if self.repeat_mode == "single":
            return self.current_song

        if self.current_index > 0:
            self.current_index -= 1
        else:
            if self.repeat_mode == "all":
                self.current_index = len(self.songs) - 1
            else:
                # Wrap to beginning but don't play if repeat is off, or just keep first
                self.current_index = 0

        return self.current_song

    def set_current_by_song(self, song: Song) -> bool:
        """Sets the active index to the matching song."""
        if song in self.songs:
            self.current_index = self.songs.index(song)
            return True
        return False

    def load_m3u(self, m3u_path: Path) -> int:
        """Loads playlist from an M3U or M3U8 file.

        Resolves relative paths relative to the playlist file.
        Returns the number of songs loaded.
        """
        logger.info("Loading playlist: %s", m3u_path)
        path = Path(m3u_path)
        if not path.exists():
            logger.warning("Playlist file not found: %s", m3u_path)
            return 0

        self.clear()
        loaded_count = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Resolve path relative to m3u file parent if not absolute
                song_path = Path(line)
                if not song_path.is_absolute():
                    song_path = (path.parent / song_path).resolve()

                if song_path.exists() and song_path.is_file():
                    try:
                        song = Song(song_path)
                        self.add_song(song)
                        loaded_count += 1
                    except Exception as e:
                        logger.error("Failed to load song %s in playlist: %s", song_path, e)
        except Exception as e:
            logger.error("Failed to read M3U file: %s", e)

        # Sync active list
        if not self.shuffle:
            self.songs = list(self.original_songs)

        logger.info("Loaded %d songs from playlist.", loaded_count)
        return loaded_count

    def save_m3u(self, m3u_path: Path) -> bool:
        """Saves current original_songs to an M3U file."""
        logger.info("Saving playlist to: %s", m3u_path)
        path = Path(m3u_path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for song in self.original_songs:
                    f.write(f"#EXTINF:{int(song.duration)},{song.artist} - {song.title}\n")
                    # Save path relative to playlist if possible, or absolute
                    try:
                        relative_path = song.filepath.relative_to(path.parent)
                        f.write(f"{relative_path}\n")
                    except ValueError:
                        f.write(f"{song.filepath.absolute()}\n")
            logger.info("Playlist saved successfully.")
            return True
        except Exception as e:
            logger.error("Failed to save playlist: %s", e)
            return False
