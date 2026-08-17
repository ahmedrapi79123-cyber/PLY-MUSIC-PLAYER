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
    # NOTE: install_requires is intentionally empty here.
    # In Flatpak, all dependencies (mutagen, rich, pillow, pystray) are
    # pre-installed by the manifest modules before this package.
    # For native/pip installs, use: pip install ply-player[tray]
    install_requires=[],
    extras_require={
        "full": [
            "mutagen>=1.46.0",
            "rich>=13.0.0",
            "pillow>=10.0.0",
        ],
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
