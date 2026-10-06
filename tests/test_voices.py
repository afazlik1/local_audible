import sys
import wave
from types import SimpleNamespace

import pytest

from backend.voices import MODELS, validate_voice
from backend import speech_worker


def test_only_allowed_voices():
    assert len(MODELS["kokoro"]["voices"]) == 20
    assert all(v["id"].startswith(("af_", "am_")) for v in MODELS["kokoro"]["voices"])
    assert all(v["id"].startswith("en_US-") for v in MODELS["piper"]["voices"])
    assert [v["id"] for v in MODELS["chatterbox"]["voices"]] == ["default"]
    for model, voice in [("kokoro", "bf_emma"), ("piper", "en_GB-alan-medium"), ("chatterbox", "reference"), ("../bad", "default")]:
        with pytest.raises(ValueError):
            validate_voice(model, voice)


def test_piper_multi_passage_wav_header_only_once(tmp_path, monkeypatch, capsys):
    calls = []
    class Voice:
        @staticmethod
        def load(path):
            return Voice()
        def synthesize_wav(self, text, wav, set_wav_format=True, syn_config=None):
            assert syn_config.length_scale == 1.0
            calls.append(set_wav_format)
            if set_wav_format:
                wav.setparams((1, 2, 22050, 0, "NONE", "none"))
            wav.writeframes(b"\x00\x00" * 100)
    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=Voice, SynthesisConfig=SimpleNamespace))
    monkeypatch.setattr(speech_worker, "piper_download", lambda *args: tmp_path / "voice.onnx")
    output = tmp_path / "audio.wav"
    speech_worker.generate("piper", "en_US-lessac-medium", "A narrative sentence. " * 100, output, tmp_path)
    assert calls[0] is True and len(calls) > 1 and not any(calls[1:])
    with wave.open(str(output)) as wav:
        assert wav.getnframes() == len(calls) * 100
    assert f"Narrating passage {len(calls)} of {len(calls)}" in capsys.readouterr().out
