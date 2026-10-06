"""Native controls only; shared server validation and UI field descriptions."""
import math


def number(key, label, default, low, high, step=0.05):
    return dict(key=key, label=label, default=default, min=low, max=high, step=step)


SPEED = number("speed", "Speaking speed", 1.0, 0.5, 2.0)
TEMP = number("temperature", "Sampling temperature (variation)", 0.7, 0.1, 1.5)
TOP_P = number("top_p", "Top-p sampling", 0.8, 0.1, 1.0)
TOP_K = number("top_k", "Top-k sampling", 30, 1, 100, 1)
OPTIONS = {
    "kokoro": [SPEED],
    "piper": [number("length_scale", "Duration scale (higher = slower)", 1.0, 0.5, 2), number("noise_scale", "Voice variation", 0.667, 0, 1), number("noise_w_scale", "Phoneme timing variation", 0.8, 0, 1)],
    "chatterbox": [number("exaggeration", "Expressiveness / exaggeration", 0.45, 0, 1), number("cfg_weight", "Guidance weight", 0.5, 0, 1), dict(TEMP, default=0.8), number("repetition_penalty", "Repetition penalty", 1.2, 1, 2)],
    "fish": [SPEED, dict(TEMP, default=0.7), dict(TOP_P, default=0.7), TOP_K],
    "orpheus": [dict(TEMP, default=0.6), TOP_P, number("repetition_penalty", "Repetition penalty", 1.3, 1, 2)],
    "csm": [dict(TEMP, default=0.9), dict(TOP_K, default=50)],
    "chattts": [dict(TEMP, default=0.3), dict(TOP_P, default=0.7), dict(TOP_K, default=20), number("seed", "Speaker seed", 42, 0, 2147483647, 1)],
    "f5": [SPEED, number("cfg_strength", "Guidance strength", 2.0, 0, 5), number("nfe_step", "Diffusion steps", 32, 8, 64, 1), number("sway_sampling_coef", "Sway sampling coefficient", -1.0, -1, 0)],
    "gpt_sovits": [number("speed_factor", "Speaking speed", 1.0, 0.5, 2), dict(TEMP, default=1.0), dict(TOP_P, default=1.0), dict(TOP_K, default=15)],
    # The official CosyVoice HTTP API does not accept speed/sampling controls.
    "cosyvoice": [],
}


def validate_options(model, values):
    schema = {item["key"]: item for item in OPTIONS[model]}
    if set(values) - set(schema):
        raise ValueError("Unsupported advanced setting for this model.")
    result = {}
    for key, field in schema.items():
        value = values.get(key, field["default"])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field['label']} must be a finite number.")
        if not field["min"] <= value <= field["max"] or (field["step"] == 1 and value != int(value)):
            raise ValueError(f"{field['label']} must be between {field['min']} and {field['max']}" + (" (integer)." if field["step"] == 1 else "."))
        result[key] = int(value) if field["step"] == 1 else value
    return result
