"""Isolated local English ASR for the exact reference excerpt shown in the UI."""
import argparse
from pathlib import Path


def transcribe(source):
    import mlx_whisper
    result = mlx_whisper.transcribe(str(source), path_or_hf_repo="mlx-community/whisper-small.en-mlx",
                                   language="en", temperature=0, condition_on_previous_text=False)
    text = result.get("text", "").strip()
    if not text:
        raise ValueError("No speech detected. Choose a recording that starts with clear English speech.")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(transcribe(args.source), encoding="utf-8")
