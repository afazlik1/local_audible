"""Fixed, server-validated narrator catalog. No arbitrary model paths or URLs."""
import importlib.util
import json
import platform
import sys
import os
from .tts_options import OPTIONS
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPER = json.loads(Path(__file__).with_name("piper_voices.json").read_text())
CHATTERBOX_REPO = "mlx-community/chatterbox-fp16"
CHATTERBOX_REVISION = "4923fcca09086356aeab5191a2348c5a17a23694"
KOKORO = [
    {"id": f"{prefix}_{name}", "label": f"{name.title()} · {gender} · US English"}
    for prefix, gender, names in [
        ("af", "female", "heart alloy aoede bella jessica kore nicole nova river sarah sky"),
        ("am", "male", "adam echo eric fenrir liam michael onyx puck santa"),
    ] for name in names.split()
]
MODELS = {
    "kokoro": {"label": "Kokoro · current engine", "voices": KOKORO,
               "note": "20 American-English presets. Selected voice files download on first use."},
    "piper": {"label": "Piper", "voices": [
        {"id": key, "label": f"{v['name'].replace('_', ' ').title()} · {v['quality']} · US English"}
        for key, v in PIPER["voices"].items()],
        "note": "US-English single-speaker models. First use downloads the selected voice (about 20–120 MB). Mixed-accent multi-speaker collections are excluded."},
    "chatterbox": {"label": "Chatterbox · MLX FP16", "supports_reference": True, "voices": [{"id": "default", "label": "Default English voice"}],
                   "note": "Default voice or an optional local sample voice. Exaggeration 0.45. Apple Silicon required. First use may download about 2.6 GB."},
}

MLX_REPOS = {"fish": "mlx-community/fishaudio-s2-pro-8bit-mlx", "orpheus": "mlx-community/orpheus-3b-0.1-ft-4bit", "csm": "mlx-community/csm-1b-8bit"}
for key, label, reference, required, transcript, note in [
    ("fish", "Fish Speech S2 Pro · MLX 8-bit", True, True, True, "English sample and its exact transcript required. Large model; first use may download weights. Check upstream model license before commercial use."),
    ("f5", "F5-TTS", True, True, True, "Requires .venv-f5. The first 10 seconds of your American-English recording are prepared and transcribed automatically. Check model license before commercial use."),
    ("gpt_sovits", "GPT-SoVITS · local service", True, True, True, "Requires the official local API on port 9880 with compatible pretrained weights. Sample and transcript required."),
    ("cosyvoice", "CosyVoice 2 · local service", True, True, True, "Requires the official CosyVoice 2 API on port 50000 (24 kHz). Sample and transcript required. This API does not expose advanced sampling controls."),
    ("orpheus", "Orpheus-TTS · MLX 4-bit", False, False, False, "Tara English narrator. First use may download weights. Sampling controls change variation, not a guaranteed emotion."),
    ("csm", "Sesame CSM-1B · MLX 8-bit", True, False, True, "Conversational English default or sample with transcript. Default prompts may require Hugging Face access to sesame/csm-1b. Accent follows the sample."),
    ("chattts", "ChatTTS", False, False, False, "Requires .venv-chattts. Seed-based synthetic English speaker; American accent is not guaranteed. Model is for non-commercial use."),
]:
    MODELS[key] = dict(label=label, supports_reference=reference, requires_reference=required,
                       requires_reference_text=transcript, note=note,
                       voices=[dict(id="tara" if key == "orpheus" else "default", label="Tara · English" if key == "orpheus" else "Sample voice" if required else "Default English voice")])


def validate_reference(model, reference, transcript):
    spec = MODELS[model]
    if reference and not spec.get("supports_reference"):
        raise ValueError("This model does not support sample voices.")
    if spec.get("requires_reference") and not reference:
        raise ValueError("This model requires a sample voice.")
    if reference and spec.get("requires_reference_text") and not transcript.strip():
        raise ValueError("Enter the exact spoken transcript of the sample voice.")
    if transcript.strip() and (not reference or not spec.get("requires_reference_text")):
        raise ValueError("A sample transcript is not supported for this selection.")


def validate_voice(model, narrator):
    if model not in MODELS or narrator not in {v["id"] for v in MODELS[model]["voices"]}:
        raise ValueError("Choose a supported model and its listed English narrator. British voices are excluded.")


def runtime(model):
    if model in {"chattts", "f5"}:
        return ROOT / f".venv-{model}/bin/python"
    return Path(sys.executable) if model == "kokoro" else ROOT / ".venv-speech/bin/python"


def available(model):
    if model in {"gpt_sovits", "cosyvoice"}:
        # Explicit administrator opt-in; never accept an arbitrary browser URL.
        if os.environ.get(f"BOOK_READER_{model.upper()}") != "1" or not runtime(model).is_file():
            return False
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 9880 if model == "gpt_sovits" else 50000), timeout=0.3):
                return True
        except OSError:
            return False
    if model in {"chattts", "f5"}:
        module = "ChatTTS" if model == "chattts" else "f5_tts"
        return runtime(model).is_file() and any((ROOT / f".venv-{model}/lib").glob(f"python*/site-packages/{module}/__init__.py"))
    if model == "kokoro":
        return importlib.util.find_spec("kokoro") is not None
    if not runtime(model).is_file():
        return False
    module = "piper" if model == "piper" else "mlx_audio"
    installed = any((ROOT / ".venv-speech/lib").glob(f"python*/site-packages/{module}/__init__.py"))
    return installed and (model == "piper" or (platform.system() == "Darwin" and platform.machine() == "arm64"))


def catalog():
    return [{"id": key, **value, "advanced": OPTIONS[key], "available": available(key)} for key, value in MODELS.items()]
