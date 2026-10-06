import sys
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.tts import KokoroTts, TtsError


def test_failed_synthesis_preserves_existing_audio(tmp_path, monkeypatch):
    output = tmp_path / "book.wav"
    output.write_bytes(b"existing audiobook")

    class Pipeline:
        def __init__(self, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            yield "text", "phonemes", [0.0, 0.1]
            raise RuntimeError("speech interrupted")

    class Writer:
        def __init__(self, path, **kwargs):
            self.path = path

        def __enter__(self):
            self.path.write_bytes(b"partial")
            return self

        def write(self, audio):
            pass

        def __exit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(SoundFile=Writer))
    with pytest.raises(TtsError, match="speech interrupted"):
        KokoroTts(Settings()).generate("Book text", output)
    assert output.read_bytes() == b"existing audiobook"
    assert not output.with_suffix(".partial.wav").exists()
