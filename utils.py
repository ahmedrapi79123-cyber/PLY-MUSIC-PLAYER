"""Utility functions for the PLY music player.

Includes audio metadata extraction, time formatting, and cover art caching.
"""

import os
from pathlib import Path
import hashlib
from typing import Dict, Any, Optional
import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from config import TEMP_DIR, logger

def format_time(seconds: float) -> str:
    """Formats duration in seconds to MM:SS format."""
    if not seconds or seconds < 0:
        return "00:00"
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"

def extract_metadata(filepath: Path) -> Dict[str, Any]:
    """Extracts metadata (Title, Artist, Album, Year, Duration) from an audio file.

    Falls back to filename/defaults if tags are missing.
    Uses GStreamer Discoverer as a fallback for formats mutagen cannot handle (e.g. WebM/Opus).
    """
    metadata = {
        "title": filepath.stem,
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "year": "Unknown Year",
        "duration": 0.0,
        "has_cover": False,
        "cover_path": None
    }

    if not filepath.exists():
        return metadata

    try:
        audio = mutagen.File(filepath)
        if audio is not None:
            # Duration
            if audio.info:
                metadata["duration"] = audio.info.length

            # Tag extraction based on format
            if isinstance(audio, MP3) or (audio.tags and isinstance(audio.tags, ID3)):
                tags = audio.tags
                if tags:
                    metadata["title"] = str(tags.get("TIT2", filepath.stem))
                    metadata["artist"] = str(tags.get("TPE1", "Unknown Artist"))
                    metadata["album"] = str(tags.get("TALB", "Unknown Album"))
                    year_tag = tags.get("TDRC") or tags.get("TYER")
                    if year_tag:
                        metadata["year"] = str(year_tag)
                    
                    # Look for APIC (Attached Picture)
                    for key in tags.keys():
                        if key.startswith("APIC"):
                            metadata["has_cover"] = True
                            break

            elif isinstance(audio, OggVorbis):
                metadata["title"] = str(audio.get("title", [filepath.stem])[0])
                metadata["artist"] = str(audio.get("artist", ["Unknown Artist"])[0])
                metadata["album"] = str(audio.get("album", ["Unknown Album"])[0])
                metadata["year"] = str(audio.get("date", ["Unknown Year"])[0])
                
                # Check for cover art
                if "metadata_block_picture" in audio or any(k.startswith("coverart") for k in audio.keys()):
                    metadata["has_cover"] = True

            elif isinstance(audio, WAVE):
                # WAV can have ID3 or RIFF tags
                if audio.tags:
                    metadata["title"] = str(audio.tags.get("TIT2", filepath.stem))
                    metadata["artist"] = str(audio.tags.get("TPE1", "Unknown Artist"))
                    metadata["album"] = str(audio.tags.get("TALB", "Unknown Album"))
                    year_tag = audio.tags.get("TDRC") or audio.tags.get("TYER")
                    if year_tag:
                        metadata["year"] = str(year_tag)
                else:
                    # Try reading RIFF tags if possible, otherwise keep defaults
                    pass
    except Exception as e:
        logger.warning("mutagen could not read %s: %s", filepath.name, e)

    # If duration is still 0 (e.g. WebM/Opus file misnamed as .mp3),
    # fall back to GStreamer Discoverer which handles any container format.
    if metadata["duration"] == 0.0:
        try:
            import gi
            gi.require_version('Gst', '1.0')
            gi.require_version('GstPbutils', '1.0')
            from gi.repository import Gst, GstPbutils
            Gst.init(None)
            disc = GstPbutils.Discoverer.new(Gst.SECOND * 5)
            info = disc.discover_uri(filepath.resolve().as_uri())
            dur = info.get_duration()
            if dur > 0:
                metadata["duration"] = dur / Gst.SECOND
                logger.info("GStreamer Discoverer duration for %s: %.2fs", filepath.name, metadata["duration"])
        except Exception as ge:
            logger.warning("GStreamer Discoverer fallback failed for %s: %s", filepath.name, ge)

    return metadata

def get_album_cover(filepath: Path) -> Optional[Path]:
    """Extracts album cover art and saves it as a temporary PNG file.

    Returns the path to the cached image, or None if no cover is found.
    """
    if not filepath.exists():
        return None

    # Generate a unique hash for the file path to cache the cover
    path_hash = hashlib.md5(str(filepath.absolute()).encode("utf-8")).hexdigest()
    cache_path = TEMP_DIR / f"{path_hash}.png"

    # If already cached, return it
    if cache_path.exists():
        return cache_path

    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return None

        cover_data = None
        mime_type = "image/png"

        # MP3 ID3 APIC tag extraction
        if isinstance(audio, MP3) or (audio.tags and isinstance(audio.tags, ID3)):
            tags = audio.tags
            if tags:
                for key in tags.keys():
                    if key.startswith("APIC"):
                        apic = tags[key]
                        cover_data = apic.data
                        mime_type = apic.mime
                        break
        # OGG Vorbis cover extraction
        elif isinstance(audio, OggVorbis):
            if "metadata_block_picture" in audio:
                # Picture is base64 or raw structure
                from mutagen.flac import Picture
                import base64
                for pic_data in audio["metadata_block_picture"]:
                    try:
                        pic = Picture(base64.b64decode(pic_data))
                        cover_data = pic.data
                        mime_type = pic.mime
                        break
                    except Exception:
                        continue

        if cover_data:
            # Save bytes to cache path
            # We don't worry about conversion for now, we just write the raw bytes
            # PIL can read it. If mime is jpeg, we still save as png or just write directly.
            # We save it directly, PIL can open it regardless of extension.
            with open(cache_path, "wb") as f:
                f.write(cover_data)
            logger.info("Extracted cover art to %s", cache_path)
            return cache_path

    except Exception as e:
        logger.warning("Failed to extract cover art from %s: %s", filepath, e)

    return None

def clean_temp_dir() -> None:
    """Cleans up all cached cover art in the temp directory."""
    try:
        for file in TEMP_DIR.iterdir():
            if file.is_file():
                file.unlink()
        logger.info("Temp directory cleaned.")
    except Exception as e:
        logger.error("Failed to clean temp directory: %s", e)

def sanitize_mp3(filepath: Path) -> Optional[Path]:
    """Strips large ID3 headers/junk data before MPEG sync word so libmpg123 can play it.

    Saves a cleaned audio stream file in TEMP_DIR and returns its path.
    """
    if not filepath.exists():
        return None

    try:
        with open(filepath, "rb") as f:
            data = f.read()

        start_offset = 0

        # Check for ID3v2 header
        if data.startswith(b"ID3") and len(data) > 10:
            # Synchsafe size calculation for ID3v2
            id3_size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
            start_offset = id3_size + 10
            # Check for footer flag
            if data[5] & 0x10:
                start_offset += 10

        # Search for first MPEG frame sync word (0xFF followed by 0xE0-0xFF)
        sync_found = -1
        search_limit = min(len(data), start_offset + 500000) # Search within first 500KB after ID3
        for i in range(start_offset, search_limit - 1):
            if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
                sync_found = i
                break

        if sync_found != -1:
            clean_path = TEMP_DIR / f"clean_{hashlib.md5(str(filepath).encode('utf-8')).hexdigest()}.mp3"
            with open(clean_path, "wb") as f:
                f.write(data[sync_found:])
            logger.info("Sanitized MP3 stream saved to %s (skipped %d bytes of ID3/junk)", clean_path, sync_found)
            return clean_path

    except Exception as e:
        logger.warning("Failed to sanitize MP3 file %s: %s", filepath, e)

    return None

import subprocess
import shutil

def transcode_to_ogg(filepath: Path) -> Optional[Path]:
    """Transcodes misnamed or non-standard audio containers (e.g. WebM, M4A, Opus) to OGG using ffmpeg.

    Returns the path to the cached OGG file in TEMP_DIR.
    """
    if not filepath.exists():
        return None

    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg is not installed on system. Cannot transcode %s", filepath)
        return None

    path_hash = hashlib.md5(str(filepath.absolute()).encode("utf-8")).hexdigest()
    ogg_cache = TEMP_DIR / f"transcoded_{path_hash}.ogg"

    if ogg_cache.exists() and ogg_cache.stat().st_size > 0:
        return ogg_cache

    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(filepath),
            "-vn", "-c:a", "libvorbis", "-q:a", "5",
            str(ogg_cache)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode == 0 and ogg_cache.exists():
            logger.info("Successfully transcoded %s to OGG: %s", filepath, ogg_cache)
            return ogg_cache
        else:
            logger.warning("ffmpeg transcoding returned code %d for %s", res.returncode, filepath)
    except Exception as e:
        logger.error("Failed to transcode audio file %s: %s", filepath, e)

    return None
