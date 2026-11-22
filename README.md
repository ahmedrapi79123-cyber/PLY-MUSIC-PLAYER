# PLY Pro 3.1.2 🎧

**PLY Pro** is a modern and lightweight music player for Linux, written in Python. It combines a GStreamer-powered playback engine with two interfaces:

- **Graphical Interface (GUI):** Built with CustomTkinter.
- **Terminal Interface (CLI):** Interactive terminal interface powered by Rich.

## Features

- **Modern GUI:** CustomTkinter interface with dark and light themes.
- **GStreamer Audio Engine:** Reliable audio playback with support for formats provided by installed GStreamer plugins.
- **Terminal Interface:** Control music playback through the Rich-based CLI.
- **MPRIS2 Integration:** Desktop media controls and media-key support.
- **System Tray:** Background playback with tray controls.
- **Music Library:** Scan folders and read track metadata.
- **Album Artwork:** Display embedded cover art.
- **Playlists:** Import and export M3U and M3U8 playlists.
- **Playback Controls:** Play, pause, stop, next, previous, shuffle, repeat, and volume.
- **Persistent Settings:** Save preferences and playback history.

---

## Requirements

- Linux
- Python 3.10 or newer
- GStreamer 1.0
- GTK and GObject introspection bindings
- Tkinter
- GStreamer base, good, and ugly plugins

## Installation

### Ubuntu / Debian

Install the system dependencies:

```bash
sudo apt-get update

sudo apt-get install \
    python3 python3-pip python3-venv \
    python3-tk python3-gi python3-gst-1.0 python3-dbus \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly
```

### Install from source

Clone the repository:

```bash
git clone https://github.com/ahmedrapi79123-cyber/PLY-MUSIC-PLAYER.git
cd PLY-MUSIC-PLAYER
```

Create and activate a virtual environment:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

Install Python dependencies and PLY Pro:

```bash
pip install -r requirements.txt
pip install .
```

Launch the graphical interface:

```bash
ply --gui
```

### Install from a Debian package

```bash
sudo apt install ./ply-player_3.1.2_all.deb
```

---

## Usage

### Graphical Interface

Launch the PLY Pro GUI:

```bash
ply --gui
```

### Terminal Interface

Play a specific audio file:

```bash
ply song.mp3
```

Play music from a directory:

```bash
ply ~/Music
```

Enable shuffle:

```bash
ply ~/Music --shuffle
```

Enable repeat:

```bash
ply ~/Music --repeat
```

Set the initial volume to 75%:

```bash
ply ~/Music --volume 75
```

Display help:

```bash
ply --help
```

---

## CLI Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `N` | Next Track |
| `B` | Previous Track |
| `S` | Stop Playback |
| `+` / `-` | Volume Up / Down |
| `H` | Toggle Shuffle |
| `R` | Cycle Repeat |
| `Q` | Quit |

---

## MPRIS2 Integration

PLY Pro registers as an MPRIS2 media player on the D-Bus session bus.

This allows compatible desktop environments and media controllers to:

- Control playback.
- Skip to the next or previous track.
- Pause and resume music.
- Use desktop media keys.

---

## Data and Configuration

PLY stores its user data in:

```text
~/.ply/
```

This directory contains application settings, playback history, logs, and cached artwork.

---

## Project Structure

```text
PLY-MUSIC-PLAYER/
├── main.py              # Application entry point
├── gui_ctk.py           # CustomTkinter graphical interface
├── gui.py               # Shared GUI and playback logic
├── cli.py               # Rich terminal interface
├── player.py            # GStreamer playback engine
├── playlist.py          # Playlist management
├── library.py           # Music library and metadata
├── settings.py          # User settings
├── config.py            # Application configuration
├── themes.py             # Theme configuration
├── icons.py              # Icon utilities
├── utils.py              # Utility functions
├── mpris.py              # MPRIS2 integration
├── assets/               # Application images and icons
├── requirements.txt      # Python dependencies
├── setup.py              # Package configuration
├── build_deb.sh          # Debian package builder
└── LICENSE               # MIT License
```

---

## Development

Run PLY Pro from the source directory:

```bash
python3 main.py --gui
```

Build a Debian package:

```bash
./build_deb.sh
```

---

## License

PLY Pro is licensed under the MIT License. See the `LICENSE` file for details.
