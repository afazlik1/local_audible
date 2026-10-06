import json
import shutil
import subprocess
import wave

import pytest
from PIL import Image

from backend.mp3 import export_mp3


@pytest.mark.parametrize("with_cover", [False, True])
def test_real_mp3_export_and_embedded_cover(tmp_path, with_cover):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg not installed")
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "none"))
        wav.writeframes(b"\x00\x00" * 24000)
    cover = tmp_path / "cover.jpg" if with_cover else None
    if cover:
        Image.new("RGB", (64, 64), "blue").save(cover)
    target = tmp_path / "book.mp3"
    export_mp3(source, target, cover)
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target)], capture_output=True, check=True)
    streams = json.loads(result.stdout)["streams"]
    assert any(s["codec_name"] == "mp3" for s in streams)
    assert any(s.get("disposition", {}).get("attached_pic") for s in streams) == with_cover
    assert not target.with_suffix(".partial.mp3").exists()


@pytest.mark.parametrize("seconds", [2, 15])
def test_preview_trims_or_pads_to_ten_seconds(tmp_path, seconds):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "none"))
        wav.writeframes(b"\x00\x00" * 24000 * seconds)
    target = tmp_path / "preview.mp3"
    export_mp3(source, target, duration=10)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    assert len(raw) == 24000 * 2 * 10
