import io
import json
import sys
from types import SimpleNamespace

import numpy as np
import soundfile as sf
import pytest

from backend import speech_adapters as adapters
from backend.tts_options import validate_options


@pytest.mark.parametrize("model", ["chattts", "f5", "gpt_sovits", "cosyvoice"])
def test_adapters_forward_settings_and_keep_paragraph_pauses(model, monkeypatch, tmp_path):
    calls = []
    class Chat:
        InferCodeParams = SimpleNamespace
        def load(self, **kwargs):
            return True
        def sample_random_speaker(self):
            return "speaker"
        def infer(self, text, **kwargs):
            assert kwargs["skip_refine_text"] and kwargs["lang"] == "en"
            assert kwargs["params_infer_code"].temperature == 0.3
            calls.append(text)
            return [np.ones(2400) * .1]
    class F5:
        def __init__(self, **kwargs):
            pass
        def infer(self, **kwargs):
            assert kwargs["speed"] == 1 and kwargs["ref_text"] == "Sample."
            calls.append(kwargs)
            return np.ones(2400) * .1, 24000, None
    def request(port, route, body, content_type):
        calls.append(body)
        if model == "cosyvoice":
            assert port == 50000 and b"Sample." in body and b"prompt_wav" in body
            return (np.ones(2400, dtype="<i2") * 3000).tobytes()
        value = json.loads(body)
        assert value["text_lang"] == "en" and value["speed_factor"] == 1
        stream = io.BytesIO()
        sf.write(stream, np.ones(2400) * .1, 24000, format="WAV")
        return stream.getvalue()
    monkeypatch.setitem(sys.modules, "ChatTTS", SimpleNamespace(Chat=Chat))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(manual_seed=lambda seed: None))
    monkeypatch.setitem(sys.modules, "f5_tts.api", SimpleNamespace(F5TTS=F5))
    monkeypatch.setattr(adapters, "local_request", request)
    reference = tmp_path / "ref.wav"
    reference.write_bytes(b"sample")
    target = tmp_path / "speech.wav"
    messages = []
    adapters.generate_external(model, [("First.", .45), ("Second.", 0)], target, reference, "Sample.", validate_options(model, {}), messages.append)
    audio, rate = sf.read(target)
    assert len(calls) == 2 and rate == 24000
    assert len(audio) == 4800 + 10800
    assert messages[-1] == "Narrating passage 2 of 2"
