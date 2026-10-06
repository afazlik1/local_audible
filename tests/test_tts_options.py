import pytest
from backend.tts_options import OPTIONS, validate_options
from backend.voices import MODELS, validate_reference


def test_catalog_defaults_and_validation():
    assert set(OPTIONS) == set(MODELS)
    for model in MODELS:
        assert validate_options(model, {}) == {f["key"]: f["default"] for f in OPTIONS[model]}
    assert validate_options("chatterbox", {"exaggeration": 0.5})["exaggeration"] == 0.5


@pytest.mark.parametrize("values", [{"exaggeration": 2}, {"exaggeration": True}, {"exaggeration": float("nan")}, {"speed": 1}, {"exaggeration": "0.5"}])
def test_invalid_options(values):
    with pytest.raises(ValueError):
        validate_options("chatterbox", values)


def test_reference_requirements():
    for model in ("fish", "f5", "gpt_sovits", "cosyvoice"):
        with pytest.raises(ValueError):
            validate_reference(model, None, "")
        with pytest.raises(ValueError):
            validate_reference(model, "sample.wav", "")
        validate_reference(model, "sample.wav", "Sample speech.")
    validate_reference("csm", None, "")
    validate_reference("chatterbox", "sample.wav", "")
    with pytest.raises(ValueError):
        validate_options("csm", {"top_k": 2.5})
