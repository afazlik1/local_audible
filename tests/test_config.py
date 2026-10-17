from backend.config import Settings


def test_model_default_is_a_non_personal_placeholder(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert Settings(_env_file=None).ollama_model == "your-vision-model"


def test_explicit_model_configuration_is_preserved(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "configured-vision-model")
    assert Settings(_env_file=None).ollama_model == "configured-vision-model"
