# PLY Music Player 🎧

**PLY** is a professional, modern, and lightweight music player written in **Python**. It features a unified playback engine with two beautiful modes of operation:
1. **Interactive Terminal User Interface (CLI)** using `Rich` for gorgeous dashboards.
2. **Graphical User Interface (GUI)** using `Tkinter` and `Pillow` for a sleek dark/light mode experience.

---

## Features / المميزات

* **Bimodal Interface**: Run in the terminal (CLI) or as a desktop application (GUI).
* **Modern Design**: Vibrant purple accents, glassmorphic layout principles, and dynamic dark/light theme switching.
* **Auto-Discovery**: Automatically scan folders, identify supported audio files, and import metadata (Title, Artist, Album, Year, Duration, Cover Art).
* **Rich Formats**: Native support for `MP3`, `WAV`, and `OGG`.
* **Playlists**: Import and export standard `M3U` and `M3U8` playlists.
* **Preferences & History**: Persistent volume, last directories, settings, and play history.
* **Non-Blocking Architecture**: Fully multi-threaded scanner and play engine so interfaces never freeze.

---

## Installation / التثبيت

### Prerequisites / المتطلبات الأساسية
* Python 3.11 or newer.
* System audio drivers installed (ALSA/PulseAudio on Linux, CoreAudio on macOS, WASAPI on Windows).

On Ubuntu/Debian, install the required packages:
```bash
sudo apt-get update
sudo apt-get install python3-tk -y
```

### Install PLY / تثبيت البرنامج
Clone or download the project folder, then run the installer:
```bash
pip install .
```
This automatically installs all dependencies (listed in `requirements.txt`) and registers the command `ply` in your system's PATH.

---

## Command Line Usage / طريقة الاستخدام عبر الطرفية

Start playing files or folders, configure modes, or trigger settings using CLI commands:

```bash
# Force launch the Graphical User Interface (GUI)
ply --gui

# Play a specific audio file directly in the terminal CLI
ply song.mp3

# Play all supported files in a directory in the CLI
ply ~/Music

# Play in the CLI with shuffle enabled
ply ~/Music --shuffle

# Play in the CLI with repeat enabled
ply ~/Music --repeat

# Play in the CLI with initial volume set to 75%
ply ~/Music --volume 75

# Display help information
ply --help
```

---

## Keyboard Shortcuts (CLI) / اختصارات لوحة المفاتيح

Control playback in the terminal CLI using single keystrokes:

| Key / المفتاح | Action / الإجراء |
|---|---|
| `Space` | Play / Pause (تشغيل / إيقاف مؤقت) |
| `N` | Next Track (الأغنية التالية) |
| `B` | Previous Track (الأغنية السابقة) |
| `S` | Stop Playback (إيقاف التشغيل) |
| `+` / `-` | Increase / Decrease Volume (رفع / خفض الصوت) |
| `H` | Toggle Shuffle Mode (تبديل الوضع العشوائي) |
| `R` | Toggle Repeat Mode (تبديل وضع التكرار: إيقاف -> تكرار الكل -> تكرار أغنية واحدة) |
| `Q` | Quit Application (خروج من البرنامج) |

---

## Graphical User Interface (GUI) / الواجهة الرسومية

The GUI offers a complete media dashboard containing:
* **Interactive Playlist Sidebar**: Shows all loaded tracks. Double-click to play any track.
* **Live Search**: Instantly filter tracks in the active list.
* **Theme Switcher**: Dynamic button `🌓` to toggle between Dark Mode and Light Mode.
* **Music Cover Art**: Displays embedded cover images (cached in `data/temp/`) or fallback vinyl art.
* **Drag-to-Seek**: Fluid slider displaying current elapsed time vs. track duration.
* **Control Dock**: Shuffle, Repeat, Prev, Play, Pause, Stop, Next, and Volume slider.
* **Importing**: Quick access buttons to load files, scan folders, or import/export M3U playlists.

---

## Directory Structure / هيكلية المشروع

```text
ply/
│
├── main.py            # Main entry point and CLI router
├── cli.py             # Rich Terminal TUI
├── gui.py             # Tkinter GUI
├── player.py          # Pygame-based playback engine
├── playlist.py        # M3U/M3U8 playlist manager
├── library.py         # Song models, folder scanner, play history
├── settings.py        # JSON settings manager
├── config.py          # Logger, environment configuration, paths
├── themes.py          # Color schemes (Dark/Light)
├── icons.py           # Programmatic PNG assets generator
├── utils.py           # Metadata reader and caching helpers
│
├── data/
│   ├── settings.json  # Saved settings
│   └── history.json   # Played songs history
│
├── logs/
│   └── ply.log        # Error and activity logs
│
├── requirements.txt   # Third-party libraries
├── README.md          # User Guide
├── LICENSE            # MIT License
└── setup.py           # Package installation script
```

---

## License / الترخيص
This project is licensed under the **MIT License**. See the `LICENSE` file for more details.
