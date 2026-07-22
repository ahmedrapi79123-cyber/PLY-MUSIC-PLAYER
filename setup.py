"""Setup configuration for the PLY music player.

Allows packaging, distribution, and easy installation via pip.
"""

from setuptools import setup

setup(
    name="ply-player",
    version="1.0.0",
    description="A professional, modern command-line and graphical music player.",
    author="PLY Developers",
    py_modules=["main", "cli", "gui", "player", "playlist", "library", "settings", "config", "themes", "icons", "utils"],
    install_requires=[
        "pygame>=2.5.0",
        "mutagen>=1.46.0",
        "rich>=13.0.0",
        "pillow>=10.0.0"
    ],
    entry_points={
        "console_scripts": [
            "ply=main:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio :: Players",
    ],
)
