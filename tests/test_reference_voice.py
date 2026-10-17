import pytest
import wave
import shutil
from backend.reference_voice import snapshot_sample, reference_seconds


def test_only_fish_reference_duration_changes():
    assert reference_seconds("fish") == 30
    assert reference_seconds("f5") == 10
    assert reference_seconds("gpt_sovits") == 10
from backend.reference_voice import samples, resolve_sample


def test_reference_allowlist(tmp_path):
    folder = tmp_path / "sample_voice"
    folder.mkdir()
    (folder / "Voice.mp3").write_bytes(b"sample")
    (folder / "notes.txt").write_text("not audio")
    (folder / "linked.mp3").symlink_to(folder / "Voice.mp3")
    assert samples(tmp_path) == [{"id": "Voice.mp3", "label": "Voice.mp3"}]
    assert resolve_sample(tmp_path, "Voice.mp3") == folder / "Voice.mp3"
    for name in ["../Voice.mp3", "linked.mp3", "/etc/passwd", "missing.mp3"]:
        with pytest.raises(ValueError):
            resolve_sample(tmp_path, name)


@pytest.mark.parametrize("seconds", [10, 30])
def test_long_reference_is_cropped_without_changing_source(tmp_path, seconds):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg missing")
    source, target = tmp_path / "long.wav", tmp_path / "excerpt.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, 24000, 0, "NONE", "none"))
        audio.writeframes(b"\x00\x00" * 24000 * 40)
    original = source.read_bytes()
    snapshot_sample(source, target, exact=True, seconds=seconds)
    assert source.read_bytes() == original
    with wave.open(str(target)) as audio:
        assert audio.getnframes() / audio.getframerate() == seconds
