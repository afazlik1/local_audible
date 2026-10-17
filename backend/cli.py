"""Two-stage local book transcription and narration, without a web server."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from .assets import SUPPORTED_EXTENSIONS, image_payload, natural_key
from .config import get_settings
from .ocr import OcrError, OllamaOcr
from .tts import KokoroTts, TtsError


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


async def transcribe(images: Path, output: Path, model: str | None = None,
                     force: bool = False, timeout: float | None = None) -> Path:
    if not images.is_dir():
        raise ValueError(f"Image folder does not exist: {images}")
    pages = sorted((p for p in images.iterdir() if p.is_file() and
                    p.suffix.lower() in SUPPORTED_EXTENSIONS), key=natural_key)
    if not pages:
        raise ValueError(f"No supported page images found in {images}")
    settings = get_settings().model_copy()
    if model:
        settings.ollama_model = model
    if timeout is not None:
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")
        settings.ocr_timeout = timeout
    ocr = OllamaOcr(settings)
    health = await ocr.health()
    if not health.get("available"):
        raise OcrError(f"{health.get('message')}. Start Ollama with: ollama serve")
    if not health.get("model_found"):
        raise OcrError(f"Model {settings.ollama_model!r} is not installed. Available: {health.get('models')}")
    cache_dir = output.parent / (output.stem + "-pages")
    texts = []
    for index, page in enumerate(pages, 1):
        fingerprint = hashlib.sha256(page.read_bytes()).hexdigest()
        cache = cache_dir / (page.name + ".json")
        saved = {}
        if cache.exists() and not force:
            try:
                saved = json.loads(cache.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        valid = (isinstance(saved, dict) and saved.get("sha256") == fingerprint
                 and saved.get("model") == settings.ollama_model and saved.get("version") == 2
                 and isinstance(saved.get("text"), str) and saved["text"].strip())
        print(f"[{index}/{len(pages)}] {page.name}: {'cached' if valid else 'transcribing…'}", flush=True)
        if valid:
            text = saved["text"]
        else:
            try:
                encoded, mime = image_payload(page)
                text = await ocr.extract(encoded, mime)
            except (OcrError, OSError) as error:
                raise OcrError(f"{page.name}: {error}. Completed pages are cached; rerun to resume.") from error
            atomic_write(cache, json.dumps({"version": 2, "model": settings.ollama_model,
                                           "sha256": fingerprint, "text": text}, ensure_ascii=False, indent=2))
        if text.strip() != "[NO NARRATIVE]":
            texts.append(text.strip())
    if not texts:
        raise OcrError("No narrative text found; the previous manuscript was preserved.")
    atomic_write(output, "\n\n".join(texts) + "\n")
    print(f"Saved {len(pages)} pages to {output}", flush=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    text_parser = commands.add_parser("text", help="Transcribe ordered page images with local Ollama")
    text_parser.add_argument("--images", type=Path, default=Path("data/images"))
    text_parser.add_argument("--output", type=Path, default=Path("data/text/book.txt"))
    text_parser.add_argument("--model", help="Exact installed Ollama model tag")
    text_parser.add_argument("--timeout", type=float, help="Seconds allowed per page (default: 1800)")
    text_parser.add_argument("--force", action="store_true", help="Transcribe again, ignoring cached pages")
    audio_parser = commands.add_parser("audio", help="Narrate a UTF-8 text file with local Kokoro")
    audio_parser.add_argument("--text", type=Path, default=Path("data/text/book.txt"))
    audio_parser.add_argument("--output", type=Path, default=Path("data/audio/book.wav"))
    audio_parser.add_argument("--voice", help="Kokoro voice, e.g. af_heart or am_michael")
    audio_parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    try:
        if args.command == "text":
            asyncio.run(transcribe(args.images, args.output, args.model, args.force, args.timeout))
        else:
            if args.output.suffix.lower() != ".wav":
                raise ValueError("Audio output must use the .wav extension.")
            if args.speed <= 0:
                raise ValueError("Speed must be greater than zero.")
            settings = get_settings().model_copy()
            if args.voice:
                settings.kokoro_voice = args.voice
            text = args.text.read_text(encoding="utf-8")
            print(f"Narrating {args.text} with {settings.kokoro_voice}…", flush=True)
            KokoroTts(settings).generate(text, args.output, speed=args.speed,
                                       progress=lambda n: print(f"  Audio segment {n} saved", flush=True))
            print(f"Saved audiobook to {args.output}", flush=True)
    except (OcrError, TtsError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Completed OCR pages remain cached.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
