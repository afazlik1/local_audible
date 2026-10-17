"""Optional isolated Python engines and official loopback-only service adapters."""
import io
import json
import urllib.request
import uuid


def local_request(port, route, body, content_type):
    request = urllib.request.Request(f"http://127.0.0.1:{port}/{route}", data=body,
                                     headers={"Content-Type": content_type})
    # No proxy or redirects: manuscript/sample data must remain on this machine.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=1800) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024:
        raise ValueError("Local TTS response exceeded the per-passage limit.")
    return data


def cosy_request(text, reference, transcript):
    boundary = uuid.uuid4().hex
    pieces = []
    for key, value in [("tts_text", text), ("prompt_text", transcript)]:
        pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    pieces += [f'--{boundary}\r\nContent-Disposition: form-data; name="prompt_wav"; filename="sample.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(), reference.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
    return local_request(50000, "inference_zero_shot", b"".join(pieces), f"multipart/form-data; boundary={boundary}")


def generate_external(model, parts, output, reference, transcript, options, progress):
    import numpy as np
    import soundfile as sf
    if model == "chattts":
        import ChatTTS
        import torch
        engine = ChatTTS.Chat()
        if not engine.load(source="huggingface", compile=False):
            raise RuntimeError("ChatTTS model could not be loaded.")
        torch.manual_seed(options["seed"])
        speaker = engine.sample_random_speaker()
        params = ChatTTS.Chat.InferCodeParams(spk_emb=speaker, temperature=options["temperature"],
                                            top_P=options["top_p"], top_K=options["top_k"], manual_seed=options["seed"])
    elif model == "f5":
        from f5_tts.api import F5TTS
        engine = F5TTS(model="F5TTS_v1_Base")
    writer = None
    try:
        for i, (part, pause) in enumerate(parts, 1):
            if model == "chattts":
                audio = engine.infer([part], lang="en", skip_refine_text=True, params_infer_code=params)[0]
                rate = 24000
            elif model == "f5":
                audio, rate, _ = engine.infer(ref_file=str(reference), ref_text=transcript, gen_text=part, **options)
            elif model == "gpt_sovits":
                body = dict(text=part, text_lang="en", ref_audio_path=str(reference.resolve()), prompt_lang="en",
                            prompt_text=transcript, media_type="wav", streaming_mode=False, **options)
                data = local_request(9880, "tts", json.dumps(body).encode(), "application/json")
                audio, rate = sf.read(io.BytesIO(data), dtype="float32")
            else:
                data = cosy_request(part, reference, transcript)
                if len(data) % 2:
                    raise ValueError("CosyVoice returned malformed PCM.")
                audio, rate = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768, 24000
            audio = np.asarray(audio, dtype=np.float32).squeeze()
            if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
                raise ValueError(f"{model} returned invalid mono audio.")
            if writer is None:
                writer = sf.SoundFile(output, "w", samplerate=rate, channels=1, subtype="PCM_16")
            if writer.samplerate != rate:
                raise ValueError("TTS changed sample rate between passages.")
            writer.write(audio)
            if pause:
                writer.write(np.zeros(round(rate * pause), dtype=np.float32))
            progress(f"Narrating passage {i} of {len(parts)}")
    finally:
        if writer:
            writer.close()
