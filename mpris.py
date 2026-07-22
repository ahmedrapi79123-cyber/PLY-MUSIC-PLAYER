"""MPRIS2 D-Bus media player interface for PLY.

Exposes the org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player
interfaces so desktop panel plugins (PulseAudio plugin, sound indicator,
etc.) can show playback controls and track info - exactly like Rhythmbox.
"""

import threading
from typing import Optional, Callable, List

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False

from config import logger

MPRIS_BUS_NAME    = "org.mpris.MediaPlayer2.ply"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_IFACE       = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
DBUS_PROPS_IFACE  = "org.freedesktop.DBus.Properties"


class MPRISService(dbus.service.Object):
    """Implements the MPRIS2 D-Bus interface for PLY."""

    def __init__(self, bus, on_play=None, on_pause=None, on_stop=None,
                 on_next=None, on_previous=None, on_seek=None,
                 on_raise_window=None):
        super().__init__(bus, MPRIS_OBJECT_PATH)
        self._on_play        = on_play
        self._on_pause       = on_pause
        self._on_stop        = on_stop
        self._on_next        = on_next
        self._on_previous    = on_previous
        self._on_seek        = on_seek
        self._on_raise_window = on_raise_window

        # Internal state
        self._playback_status = "Stopped"
        self._metadata: dict = {}
        self._volume: float  = 0.7
        self._position: int  = 0   # microseconds

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2 interface
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

    @dbus.service.method(DBUS_PROPS_IFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self._get_property(interface, prop)

    @dbus.service.method(DBUS_PROPS_IFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == MPRIS_IFACE:
            return {
                "CanQuit":             dbus.Boolean(True),
                "CanRaise":            dbus.Boolean(True),
                "HasTrackList":        dbus.Boolean(False),
                "Identity":            dbus.String("PLY Music Player"),
                "DesktopEntry":        dbus.String("ply"),
                "SupportedUriSchemes": dbus.Array(["file"], signature="s"),
                "SupportedMimeTypes":  dbus.Array([
                    "audio/mpeg", "audio/ogg", "audio/flac",
                    "audio/webm", "audio/mp4", "audio/x-wav"
                ], signature="s"),
            }
        elif interface == MPRIS_PLAYER_IFACE:
            return self._all_player_properties()
        return {}

    @dbus.service.method(DBUS_PROPS_IFACE,
                         in_signature="ssv")
    def Set(self, interface, prop, value):
        if interface == MPRIS_PLAYER_IFACE and prop == "Volume":
            self._volume = float(value)

    @dbus.service.signal(DBUS_PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2.Player interface — Methods
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
    def Seek(self, offset_us):
        if self._on_seek:
            self._on_seek(offset_us / 1_000_000)

    @dbus.service.method(MPRIS_PLAYER_IFACE, in_signature="ox")
    def SetPosition(self, trackid, position_us):
        if self._on_seek:
            self._on_seek(position_us / 1_000_000)

    @dbus.service.method(MPRIS_PLAYER_IFACE, in_signature="s")
    def OpenUri(self, uri):
        pass

    # ------------------------------------------------------------------ #
    # org.mpris.MediaPlayer2.Player interface — Seeked signal
    # ------------------------------------------------------------------ #
    @dbus.service.signal(MPRIS_PLAYER_IFACE, signature="x")
    def Seeked(self, position_us):
        pass

    # ------------------------------------------------------------------ #
    # State updaters (called by PLY internals)
    # ------------------------------------------------------------------ #
    def _all_player_properties(self):
        return {
            "PlaybackStatus": dbus.String(self._playback_status),
            "LoopStatus":     dbus.String("None"),
            "Rate":           dbus.Double(1.0),
            "Shuffle":        dbus.Boolean(False),
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

    def _get_property(self, interface, prop):
        props = self.GetAll(interface)
        return props.get(prop, dbus.String(""))

    def update_playback_status(self, status: str):
        """Update playback status: 'Playing', 'Paused', or 'Stopped'."""
        self._playback_status = status
        self.PropertiesChanged(
            MPRIS_PLAYER_IFACE,
            {"PlaybackStatus": dbus.String(status)},
            []
        )

    def update_metadata(self, title: str, artist: str, album: str,
                        duration_s: float, track_id: str = "/org/ply/track/0"):
        """Update the current track metadata."""
        self._metadata = {
            "mpris:trackid":  dbus.ObjectPath(track_id),
            "mpris:length":   dbus.Int64(int(duration_s * 1_000_000)),
            "xesam:title":    dbus.String(title),
            "xesam:artist":   dbus.Array([artist], signature="s"),
            "xesam:album":    dbus.String(album),
        }
        self.PropertiesChanged(
            MPRIS_PLAYER_IFACE,
            {"Metadata": dbus.Dictionary(self._metadata, signature="sv")},
            []
        )

    def update_position(self, position_s: float):
        """Update current playback position."""
        self._position = int(position_s * 1_000_000)

    def update_volume(self, volume_0_100: int):
        """Update volume (0–100 scale)."""
        self._volume = volume_0_100 / 100.0
        self.PropertiesChanged(
            MPRIS_PLAYER_IFACE,
            {"Volume": dbus.Double(self._volume)},
            []
        )


class MPRISController:
    """Manages the MPRIS2 D-Bus service in a background GLib thread."""

    def __init__(self):
        self._service: Optional[MPRISService] = None
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._bus: Optional[dbus.SessionBus] = None

    def start(self, on_play=None, on_pause=None, on_stop=None,
              on_next=None, on_previous=None, on_seek=None,
              on_raise_window=None) -> bool:
        """Start the MPRIS2 D-Bus service. Returns True on success."""
        if not DBUS_AVAILABLE:
            logger.warning("python3-dbus not available. MPRIS2 disabled.")
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
                on_raise_window=on_raise_window,
            )
            self._loop = GLib.MainLoop()
            self._thread = threading.Thread(
                target=self._loop.run, daemon=True
            )
            self._thread.start()
            logger.info("MPRIS2 D-Bus service started as '%s'", MPRIS_BUS_NAME)
            return True
        except Exception as e:
            logger.error("Failed to start MPRIS2 service: %s", e)
            return False

    def stop(self):
        """Stop the MPRIS2 D-Bus service."""
        if self._loop and self._loop.is_running():
            self._loop.quit()

    def update_playing(self, title: str, artist: str, album: str,
                       duration_s: float, volume: int):
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
            logger.warning("MPRIS2 update_playing error: %s", e)

    def update_paused(self):
        if self._service:
            try:
                self._service.update_playback_status("Paused")
            except Exception as e:
                logger.warning("MPRIS2 update_paused error: %s", e)

    def update_stopped(self):
        if self._service:
            try:
                self._service.update_playback_status("Stopped")
            except Exception as e:
                logger.warning("MPRIS2 update_stopped error: %s", e)

    def update_position(self, position_s: float):
        if self._service:
            try:
                self._service.update_position(position_s)
            except Exception:
                pass
