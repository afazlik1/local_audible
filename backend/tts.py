from pathlib import Path
from collections.abc import Callable
import re

from .config import Settings


class TtsError(RuntimeError):
    pass


class KokoroTts:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, text: str, output_path: Path, speed: float = 1.0,
                 progress: Callable[[int], None] | None = None) -> None:
        if not text.strip():
            raise TtsError("The input text file is empty.")
        try:
            from kokoro import KPipeline
            import soundfile as sf
        except ImportError as error:
            raise TtsError(
                "Kokoro is not installed. Install the optional dependency with "
                "python -m pip install -e '.[kokoro]'."
            ) from error

        temporary = output_path.with_suffix(".partial.wav")
        try:
            pipeline = KPipeline(lang_code=self.settings.kokoro_lang_code, repo_id="hexgrad/Kokoro-82M")
            # OCR often preserves physical line wraps. Keep paragraph breaks, but
            # don't make the narrator pause after every printed line.
            narration = "\n\n".join(" ".join(part.splitlines()) for part in re.split(r"\n\s*\n", text))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            frames = 0
            with sf.SoundFile(temporary, mode="w", samplerate=24000, channels=1, subtype="PCM_16") as writer:
                for index, (_, _, audio) in enumerate(pipeline(narration, voice=self.settings.kokoro_voice, speed=speed), 1):
                    if audio is None:
                        continue
                    writer.write(audio)
                    frames += len(audio)
                    if progress:
                        progress(index)
            if not frames:
                raise TtsError("Kokoro returned no audio for this text.")
            temporary.replace(output_path)
        except TtsError:
            raise
        except Exception as error:
            raise TtsError(f"Kokoro audio generation failed: {error}") from error
        finally:
            temporary.unlink(missing_ok=True)
