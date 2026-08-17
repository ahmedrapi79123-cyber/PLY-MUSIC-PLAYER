"""Graphical User Interface (GUI) for the PLY music player.

Provides a modern, styled Tkinter-based interface with playback controls,
playlist viewer, search, and dynamic dark/light mode.
Supports MPRIS2 panel integration and background playback via system tray.
"""

import os
import threading
from pathlib import Path
from typing import Dict, Optional, List
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from config import ASSETS_DIR, logger, SUPPORTED_EXTENSIONS
from settings import Settings
from themes import ThemeManager
from player import Player
from playlist import Playlist
from library import Library, Song
from utils import format_time, clean_temp_dir
from icons import generate_default_assets

try:
    import gi
    gi.require_version("AyatanaAppIndicator3", "0.1")
    gi.require_version("Gtk", "3.0")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator  # type: ignore
    from gi.repository import Gtk as _Gtk  # type: ignore
    TRAY_AVAILABLE = True
    TRAY_BACKEND = "appindicator"
    logger.info("System tray backend: AyatanaAppIndicator3")
except (ImportError, ValueError):
    try:
        # Fallback: pystray (for native non-Flatpak installs)
        import pystray
        from PIL import Image as _PilImage
        TRAY_AVAILABLE = True
        TRAY_BACKEND = "pystray"
        logger.info("System tray backend: pystray (fallback)")
    except ImportError:
        TRAY_AVAILABLE = False
        TRAY_BACKEND = "none"
        logger.warning("No system tray backend available (install libayatana-appindicator3 or pystray).")

class GUI:
    """Tkinter-based Graphical User Interface for the PLY music player."""

    def __init__(self, player: Player, playlist: Playlist, library: Library, settings: Settings) -> None:
        self.player = player
        self.playlist = playlist
        self.library = library
        self.settings = settings
        self.theme_mgr = ThemeManager(dark_mode=settings.get("dark_mode"))

        # Generate PNG assets if not already present
        generate_default_assets()

        # Tkinter Root Setup
        self.root = tk.Tk()
        self.root.title("PLY Music Player")
        self.root.geometry("1000x650")
        self.root.minsize(800, 550)

        # Image caching to prevent garbage collection
        self.images: Dict[str, ImageTk.PhotoImage] = {}

        # Set Window Icon
        self._set_window_icon()

        # State variables
        self.is_dragging_slider = False
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_playlist)

        # Build elements
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._setup_styles()
        self._create_widgets()
        self._apply_theme()

        # Load session configuration
        self._load_last_session()

        # Configure player end event callback
        self.player.set_on_song_end(self._on_song_finished)

        # Start periodic GUI updates
        self._update_loop()

        # Window closing handler — hides to tray instead of quitting
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # MPRIS2 controller (set externally by main.py after construction)
        self.mpris = None

        # System tray icon state
        self._tray_icon = None
        self._tray_menu = None          # GTK menu (AppIndicator backend)
        self._tray_glib_loop = None     # GLib.MainLoop for tray GTK events
        self._tray_thread: Optional[threading.Thread] = None
        self._app_quitting = False

    def _set_window_icon(self) -> None:
        """Loads and sets the window titlebar icon."""
        icon_path = ASSETS_DIR / "music.png"
        if not icon_path.exists():
            system_icon = Path("/usr/share/pixmaps/music.png")
            if system_icon.exists():
                icon_path = system_icon
                
        if icon_path.exists():
            try:
                img = Image.open(icon_path)
                self.images["window_icon"] = ImageTk.PhotoImage(img)
                self.root.iconphoto(False, self.images["window_icon"])
                logger.info("Window icon set from: %s", icon_path)
            except Exception as e:
                logger.error("Failed to set window icon: %s", e)


    def _create_widgets(self) -> None:
        """Builds all panels and widgets inside the main window."""
        theme = self.theme_mgr.get_gui_theme()

        # Outer frames
        self.main_container = tk.Frame(self.root, bg=theme["bg"])
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Sidebar (Left) - width 300
        self.sidebar = tk.Frame(self.main_container, bg=theme["container_bg"], width=320, bd=0)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Main Panel (Right)
        self.main_panel = tk.Frame(self.main_container, bg=theme["bg"], bd=0)
        self.main_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # =====================================================================
        # SIDEBAR WIDGETS
        # =====================================================================
        # Logo and Title Header
        self.logo_frame = tk.Frame(self.sidebar, bg=theme["container_bg"], pady=15, padx=15)
        self.logo_frame.pack(fill=tk.X)

        self._load_logo_image()
        if "logo" in self.images:
            self.logo_label = tk.Label(self.logo_frame, image=self.images["logo"], bg=theme["container_bg"])
            self.logo_label.pack(side=tk.LEFT)
        
        self.title_label = tk.Label(
            self.logo_frame, text="PLY", font=("Helvetica", 20, "bold"),
            fg=theme["accent"], bg=theme["container_bg"]
        )
        self.title_label.pack(side=tk.LEFT, padx=10)

        # Dark/Light Toggle Button
        self.theme_btn = self._create_flat_button(
            self.logo_frame, text="🌓", command=self._toggle_theme,
            width=3, font=("Helvetica", 12)
        )
        self.theme_btn.pack(side=tk.RIGHT)

        # Search Bar
        self.search_frame = tk.Frame(self.sidebar, bg=theme["container_bg"], padx=15, pady=5)
        self.search_frame.pack(fill=tk.X)
        
        self.search_label = tk.Label(self.search_frame, text="🔍", bg=theme["container_bg"], fg=theme["fg"])
        self.search_label.pack(side=tk.LEFT)
        
        self.search_entry = tk.Entry(
            self.search_frame, textvariable=self.search_var, font=("Helvetica", 10),
            bg=theme["bg"], fg=theme["fg"], insertbackground=theme["fg"],
            bd=1, relief=tk.FLAT
        )
        self.search_entry.pack(fill=tk.X, expand=True, padx=5, ipady=4)

        # Treeview Playlist
        self.tree_frame = tk.Frame(self.sidebar, bg=theme["container_bg"], padx=15, pady=10)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)

        # Scrollbars
        self.tree_scroll = ttk.Scrollbar(self.tree_frame)
        self.tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.playlist_tree = ttk.Treeview(
            self.tree_frame, columns=("Index", "Title", "Duration"), show="headings",
            selectmode="browse", yscrollcommand=self.tree_scroll.set
        )
        self.playlist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_scroll.config(command=self.playlist_tree.yview)

        self.playlist_tree.heading("Index", text="#")
        self.playlist_tree.heading("Title", text="Title")
        self.playlist_tree.heading("Duration", text="Time")

        self.playlist_tree.column("Index", width=30, minwidth=30, stretch=tk.NO, anchor=tk.CENTER)
        self.playlist_tree.column("Title", width=180, minwidth=100, stretch=tk.YES)
        self.playlist_tree.column("Duration", width=50, minwidth=50, stretch=tk.NO, anchor=tk.E)

        self.playlist_tree.bind("<Double-1>", self._on_tree_double_click)

        # Import Buttons
        self.import_frame = tk.Frame(self.sidebar, bg=theme["container_bg"], pady=10, padx=15)
        self.import_frame.pack(fill=tk.X)

        self.btn_open_file = self._create_flat_button(
            self.import_frame, text="Open File", command=self._open_file
        )
        self.btn_open_file.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_open_dir = self._create_flat_button(
            self.import_frame, text="Open Folder", command=self._open_folder
        )
        self.btn_open_dir.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Playlist Load/Save
        self.playlist_actions_frame = tk.Frame(self.sidebar, bg=theme["container_bg"], pady=5, padx=15)
        self.playlist_actions_frame.pack(fill=tk.X)

        self.btn_load_pl = self._create_flat_button(
            self.playlist_actions_frame, text="Load M3U", command=self._load_playlist_dialog, font=("Helvetica", 9)
        )
        self.btn_load_pl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_save_pl = self._create_flat_button(
            self.playlist_actions_frame, text="Save M3U", command=self._save_playlist_dialog, font=("Helvetica", 9)
        )
        self.btn_save_pl.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # =====================================================================
        # MAIN PANEL WIDGETS
        # =====================================================================
        # Cover Art Frame
        self.cover_frame = tk.Frame(self.main_panel, bg=theme["bg"], pady=20)
        self.cover_frame.pack(fill=tk.BOTH, expand=True)

        self.cover_label = tk.Label(self.cover_frame, bg=theme["bg"])
        self.cover_label.pack(expand=True)
        self._load_default_cover()

        # Song Details
        self.details_frame = tk.Frame(self.main_panel, bg=theme["bg"], pady=10)
        self.details_frame.pack(fill=tk.X)

        self.song_title_label = tk.Label(
            self.details_frame, text="No Song Selected", font=("Helvetica", 16, "bold"),
            fg=theme["fg"], bg=theme["bg"]
        )
        self.song_title_label.pack()

        self.song_artist_label = tk.Label(
            self.details_frame, text="-", font=("Helvetica", 12),
            fg=theme["muted_fg"], bg=theme["bg"]
        )
        self.song_artist_label.pack(pady=2)

        self.song_album_label = tk.Label(
            self.details_frame, text="-", font=("Helvetica", 10, "italic"),
            fg=theme["muted_fg"], bg=theme["bg"]
        )
        self.song_album_label.pack()

        # Progress Seek Bar
        self.progress_frame = tk.Frame(self.main_panel, bg=theme["bg"], padx=40, pady=10)
        self.progress_frame.pack(fill=tk.X)

        self.time_elapsed_label = tk.Label(
            self.progress_frame, text="00:00", font=("Helvetica", 9),
            fg=theme["muted_fg"], bg=theme["bg"]
        )
        self.time_elapsed_label.pack(side=tk.LEFT)

        self.time_total_label = tk.Label(
            self.progress_frame, text="00:00", font=("Helvetica", 9),
            fg=theme["muted_fg"], bg=theme["bg"]
        )
        self.time_total_label.pack(side=tk.RIGHT)

        # Scale slider for seeking
        self.seek_slider = ttk.Scale(
            self.progress_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            command=self._on_slider_change
        )
        self.seek_slider.pack(fill=tk.X, expand=True, padx=10)
        self.seek_slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.seek_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Control Panel
        self.controls_frame = tk.Frame(self.main_panel, bg=theme["bg"], pady=15, padx=40)
        self.controls_frame.pack(fill=tk.X)

        # Load controls icons
        self._load_control_icons()

        # Shuffle and Repeat
        self.btn_shuffle = self._create_flat_button(
            self.controls_frame, text="🔀", command=self._toggle_shuffle,
            width=4, font=("Helvetica", 12)
        )
        self.btn_shuffle.pack(side=tk.LEFT, padx=10)

        self.btn_repeat = self._create_flat_button(
            self.controls_frame, text="🔁", command=self._toggle_repeat,
            width=4, font=("Helvetica", 12)
        )
        self.btn_repeat.pack(side=tk.LEFT, padx=10)

        # Media center controls (Prev, Play, Pause, Stop, Next)
        self.media_frame = tk.Frame(self.controls_frame, bg=theme["bg"])
        self.media_frame.pack(side=tk.LEFT, expand=True)

        self.btn_prev = self._create_flat_button(
            self.media_frame, text="⏮", image=self.images.get("previous"),
            command=self._prev_song, width=40 if "previous" in self.images else 4
        )
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        self.btn_play = self._create_flat_button(
            self.media_frame, text="▶", image=self.images.get("play"),
            command=self._play_song, width=40 if "play" in self.images else 4
        )
        self.btn_play.pack(side=tk.LEFT, padx=5)

        self.btn_pause = self._create_flat_button(
            self.media_frame, text="⏸", image=self.images.get("pause"),
            command=self._pause_song, width=40 if "pause" in self.images else 4
        )
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = self._create_flat_button(
            self.media_frame, text="■", image=self.images.get("stop"),
            command=self._stop_song, width=40 if "stop" in self.images else 4
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_next = self._create_flat_button(
            self.media_frame, text="⏭", image=self.images.get("next"),
            command=self._next_song, width=40 if "next" in self.images else 4
        )
        self.btn_next.pack(side=tk.LEFT, padx=5)

        # Volume Controls
        self.volume_frame = tk.Frame(self.controls_frame, bg=theme["bg"])
        self.volume_frame.pack(side=tk.RIGHT)

        self.volume_icon = tk.Label(self.volume_frame, text="🔊", bg=theme["bg"], fg=theme["fg"])
        self.volume_icon.pack(side=tk.LEFT, padx=(0, 5))

        self.volume_slider = ttk.Scale(
            self.volume_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            command=self._set_volume, length=100
        )
        self.volume_slider.pack(side=tk.LEFT)

    def _create_flat_button(self, parent, text="", image=None, command=None, width=None, font=("Helvetica", 10, "bold")) -> tk.Button:
        """Helper to create standard customized hoverable flat buttons."""
        theme = self.theme_mgr.get_gui_theme()
        
        btn = tk.Button(
            parent, text=text, image=image, command=command, width=width,
            bg=theme["btn_bg"], fg=theme["btn_fg"], activebackground=theme["accent"],
            activeforeground="#ffffff", relief=tk.FLAT, bd=0, font=font, padx=10, pady=5
        )

        def on_enter(e):
            btn.config(bg=theme["accent"], fg="#ffffff")

        def on_leave(e):
            # Check toggle state colors if it's shuffle or repeat
            if btn == self.btn_shuffle and self.playlist.shuffle:
                btn.config(bg=theme["accent_active"], fg="#ffffff")
            elif btn == self.btn_repeat and self.playlist.repeat_mode != "off":
                btn.config(bg=theme["accent_active"], fg="#ffffff")
            else:
                btn.config(bg=theme["btn_bg"], fg=theme["btn_fg"])

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _setup_styles(self) -> None:
        """Configures ttk widget styling for Scrollbars, Scales, and Treeviews."""
        theme = self.theme_mgr.get_gui_theme()

        # Treeview styling
        self.style.configure(
            "Treeview",
            background=theme["container_bg"],
            fieldbackground=theme["container_bg"],
            foreground=theme["fg"],
            bordercolor=theme["border"],
            rowheight=25,
            font=("Helvetica", 9)
        )
        self.style.map(
            "Treeview",
            background=[("selected", theme["selection_bg"])],
            foreground=[("selected", theme["selection_fg"])]
        )
        self.style.configure(
            "Treeview.Heading",
            background=theme["border"],
            foreground=theme["fg"],
            font=("Helvetica", 9, "bold")
        )

        # Scale slider styling
        self.style.configure(
            "Horizontal.TScale",
            troughcolor=theme["slider_trough"],
            background=theme["bg"]
        )

    def _apply_theme(self) -> None:
        """Dynamically applies current theme colors to all active components."""
        theme = self.theme_mgr.get_gui_theme()
        self._setup_styles()

        # Tkinter Frames Backgrounds
        self.main_container.config(bg=theme["bg"])
        self.sidebar.config(bg=theme["container_bg"])
        self.main_panel.config(bg=theme["bg"])
        
        self.logo_frame.config(bg=theme["container_bg"])
        if hasattr(self, "logo_label"):
            self.logo_label.config(bg=theme["container_bg"])
        self.title_label.config(bg=theme["container_bg"], fg=theme["accent"])
        self.theme_btn.config(bg=theme["btn_bg"], fg=theme["btn_fg"])

        self.search_frame.config(bg=theme["container_bg"])
        self.search_label.config(bg=theme["container_bg"], fg=theme["fg"])
        self.search_entry.config(bg=theme["bg"], fg=theme["fg"], insertbackground=theme["fg"])

        self.tree_frame.config(bg=theme["container_bg"])
        self.import_frame.config(bg=theme["container_bg"])
        self.playlist_actions_frame.config(bg=theme["container_bg"])

        # Main elements
        self.cover_frame.config(bg=theme["bg"])
        self.cover_label.config(bg=theme["bg"])
        self.details_frame.config(bg=theme["bg"])
        self.song_title_label.config(fg=theme["fg"], bg=theme["bg"])
        self.song_artist_label.config(fg=theme["muted_fg"], bg=theme["bg"])
        self.song_album_label.config(fg=theme["muted_fg"], bg=theme["bg"])

        self.progress_frame.config(bg=theme["bg"])
        self.time_elapsed_label.config(fg=theme["muted_fg"], bg=theme["bg"])
        self.time_total_label.config(fg=theme["muted_fg"], bg=theme["bg"])

        self.controls_frame.config(bg=theme["bg"])
        self.media_frame.config(bg=theme["bg"])
        self.volume_frame.config(bg=theme["bg"])
        self.volume_icon.config(bg=theme["bg"], fg=theme["fg"])

        # Update Buttons
        buttons = [
            self.btn_open_file, self.btn_open_dir, self.btn_load_pl, self.btn_save_pl,
            self.btn_prev, self.btn_play, self.btn_pause, self.btn_stop, self.btn_next
        ]
        for btn in buttons:
            btn.config(bg=theme["btn_bg"], fg=theme["btn_fg"])

        # Shuffle and Repeat toggled states colors
        shuf_bg = theme["accent_active"] if self.playlist.shuffle else theme["btn_bg"]
        shuf_fg = "#ffffff" if self.playlist.shuffle else theme["btn_fg"]
        self.btn_shuffle.config(bg=shuf_bg, fg=shuf_fg)

        rep_bg = theme["accent_active"] if self.playlist.repeat_mode != "off" else theme["btn_bg"]
        rep_fg = "#ffffff" if self.playlist.repeat_mode != "off" else theme["btn_fg"]
        self.btn_repeat.config(bg=rep_bg, fg=rep_fg)

        # Update Treeview rows dynamically by re-rendering
        self._render_treeview()

    def _toggle_theme(self) -> None:
        """Toggles current theme setting."""
        self.theme_mgr.toggle_theme()
        self.settings.set("dark_mode", self.theme_mgr.dark_mode)
        self._apply_theme()

    def _load_logo_image(self) -> None:
        """Loads and sizes the application logo."""
        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            try:
                img = Image.open(logo_path).resize((32, 32), Image.Resampling.LANCZOS)
                self.images["logo"] = ImageTk.PhotoImage(img)
            except Exception as e:
                logger.error("Failed to load logo image: %s", e)

    def _load_control_icons(self) -> None:
        """Loads all transparent PNG controls icons."""
        icons = ["play", "pause", "stop", "next", "previous"]
        for icon in icons:
            icon_path = ASSETS_DIR / f"{icon}.png"
            if icon_path.exists():
                try:
                    img = Image.open(icon_path).resize((24, 24), Image.Resampling.LANCZOS)
                    self.images[icon] = ImageTk.PhotoImage(img)
                except Exception as e:
                    logger.error("Failed to load icon %s: %s", icon, e)

    def _load_default_cover(self) -> None:
        """Generates a default disk cover image."""
        theme = self.theme_mgr.get_gui_theme()
        logo_path = ASSETS_DIR / "logo.png"
        
        # Load logo as fallback cover
        if logo_path.exists():
            try:
                img = Image.open(logo_path).resize((250, 250), Image.Resampling.LANCZOS)
                self.images["cover_default"] = ImageTk.PhotoImage(img)
                self.cover_label.config(image=self.images["cover_default"])
                return
            except Exception:
                pass

        # Canvas drawing fallback
        self.images["cover_default"] = None
        self.cover_label.config(text="💿", font=("Helvetica", 100), fg=theme["accent"])

    def _update_song_cover(self, song: Song) -> None:
        """Updates the cover art in the main GUI thread."""
        theme = self.theme_mgr.get_gui_theme()
        # Clean background cover frame
        cover_path = song.load_cover()
        
        if cover_path and cover_path.exists():
            try:
                img = Image.open(cover_path).resize((250, 250), Image.Resampling.LANCZOS)
                self.images["cover_active"] = ImageTk.PhotoImage(img)
                self.cover_label.config(image=self.images["cover_active"], text="")
                return
            except Exception as e:
                logger.error("Failed to load custom song cover: %s", e)

        self._load_default_cover()

    # =====================================================================
    # PLAYBACK OPERATIONS
    # =====================================================================
    def _notify_mpris_playing(self, song: "Song") -> None:
        """Notify MPRIS2 of currently playing song."""
        if self.mpris and song:
            try:
                self.mpris.update_playing(
                    title=song.title,
                    artist=song.artist,
                    album=song.album,
                    duration_s=song.duration,
                    volume=self.player.volume
                )
            except Exception:
                pass

    def _play_song(self, song: Optional[Song] = None) -> None:
        """Handles song playback."""
        if not song:
            song = self.playlist.current_song

        if not song:
            if self.playlist.songs:
                song = self.playlist.songs[0]
                self.playlist.current_index = 0
            else:
                self._open_file()
                return

        if song:
            # If playing the same song and paused, resume
            if self.player.current_song == song and self.player.state == "paused":
                self.player.resume()
                if self.mpris:
                    self.mpris.update_playing(
                        song.title, song.artist, song.album,
                        song.duration, self.player.volume
                    )
            else:
                self.player.play(song)
                self.library.add_to_history(song)
                self._notify_mpris_playing(song)
            self._update_ui_state(song)

    def _pause_song(self) -> None:
        """Pauses current song playback."""
        self.player.pause()
        if self.mpris:
            self.mpris.update_paused()

    def _stop_song(self) -> None:
        """Stops current playback."""
        self.player.stop()
        self.seek_slider.set(0)
        self.time_elapsed_label.config(text="00:00")
        if self.mpris:
            self.mpris.update_stopped()

    def _next_song(self) -> None:
        """Plays the next song in the queue."""
        next_song = self.playlist.next_song()
        if next_song:
            self._play_song(next_song)
        else:
            self._stop_song()

    def _prev_song(self) -> None:
        """Plays the previous song in the queue."""
        prev_song = self.playlist.prev_song()
        if prev_song:
            self._play_song(prev_song)

    def _on_song_finished(self) -> None:
        """Monitors when a track ends and routes to the next song."""
        # Safe execution inside main thread queue
        self.root.after(0, self._next_song)

    def _set_volume(self, value) -> None:
        """Updates player volume from slider."""
        vol = int(float(value))
        self.player.set_volume(vol)
        self.settings.set("last_volume", vol)

    # =====================================================================
    # SEEK SLIDER CONTROL
    # =====================================================================
    def _on_slider_press(self, event) -> None:
        self.is_dragging_slider = True

    def _on_slider_release(self, event) -> None:
        self.is_dragging_slider = False
        if self.playlist.current_song:
            seek_pos = float(self.seek_slider.get())
            self.player.seek(seek_pos)

    def _on_slider_change(self, value) -> None:
        # Update elapsed label in real time as the user drags
        if self.is_dragging_slider:
            self.time_elapsed_label.config(text=format_time(float(value)))

    # =====================================================================
    # PLAYLIST / DIRECTORY MANIPULATION
    # =====================================================================
    def _open_file(self) -> None:
        """Opens a file dialog to load and play a single audio file."""
        ext_str = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        file_path = filedialog.askopenfilename(
            title="Open Audio File",
            filetypes=[("Audio Files", ext_str), ("All Files", "*")]
        )
        if file_path:
            song_path = Path(file_path)
            song = Song(song_path)
            self.playlist.clear()
            self.playlist.add_song(song)
            self._render_treeview()
            self._play_song(song)
            self.settings.set("last_folder", str(song_path.parent))

    def _open_folder(self) -> None:
        """Opens a folder dialog and scans it recursively in a background thread."""
        dir_path = filedialog.askdirectory(title="Open Music Folder")
        if dir_path:
            folder = Path(dir_path)
            self.settings.set("last_folder", str(folder))
            
            # Start background folder scanning thread
            scan_thread = threading.Thread(target=self._scan_folder_worker, args=(folder,), daemon=True)
            scan_thread.start()

    def _scan_folder_worker(self, folder: Path) -> None:
        """Worker thread scanning the folder to avoid freezing Tkinter GUI."""
        self.root.after(0, lambda: self.root.config(cursor="watch"))
        songs = self.library.scan_directory(folder)
        
        # Load songs to playlist on completion
        def on_complete():
            self.root.config(cursor="")
            self.playlist.clear()
            for s in songs:
                self.playlist.add_song(s)
            self._render_treeview()
            if self.playlist.songs:
                self.playlist.current_index = 0
                # Play first song
                self._play_song(self.playlist.current_song)
            else:
                messagebox.showinfo("PLY Music", "No supported audio files found in selected directory.")

        self.root.after(0, on_complete)

    def _render_treeview(self) -> None:
        """Clears and re-inserts songs into the Treeview based on current playlist."""
        # Clear
        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)

        songs_list = self.playlist.songs
        search_query = self.search_var.get().lower()

        for idx, song in enumerate(songs_list):
            # Check search filter
            if search_query:
                match = (
                    search_query in song.title.lower() or
                    search_query in song.artist.lower() or
                    search_query in song.album.lower()
                )
                if not match:
                    continue

            # Check tags
            tag = "playing" if idx == self.playlist.current_index else ""
            self.playlist_tree.insert(
                "", tk.END, iid=str(idx),
                values=(idx + 1, song.title, format_time(song.duration)),
                tags=(tag,)
            )

        # Style tag colors
        theme = self.theme_mgr.get_gui_theme()
        self.playlist_tree.tag_configure("playing", background=theme["accent"], foreground="#ffffff")

    def _filter_playlist(self, *args) -> None:
        """Filters the playlist view when the search string changes."""
        self._render_treeview()

    def _on_tree_double_click(self, event) -> None:
        """Handles double clicking a song item in the Treeview."""
        selected_item = self.playlist_tree.selection()
        if selected_item:
            idx = int(selected_item[0])
            if 0 <= idx < len(self.playlist.songs):
                self.playlist.current_index = idx
                self._play_song(self.playlist.songs[idx])

    # =====================================================================
    # PLAYLIST LOAD/SAVE DIALOGS
    # =====================================================================
    def _load_playlist_dialog(self) -> None:
        """Dialogue to load M3U file."""
        file_path = filedialog.askopenfilename(
            title="Load M3U Playlist",
            filetypes=[("M3U Playlist", "*.m3u *.m3u8")]
        )
        if file_path:
            self.playlist.load_m3u(Path(file_path))
            self._render_treeview()
            if self.playlist.songs:
                self.playlist.current_index = 0
                self._play_song(self.playlist.songs[0])

    def _save_playlist_dialog(self) -> None:
        """Dialogue to save M3U file."""
        if not self.playlist.original_songs:
            messagebox.showwarning("PLY Music", "Active playlist is empty. Nothing to save.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save M3U Playlist",
            defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u"), ("M3U8 UTF-8 Playlist", "*.m3u8")]
        )
        if file_path:
            self.playlist.save_m3u(Path(file_path))
            messagebox.showinfo("PLY Music", "Playlist saved successfully.")

    def _open_uri(self, path) -> None:
        """Opens and plays a file from a URI (called by MPRIS OpenUri)."""
        from pathlib import Path as _Path
        from library import Song as _Song
        try:
            song_path = _Path(path).resolve()
            if not song_path.exists() or not song_path.is_file():
                logger.warning("MPRIS OpenUri: file not found: %s", song_path)
                return
            song = _Song(song_path)
            self.playlist.clear()
            self.playlist.add_song(song)
            self._render_treeview()
            self._play_song(song)
            self.settings.set("last_folder", str(song_path.parent))
            logger.info("Opened via MPRIS OpenUri: %s", song_path)
        except Exception as e:
            logger.error("Failed to open URI '%s': %s", path, e)

    # =====================================================================
    # TOGGLE PLAYBACK MODES
    # =====================================================================
    def _toggle_shuffle(self) -> None:
        """Toggles playlist shuffle state."""
        self.playlist.shuffle = not self.playlist.shuffle
        self.settings.set("shuffle", self.playlist.shuffle)
        
        # Update styling
        theme = self.theme_mgr.get_gui_theme()
        shuf_bg = theme["accent_active"] if self.playlist.shuffle else theme["btn_bg"]
        shuf_fg = "#ffffff" if self.playlist.shuffle else theme["btn_fg"]
        self.btn_shuffle.config(bg=shuf_bg, fg=shuf_fg)
        
        self._render_treeview()

    def _toggle_repeat(self) -> None:
        """Toggles playlist repeat state."""
        current = self.playlist.repeat_mode
        if current == "off":
            self.playlist.repeat_mode = "all"
        elif current == "all":
            self.playlist.repeat_mode = "single"
        else:
            self.playlist.repeat_mode = "off"
        
        self.settings.set("repeat", self.playlist.repeat_mode)

        # Update styling
        theme = self.theme_mgr.get_gui_theme()
        rep_bg = theme["accent_active"] if self.playlist.repeat_mode != "off" else theme["btn_bg"]
        rep_fg = "#ffffff" if self.playlist.repeat_mode != "off" else theme["btn_fg"]
        self.btn_repeat.config(bg=rep_bg, fg=rep_fg)

    # =====================================================================
    # UPDATE LOOPS & SYNC
    # =====================================================================
    def _update_ui_state(self, song: Song) -> None:
        """Updates text descriptions and cover art when playing a song."""
        self.song_title_label.config(text=song.title)
        self.song_artist_label.config(text=song.artist)
        self.song_album_label.config(text=f"{song.album} ({song.year})")
        self.time_total_label.config(text=format_time(song.duration))

        # Update seek scale range
        self.seek_slider.config(to=song.duration)
        self.seek_slider.set(0)

        # Dynamic cover art extraction
        self._update_song_cover(song)

        # Re-highlight playing song in Treeview
        self._render_treeview()

        # Selection focus
        if 0 <= self.playlist.current_index < len(self.playlist.songs):
            self.playlist_tree.selection_set(str(self.playlist.current_index))
            self.playlist_tree.see(str(self.playlist.current_index))

    def _update_loop(self) -> None:
        """Periodic loop to update current playback time and seek slider position."""
        if self.player.state == "playing" and not self.is_dragging_slider:
            current_time = self.player.get_elapsed_time()
            self.seek_slider.set(current_time)
            self.time_elapsed_label.config(text=format_time(current_time))

        # Schedule next update in 200 ms
        self.root.after(200, self._update_loop)

    def _load_last_session(self) -> None:
        """Restores properties (volume, folder, last song) from settings file."""
        vol = self.settings.get("last_volume")
        self.volume_slider.set(vol)
        self.player.set_volume(vol)

        last_folder = self.settings.get("last_folder")
        last_song_path = self.settings.get("last_song")

        # Set repeat and shuffle modes in controls
        self.playlist.shuffle = self.settings.get("shuffle")
        # repeat is stored as string: "off", "all", or "single"
        saved_repeat = self.settings.get("repeat")
        if isinstance(saved_repeat, bool):
            saved_repeat = "all" if saved_repeat else "off"
        self.playlist.repeat_mode = saved_repeat if saved_repeat in ("off", "all", "single") else "off"

        # Apply settings
        theme = self.theme_mgr.get_gui_theme()
        shuf_bg = theme["accent_active"] if self.playlist.shuffle else theme["btn_bg"]
        self.btn_shuffle.config(bg=shuf_bg)
        rep_bg = theme["accent_active"] if self.playlist.repeat_mode != "off" else theme["btn_bg"]
        self.btn_repeat.config(bg=rep_bg)

        # Restore folder scan if exists
        if last_folder and os.path.exists(last_folder):
            folder = Path(last_folder)
            songs = self.library.scan_directory(folder)
            for s in songs:
                self.playlist.add_song(s)
            self._render_treeview()

            # Restore last playing song
            if last_song_path and os.path.exists(last_song_path):
                song_p = Path(last_song_path)
                for s in self.playlist.songs:
                    if s.filepath == song_p:
                        self.playlist.set_current_by_song(s)
                        # Load details but do not autostart
                        self._update_ui_state(s)
                        break

    # =====================================================================
    # BACKGROUND / TRAY / MPRIS INTEGRATION
    # =====================================================================
    def _hide_to_tray(self) -> None:
        """Hide the window to the system tray. Music keeps playing."""
        self.root.withdraw()  # hide window
        if TRAY_AVAILABLE and self._tray_icon is None:
            self._start_tray_icon()
        logger.info("GUI hidden to system tray. Playback continues in background.")

    def show_window(self) -> None:
        """Restore the GUI window from the system tray."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _start_tray_icon(self) -> None:
        """Start system tray icon using AyatanaAppIndicator3 (preferred) or pystray (fallback)."""
        if not TRAY_AVAILABLE:
            return
        if TRAY_BACKEND == "appindicator":
            self._start_tray_appindicator()
        elif TRAY_BACKEND == "pystray":
            self._start_tray_pystray()

    def _start_tray_appindicator(self) -> None:
        """Start tray icon via AyatanaAppIndicator3."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("GLib", "2.0")

            from gi.repository import Gtk as _Gtk
            from gi.repository import GLib as _GLib

            # ---------------------------------------------------------
            # Icon
            # ---------------------------------------------------------
            icon_path = ASSETS_DIR / "music.png"

            if not icon_path.exists():
                icon_path = Path(
                    "/app/share/icons/hicolor/128x128/apps/"
                    "io.github.ahmed.ply.png"
                )

            if icon_path.exists():
                icon_theme = _Gtk.IconTheme.get_default()

                # Make Flatpak application icon directory visible to GTK
                icon_theme.append_search_path("/app/share/icons")
                icon_theme.append_search_path("/app/share/icons/hicolor/128x128/apps")

                icon_name = "io.github.ahmed.ply"

                logger.info(
                    "Tray icon configured: name=%s path=%s",
                    icon_name,
                    icon_path,
                )
            else:
                icon_name = "audio-x-generic"
                logger.warning("PLY tray icon file not found.")

            # ---------------------------------------------------------
            # Create AppIndicator
            # ---------------------------------------------------------
            indicator = AppIndicator.Indicator.new(
                "ply-music-player",
                icon_name,
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )

            indicator.set_status(
                AppIndicator.IndicatorStatus.ACTIVE
            )

            indicator.set_title("PLY Music Player")

            # ---------------------------------------------------------
            # Build GTK menu
            # ---------------------------------------------------------
            menu = _Gtk.Menu()

            item_open = _Gtk.MenuItem(label="Open PLY")
            item_open.connect(
                "activate",
                lambda _: self.root.after(0, self.show_window)
            )
            menu.append(item_open)

            menu.append(_Gtk.SeparatorMenuItem())

            item_prev = _Gtk.MenuItem(label="⏮ Previous")
            item_prev.connect(
                "activate",
                lambda _: self.root.after(0, self._prev_song)
            )
            menu.append(item_prev)

            item_pp = _Gtk.MenuItem(label="▶/⏸ Play/Pause")
            item_pp.connect(
                "activate",
                lambda _: self.root.after(0, self._toggle_play_pause)
            )
            menu.append(item_pp)

            item_next = _Gtk.MenuItem(label="⏭ Next")
            item_next.connect(
                "activate",
                lambda _: self.root.after(0, self._next_song)
            )
            menu.append(item_next)

            menu.append(_Gtk.SeparatorMenuItem())

            item_quit = _Gtk.MenuItem(label="⏹ Quit PLY")
            item_quit.connect(
                "activate",
                lambda _: self.root.after(0, self._quit_app)
            )
            menu.append(item_quit)

            menu.show_all()
            indicator.set_menu(menu)

            # ---------------------------------------------------------
            # Keep references alive
            # ---------------------------------------------------------
            self._tray_icon = indicator
            self._tray_menu = menu

            # ---------------------------------------------------------
            # GLib event loop
            # ---------------------------------------------------------
            self._tray_glib_loop = _GLib.MainLoop()

            self._tray_thread = threading.Thread(
                target=self._tray_glib_loop.run,
                daemon=True,
                name="tray-glib",
            )

            self._tray_thread.start()

            logger.info(
                "AyatanaAppIndicator3 tray icon started "
                "(icon name: %s, path: %s).",
                icon_name,
                icon_path,
            )

        except Exception as e:
            logger.exception(
                "Failed to create AyatanaAppIndicator3 tray icon: %s",
                e,
            )
            self._tray_icon = None

    def _start_tray_pystray(self) -> None:
        """Fallback: start pystray tray icon (for native non-Flatpak installs)."""
        try:
            icon_path = ASSETS_DIR / "music.png"
            if not icon_path.exists():
                icon_path = Path("/usr/share/pixmaps/music.png")
            import pystray as _pystray
            tray_image = Image.open(icon_path).resize((64, 64))
            menu = _pystray.Menu(
                _pystray.MenuItem("Open PLY", lambda icon, item: self.root.after(0, self.show_window)),
                _pystray.Menu.SEPARATOR,
                _pystray.MenuItem("\u23ee Previous", lambda icon, item: self.root.after(0, self._prev_song)),
                _pystray.MenuItem("\u25b6/\u23f8 Play/Pause", lambda icon, item: self.root.after(0, self._toggle_play_pause)),
                _pystray.MenuItem("\u23ed Next", lambda icon, item: self.root.after(0, self._next_song)),
                _pystray.Menu.SEPARATOR,
                _pystray.MenuItem("\u23f9 Quit PLY", lambda icon, item: self.root.after(0, self._quit_app)),
            )
            self._tray_icon = _pystray.Icon("ply", tray_image, "PLY Music Player", menu)
            self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
            self._tray_thread.start()
            logger.info("pystray tray icon started (fallback backend).")
        except Exception as e:
            logger.warning("Failed to create pystray tray icon: %s", e)
            self._tray_icon = None


    def _toggle_play_pause(self) -> None:
        """Toggle play/pause from tray or MPRIS."""
        if self.player.state == "playing":
            self._pause_song()
        elif self.player.state == "paused":
            self.player.resume()
            if self.mpris:
                current = self.playlist.current_song
                if current:
                    self.mpris.update_playing(
                        current.title, current.artist, current.album,
                        current.duration, self.player.volume
                    )
        elif self.player.state == "stopped":
            self._play_song()

    def _quit_app(self) -> None:
        """Full application quit: stop music, destroy tray, close window."""
        self._app_quitting = True
        # Stop tray icon (backend-agnostic)
        if self._tray_icon:
            try:
                if TRAY_BACKEND == "appindicator":
                    self._tray_icon.set_status(AppIndicator.IndicatorStatus.PASSIVE)
                    if hasattr(self, "_tray_glib_loop") and self._tray_glib_loop:
                        self._tray_glib_loop.quit()
                elif TRAY_BACKEND == "pystray":
                    self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        self.shutdown()

    def shutdown(self) -> None:
        """Full shutdown: save settings, stop player, clean up."""
        self.player.stop()
        self.player.close()

        self.settings.set("last_volume", self.player.volume)
        self.settings.set("shuffle", self.playlist.shuffle)
        # Save repeat_mode as string ("off", "all", "single")
        self.settings.set("repeat", self.playlist.repeat_mode)

        current = self.playlist.current_song
        if current:
            self.settings.set("last_song", str(current.filepath))

        clean_temp_dir()
        self.root.destroy()
        logger.info("GUI Shutdown complete.")

    def run(self) -> None:
        """Starts the Tkinter main event loop."""
        self.root.mainloop()
