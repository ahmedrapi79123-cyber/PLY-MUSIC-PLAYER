# PLY Music Player 🎧

**PLY** is a professional, modern, and lightweight music player written in **Python**. It features a unified playback engine powered by **GStreamer** with two beautiful modes of operation:
1. **Interactive Terminal User Interface (CLI)** using `Rich` for gorgeous dashboards.
2. **Graphical User Interface (GUI)** using `Tkinter` and `Pillow` for a sleek dark/light mode experience.

---

## Features

* **Bimodal Interface**: Run in the terminal (CLI) or as a desktop application (GUI).
* **GStreamer Audio Engine**: Uses the same playback engine as Rhythmbox and GNOME Music for reliable, high-quality audio.
* **MPRIS2 Integration**: Control playback from your desktop panel, PulseAudio plugin, or any MPRIS-compatible controller.
* **Background Playback**: Close the GUI window and music keeps playing. A system tray icon provides quick controls.
* **Modern Design**: Vibrant purple accents, glassmorphic layout principles, and dynamic dark/light theme switching.
* **Auto-Discovery**: Automatically scan folders, identify supported audio files, and import metadata (Title, Artist, Album, Year, Duration, Cover Art).
* **Rich Formats**: Native support for `MP3`, `WAV`, and `OGG` (more formats supported if GStreamer plugins are available).
* **Playlists**: Import and export standard `M3U` and `M3U8` playlists.
* **Preferences & History**: Persistent volume, last directories, settings, and play history.
* **Non-Blocking Architecture**: Fully multi-threaded scanner and play engine so interfaces never freeze.

---

## Installation

### Prerequisites
* Python 3.10 or newer.
* GStreamer 1.0 with base/good plugins.
* System audio drivers installed (PulseAudio/PipeWire on Linux).

### Ubuntu/Debian

Install the required system packages:
```bash
sudo apt-get update
sudo apt-get install python3-tk python3-gi python3-gst-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly python3-dbus -y
```

### Install from source
Clone the repository and install:
```bash
pip install .
```
This registers the `ply` command in your PATH.

### Install from .deb package
```bash
sudo apt install ./ply-player_1.0.0_all.deb
```

### Install from Flatpak
```bash
flatpak install flathub io.github.ahmed.ply
flatpak run io.github.ahmed.ply
```

---

## Command Line Usage

```bash
# Launch the Graphical User Interface (GUI)
ply --gui

# Play a specific audio file in the terminal CLI
ply song.mp3

# Play all supported files in a directory
ply ~/Music

# Play with shuffle enabled
ply ~/Music --shuffle

# Play with repeat enabled
ply ~/Music --repeat

# Set initial volume to 75%
ply ~/Music --volume 75

# Display help
ply --help
```

---

## Keyboard Shortcuts (CLI)

| Key     | Action                          |
|---------|---------------------------------|
| `Space` | Play / Pause                    |
| `N`     | Next Track                      |
| `B`     | Previous Track                  |
| `S`     | Stop Playback                   |
| `+`/`-` | Volume Up / Down                |
| `H`     | Toggle Shuffle                  |
| `R`     | Cycle Repeat (Off → All → One)  |
| `Q`     | Quit                            |

---

## Graphical User Interface (GUI)

The GUI offers a complete media dashboard containing:
* **Interactive Playlist Sidebar**: Shows all loaded tracks. Double-click to play any track.
* **Live Search**: Instantly filter tracks in the active list.
* **Theme Switcher**: Toggle between Dark Mode and Light Mode.
* **Music Cover Art**: Displays embedded cover images or fallback vinyl art.
* **Drag-to-Seek**: Fluid slider displaying current elapsed time vs. track duration.
* **Control Dock**: Shuffle, Repeat, Prev, Play, Pause, Stop, Next, and Volume slider.
* **Importing**: Load files, scan folders, or import/export M3U playlists.
* **System Tray**: Close the window to minimize to tray with playback controls.

---

## MPRIS2 Support

PLY registers as `org.mpris.MediaPlayer2.ply` on the D-Bus session bus, providing standard media player controls to desktop environments. This means:
* PulseAudio panel plugin shows PLY with play/pause/next/previous controls.
* Desktop media keys work automatically.
* Any MPRIS2-compatible controller can manage PLY.

---

## Data & Configuration

PLY stores its data in `~/.ply/`:

```text
~/.ply/
├── data/
│   ├── settings.json   # User preferences
│   ├── history.json    # Play history
│   └── temp/           # Cached cover art
├── logs/
│   └── ply.log         # Application log
└── assets/             # Generated icons
```

---

## Directory Structure

```text
ply/
├── main.py            # Entry point and CLI router
├── cli.py             # Rich Terminal TUI
├── gui.py             # Tkinter GUI
├── player.py          # GStreamer playbin audio engine
├── playlist.py        # M3U/M3U8 playlist manager
├── library.py         # Song models, folder scanner, play history
├── settings.py        # JSON settings manager
├── config.py          # Logger, paths, configuration
├── themes.py          # Color schemes (Dark/Light)
├── icons.py           # Programmatic PNG assets generator
├── utils.py           # Metadata reader and caching helpers
├── mpris.py           # MPRIS2 D-Bus media controller
├── requirements.txt   # Python dependencies
├── setup.py           # Package installer
├── build_deb.sh       # Debian package builder
├── flatpak/           # Flatpak packaging files
└── LICENSE            # MIT License
```

---

## Development

### Running from source
```bash
python3 main.py --gui
```

### Building the .deb package
```bash
./build_deb.sh
```

### Building the Flatpak
```bash
flatpak-builder --user --install --force-clean build-flatpak flatpak/io.github.ahmed.ply.yml
```

---

## License
This project is licensed under the **MIT License**. See the `LICENSE` file for more details.
