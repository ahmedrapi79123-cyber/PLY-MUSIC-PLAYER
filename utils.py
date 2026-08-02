"""Utility functions for the PLY music player.

Includes audio metadata extraction, time formatting, and cover art caching.
Supports MP3, OGG, FLAC, WAV, Opus, M4A/AAC via mutagen with GStreamer fallback.
"""

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

try:
    from mutagen.flac import FLAC, Picture as FlacPicture
    FLAC_AVAILABLE = True
except ImportError:
    FLAC_AVAILABLE = False

try:
    from mutagen.mp4 import MP4
    MP4_AVAILABLE = True
except ImportError:
    MP4_AVAILABLE = False

from config import TEMP_DIR, logger


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------

def format_time(seconds: float) -> str:
    """Formats duration in seconds to MM:SS format."""
    if not seconds or seconds < 0:
        return "00:00"
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(filepath: Path) -> Dict[str, Any]:
    """Extracts metadata (Title, Artist, Album, Year, Duration) from an audio file.

    Supports MP3, OGG, FLAC, WAV, Opus, M4A/AAC via mutagen.
    Falls back to GStreamer Discoverer for any format mutagen cannot handle.
    Returns safe defaults if the file cannot be read.
    """
    filepath = Path(filepath)
    metadata: Dict[str, Any] = {
        "title": filepath.stem,
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "year": "Unknown Year",
        "duration": 0.0,
        "has_cover": False,
        "cover_path": None,
    }

    if not filepath.exists():
        return metadata

    try:
        audio = mutagen.File(filepath, easy=False)
        if audio is not None:
            # Duration
            if audio.info:
                metadata["duration"] = float(audio.info.length)

            # ---- MP3 / ID3 ----
            if isinstance(audio, MP3) or (
                audio.tags is not None and isinstance(audio.tags, ID3)
            ):
                tags = audio.tags
                if tags:
                    metadata["title"]  = str(tags.get("TIT2", filepath.stem))
                    metadata["artist"] = str(tags.get("TPE1", "Unknown Artist"))
                    metadata["album"]  = str(tags.get("TALB", "Unknown Album"))
                    year_tag = tags.get("TDRC") or tags.get("TYER")
                    if year_tag:
                        metadata["year"] = str(year_tag).split("-")[0]
                    for key in tags.keys():
                        if key.startswith("APIC"):
                            metadata["has_cover"] = True
                            break

            # ---- OGG Vorbis ----
            elif isinstance(audio, OggVorbis):
                metadata["title"]  = str(audio.get("title",  [filepath.stem])[0])
                metadata["artist"] = str(audio.get("artist", ["Unknown Artist"])[0])
                metadata["album"]  = str(audio.get("album",  ["Unknown Album"])[0])
                metadata["year"]   = str(audio.get("date",   ["Unknown Year"])[0])
                if "metadata_block_picture" in audio or any(
                    k.startswith("coverart") for k in audio.keys()
                ):
                    metadata["has_cover"] = True

            # ---- FLAC ----
            elif FLAC_AVAILABLE and isinstance(audio, FLAC):
                metadata["title"]  = str(audio.get("title",  [filepath.stem])[0])
                metadata["artist"] = str(audio.get("artist", ["Unknown Artist"])[0])
                metadata["album"]  = str(audio.get("album",  ["Unknown Album"])[0])
                metadata["year"]   = str(audio.get("date",   ["Unknown Year"])[0])
                if audio.pictures:
                    metadata["has_cover"] = True

            # ---- WAV (ID3 or RIFF) ----
            elif isinstance(audio, WAVE):
                if audio.tags:
                    metadata["title"]  = str(audio.tags.get("TIT2", filepath.stem))
                    metadata["artist"] = str(audio.tags.get("TPE1", "Unknown Artist"))
                    metadata["album"]  = str(audio.tags.get("TALB", "Unknown Album"))
                    year_tag = audio.tags.get("TDRC") or audio.tags.get("TYER")
                    if year_tag:
                        metadata["year"] = str(year_tag).split("-")[0]

            # ---- M4A / AAC (MP4 container) ----
            elif MP4_AVAILABLE and isinstance(audio, MP4):
                tags = audio.tags
                if tags:
                    metadata["title"]  = str(tags.get("\xa9nam", [filepath.stem])[0])
                    metadata["artist"] = str(tags.get("\xa9ART", ["Unknown Artist"])[0])
                    metadata["album"]  = str(tags.get("\xa9alb", ["Unknown Album"])[0])
                    year_raw = tags.get("\xa9day", ["Unknown Year"])
                    metadata["year"]   = str(year_raw[0]).split("-")[0]
                    if "covr" in tags:
                        metadata["has_cover"] = True

    except Exception as e:
        logger.warning("mutagen could not read '%s': %s", filepath.name, e)

    # GStreamer Discoverer fallback for duration when mutagen fails or returns 0
    if metadata["duration"] == 0.0:
        _gst_fill_duration(filepath, metadata)

    return metadata


def _gst_fill_duration(filepath: Path, metadata: Dict[str, Any]) -> None:
    """Uses GStreamer Discoverer to fill in the duration field."""
    try:
        import gi  # type: ignore
        gi.require_version("Gst", "1.0")
        gi.require_version("GstPbutils", "1.0")
        from gi.repository import Gst, GstPbutils  # type: ignore

        Gst.init(None)
        disc = GstPbutils.Discoverer.new(Gst.SECOND * 5)
        info = disc.discover_uri(filepath.resolve().as_uri())
        dur = info.get_duration()
        if dur > 0:
            metadata["duration"] = dur / Gst.SECOND
            logger.info(
                "GStreamer Discoverer duration for '%s': %.2fs",
                filepath.name,
                metadata["duration"],
            )
    except Exception as ge:
        logger.warning(
            "GStreamer Discoverer fallback failed for '%s': %s", filepath.name, ge
        )


# ---------------------------------------------------------------------------
# Cover art extraction
# ---------------------------------------------------------------------------

def get_album_cover(filepath: Path) -> Optional[Path]:
    """Extracts album cover art and saves it as a cached PNG file.

    Returns the path to the cached PNG image, or None if no cover is found.
    The cached file is always a valid PNG regardless of the source format.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    # Generate a stable cache key from the absolute file path
    path_hash = hashlib.md5(str(filepath.absolute()).encode("utf-8")).hexdigest()
    cache_path = TEMP_DIR / f"{path_hash}.png"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    cover_data: Optional[bytes] = None

    try:
        audio = mutagen.File(filepath, easy=False)
        if audio is None:
            return None

        # ---- MP3 / ID3 ----
        if isinstance(audio, MP3) or (
            audio.tags is not None and isinstance(audio.tags, ID3)
        ):
            tags = audio.tags
            if tags:
                for key in tags.keys():
                    if key.startswith("APIC"):
                        cover_data = tags[key].data
                        break

        # ---- OGG Vorbis ----
        elif isinstance(audio, OggVorbis):
            if "metadata_block_picture" in audio:
                import base64
                for pic_raw in audio["metadata_block_picture"]:
                    try:
                        pic = FlacPicture(base64.b64decode(pic_raw))
                        cover_data = pic.data
                        break
                    except Exception:
                        continue

        # ---- FLAC ----
        elif FLAC_AVAILABLE and isinstance(audio, FLAC):
            if audio.pictures:
                cover_data = audio.pictures[0].data

        # ---- M4A / MP4 ----
        elif MP4_AVAILABLE and isinstance(audio, MP4):
            tags = audio.tags
            if tags and "covr" in tags:
                cover_data = bytes(tags["covr"][0])

    except Exception as e:
        logger.warning("Failed to extract cover art from '%s': %s", filepath.name, e)
        return None

    if not cover_data:
        return None

    # Convert raw image bytes → proper PNG using PIL
    try:
        from PIL import Image  # type: ignore
        import io

        img = Image.open(io.BytesIO(cover_data)).convert("RGB")
        img.save(cache_path, "PNG", optimize=True)
        logger.info("Cached cover art for '%s' → %s", filepath.name, cache_path)
        return cache_path
    except Exception as e:
        logger.warning("Failed to convert cover art to PNG for '%s': %s", filepath.name, e)

    return None


# ---------------------------------------------------------------------------
# Temp-dir cleanup
# ---------------------------------------------------------------------------

def clean_temp_dir() -> None:
    """Cleans up all cached cover art in the temp directory."""
    try:
        for file in TEMP_DIR.iterdir():
            if file.is_file():
                file.unlink(missing_ok=True)
        logger.info("Temp directory cleaned.")
    except Exception as e:
        logger.error("Failed to clean temp directory: %s", e)


# ---------------------------------------------------------------------------
# Optional: OGG transcoding via ffmpeg (unused by default but kept as utility)
# ---------------------------------------------------------------------------

def transcode_to_ogg(filepath: Path) -> Optional[Path]:
    """Transcodes any audio file to OGG using ffmpeg.

    Useful as a last-resort fallback for formats GStreamer cannot play.
    Returns the cached OGG path, or None if ffmpeg is unavailable or fails.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not installed — cannot transcode '%s'", filepath.name)
        return None

    path_hash = hashlib.md5(str(filepath.absolute()).encode("utf-8")).hexdigest()
    ogg_cache = TEMP_DIR / f"transcoded_{path_hash}.ogg"

    if ogg_cache.exists() and ogg_cache.stat().st_size > 0:
        return ogg_cache

    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(filepath),
            "-vn", "-c:a", "libvorbis", "-q:a", "5",
            str(ogg_cache),
        ]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
        )
        if res.returncode == 0 and ogg_cache.exists():
            logger.info("Transcoded '%s' → %s", filepath.name, ogg_cache)
            return ogg_cache
        logger.warning(
            "ffmpeg returned code %d for '%s'", res.returncode, filepath.name
        )
    except Exception as e:
        logger.error("Transcoding failed for '%s': %s", filepath.name, e)

    return None
