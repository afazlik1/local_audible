"""Run inference outside the web server, validating output before publishing it."""
import asyncio
import os
import wave
import json
import re

from .voices import ROOT, available, runtime, validate_voice


async def generate_speech(model, narrator, source, output, cache, update, reference=None, advanced=None, reference_text=""):
    validate_voice(model, narrator)
    if not available(model):
        raise RuntimeError("Selected speech runtime is not installed. See README.md.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial.wav")
    proc = None
    try:
        with output.with_suffix(".log").open("w", encoding="utf-8") as log:
            proc = await asyncio.create_subprocess_exec(
                str(runtime(model)), "-m", "backend.speech_worker", "--model", model,
                "--narrator", narrator, "--text", str(source.resolve()), "--output", str(temporary.resolve()),
                "--cache", str(cache.resolve()),
                "--advanced", json.dumps(advanced or {}), "--reference-text", reference_text,
                *(["--reference", str(reference.resolve())] if reference else []), cwd=ROOT,
                env=dict(os.environ, PYTHONUNBUFFERED="1", HF_HUB_DISABLE_XET="1", TOKENIZERS_PARALLELISM="false"),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            tail = []
            cause = ""
            async with asyncio.timeout(14400):
                async for raw in proc.stdout:
                    line = raw.decode(errors="replace").strip()
                    log.write(line + "\n")
                    log.flush()
                    tail = (tail + [line])[-8:]
                    if re.match(r"^[\w.]+(?:Error|Exception):", line):
                        cause = line[:500]
                    if line.startswith("BOOK_PROGRESS "):
                        update(line.removeprefix("BOOK_PROGRESS "))
                if await proc.wait():
                    raise RuntimeError("Speech generation failed: " + (cause + "\n" if cause else "") + "\n".join(tail)[-1000:])
        with wave.open(str(temporary), "rb") as audio:
            if audio.getnframes() <= 0:
                raise RuntimeError("The selected model returned an empty WAV.")
        temporary.replace(output)
    finally:
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        temporary.unlink(missing_ok=True)
