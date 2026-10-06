# Speech engines and reference voices

Inference is local to the configured services. First-use downloads contact model hosts. No engine is silently substituted after failure. Availability checks detect runtime presence/connectivity, not successful loading of every checkpoint.

## Kokoro

Install the `kokoro` extra in the main environment as shown in the README. There are 20 US-English presets and a speed control. This is also the CLI WAV engine.

## Piper and MLX engines

On Apple Silicon:

```sh
python3.12 -m venv .venv-speech
.venv-speech/bin/python -m pip install -r requirements-speech.txt
```

This isolates Piper, MLX Audio and MLX Whisper from the API/Kokoro environment. MLX Audio is pinned to a compatibility-tested Git revision. Fish uses strict speech/codec parameter validation; do not disable checks or casually upgrade its runtime.

- **Piper:** 23 US-English voice/quality combinations, not 23 unique people. Weights/configuration/model cards download with integrity checks. Voice licenses vary.
- **Chatterbox:** MLX FP16, default or optional reference. Defaults: exaggeration 0.45, guidance 0.5, temperature 0.8, repetition penalty 1.2.
- **Fish S2 Pro:** MLX 8-bit; this integration requires a reference and matching transcript. Large first-use download.
- **Orpheus:** MLX 4-bit, Tara. Sampling controls are not guaranteed emotion controls.
- **CSM-1B:** MLX 8-bit, default or reference. Default assets may require authorized Hugging Face access. Accent is not guaranteed.

Piper itself is not MLX-based. The combined requirements target Apple Silicon; other platforms need a compatible Piper/soundfile-only setup, which is not comprehensively tested here.

## Optional adapters

These integrations are not bundled turnkey installations. Supply their upstream prerequisites and checkpoints separately:

```sh
python3.12 -m venv .venv-chattts
.venv-chattts/bin/python -m pip install ChatTTS soundfile
python3.12 -m venv .venv-f5
.venv-f5/bin/python -m pip install f5-tts soundfile
```

Follow [ChatTTS](https://github.com/2noise/ChatTTS) and [F5-TTS](https://github.com/SWivid/F5-TTS) platform instructions. ChatTTS seeds produce synthetic speakers, not verified US narrators. Automatic reference transcription also needs MLX Whisper in .venv-speech.

For [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS), run the official API v2 at `127.0.0.1:9880` with compatible weights and access to local reference snapshots. For [CosyVoice](https://github.com/FunAudioLLM/CosyVoice), use its FastAPI zero-shot endpoint with **CosyVoice2-0.5B / 24 kHz** at `127.0.0.1:50000`. Restrict both to loopback; upstream scripts may bind all interfaces.

Export only the service switches you need before starting the API:

```sh
export BOOK_READER_GPT_SOVITS=1
export BOOK_READER_COSYVOICE=1
```

These legacy names remain for compatibility and are process variables, not .env settings. A .venv-speech worker is also required. The app does not manage external service weights or start/stop servers. CosyVoice's integrated API exposes no advanced sampling controls.

## References and previews

Create `data/sample_voice/` for permitted English recordings (MP3, WAV, FLAC, M4A, OGG, up to 50 MB). Select one in the dropdown; unsupported engines do not show this control. A reference disables preset voice selection.

- Fish uses the first **30 seconds**; Chatterbox uses up to **30 seconds** without requiring a transcript.
- Other transcript-based integrations prepare the first **10 seconds**.
- Transcript preparation rejects recordings under three seconds; valid short recordings use their available duration.
- MLX Whisper transcribes the exact excerpt locally. Listen and correct it before synthesis; this is not preview text.
- Originals are unchanged. Cached excerpts/transcripts and per-generation snapshots preserve reproducibility.

The optional comparison preview is always **ten seconds**, independently of reference length. Short audio is padded; long audio is trimmed. Generation can take much longer than ten seconds. Settings changes invalidate the previous preview selection.

## Output and troubleshooting

Web output is validated 128 kbps MP3 with optional ID3 front-cover artwork and model/narrator/revision filenames. CLI output remains WAV. Settings are recorded beside approved text.

Blank lines add pauses: one adds 450 ms, two 775 ms, three or more 1.1 seconds, beyond the model's own pauses. Single wrapped lines add no explicit gap.

- Setup required: check the named environment and upstream dependencies.
- Slow first generation: allow for weight download/load; RAM/disk needs vary.
- Reference transcript missing: prepare a recording and check its actual words.
- Fish checkpoint error: use pinned requirements, not relaxed weight validation.
- MP3 failure: confirm ffmpeg and ffprobe are on the API PATH.
- Interrupted narration: retry; audio synthesis restarts rather than resumes.

See [third-party notices](../THIRD_PARTY.md) before distributing models or using them commercially.
