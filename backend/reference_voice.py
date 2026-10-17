"""Allowlisted local sample voices; no caller-supplied filesystem paths."""
import subprocess
from pathlib import Path

EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}


def samples(data_dir):
    folder = data_dir / "sample_voice"
    if not folder.is_dir():
        return []
    return [{"id": p.name, "label": p.name} for p in sorted(folder.iterdir())
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS]


def resolve_sample(data_dir, name):
    if name not in {s["id"] for s in samples(data_dir)}:
        raise ValueError("Choose a sample from data/sample_voice, or use the default voice.")
    path = data_dir / "sample_voice" / name
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Sample voice files must be 50 MB or smaller.")
    return path


def reference_seconds(model):
    return 30 if model == "fish" else 10


def snapshot_sample(source, target, exact=False, seconds=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                        "-t", str(seconds if seconds is not None else (10 if exact else 30)), "-vn", "-ac", "1", "-ar", "24000", str(target)],
                       check=True, capture_output=True, timeout=60)
        import wave
        with wave.open(str(target)) as audio:
            if audio.getnframes() < audio.getframerate() * (3 if exact else 1):
                raise ValueError(f"Use a sample containing at least {3 if exact else 1} seconds of speech.")
    except Exception:
        target.unlink(missing_ok=True)
        raise
