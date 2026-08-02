"""Setup configuration for the PLY music player.

Allows packaging, distribution, and easy installation via pip.
"""

from setuptools import setup

setup(
    name="ply-player",
    version="1.0.0",
    description="A professional, modern command-line and graphical music player.",
    author="Ahmed",
    author_email="developer@ply.org",
    url="https://github.com/ahmedrapi79123-cyber/PLY-MUSIC-PLAYER",
    license="MIT",
    py_modules=[
        "main", "cli", "gui", "player", "playlist",
        "library", "settings", "config", "themes", "icons", "utils", "mpris",
    ],
    install_requires=[
        "mutagen>=1.46.0",
        "rich>=13.0.0",
        "pillow>=10.0.0",
        # pystray is optional (system tray support) — gracefully skipped if absent.
        # Install it with: pip install pystray>=0.19.5
    ],
    extras_require={
        "tray": ["pystray>=0.19.5"],
    },
    entry_points={
        "console_scripts": [
            "ply=main:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
        "Topic :: Multimedia :: Sound/Audio :: Players",
        "License :: OSI Approved :: MIT License",
    ],
)
