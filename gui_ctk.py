"""CustomTkinter interface for PLY Pro.

The playback, playlist, library, settings, MPRIS and tray behavior is reused
from the existing GUI controller. Every visible application widget created
by this module is a CustomTkinter widget; no ttk/Tk widgets are placed in the
window. File and message dialogs are also implemented as CTkToplevel windows.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import customtkinter as ctk
import tkinter as tk  # StringVar and key/focus integration only; no Tk widgets.
from PIL import Image, ImageTk

from config import ASSETS_DIR, logger, SUPPORTED_EXTENSIONS
from settings import Settings
from themes import ThemeManager
from player import Player
from playlist import Playlist
from library import Library, Song
from utils import format_time, clean_temp_dir
from icons import generate_default_assets
from gui import GUI as _LegacyGUI  # Reuse non-visual playback/session/tray logic.


PALETTES = {
    "dark": {
        "bg": "#101218", "panel": "#191D27", "card": "#222836",
        "fg": "#F4F5F8", "muted": "#9AA4B5", "accent": "#8B5CF6",
        "accent_hover": "#7C3AED", "accent_active": "#6D28D9",
        "border": "#303848", "track": "#343B4B", "success": "#34D399",
        "danger": "#F87171", "selected": "#3B2B68",
    },
    "light": {
        "bg": "#F3F5FA", "panel": "#FFFFFF", "card": "#E9EDF5",
        "fg": "#202434", "muted": "#687386", "accent": "#7651E8",
        "accent_hover": "#6540D2", "accent_active": "#5836BF",
        "border": "#D9DFEA", "track": "#D5DAE5", "success": "#0F9F73",
        "danger": "#D94848", "selected": "#DED5FA",
    },
}


class GUI(_LegacyGUI):
    """PLY Pro GUI implemented with CustomTkinter widgets only."""

    def __init__(self, player: Player, playlist: Playlist, library: Library,
                 settings: Settings) -> None:
        self.player = player
        self.playlist = playlist
        self.library = library
        self.settings = settings
        self.theme_mgr = ThemeManager(dark_mode=settings.get("dark_mode"))

        generate_default_assets()
        ctk.set_appearance_mode("dark" if self.theme_mgr.dark_mode else "light")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("PLY Pro")
        self.root.geometry("1120x740")
        self.root.minsize(900, 620)
        self.root.configure(fg_color=self._colors["bg"])

        self.images: Dict[str, Any] = {}
        self._tk_images: Dict[str, Any] = {}
        self._playlist_buttons: Dict[int, ctk.CTkButton] = {}
        self._scan_in_progress = False
        self.is_dragging_slider = False
        self.search_var = tk.StringVar(master=self.root)
        self.search_var.trace_add("write", self._filter_playlist)
        self.mpris = None

        self._tray_icon = None
        self._tray_menu = None
        self._tray_glib_loop = None
        self._tray_thread = None
        self._tray_glib = None
        self._tray_appindicator = None
        self._gtk_poll_id = None
        self._app_quitting = False

        self._set_window_icon()
        self._create_widgets()
        self._apply_theme()
        self._load_last_session()
        self.player.set_on_song_end(self._on_song_finished)
        self._update_loop()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

    
    def _hide_to_tray(self) -> None:
        """Hide PLY Pro only after the tray icon is available."""
        if self._tray_icon is None:
            self._start_tray_appindicator()

        if self._tray_icon is not None:
            self.root.withdraw()
            logger.info("PLY Pro hidden to system tray.")
        else:
            logger.error("System tray unavailable. Keeping window visible.")

    def _start_tray_appindicator(self) -> None:
        """Create the AppIndicator without a separate GTK thread."""
        if self._tray_icon is not None:
            return

        try:
            import gi
            gi.require_version("AyatanaAppIndicator3", "0.1")
            gi.require_version("Gtk", "3.0")
            gi.require_version("GLib", "2.0")

            from gi.repository import AyatanaAppIndicator3 as AppIndicator
            from gi.repository import Gtk, GLib

            icon_name = "audio-x-generic"
            icon_path = ASSETS_DIR / "music.png"

            icon_dirs = [
                Path("/app/share/icons/hicolor/128x128/apps"),
                Path("/usr/share/icons/hicolor/128x128/apps"),
            ]

            app_icon_name = "io.github.ahmedrapi79123_cyber.PLY-MUSIC-PLAYER"

            for icon_dir in icon_dirs:
                candidate = icon_dir / f"{app_icon_name}.png"
                if candidate.exists():
                    icon_path = candidate
                    break

            if icon_path.exists():
                Gtk.IconTheme.get_default().append_search_path(
                    str(icon_path.parent)
                )
                icon_name = icon_path.stem

            indicator = AppIndicator.Indicator.new(
                "ply-pro",
                icon_name,
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )

            indicator.set_title("PLY Pro")
            indicator.set_status(
                AppIndicator.IndicatorStatus.ACTIVE
            )

            menu = Gtk.Menu()

            def add_item(label: str, callback) -> None:
                item = Gtk.MenuItem(label=label)
                item.connect(
                    "activate",
                    lambda *_args: callback()
                )
                menu.append(item)

            add_item("Open PLY Pro", self.show_window)

            menu.append(Gtk.SeparatorMenuItem())

            add_item("⏮ Previous", self._prev_song)
            add_item("▶/⏸ Play/Pause", self._toggle_play_pause)
            add_item("⏭ Next", self._next_song)

            menu.append(Gtk.SeparatorMenuItem())

            add_item("⏹ Quit PLY Pro", self._quit_app)

            menu.show_all()
            indicator.set_menu(menu)

            self._tray_icon = indicator
            self._tray_menu = menu
            self._tray_glib = GLib
            self._tray_appindicator = AppIndicator

            self._gtk_poll_id = self.root.after(
                25, self._pump_gtk_events
            )

            logger.info("PLY Pro AppIndicator tray started.")

        except Exception:
            self._tray_icon = None
            logger.exception("Failed to start PLY Pro system tray.")

    def _pump_gtk_events(self) -> None:
        """Process GTK events from the CustomTkinter main thread."""
        if self._app_quitting or self._tray_glib is None:
            return

        try:
            context = self._tray_glib.MainContext.default()

            for _ in range(50):
                if self._app_quitting or not context.pending():
                    break
                context.iteration(False)

        except Exception:
            logger.exception("Failed to process GTK tray events.")

        if not self._app_quitting:
            try:
                self._gtk_poll_id = self.root.after(
                    25, self._pump_gtk_events
                )
            except tk.TclError:
                pass

    def _quit_app(self) -> None:
        """Quit PLY Pro and remove its system tray icon."""
        self._app_quitting = True

        if self._gtk_poll_id is not None:
            try:
                self.root.after_cancel(self._gtk_poll_id)
            except tk.TclError:
                pass

        if self._tray_icon is not None:
            try:
                self._tray_icon.set_status(
                    self._tray_appindicator.IndicatorStatus.PASSIVE
                )
            except Exception:
                logger.exception("Could not remove tray indicator.")

        self._tray_icon = None
        self._tray_menu = None

        self.shutdown()


    @property
    def _colors(self) -> Dict[str, str]:
        return PALETTES["dark" if self.theme_mgr.dark_mode else "light"]

    def _set_window_icon(self) -> None:
        icon_path = ASSETS_DIR / "music.png"
        if not icon_path.exists():
            icon_path = Path("/usr/share/pixmaps/music.png")
        if icon_path.exists():
            try:
                image = Image.open(icon_path)
                self._tk_images["window_icon"] = ImageTk.PhotoImage(image)
                self.root.iconphoto(False, self._tk_images["window_icon"])
            except Exception as exc:
                logger.warning("Could not set PLY Pro window icon: %s", exc)

    def _create_widgets(self) -> None:
        c = self._colors
        self.main_container = ctk.CTkFrame(self.root, corner_radius=0, fg_color=c["bg"])
        self.main_container.pack(fill="both", expand=True)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self.main_container, width=330, corner_radius=0,
                                    fg_color=c["panel"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(24, 18))
        self._load_logo_image()
        if self.images.get("logo"):
            self.logo_label = ctk.CTkLabel(header, text="", image=self.images["logo"])
            self.logo_label.pack(side="left", padx=(0, 10))
        self.title_label = ctk.CTkLabel(header, text="PLY PRO", font=ctk.CTkFont("Arial", 23, "bold"),
                                        text_color=c["accent"])
        self.title_label.pack(side="left")
        self.theme_btn = ctk.CTkButton(header, text="☼" if self.theme_mgr.dark_mode else "☾",
                                       width=38, height=36, corner_radius=12,
                                       command=self._toggle_theme)
        self.theme_btn.pack(side="right")

        self.search_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.search_frame.pack(fill="x", padx=18, pady=(0, 14))
        self.search_entry = ctk.CTkEntry(
            self.search_frame, textvariable=self.search_var, height=42,
            placeholder_text="Search songs, artists, albums...", corner_radius=12,
            border_width=1,
        )
        self.search_entry.pack(fill="x")

        section = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        section.pack(fill="x", padx=22, pady=(4, 8))
        ctk.CTkLabel(section, text="YOUR PLAYLIST", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=c["muted"]).pack(side="left")
        self.song_count_label = ctk.CTkLabel(section, text="0 TRACKS", font=ctk.CTkFont(size=10, weight="bold"),
                                             text_color=c["muted"])
        self.song_count_label.pack(side="right")

        self.tree_frame = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent", corner_radius=12,
            scrollbar_button_color=c["border"], scrollbar_button_hover_color=c["accent"],
        )
        self.tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        # Keep application rows inside our own frame.  CTkScrollableFrame has
        # internal canvas/frame children, so never clear its own winfo_children().
        self.playlist_items = ctk.CTkFrame(self.tree_frame, fg_color="transparent", corner_radius=0)
        self.playlist_items.pack(fill="both", expand=True)

        self.import_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.import_frame.pack(fill="x", padx=18, pady=(2, 8))
        self.btn_open_file = self._create_flat_button(self.import_frame, "＋  Add Song", self._open_file)
        self.btn_open_file.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_open_dir = self._create_flat_button(self.import_frame, "▣  Folder", self._open_folder)
        self.btn_open_dir.pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.playlist_actions_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.playlist_actions_frame.pack(fill="x", padx=18, pady=(0, 10))
        self.btn_load_pl = self._create_flat_button(self.playlist_actions_frame, "Load M3U", self._load_playlist_dialog, secondary=True)
        self.btn_load_pl.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_save_pl = self._create_flat_button(self.playlist_actions_frame, "Save M3U", self._save_playlist_dialog, secondary=True)
        self.btn_save_pl.pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.scan_status = ctk.CTkLabel(self.sidebar, text="Ready to play", anchor="w",
                                        text_color=c["muted"], font=ctk.CTkFont(size=11))
        self.scan_status.pack(fill="x", padx=22, pady=(0, 16))

        # Main content
        self.main_panel = ctk.CTkFrame(self.main_container, corner_radius=0, fg_color=c["bg"])
        self.main_panel.grid(row=0, column=1, sticky="nsew")
        self.main_panel.grid_columnconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(1, weight=1)

        topbar = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        topbar.pack(fill="x", padx=34, pady=(27, 4))
        ctk.CTkLabel(topbar, text="NOW PLAYING", text_color=c["muted"],
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.play_state_label = ctk.CTkLabel(topbar, text="●  READY", text_color=c["success"],
                                              font=ctk.CTkFont(size=11, weight="bold"))
        self.play_state_label.pack(side="right")

        self.cover_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.cover_frame.pack(fill="both", expand=True, padx=30, pady=(8, 0))
        self.cover_label = ctk.CTkLabel(self.cover_frame, text="", fg_color="transparent")
        self.cover_label.pack(expand=True)
        self._load_default_cover()

        self.details_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.details_frame.pack(fill="x", padx=45, pady=(0, 12))
        self.song_title_label = ctk.CTkLabel(self.details_frame, text="No Song Selected",
                                              font=ctk.CTkFont(size=24, weight="bold"),
                                              text_color=c["fg"], wraplength=620)
        self.song_title_label.pack()
        self.song_artist_label = ctk.CTkLabel(self.details_frame, text="Choose a song to get started",
                                               font=ctk.CTkFont(size=14), text_color=c["muted"])
        self.song_artist_label.pack(pady=(5, 1))
        self.song_album_label = ctk.CTkLabel(self.details_frame, text="",
                                              font=ctk.CTkFont(size=11), text_color=c["muted"])
        self.song_album_label.pack()

        self.progress_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=58, pady=(8, 3))
        self.time_elapsed_label = ctk.CTkLabel(self.progress_frame, text="00:00", width=48,
                                                text_color=c["muted"], font=ctk.CTkFont(size=11))
        self.time_elapsed_label.pack(side="left")
        self.time_total_label = ctk.CTkLabel(self.progress_frame, text="00:00", width=48,
                                              text_color=c["muted"], font=ctk.CTkFont(size=11))
        self.time_total_label.pack(side="right")
        self.seek_slider = ctk.CTkSlider(self.progress_frame, from_=0, to=100, height=18,
                                         command=self._on_slider_change)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=12)
        self.seek_slider.set(0)
        self.seek_slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.seek_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        self.controls_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.controls_frame.pack(fill="x", padx=48, pady=(8, 26))
        self.controls_frame.grid_columnconfigure(0, weight=1)
        self.controls_frame.grid_columnconfigure(1, weight=2)
        self.controls_frame.grid_columnconfigure(2, weight=1)

        left_controls = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        left_controls.grid(row=0, column=0, sticky="w")
        self.btn_shuffle = self._create_flat_button(left_controls, "⤨", self._toggle_shuffle, square=True)
        self.btn_shuffle.pack(side="left", padx=(0, 8))
        self.btn_repeat = self._create_flat_button(left_controls, "↻", self._toggle_repeat, square=True)
        self.btn_repeat.pack(side="left")

        self.media_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.media_frame.grid(row=0, column=1)
        self._load_control_icons()
        self.btn_prev = self._create_flat_button(self.media_frame, "|◀", self._prev_song, square=True, image=self.images.get("previous"))
        self.btn_prev.pack(side="left", padx=5)
        self.btn_play_pause = self._create_flat_button(self.media_frame, "▶", self._toggle_play_pause,
                                                       primary=True, square=True, image=self.images.get("play"))
        self.btn_play_pause.pack(side="left", padx=7)
        self.btn_stop = self._create_flat_button(self.media_frame, "■", self._stop_song, square=True, image=self.images.get("stop"))
        self.btn_stop.pack(side="left", padx=5)
        self.btn_next = self._create_flat_button(self.media_frame, "▶|", self._next_song, square=True, image=self.images.get("next"))
        self.btn_next.pack(side="left", padx=5)

        self.volume_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.volume_frame.grid(row=0, column=2, sticky="e")
        self.volume_icon = ctk.CTkLabel(self.volume_frame, text="◖))", text_color=c["muted"])
        self.volume_icon.pack(side="left", padx=(0, 7))
        self.volume_slider = ctk.CTkSlider(self.volume_frame, from_=0, to=100, width=110,
                                           height=16, command=self._set_volume)
        self.volume_slider.pack(side="left")
        self.volume_slider.set(70)

    def _create_flat_button(self, parent, text: str, command, *, primary: bool = False,
                             secondary: bool = False, square: bool = False, image=None) -> ctk.CTkButton:
        c = self._colors
        if primary:
            fg, hover, text_color, width, height, radius = c["accent"], c["accent_hover"], "#FFFFFF", 58, 54, 18
        elif secondary:
            fg, hover, text_color, width, height, radius = c["card"], c["border"], c["fg"], 1, 36, 10
        elif square:
            fg, hover, text_color, width, height, radius = c["card"], c["accent"], c["fg"], 42, 42, 14
        else:
            fg, hover, text_color, width, height, radius = c["accent"], c["accent_hover"], "#FFFFFF", 1, 40, 12
        # Do not show a Unicode fallback and a PNG icon together; that caused
        # duplicated play/stop/previous/next symbols in the first UI pass.
        button_text = "" if image is not None else text
        return ctk.CTkButton(parent, text=button_text, image=image, command=command,
                             fg_color=fg, hover_color=hover, text_color=text_color,
                             width=width, height=height, corner_radius=radius,
                             font=ctk.CTkFont(size=12, weight="bold"),
                             border_width=0, compound="left")

    def _apply_theme(self) -> None:
        c = self._colors
        ctk.set_appearance_mode("dark" if self.theme_mgr.dark_mode else "light")
        self.root.configure(fg_color=c["bg"])
        self.main_container.configure(fg_color=c["bg"])
        self.sidebar.configure(fg_color=c["panel"])
        self.main_panel.configure(fg_color=c["bg"])
        self.tree_frame.configure(fg_color="transparent", scrollbar_button_color=c["border"],
                                  scrollbar_button_hover_color=c["accent"])
        for widget in (self.title_label, self.song_title_label):
            widget.configure(text_color=c["accent"] if widget is self.title_label else c["fg"])
        self.song_artist_label.configure(text_color=c["muted"])
        self.song_album_label.configure(text_color=c["muted"])
        self.time_elapsed_label.configure(text_color=c["muted"])
        self.time_total_label.configure(text_color=c["muted"])
        self.scan_status.configure(text_color=c["muted"])
        self.song_count_label.configure(text_color=c["muted"])
        self.seek_slider.configure(progress_color=c["accent"], button_color=c["accent"],
                                   button_hover_color=c["accent_hover"])
        self.volume_slider.configure(progress_color=c["accent"], button_color=c["accent"],
                                     button_hover_color=c["accent_hover"])
        self.theme_btn.configure(fg_color=c["card"], hover_color=c["border"], text_color=c["fg"],
                                 text="☼" if self.theme_mgr.dark_mode else "☾")
        self.play_state_label.configure(text_color=c["success"] if self.player.state == "playing" else c["muted"])
        self._update_theme_images()
        self._render_treeview()

    def _toggle_theme(self) -> None:
        self.theme_mgr.toggle_theme()
        self.settings.set("dark_mode", self.theme_mgr.dark_mode)
        self._load_logo_image()
        self._load_control_icons()
        self._apply_theme()
        self._load_default_cover()
        if self.playlist.current_song:
            self._update_song_cover(self.playlist.current_song)

    def _load_logo_image(self) -> None:
        name = "logo.png" if self.theme_mgr.dark_mode else "logo1.png"
        path = ASSETS_DIR / name
        if path.exists():
            try:
                image = Image.open(path).convert("RGBA")
                self.images["logo"] = ctk.CTkImage(light_image=image, dark_image=image, size=(34, 34))
            except Exception as exc:
                logger.warning("Could not load logo: %s", exc)

    def _load_control_icons(self) -> None:
        for name in ("play", "pause", "stop", "next", "previous"):
            suffix = "_white" if self.theme_mgr.dark_mode else ""
            path = ASSETS_DIR / f"{name}{suffix}.png"
            if not path.exists():
                path = ASSETS_DIR / f"{name}.png"
            if path.exists():
                try:
                    image = Image.open(path).convert("RGBA")
                    self.images[name] = ctk.CTkImage(light_image=image, dark_image=image, size=(24, 24))
                except Exception as exc:
                    logger.warning("Could not load %s icon: %s", name, exc)

    def _update_theme_images(self) -> None:
        if hasattr(self, "logo_label") and self.images.get("logo"):
            self.logo_label.configure(image=self.images["logo"])
        mapping = (("btn_prev", "previous", "|◀"), ("btn_stop", "stop", "■"),
                   ("btn_next", "next", "▶|"))
        for attr, key, fallback in mapping:
            if hasattr(self, attr):
                icon = self.images.get(key)
                getattr(self, attr).configure(image=icon, text="" if icon is not None else fallback)
        if hasattr(self, "btn_play_pause"):
            key = "pause" if self.player.state == "playing" else "play"
            icon = self.images.get(key)
            fallback = "Ⅱ" if self.player.state == "playing" else "▶"
            self.btn_play_pause.configure(image=icon, text="" if icon is not None else fallback)

    def _load_default_cover(self) -> None:
        name = "logo.png" if self.theme_mgr.dark_mode else "logo1.png"
        path = ASSETS_DIR / name
        if path.exists():
            try:
                image = Image.open(path).convert("RGBA")
                self.images["cover_default"] = ctk.CTkImage(light_image=image, dark_image=image, size=(270, 270))
                self.cover_label.configure(image=self.images["cover_default"], text="")
                return
            except Exception as exc:
                logger.warning("Could not load default cover: %s", exc)
        self.cover_label.configure(image=None, text="♫", font=ctk.CTkFont(size=110), text_color=self._colors["accent"])

    def _update_song_cover(self, song: Song) -> None:
        path = song.load_cover()
        if path and Path(path).exists():
            try:
                image = Image.open(path).convert("RGBA")
                self.images["cover_active"] = ctk.CTkImage(light_image=image, dark_image=image, size=(270, 270))
                self.cover_label.configure(image=self.images["cover_active"], text="")
                return
            except Exception as exc:
                logger.warning("Could not load song cover: %s", exc)
        self._load_default_cover()

    def _bind_shortcuts(self) -> None:
        for key, callback in (("<space>", self._on_space), ("n", self._on_next_sound),
                              ("b", self._on_prev_song), ("<Down>", self._on_next_sound),
                              ("<Up>", self._on_prev_song), ("s", self._on_key_s),
                              ("h", self._on_key_h), ("r", self._on_key_r), ("m", self._on_key_m)):
            self.root.bind(key, callback)

    def _is_search_focused(self) -> bool:
        try:
            focused = self.root.focus_get()
            return focused is self.search_entry or focused is getattr(self.search_entry, "_entry", None)
        except Exception:
            return False

    def _on_space(self, event=None):
        if not self._is_search_focused(): self._toggle_play_pause()
        return "break"

    def _on_next_sound(self, event=None):
        if not self._is_search_focused(): self._next_song()
        return "break"

    def _on_prev_song(self, event=None):
        if not self._is_search_focused(): self._prev_song()
        return "break"

    def _on_key_s(self, event=None):
        if not self._is_search_focused(): self._stop_song()
        return "break"

    def _on_key_h(self, event=None):
        if not self._is_search_focused(): self._toggle_shuffle()
        return "break"

    def _on_key_r(self, event=None):
        if not self._is_search_focused(): self._toggle_repeat()
        return "break"

    def _on_key_m(self, event=None):
        if not self._is_search_focused(): self._toggle_mute()
        return "break"

    def _update_play_pause_button(self) -> None:
        playing = self.player.state == "playing"
        key = "pause" if playing else "play"
        icon = self.images.get(key)
        self.btn_play_pause.configure(text="" if icon is not None else ("Ⅱ" if playing else "▶"),
                                      image=icon)
        self.play_state_label.configure(text="●  PLAYING" if playing else ("Ⅱ  PAUSED" if self.player.state == "paused" else "●  READY"),
                                        text_color=self._colors["success"] if playing else self._colors["muted"])

    def _stop_song(self) -> None:
        self.player.stop()
        self.seek_slider.set(0)
        self.time_elapsed_label.configure(text="00:00")
        self._update_play_pause_button()
        if self.mpris:
            self.mpris.update_stopped()

    def _set_volume(self, value) -> None:
        volume = max(0, min(100, int(float(value))))
        self.player.set_volume(volume)
        self.settings.set("last_volume", volume)

    def _on_slider_press(self, event=None) -> None:
        self.is_dragging_slider = True

    def _on_slider_release(self, event=None) -> None:
        self.is_dragging_slider = False
        if self.playlist.current_song:
            self.player.seek(float(self.seek_slider.get()))

    def _on_slider_change(self, value) -> None:
        if self.is_dragging_slider:
            self.time_elapsed_label.configure(text=format_time(float(value)))

    def _on_playlist_item_click(self, index: int) -> None:
        if 0 <= index < len(self.playlist.songs):
            self.playlist.current_index = index
            self._play_song(self.playlist.songs[index])

    def _render_treeview(self) -> None:
        if not hasattr(self, "tree_frame"):
            return
        # Clear only our content frame, never CTkScrollableFrame's canvas or
        # internal scroll frame.  Destroying those internals makes the playlist
        # area appear empty even while the track counter reports loaded songs.
        for child in self.tree_frame.winfo_children():
            child.destroy()
        self._playlist_buttons.clear()
        query = self.search_var.get().strip().lower()
        songs = self.playlist.songs
        self.song_count_label.configure(text=f"{len(songs)} TRACKS")
        shown = 0
        for index, song in enumerate(songs):
            if query and not any(query in str(value or "").lower()
                                 for value in (song.title, song.artist, song.album)):
                continue
            active = index == self.playlist.current_index
            c = self._colors
            title = song.title or song.filepath.stem
            artist = song.artist or "Unknown artist"
            text = f"{index + 1:02d}   {title}\n       {artist}   ·   {format_time(song.duration)}"
            button = ctk.CTkButton(
                self.tree_frame, text=text, anchor="w", height=58,
                corner_radius=11, fg_color=c["selected"] if active else "transparent",
                hover_color=c["card"], text_color=c["accent"] if active else c["fg"],
                font=ctk.CTkFont(size=12, weight="bold" if active else "normal"),
                command=lambda idx=index: self._on_playlist_item_click(idx),
            )
            button.pack(fill="x", padx=4, pady=3)
            self._playlist_buttons[index] = button
            shown += 1
        if shown == 0:
            message = "No matching tracks" if query else "Your playlist is empty\nAdd songs or open a folder"
            ctk.CTkLabel(self.tree_frame, text=message, text_color=self._colors["muted"],
                         justify="center", font=ctk.CTkFont(size=12)).pack(fill="x", pady=30)

    def _filter_playlist(self, *args) -> None:
        self._render_treeview()

    def _on_tree_double_click(self, event=None) -> None:
        # Kept as a compatibility hook for callers; playlist rows use CTkButtons.
        selection = getattr(event, "index", None)
        if isinstance(selection, int):
            self._on_playlist_item_click(selection)

    def _update_ui_state(self, song: Song) -> None:
        self.song_title_label.configure(text=song.title or song.filepath.stem)
        self.song_artist_label.configure(text=song.artist or "Unknown artist")
        album = song.album or ""
        year = getattr(song, "year", None)
        self.song_album_label.configure(text=f"{album}  ·  {year}" if album and year else album)
        self.time_total_label.configure(text=format_time(song.duration))
        self.seek_slider.configure(to=max(1, float(song.duration or 1)))
        self.seek_slider.set(0)
        self._update_song_cover(song)
        self._render_treeview()

    def _update_loop(self) -> None:
        if self.player.state == "playing" and not self.is_dragging_slider:
            current = self.player.get_elapsed_time()
            self.seek_slider.set(current)
            self.time_elapsed_label.configure(text=format_time(current))
        self.root.after(200, self._update_loop)

    def _toggle_shuffle(self) -> None:
        self.playlist.shuffle = not self.playlist.shuffle
        self.settings.set("shuffle", self.playlist.shuffle)
        self._update_mode_buttons()
        self._render_treeview()

    def _toggle_repeat(self) -> None:
        current = self.playlist.repeat_mode
        self.playlist.repeat_mode = "all" if current == "off" else ("single" if current == "all" else "off")
        self.settings.set("repeat", self.playlist.repeat_mode)
        self._update_mode_buttons()

    def _update_mode_buttons(self) -> None:
        c = self._colors
        self.btn_shuffle.configure(fg_color=c["accent_active"] if self.playlist.shuffle else c["card"],
                                   text_color="#FFFFFF" if self.playlist.shuffle else c["fg"])
        active_repeat = self.playlist.repeat_mode != "off"
        self.btn_repeat.configure(fg_color=c["accent_active"] if active_repeat else c["card"],
                                  text_color="#FFFFFF" if active_repeat else c["fg"],
                                  text="↻¹" if self.playlist.repeat_mode == "single" else "↻")

    def _load_last_session(self) -> None:
        volume = self.settings.get("last_volume")
        self.volume_slider.set(volume)
        self.player.set_volume(volume)
        self.playlist.shuffle = bool(self.settings.get("shuffle"))
        repeat = self.settings.get("repeat")
        if isinstance(repeat, bool): repeat = "all" if repeat else "off"
        self.playlist.repeat_mode = repeat if repeat in ("off", "all", "single") else "off"
        self._update_mode_buttons()
        folder = self.settings.get("last_folder")
        last_song = self.settings.get("last_song")
        if folder and os.path.isdir(folder):
            self.root.after(100, lambda: self._start_last_session_scan(Path(folder), last_song))

    def _start_last_session_scan(self, folder: Path, last_song_path: Optional[str]) -> None:
        if self._scan_in_progress:
            return
        self._scan_in_progress = True
        self.scan_status.configure(text="Restoring your music library…")
        thread = threading.Thread(target=self._restore_last_session_worker,
                                  args=(folder, last_song_path), daemon=True)
        thread.start()

    def _restore_last_session_worker(self, folder: Path, last_song_path: Optional[str]) -> None:
        try:
            songs = self.library.scan_directory(folder)
        except Exception:
            logger.exception("Failed to restore last music folder: %s", folder)
            songs = []
        def finish() -> None:
            self._scan_in_progress = False
            for song in songs:
                self.playlist.add_song(song)
            self._render_treeview()
            self.scan_status.configure(text=f"{len(songs)} tracks loaded" if songs else "Ready to play")
            if last_song_path and os.path.exists(last_song_path):
                wanted = Path(last_song_path)
                for song in self.playlist.songs:
                    if song.filepath == wanted:
                        self.playlist.set_current_by_song(song)
                        self._update_ui_state(song)
                        break
        self.root.after(0, finish)

    def _scan_folder_worker(self, folder: Path) -> None:
        try:
            songs = self.library.scan_directory(folder)
        except Exception:
            logger.exception("Failed to scan folder: %s", folder)
            songs = []
        def finish() -> None:
            self._scan_in_progress = False
            self.playlist.clear()
            for song in songs:
                self.playlist.add_song(song)
            self._render_treeview()
            self.scan_status.configure(text=f"{len(songs)} tracks loaded" if songs else "No supported audio files found")
            if songs:
                self.playlist.current_index = 0
                self._play_song(self.playlist.current_song)
            else:
                self._show_message("No music found", "No supported audio files were found in this folder.")
        self.root.after(0, finish)

    # ---------- CustomTkinter dialogs ----------
    def _show_message(self, title: str, message: str, kind: str = "info") -> bool:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry("430x210")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(fg_color=self._colors["panel"])
        result = {"value": False}
        accent = self._colors["danger"] if kind == "error" else self._colors["accent"]
        ctk.CTkLabel(dialog, text=title, font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self._colors["fg"]).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(dialog, text=message, wraplength=380, justify="left",
                     text_color=self._colors["muted"]).pack(anchor="w", padx=24, pady=(0, 18), fill="x")
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=20, pady=16)
        def close(value: bool) -> None:
            result["value"] = value
            dialog.destroy()
        if kind == "question":
            ctk.CTkButton(buttons, text="Cancel", fg_color=self._colors["card"],
                          hover_color=self._colors["border"], command=lambda: close(False)).pack(side="right", padx=(8, 0))
            ctk.CTkButton(buttons, text="Continue", fg_color=accent,
                          hover_color=self._colors["accent_hover"], command=lambda: close(True)).pack(side="right")
        else:
            ctk.CTkButton(buttons, text="OK", width=90, fg_color=accent,
                          hover_color=self._colors["accent_hover"], command=lambda: close(True)).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.wait_visibility()
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def _custom_file_dialog(self, mode: str, title: str, extensions=None,
                            initialdir: Optional[Path] = None) -> Optional[Path]:
        allowed = {str(ext).lower() for ext in (extensions or [])}
        start = initialdir or (Path(self.settings.get("last_folder"))
                               if self.settings.get("last_folder") else Path.home() / "Music")
        if not start.exists() or not start.is_dir(): start = Path.home()
        state = {"directory": start.resolve(), "selected": None}

        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.geometry("760x540")
        dialog.minsize(600, 420)
        dialog.transient(self.root)
        dialog.configure(fg_color=self._colors["bg"])
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(2, weight=1)
        result = {"path": None}

        top = ctk.CTkFrame(dialog, fg_color=self._colors["panel"], corner_radius=12)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(top, text="↑", width=38, command=lambda: navigate(state["directory"].parent)).grid(row=0, column=0, padx=8, pady=8)
        path_var = tk.StringVar(master=dialog, value=str(state["directory"]))
        path_entry = ctk.CTkEntry(top, textvariable=path_var, height=36)
        path_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=8)
        ctk.CTkButton(top, text="Go", width=55, command=lambda: navigate(Path(path_var.get()).expanduser())).grid(row=0, column=2, padx=(0, 8), pady=8)

        list_frame = ctk.CTkScrollableFrame(dialog, fg_color=self._colors["panel"], corner_radius=12)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=4)
        # Same rule as the playlist: isolate entries from the scroll frame internals.
        info_label = ctk.CTkLabel(dialog, text="", anchor="w", text_color=self._colors["muted"])
        info_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(5, 0))

        filename_var = tk.StringVar(master=dialog, value="playlist.m3u")
        if mode == "save":
            filename_row = ctk.CTkFrame(dialog, fg_color="transparent")
            filename_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 0))
            ctk.CTkLabel(filename_row, text="File name", width=85, anchor="w").pack(side="left")
            ctk.CTkEntry(filename_row, textvariable=filename_var, height=36).pack(side="left", fill="x", expand=True)

        def navigate(path: Path) -> None:
            try:
                path = path.expanduser().resolve()
                if not path.is_dir():
                    info_label.configure(text="That folder does not exist.")
                    return
                state["directory"] = path
                state["selected"] = None
                path_var.set(str(path))
                refresh()
            except Exception as exc:
                info_label.configure(text=str(exc))

        def choose_file(path: Path) -> None:
            state["selected"] = path
            info_label.configure(text=path.name)
            if mode == "save": filename_var.set(path.name)

        def refresh() -> None:
            for child in list_frame.winfo_children(): child.destroy()
            try:
                entries = sorted(state["directory"].iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            except OSError as exc:
                info_label.configure(text=f"Cannot open folder: {exc}")
                return
            visible = 0
            for item in entries:
                is_dir = item.is_dir()
                if mode == "folder" and not is_dir: continue
                if mode in ("open", "playlist") and not is_dir and allowed and item.suffix.lower() not in allowed: continue
                label = ("📁  " if is_dir else "♫  ") + item.name
                def activate(p=item, directory=is_dir):
                    if directory: navigate(p)
                    else: choose_file(p)
                button = ctk.CTkButton(list_frame, text=label, anchor="w", height=34,
                                       fg_color="transparent", hover_color=self._colors["card"],
                                       text_color=self._colors["fg"], command=activate)
                button.pack(fill="x", padx=4, pady=2)
                visible += 1
            if not visible:
                ctk.CTkLabel(list_frame, text="This folder is empty or contains no matching files.",
                             text_color=self._colors["muted"]).pack(pady=24)

        def finish() -> None:
            if mode == "folder":
                result["path"] = state["directory"]
            elif mode == "save":
                name = filename_var.get().strip()
                if not name:
                    info_label.configure(text="Enter a file name first.")
                    return
                path = Path(name).expanduser()
                if not path.is_absolute(): path = state["directory"] / path
                if path.suffix.lower() not in (".m3u", ".m3u8"):
                    path = path.with_suffix(".m3u")
                if path.exists() and not self._show_message("Replace file?", f"{path.name} already exists. Replace it?", "question"):
                    return
                result["path"] = path
            else:
                selected = state["selected"]
                if selected is None or not selected.is_file():
                    info_label.configure(text="Select a file first.")
                    return
                result["path"] = selected
            dialog.destroy()

        bottom = ctk.CTkFrame(dialog, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=16, pady=14)
        ctk.CTkButton(bottom, text="Cancel", fg_color=self._colors["card"],
                      hover_color=self._colors["border"], command=dialog.destroy).pack(side="right", padx=(8, 0))
        action = {"open": "Open", "folder": "Choose This Folder", "playlist": "Open", "save": "Save"}[mode]
        ctk.CTkButton(bottom, text=action, command=finish).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        refresh()
        dialog.wait_visibility()
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["path"]

    def _open_file(self) -> None:
        path = self._custom_file_dialog("open", "Open Audio File", SUPPORTED_EXTENSIONS)
        if path:
            try:
                song = Song(path)
                self.playlist.clear()
                self.playlist.add_song(song)
                self._render_treeview()
                self._play_song(song)
                self.settings.set("last_folder", str(path.parent))
            except Exception as exc:
                logger.exception("Could not open audio file")
                self._show_message("Unable to open file", str(exc), "error")

    def _open_folder(self) -> None:
        if self._scan_in_progress:
            self._show_message("Scan in progress", "Please wait for the current library scan to finish.")
            return
        folder = self._custom_file_dialog("folder", "Choose Music Folder")
        if folder:
            self.settings.set("last_folder", str(folder))
            self._scan_in_progress = True
            self.scan_status.configure(text="Scanning music folder…")
            threading.Thread(target=self._scan_folder_worker, args=(folder,), daemon=True).start()

    def _load_playlist_dialog(self) -> None:
        path = self._custom_file_dialog("playlist", "Load M3U Playlist", {".m3u", ".m3u8"})
        if path:
            try:
                self.playlist.load_m3u(path)
                self._render_treeview()
                if self.playlist.songs:
                    self.playlist.current_index = 0
                    self._play_song(self.playlist.songs[0])
            except Exception as exc:
                logger.exception("Could not load playlist")
                self._show_message("Unable to load playlist", str(exc), "error")

    def _save_playlist_dialog(self) -> None:
        if not self.playlist.original_songs:
            self._show_message("Empty playlist", "There are no tracks to save.")
            return
        path = self._custom_file_dialog("save", "Save M3U Playlist")
        if path:
            try:
                self.playlist.save_m3u(path)
                self._show_message("Playlist saved", f"Playlist saved to:\n{path}")
            except Exception as exc:
                logger.exception("Could not save playlist")
                self._show_message("Unable to save playlist", str(exc), "error")

    def _toggle_mute(self) -> None:
        current = int(self.volume_slider.get())
        if current > 0:
            self._previous_volume = current
            self.volume_slider.set(0)
            self._set_volume(0)
        else:
            restored = getattr(self, "_previous_volume", 70)
            self.volume_slider.set(restored)
            self._set_volume(restored)

    def run(self) -> None:
        self.root.mainloop()
