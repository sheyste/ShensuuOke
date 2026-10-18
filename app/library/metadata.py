"""Metadata extraction. Never raises: problems are reported in the 'error' field."""
from __future__ import annotations
import os

MIDI_EXT = {".mid", ".midi", ".kar"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
SUPPORTED_EXT = MIDI_EXT | AUDIO_EXT | VIDEO_EXT


def kind_of(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in MIDI_EXT: return "midi"
    if ext in AUDIO_EXT: return "audio"
    if ext in VIDEO_EXT: return "video"
    return None


def _from_filename(path):
    stem = os.path.splitext(os.path.basename(path))[0].replace("_", " ").strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return title.strip(), artist.strip()
    return stem, ""


def index_metadata(path: str) -> dict:
    """Return metadata without opening/parsing the file contents.

    This is used while adding a folder so a large MIDI collection can be
    indexed quickly.  Full metadata is filled in when the song is played.
    """
    title, artist = _from_filename(path)
    ext = os.path.splitext(path)[1].lower()
    return {"filename": os.path.basename(path), "title": title, "artist": artist,
            "format": ext.lstrip(".").upper(), "duration": None, "has_lyrics": 0,
            "error": None}


def read_metadata(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    title, artist = _from_filename(path)
    info = {"filename": os.path.basename(path), "title": title, "artist": artist,
            "format": ext.lstrip(".").upper(), "duration": None, "has_lyrics": 0, "error": None}
    kind = kind_of(path)
    try:
        if kind == "midi":
            from app.audio.midi_engine import load_midi
            song = load_midi(path)
            info["duration"] = song.duration
            info["has_lyrics"] = 1 if song.has_lyrics else 0
            if song.title: info["title"] = song.title
            if song.artist: info["artist"] = song.artist
        else:
            try:
                import mutagen
            except ImportError:
                return info          # degraded: filename-based metadata only
            audio = mutagen.File(path, easy=True)
            if audio is None:
                if kind == "audio":
                    info["error"] = "Unrecognized or corrupted audio file."
                return info
            if getattr(audio, "info", None) is not None:
                info["duration"] = getattr(audio.info, "length", None)
            tags = audio.tags or {}
            t, a = tags.get("title"), tags.get("artist")
            if t and t[0].strip(): info["title"] = t[0].strip()
            if a and a[0].strip(): info["artist"] = a[0].strip()
    except Exception as e:
        info["error"] = f"Cannot read file: {e}"
    return info
