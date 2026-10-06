"""Disposable local inference process; receives a frozen approved manuscript."""
import argparse
import hashlib
import urllib.request
import wave
import json
from pathlib import Path

from .narration import speech_plan
from .voices import CHATTERBOX_REPO, CHATTERBOX_REVISION, PIPER, MLX_REPOS, validate_voice, validate_reference
from .tts_options import validate_options


def progress(message):
    print("BOOK_PROGRESS " + message, flush=True)


def piper_download(narrator, cache):
    entry = PIPER["voices"][narrator]
    cache.mkdir(parents=True, exist_ok=True)
    for remote, info in entry["files"].items():
        name = Path(remote).name
        target = cache / (f"{narrator}-MODEL_CARD" if name == "MODEL_CARD" else name)
        def valid(path):
            if not path.is_file() or path.stat().st_size != info["size_bytes"]:
                return False
            with path.open("rb") as f:
                return hashlib.file_digest(f, "md5").hexdigest() == info["md5_digest"]
        if valid(target):
            continue
        progress(f"Downloading Piper {narrator}: {name}")
        temporary = target.with_suffix(target.suffix + ".download")
        try:
            url = f"https://huggingface.co/rhasspy/piper-voices/resolve/{PIPER['revision']}/{remote}"
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            if not valid(temporary):
                raise ValueError(f"Piper download failed integrity check: {name}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return cache / f"{narrator}.onnx"


def generate(model, narrator, text, output, cache, reference=None, advanced=None, reference_text=""):
    validate_voice(model, narrator)
    options = validate_options(model, advanced or {})
    validate_reference(model, reference, reference_text)
    if not text.strip():
        raise ValueError("Approved manuscript is empty.")
    parts = speech_plan(text, 700 if model in {"kokoro", "piper"} else 250)
    progress(f"Narrating passage 0 of {len(parts)} — loading model")
    if model == "kokoro":
        from kokoro import KPipeline
        import soundfile as sf
        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        with sf.SoundFile(output, "w", samplerate=24000, channels=1, subtype="PCM_16") as writer:
            for i, (part, pause) in enumerate(parts, 1):
                frames = 0
                for _, _, audio in pipeline(part, voice=narrator, speed=options["speed"]):
                    if audio is None:
                        raise ValueError("Kokoro returned no audio for a segment.")
                    writer.write(audio)
                    frames += len(audio)
                if not frames:
                    raise ValueError("Kokoro returned no speech for a passage.")
                if pause:
                    writer.write([0.0] * round(24000 * pause))
                progress(f"Narrating passage {i} of {len(parts)}")
        return
    if model == "piper":
        from piper import PiperVoice, SynthesisConfig
        voice = PiperVoice.load(str(piper_download(narrator, cache / "piper")))
        with wave.open(str(output), "wb") as wav:
            for i, (part, pause) in enumerate(parts, 1):
                before = wav.getnframes()
                voice.synthesize_wav(part, wav, syn_config=SynthesisConfig(**options), set_wav_format=i == 1)
                if wav.getnframes() == before:
                    raise ValueError("Piper returned no speech for a passage.")
                if pause:
                    wav.writeframes(b"\x00" * round(wav.getframerate() * pause) * wav.getsampwidth() * wav.getnchannels())
                progress(f"Narrating passage {i} of {len(parts)}")
        return
    if model in {"chattts", "f5", "cosyvoice", "gpt_sovits"}:
        from .speech_adapters import generate_external
        generate_external(model, parts, output, reference, reference_text, options, progress)
        return
    from huggingface_hub import snapshot_download
    from mlx_audio.tts.utils import load_model
    import numpy as np
    import soundfile as sf
    progress(f"Narrating passage 0 of {len(parts)} — loading {model}; first use may download weights")
    path = snapshot_download(CHATTERBOX_REPO, revision=CHATTERBOX_REVISION,
                             allow_patterns=["*.json", "*.safetensors"]) if model == "chatterbox" else MLX_REPOS[model]
    if model == "fish":
        from .fish_compat import load_fish_model
        engine = load_fish_model(path)
    else:
        engine = load_model(path)
    kwargs = dict(options)
    if model == "chatterbox":
        kwargs.update(ref_audio=str(reference) if reference else None, max_tokens=3072, lang_code="en")
    elif model == "fish":
        from mlx_audio.utils import load_audio
        kwargs.update(ref_audio=load_audio(str(reference), sample_rate=engine.sample_rate), ref_text=reference_text, max_tokens=3072)
    elif model == "orpheus":
        kwargs.update(voice=narrator, max_tokens=3072)
    elif model == "csm":
        from mlx_audio.lm.sample_utils import make_sampler
        kwargs = dict(sampler=make_sampler(temp=options["temperature"], top_k=options["top_k"]), max_audio_length_ms=90000,
                      ref_audio=str(reference) if reference else None, ref_text=reference_text or None)
    with sf.SoundFile(output, "w", samplerate=engine.sample_rate, channels=1, subtype="PCM_16") as writer:
        for i, (part, pause) in enumerate(parts, 1):
            frames = 0
            for result in engine.generate(text=part.strip(), verbose=False, **kwargs):
                if (model != "csm" and result.token_count >= 3072) or (model == "csm" and len(result.audio) >= engine.sample_rate * 89.9):
                    raise ValueError(f"{model} reached its output limit; refusing potentially incomplete audio.")
                audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
                if not audio.size or not np.isfinite(audio).all():
                    raise ValueError(f"{model} returned invalid audio.")
                writer.write(audio)
                frames += len(audio)
            if not frames:
                raise ValueError(f"{model} returned no speech for a passage.")
            if pause:
                writer.write(np.zeros(round(engine.sample_rate * pause), dtype=np.float32))
            progress(f"Narrating passage {i} of {len(parts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--advanced", default="{}")
    parser.add_argument("--reference-text", default="")
    for name in ["model", "narrator", "text", "output", "cache"]:
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    generate(args.model, args.narrator, Path(args.text).read_text(encoding="utf-8"),
             Path(args.output), Path(args.cache), args.reference, json.loads(args.advanced), args.reference_text)
