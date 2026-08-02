"""MPRIS2 D-Bus media player interface for PLY.

Exposes the org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player
interfaces so desktop panel plugins (PulseAudio plugin, sound indicator,
etc.) can show playback controls and track info.
"""

import threading
import urllib.parse
from pathlib import Path
from typing import Optional, Callable

try:
    import dbus                         # type: ignore
    import dbus.service                 # type: ignore
    import dbus.mainloop.glib           # type: ignore
    from gi.repository import GLib      # type: ignore
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False

from config import logger

MPRIS_BUS_NAME     = "org.mpris.MediaPlayer2.ply"
MPRIS_OBJECT_PATH  = "/org/mpris/MediaPlayer2"
MPRIS_IFACE        = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
DBUS_PROPS_IFACE   = "org.freedesktop.DBus.Properties"


class MPRISService(dbus.service.Object):
    """Implements the MPRIS2 D-Bus interface for PLY."""

    def __init__(
        self,
        bus,
        on_play=None,
        on_pause=None,
        on_stop=None,
        on_next=None,
        on_previous=None,
        on_seek=None,
        on_open_uri=None,
        on_raise_window=None,
        get_loop_status: Optional[Callable[[], str]] = None,
        get_shuffle: Optional[Callable[[], bool]] = None,
    ):
        super().__init__(bus, MPRIS_OBJECT_PATH)
        self._on_play         = on_play
        self._on_pause        = on_pause
        self._on_stop         = on_stop
        self._on_next         = on_next
        self._on_previous     = on_previous
        self._on_seek         = on_seek
        self._on_open_uri     = on_open_uri
        self._on_raise_window = on_raise_window
        self._get_loop_status = get_loop_status
        self._get_shuffle     = get_shuffle

        # Internal state
        self._playback_status: str  = "Stopped"
        self._metadata: dict        = {}
        self._volume: float         = 0.7
        self._position: int         = 0   # microseconds

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2 — Root interface                            #
    # ------------------------------------------------------------------ #

    @dbus.service.method(MPRIS_IFACE)
    def Raise(self):
        """Bring the player window to the front."""
        if self._on_raise_window:
            self._on_raise_window()

    @dbus.service.method(MPRIS_IFACE)
    def Quit(self):
        """Quit the player."""
        if self._on_stop:
            self._on_stop()

    # ------------------------------------------------------------------ #
    # org.freedesktop.DBus.Properties                                    #
    # ------------------------------------------------------------------ #

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self._get_property(interface, prop)

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == MPRIS_IFACE:
            return {
                "CanQuit":             dbus.Boolean(True),
                "CanRaise":            dbus.Boolean(True),
                "HasTrackList":        dbus.Boolean(False),
                "Identity":            dbus.String("PLY Music Player"),
                "DesktopEntry":        dbus.String("io.github.ahmed.ply"),
                "SupportedUriSchemes": dbus.Array(["file"], signature="s"),
                "SupportedMimeTypes":  dbus.Array(
                    [
                        "audio/mpeg",
                        "audio/ogg",
                        "audio/flac",
                        "audio/x-flac",
                        "audio/opus",
                        "audio/mp4",
                        "audio/x-m4a",
                        "audio/x-wav",
                    ],
                    signature="s",
                ),
            }
        elif interface == MPRIS_PLAYER_IFACE:
            return self._all_player_properties()
        return {}

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ssv")
    def Set(self, interface, prop, value):
        if interface == MPRIS_PLAYER_IFACE and prop == "Volume":
            self._volume = max(0.0, min(1.0, float(value)))

    @dbus.service.signal(DBUS_PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2.Player — Methods                            #
    # ------------------------------------------------------------------ #

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def Play(self):
        if self._on_play:
            self._on_play()

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def Pause(self):
        if self._on_pause:
            self._on_pause()

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def PlayPause(self):
        if self._playback_status == "Playing":
            if self._on_pause:
                self._on_pause()
        else:
            if self._on_play:
                self._on_play()

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def Stop(self):
        if self._on_stop:
            self._on_stop()

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def Next(self):
        if self._on_next:
            self._on_next()

    @dbus.service.method(MPRIS_PLAYER_IFACE)
    def Previous(self):
        if self._on_previous:
            self._on_previous()

    @dbus.service.method(MPRIS_PLAYER_IFACE, in_signature="x")
    def Seek(self, offset_us: int):
        """Seek by offset (microseconds, may be negative)."""
        if self._on_seek:
            # Convert current position + offset to absolute seconds
            current_s = self._position / 1_000_000
            new_pos_s = max(0.0, current_s + offset_us / 1_000_000)
            self._on_seek(new_pos_s)

    @dbus.service.method(MPRIS_PLAYER_IFACE, in_signature="ox")
    def SetPosition(self, trackid, position_us: int):
        """Seek to absolute position (microseconds)."""
        if self._on_seek:
            self._on_seek(max(0.0, position_us / 1_000_000))

    @dbus.service.method(MPRIS_PLAYER_IFACE, in_signature="s")
    def OpenUri(self, uri: str):
        """Open and play the given URI.

        Supports file:// URIs and bare file paths.
        Calls the on_open_uri callback with the resolved Path.
        """
        try:
            if uri.startswith("file://"):
                path = Path(urllib.parse.unquote(uri[7:]))
            else:
                path = Path(uri)

            path = path.resolve()

            if not path.exists():
                logger.warning("MPRIS OpenUri: file not found: %s", path)
                return

            if not path.is_file():
                logger.warning("MPRIS OpenUri: not a file: %s", path)
                return

            if self._on_open_uri:
                self._on_open_uri(path)
                logger.info("MPRIS OpenUri: opening '%s'", path)
            else:
                logger.warning("MPRIS OpenUri: no callback registered.")
        except Exception as e:
            logger.error("MPRIS OpenUri error for '%s': %s", uri, e)

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2.Player — Signals                            #
    # ------------------------------------------------------------------ #

    @dbus.service.signal(MPRIS_PLAYER_IFACE, signature="x")
    def Seeked(self, position_us: int):
        pass

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _loop_status(self) -> str:
        """Maps PLY repeat_mode to MPRIS LoopStatus string."""
        if self._get_loop_status:
            mode = self._get_loop_status()
            return {"off": "None", "all": "Playlist", "single": "Track"}.get(mode, "None")
        return "None"

    def _shuffle_state(self) -> bool:
        if self._get_shuffle:
            return bool(self._get_shuffle())
        return False

    def _all_player_properties(self) -> dict:
        return {
            "PlaybackStatus": dbus.String(self._playback_status),
            "LoopStatus":     dbus.String(self._loop_status()),
            "Rate":           dbus.Double(1.0),
            "Shuffle":        dbus.Boolean(self._shuffle_state()),
            "Metadata":       dbus.Dictionary(self._metadata, signature="sv"),
            "Volume":         dbus.Double(self._volume),
            "Position":       dbus.Int64(self._position),
            "MinimumRate":    dbus.Double(1.0),
            "MaximumRate":    dbus.Double(1.0),
            "CanGoNext":      dbus.Boolean(True),
            "CanGoPrevious":  dbus.Boolean(True),
            "CanPlay":        dbus.Boolean(True),
            "CanPause":       dbus.Boolean(True),
            "CanSeek":        dbus.Boolean(True),
            "CanControl":     dbus.Boolean(True),
        }

    def _get_property(self, interface: str, prop: str):
        props = self.GetAll(interface)
        return props.get(prop, dbus.String(""))

    # ------------------------------------------------------------------ #
    # State updaters (called by PLY internals)                           #
    # ------------------------------------------------------------------ #

    def update_playback_status(self, status: str) -> None:
        """Update playback status: 'Playing', 'Paused', or 'Stopped'."""
        self._playback_status = status
        try:
            self.PropertiesChanged(
                MPRIS_PLAYER_IFACE,
                {"PlaybackStatus": dbus.String(status)},
                [],
            )
        except Exception as e:
            logger.debug("MPRIS PropertiesChanged error: %s", e)

    def update_metadata(
        self,
        title: str,
        artist: str,
        album: str,
        duration_s: float,
        track_id: str = "/org/ply/track/0",
    ) -> None:
        """Update the current track metadata."""
        self._metadata = {
            "mpris:trackid": dbus.ObjectPath(track_id),
            "mpris:length":  dbus.Int64(int(duration_s * 1_000_000)),
            "xesam:title":   dbus.String(title),
            "xesam:artist":  dbus.Array([artist], signature="s"),
            "xesam:album":   dbus.String(album),
        }
        try:
            self.PropertiesChanged(
                MPRIS_PLAYER_IFACE,
                {"Metadata": dbus.Dictionary(self._metadata, signature="sv")},
                [],
            )
        except Exception as e:
            logger.debug("MPRIS metadata update error: %s", e)

    def update_position(self, position_s: float) -> None:
        """Update current playback position (seconds)."""
        self._position = int(position_s * 1_000_000)

    def update_volume(self, volume_0_100: int) -> None:
        """Update volume (0–100 scale → 0.0–1.0)."""
        self._volume = max(0.0, min(1.0, volume_0_100 / 100.0))
        try:
            self.PropertiesChanged(
                MPRIS_PLAYER_IFACE,
                {"Volume": dbus.Double(self._volume)},
                [],
            )
        except Exception as e:
            logger.debug("MPRIS volume update error: %s", e)

    def update_loop_and_shuffle(self) -> None:
        """Emit property change for LoopStatus and Shuffle."""
        try:
            self.PropertiesChanged(
                MPRIS_PLAYER_IFACE,
                {
                    "LoopStatus": dbus.String(self._loop_status()),
                    "Shuffle":    dbus.Boolean(self._shuffle_state()),
                },
                [],
            )
        except Exception as e:
            logger.debug("MPRIS loop/shuffle update error: %s", e)


# ---------------------------------------------------------------------------
# High-level controller
# ---------------------------------------------------------------------------

class MPRISController:
    """Manages the MPRIS2 D-Bus service in a background GLib main loop thread."""

    def __init__(self) -> None:
        self._service: Optional[MPRISService] = None
        self._loop: Optional[GLib.MainLoop]   = None
        self._thread: Optional[threading.Thread] = None
        self._bus = None

    def start(
        self,
        on_play=None,
        on_pause=None,
        on_stop=None,
        on_next=None,
        on_previous=None,
        on_seek=None,
        on_open_uri=None,
        on_raise_window=None,
        get_loop_status: Optional[Callable[[], str]] = None,
        get_shuffle: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Start the MPRIS2 D-Bus service. Returns True on success."""
        if not DBUS_AVAILABLE:
            logger.warning("python3-dbus not available — MPRIS2 disabled.")
            return False

        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SessionBus()
            self._bus.request_name(MPRIS_BUS_NAME)
            self._service = MPRISService(
                self._bus,
                on_play=on_play,
                on_pause=on_pause,
                on_stop=on_stop,
                on_next=on_next,
                on_previous=on_previous,
                on_seek=on_seek,
                on_open_uri=on_open_uri,
                on_raise_window=on_raise_window,
                get_loop_status=get_loop_status,
                get_shuffle=get_shuffle,
            )
            self._loop = GLib.MainLoop()
            self._thread = threading.Thread(target=self._loop.run, daemon=True)
            self._thread.start()
            logger.info("MPRIS2 D-Bus service started as '%s'", MPRIS_BUS_NAME)
            return True
        except Exception as e:
            logger.error("Failed to start MPRIS2 service: %s", e)
            return False

    def stop(self) -> None:
        """Stop the MPRIS2 D-Bus service."""
        if self._loop and self._loop.is_running():
            self._loop.quit()

    # ------------------------------------------------------------------ #
    # Public state-update helpers                                        #
    # ------------------------------------------------------------------ #

    def update_playing(
        self,
        title: str,
        artist: str,
        album: str,
        duration_s: float,
        volume: int,
    ) -> None:
        """Notify MPRIS2 that a new song is playing."""
        if not self._service:
            return
        try:
            import hashlib
            track_id = "/org/ply/track/" + hashlib.md5(title.encode()).hexdigest()[:8]
            self._service.update_metadata(title, artist, album, duration_s, track_id)
            self._service.update_playback_status("Playing")
            self._service.update_volume(volume)
        except Exception as e:
            logger.warning("MPRIS update_playing error: %s", e)

    def update_paused(self) -> None:
        if self._service:
            try:
                self._service.update_playback_status("Paused")
            except Exception as e:
                logger.warning("MPRIS update_paused error: %s", e)

    def update_stopped(self) -> None:
        if self._service:
            try:
                self._service.update_playback_status("Stopped")
            except Exception as e:
                logger.warning("MPRIS update_stopped error: %s", e)

    def update_position(self, position_s: float) -> None:
        if self._service:
            try:
                self._service.update_position(position_s)
            except Exception:
                pass

    def update_loop_and_shuffle(self) -> None:
        if self._service:
            try:
                self._service.update_loop_and_shuffle()
            except Exception as e:
                logger.warning("MPRIS update_loop_and_shuffle error: %s", e)
