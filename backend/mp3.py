"""MP3 export with optional embedded ID3 front-cover artwork."""
import json
import shutil
import subprocess


def require_encoder():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("MP3 export requires FFmpeg and ffprobe installed on this computer.")


def export_mp3(wav, target, cover=None, duration=None):
    require_encoder()
    temporary = target.with_suffix(".partial.mp3")
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav)]
    if cover:
        args += ["-i", str(cover)]
    args += ["-map", "0:a:0"]
    if duration is not None:
        args += ["-af", f"apad,atrim=duration={float(duration)}"]
    if cover:
        args += ["-map", "1:v:0", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic",
                 "-metadata:s:v:0", "title=Album cover", "-metadata:s:v:0", "comment=Cover (front)"]
    args += ["-c:a", "libmp3lame", "-b:a", "128k", "-id3v2_version", "3", str(temporary)]
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=3600)
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(temporary)],
                                check=True, capture_output=True, timeout=30)
        streams = json.loads(result.stdout)["streams"]
        if not any(s.get("codec_name") == "mp3" for s in streams):
            raise RuntimeError("MP3 export did not produce a valid audio stream.")
        if cover and not any(s.get("disposition", {}).get("attached_pic") for s in streams):
            raise RuntimeError("MP3 cover artwork was not embedded successfully.")
        temporary.replace(target)
    except subprocess.CalledProcessError as error:
        raise RuntimeError("MP3 export failed: " + error.stderr.decode(errors="replace")[-1000:]) from error
    finally:
        temporary.unlink(missing_ok=True)
