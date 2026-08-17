"""MPRIS2 D-Bus media player interface for PLY.

Exposes the org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player
interfaces so desktop panel plugins (sound indicators, taskbars, etc.)
can show playback controls and track info.

This implementation uses Gio.DBus (PyGObject) rather than dbus-python,
making it compatible with Flatpak sandboxes without any extra dependencies.
"""

import hashlib
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional

try:
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import Gio, GLib  # type: ignore
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False

from config import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MPRIS_BUS_NAME      = "org.mpris.MediaPlayer2.ply"
MPRIS_OBJECT_PATH   = "/org/mpris/MediaPlayer2"
MPRIS_IFACE         = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_IFACE  = "org.mpris.MediaPlayer2.Player"
DBUS_PROPS_IFACE    = "org.freedesktop.DBus.Properties"
DBUS_INTROSPECT     = "org.freedesktop.DBus.Introspectable"

# ---------------------------------------------------------------------------
# D-Bus XML introspection
# ---------------------------------------------------------------------------
_INTROSPECT_XML = """
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
  "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="org.freedesktop.DBus.Introspectable">
    <method name="Introspect">
      <arg direction="out" name="data" type="s"/>
    </method>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg direction="in"  name="interface_name" type="s"/>
      <arg direction="in"  name="property_name"  type="s"/>
      <arg direction="out" name="value"           type="v"/>
    </method>
    <method name="GetAll">
      <arg direction="in"  name="interface_name" type="s"/>
      <arg direction="out" name="props"          type="a{sv}"/>
    </method>
    <method name="Set">
      <arg direction="in" name="interface_name" type="s"/>
      <arg direction="in" name="property_name"  type="s"/>
      <arg direction="in" name="value"          type="v"/>
    </method>
    <signal name="PropertiesChanged">
      <arg name="interface_name" type="s"/>
      <arg name="changed_properties" type="a{sv}"/>
      <arg name="invalidated_properties" type="as"/>
    </signal>
  </interface>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit"             type="b"  access="read"/>
    <property name="CanRaise"            type="b"  access="read"/>
    <property name="HasTrackList"        type="b"  access="read"/>
    <property name="Identity"            type="s"  access="read"/>
    <property name="DesktopEntry"        type="s"  access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes"  type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Play"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId"  type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" name="Uri" type="s"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s"     access="read"/>
    <property name="LoopStatus"     type="s"     access="readwrite"/>
    <property name="Rate"           type="d"     access="readwrite"/>
    <property name="Shuffle"        type="b"     access="readwrite"/>
    <property name="Metadata"       type="a{sv}" access="read"/>
    <property name="Volume"         type="d"     access="readwrite"/>
    <property name="Position"       type="x"     access="read"/>
    <property name="MinimumRate"    type="d"     access="read"/>
    <property name="MaximumRate"    type="d"     access="read"/>
    <property name="CanGoNext"      type="b"     access="read"/>
    <property name="CanGoPrevious"  type="b"     access="read"/>
    <property name="CanPlay"        type="b"     access="read"/>
    <property name="CanPause"       type="b"     access="read"/>
    <property name="CanSeek"        type="b"     access="read"/>
    <property name="CanControl"     type="b"     access="read"/>
  </interface>
</node>
"""


# ---------------------------------------------------------------------------
# GLib variant helpers
# ---------------------------------------------------------------------------

def _v(type_str: str, value) -> GLib.Variant:
    """Create a GLib.Variant of the given type string."""
    return GLib.Variant(type_str, value)


def _dict_to_variant(d: dict) -> GLib.Variant:
    """Convert a plain dict to GLib.Variant a{sv}."""
    return GLib.Variant("a{sv}", {k: _v("v", v) if not isinstance(v, GLib.Variant) else v
                                   for k, v in d.items()})


# ---------------------------------------------------------------------------
# MPRISServer — Gio.DBus native implementation
# ---------------------------------------------------------------------------

class MPRISServer:
    """Implements MPRIS2 via Gio.DBus (no dbus-python required)."""

    def __init__(self) -> None:
        self._connection: Optional[Gio.DBusConnection] = None
        self._registration_ids: list = []
        self._owner_id: int = 0
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[threading.Thread] = None

        # State
        self._playback_status = "Stopped"
        self._metadata: dict = {}
        self._volume = 0.7
        self._position = 0          # microseconds
        self._loop_status = "None"  # None, Playlist, Track
        self._shuffle = False

        # Callbacks
        self.on_play:         Optional[Callable] = None
        self.on_pause:        Optional[Callable] = None
        self.on_stop:         Optional[Callable] = None
        self.on_next:         Optional[Callable] = None
        self.on_previous:     Optional[Callable] = None
        self.on_seek:         Optional[Callable] = None
        self.on_open_uri:     Optional[Callable] = None
        self.on_raise_window: Optional[Callable] = None
        self.get_loop_status: Optional[Callable[[], str]] = None
        self.get_shuffle:     Optional[Callable[[], bool]] = None

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Connect to session bus and claim the MPRIS bus name. Returns True on success."""
        if not DBUS_AVAILABLE:
            logger.warning("PyGObject/Gio not available — MPRIS2 disabled.")
            return False
        try:
            self._loop = GLib.MainLoop()
            self._owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                MPRIS_BUS_NAME,
                Gio.BusNameOwnerFlags.NONE,
                self._on_bus_acquired,
                self._on_name_acquired,
                self._on_name_lost,
            )
            self._thread = threading.Thread(target=self._loop.run, daemon=True, name="mpris-glib")
            self._thread.start()
            logger.info("MPRIS2 GLib loop started, claiming '%s'", MPRIS_BUS_NAME)
            return True
        except Exception as e:
            logger.error("Failed to start MPRIS2 service: %s", e)
            return False

    def stop(self) -> None:
        """Release the bus name and stop the GLib loop."""
        try:
            if self._owner_id:
                Gio.bus_unown_name(self._owner_id)
            if self._loop and self._loop.is_running():
                self._loop.quit()
        except Exception as e:
            logger.debug("MPRIS stop error: %s", e)

    # ------------------------------------------------------------------
    # Bus acquisition callbacks
    # ------------------------------------------------------------------

    def _on_bus_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        self._connection = connection
        try:
            node_info = Gio.DBusNodeInfo.new_for_xml(_INTROSPECT_XML)
        except Exception as e:
            logger.error("MPRIS: Could not parse introspect XML: %s", e)
            return

        for iface in node_info.interfaces:
            reg_id = connection.register_object(
                MPRIS_OBJECT_PATH,
                iface,
                self._handle_method_call,
                self._handle_get_property,
                self._handle_set_property,
            )
            if reg_id:
                self._registration_ids.append(reg_id)

        logger.info("MPRIS2 registered on D-Bus as '%s'", name)

    def _on_name_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        logger.info("MPRIS2 bus name acquired: %s", name)

    def _on_name_lost(self, connection: Optional[Gio.DBusConnection], name: str) -> None:
        logger.warning("MPRIS2 bus name lost: %s", name)

    # ------------------------------------------------------------------
    # Method call handler
    # ------------------------------------------------------------------

    def _handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        try:
            if interface_name == DBUS_INTROSPECT and method_name == "Introspect":
                invocation.return_value(GLib.Variant("(s)", (_INTROSPECT_XML,)))
                return

            if interface_name == DBUS_PROPS_IFACE:
                self._handle_props_method(method_name, parameters, invocation)
                return

            if interface_name == MPRIS_IFACE:
                self._handle_root_method(method_name, invocation)
                return

            if interface_name == MPRIS_PLAYER_IFACE:
                self._handle_player_method(method_name, parameters, invocation)
                return

            invocation.return_error_literal(
                Gio.io_error_quark(),
                Gio.IOErrorEnum.NOT_SUPPORTED,
                f"Unknown interface: {interface_name}",
            )
        except Exception as e:
            logger.error("MPRIS method call error %s.%s: %s", interface_name, method_name, e)
            try:
                invocation.return_error_literal(
                    Gio.io_error_quark(), Gio.IOErrorEnum.FAILED, str(e)
                )
            except Exception:
                pass

    def _handle_props_method(
        self, method: str, params: GLib.Variant, inv: Gio.DBusMethodInvocation
    ) -> None:
        if method == "GetAll":
            iface = params.get_child_value(0).get_string()
            props = self._get_all_props(iface)
            inv.return_value(GLib.Variant("(a{sv})", (props,)))
        elif method == "Get":
            iface = params.get_child_value(0).get_string()
            prop  = params.get_child_value(1).get_string()
            props = self._get_all_props(iface)
            val   = props.get(prop, GLib.Variant("s", ""))
            inv.return_value(GLib.Variant("(v)", (val,)))
        elif method == "Set":
            iface = params.get_child_value(0).get_string()
            prop  = params.get_child_value(1).get_string()
            val   = params.get_child_value(2).get_child_value(0)
            if iface == MPRIS_PLAYER_IFACE and prop == "Volume":
                self._volume = max(0.0, min(1.0, val.get_double()))
            inv.return_value(None)
        else:
            inv.return_value(None)

    def _handle_root_method(self, method: str, inv: Gio.DBusMethodInvocation) -> None:
        if method == "Raise" and self.on_raise_window:
            self.on_raise_window()
        elif method == "Quit" and self.on_stop:
            self.on_stop()
        inv.return_value(None)

    def _handle_player_method(
        self, method: str, params: GLib.Variant, inv: Gio.DBusMethodInvocation
    ) -> None:
        if   method == "Play"      and self.on_play:      self.on_play()
        elif method == "Pause"     and self.on_pause:     self.on_pause()
        elif method == "Stop"      and self.on_stop:      self.on_stop()
        elif method == "Next"      and self.on_next:      self.on_next()
        elif method == "Previous"  and self.on_previous:  self.on_previous()
        elif method == "PlayPause":
            if self._playback_status == "Playing":
                if self.on_pause: self.on_pause()
            else:
                if self.on_play:  self.on_play()
        elif method == "Seek":
            offset_us = params.get_child_value(0).get_int64()
            if self.on_seek:
                cur_s   = self._position / 1_000_000
                new_s   = max(0.0, cur_s + offset_us / 1_000_000)
                self.on_seek(new_s)
        elif method == "SetPosition":
            pos_us = params.get_child_value(1).get_int64()
            if self.on_seek:
                self.on_seek(max(0.0, pos_us / 1_000_000))
        elif method == "OpenUri":
            uri = params.get_child_value(0).get_string()
            self._open_uri(uri)
        inv.return_value(None)

    def _open_uri(self, uri: str) -> None:
        try:
            if uri.startswith("file://"):
                path = Path(urllib.parse.unquote(uri[7:]))
            else:
                path = Path(uri)
            path = path.resolve()
            if not path.exists() or not path.is_file():
                logger.warning("MPRIS OpenUri: file not found: %s", path)
                return
            if self.on_open_uri:
                self.on_open_uri(path)
                logger.info("MPRIS OpenUri: opened '%s'", path)
        except Exception as e:
            logger.error("MPRIS OpenUri error for '%s': %s", uri, e)

    # ------------------------------------------------------------------
    # Property getter
    # ------------------------------------------------------------------

    def _handle_get_property(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        property_name: str,
    ) -> Optional[GLib.Variant]:
        props = self._get_all_props(interface_name)
        return props.get(property_name)

    def _handle_set_property(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        property_name: str,
        value: GLib.Variant,
    ) -> bool:
        if interface_name == MPRIS_PLAYER_IFACE and property_name == "Volume":
            self._volume = max(0.0, min(1.0, value.get_double()))
            return True
        return False

    def _current_loop_status(self) -> str:
        if self.get_loop_status:
            mode = self.get_loop_status()
            return {"off": "None", "all": "Playlist", "single": "Track"}.get(mode, "None")
        return self._loop_status

    def _current_shuffle(self) -> bool:
        if self.get_shuffle:
            return bool(self.get_shuffle())
        return self._shuffle

    def _get_all_props(self, interface_name: str) -> dict:
        if interface_name == MPRIS_IFACE:
            return {
                "CanQuit":             GLib.Variant("b",  True),
                "CanRaise":            GLib.Variant("b",  True),
                "HasTrackList":        GLib.Variant("b",  False),
                "Identity":            GLib.Variant("s",  "PLY Music Player"),
                "DesktopEntry":        GLib.Variant("s",  "io.github.ahmed.ply"),
                "SupportedUriSchemes": GLib.Variant("as", ["file"]),
                "SupportedMimeTypes":  GLib.Variant("as", [
                    "audio/mpeg", "audio/ogg", "audio/flac", "audio/x-flac",
                    "audio/opus", "audio/mp4", "audio/x-m4a", "audio/x-wav",
                ]),
            }
        elif interface_name == MPRIS_PLAYER_IFACE:
            return {
                "PlaybackStatus": GLib.Variant("s",    self._playback_status),
                "LoopStatus":     GLib.Variant("s",    self._current_loop_status()),
                "Rate":           GLib.Variant("d",    1.0),
                "Shuffle":        GLib.Variant("b",    self._current_shuffle()),
                "Metadata":       GLib.Variant("a{sv}", self._metadata),
                "Volume":         GLib.Variant("d",    self._volume),
                "Position":       GLib.Variant("x",    self._position),
                "MinimumRate":    GLib.Variant("d",    1.0),
                "MaximumRate":    GLib.Variant("d",    1.0),
                "CanGoNext":      GLib.Variant("b",    True),
                "CanGoPrevious":  GLib.Variant("b",    True),
                "CanPlay":        GLib.Variant("b",    True),
                "CanPause":       GLib.Variant("b",    True),
                "CanSeek":        GLib.Variant("b",    True),
                "CanControl":     GLib.Variant("b",    True),
            }
        return {}

    # ------------------------------------------------------------------
    # State update helpers (thread-safe via GLib.idle_add)
    # ------------------------------------------------------------------

    def _emit_properties_changed(self, interface: str, changed: dict) -> None:
        """Emit PropertiesChanged signal — must be called from GLib thread."""
        if not self._connection:
            return
        try:
            self._connection.emit_signal(
                None,
                MPRIS_OBJECT_PATH,
                DBUS_PROPS_IFACE,
                "PropertiesChanged",
                GLib.Variant("(sa{sv}as)", (interface, changed, [])),
            )
        except Exception as e:
            logger.debug("MPRIS PropertiesChanged emit error: %s", e)

    def _schedule(self, fn) -> None:
        """Schedule fn to run on the GLib main loop thread."""
        if self._loop and self._loop.is_running():
            GLib.idle_add(fn)

    def update_playback_status(self, status: str) -> None:
        self._playback_status = status
        self._schedule(lambda: self._emit_properties_changed(
            MPRIS_PLAYER_IFACE, {"PlaybackStatus": GLib.Variant("s", status)}
        ))

    def update_metadata(
        self, title: str, artist: str, album: str,
        duration_s: float, track_id: str = "/org/ply/track/0"
    ) -> None:
        self._metadata = {
            "mpris:trackid": GLib.Variant("o",  track_id),
            "mpris:length":  GLib.Variant("x",  int(duration_s * 1_000_000)),
            "xesam:title":   GLib.Variant("s",  title),
            "xesam:artist":  GLib.Variant("as", [artist]),
            "xesam:album":   GLib.Variant("s",  album),
        }
        meta_copy = dict(self._metadata)
        self._schedule(lambda: self._emit_properties_changed(
            MPRIS_PLAYER_IFACE, {"Metadata": GLib.Variant("a{sv}", meta_copy)}
        ))

    def update_position(self, position_s: float) -> None:
        self._position = int(position_s * 1_000_000)

    def update_volume(self, volume_0_100: int) -> None:
        self._volume = max(0.0, min(1.0, volume_0_100 / 100.0))
        vol = self._volume
        self._schedule(lambda: self._emit_properties_changed(
            MPRIS_PLAYER_IFACE, {"Volume": GLib.Variant("d", vol)}
        ))

    def update_loop_and_shuffle(self) -> None:
        ls = self._current_loop_status()
        sh = self._current_shuffle()
        self._schedule(lambda: self._emit_properties_changed(
            MPRIS_PLAYER_IFACE, {
                "LoopStatus": GLib.Variant("s", ls),
                "Shuffle":    GLib.Variant("b", sh),
            }
        ))


# ---------------------------------------------------------------------------
# MPRISController — public API (same interface as before)
# ---------------------------------------------------------------------------

class MPRISController:
    """High-level controller for the MPRIS2 D-Bus service."""

    def __init__(self) -> None:
        self._server: Optional[MPRISServer] = None

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
        if not DBUS_AVAILABLE:
            logger.warning("PyGObject/Gio not available — MPRIS2 disabled.")
            return False
        self._server = MPRISServer()
        self._server.on_play         = on_play
        self._server.on_pause        = on_pause
        self._server.on_stop         = on_stop
        self._server.on_next         = on_next
        self._server.on_previous     = on_previous
        self._server.on_seek         = on_seek
        self._server.on_open_uri     = on_open_uri
        self._server.on_raise_window = on_raise_window
        self._server.get_loop_status = get_loop_status
        self._server.get_shuffle     = get_shuffle
        return self._server.start()

    def stop(self) -> None:
        if self._server:
            self._server.stop()

    # Public state-update helpers

    def update_playing(
        self, title: str, artist: str, album: str, duration_s: float, volume: int
    ) -> None:
        if not self._server:
            return
        try:
            track_id = "/org/ply/track/" + hashlib.md5(title.encode()).hexdigest()[:8]
            self._server.update_metadata(title, artist, album, duration_s, track_id)
            self._server.update_playback_status("Playing")
            self._server.update_volume(volume)
        except Exception as e:
            logger.warning("MPRIS update_playing error: %s", e)

    def update_paused(self) -> None:
        if self._server:
            try:
                self._server.update_playback_status("Paused")
            except Exception as e:
                logger.warning("MPRIS update_paused error: %s", e)

    def update_stopped(self) -> None:
        if self._server:
            try:
                self._server.update_playback_status("Stopped")
            except Exception as e:
                logger.warning("MPRIS update_stopped error: %s", e)

    def update_position(self, position_s: float) -> None:
        if self._server:
            try:
                self._server.update_position(position_s)
            except Exception:
                pass

    def update_loop_and_shuffle(self) -> None:
        if self._server:
            try:
                self._server.update_loop_and_shuffle()
            except Exception as e:
                logger.warning("MPRIS update_loop_and_shuffle error: %s", e)
