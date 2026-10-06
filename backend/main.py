"""Single-user local workspace with human approval before narration."""
import asyncio
import json
import io
import shutil
import uuid
import tempfile
import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from .assets import SUPPORTED_EXTENSIONS, discover_pages, image_payload, normalize_image
from .cli import atomic_write
from .config import get_settings
from .narration import integrate, review_chunks
from .ocr import OllamaOcr
from .schemas import AudioSubmit, BookManifest, ManuscriptUpdate, PreviewSubmit, Page
from .storage import ManifestStore, utc_now
from .documents import extract_document
from .pdf_layout import select_page
from .speech import generate_speech
from .voices import ROOT, runtime, MODELS, available, catalog, validate_voice, validate_reference
from .tts_options import validate_options
from .mp3 import export_mp3, require_encoder
from .reference_voice import samples, resolve_sample, snapshot_sample, reference_seconds

settings = get_settings()
store = ManifestStore(settings.data_dir)
ocr = OllamaOcr(settings)
task: asyncio.Task | None = None
lock = asyncio.Lock()
preview = {"id": None, "status": "idle", "progress": "", "audio_url": None, "error": None}
reference_preparation = {"id": None, "status": "idle"}
PREVIEW_TEXT = (
    "The morning light fell softly across the library. I opened a book and began to read. "
    "Every page offered a new idea, a quiet discovery, and a reason to keep listening. "
    "Outside, the world was waking up, but here there was time to pause, imagine, and enjoy the story. "
    "A good story invites us to see familiar things in a different way."
)


@asynccontextmanager
async def lifespan(app):
    manifest = store.load()
    if manifest and manifest.book_status in {"assembling", "refining", "audio"}:
        manifest.book_status = "error"
        manifest.book_error = "Processing was interrupted. Retry preparation or submit reviewed text again."
        store.save(manifest)
    yield
    if task:
        await task


app = FastAPI(title="Local Audible", lifespan=lifespan)
for route, folder in [("audio", "audio"), ("images", "images"), ("files", "text")]:
    (settings.data_dir / folder).mkdir(parents=True, exist_ok=True)
    app.mount(f"/{route}", StaticFiles(directory=settings.data_dir / folder), name=route)


@app.middleware("http")
async def local_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT"} and origin and origin not in {
        "http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"
    }:
        return JSONResponse({"detail": "Use the Local Audible interface on this computer."}, status_code=403)
    return await call_next(request)


def can_review_with_warnings(manifest):
    # Also recognizes saved failures from before the manual-review option existed.
    return (manifest.book_status == "error" and not manifest.review_ready
            and bool(manifest.manuscript_text.strip())
            and (manifest.book_error or "").startswith((
                "Text optimization could not verify",
                "Narrative preservation check flagged",
                "Could not verify narrative preservation")))


def get_manifest():
    manifest = store.load()
    if manifest is None:
        manifest = discover_pages(settings.book_images_dir, settings.data_dir / "images")
        store.save(manifest)
    manifest.review_fallback_available = can_review_with_warnings(manifest)
    return manifest


def ensure_idle():
    if task and not task.done():
        raise HTTPException(409, "Book or voice preview processing is already running. Wait for it to finish.")


def write_text(name, text):
    atomic_write(settings.data_dir / "text" / name, text)
    return f"/files/{name}"


@app.get("/api/health")
async def health():
    return {"api": "ok", "ollama": await ocr.health(), "tts_provider": settings.tts_provider}


@app.get("/api/book", response_model=BookManifest)
async def book():
    return get_manifest()


@app.get("/api/voices")
async def voices():
    return catalog()


@app.get("/api/sample-voices")
async def sample_voices():
    return samples(settings.data_dir)


@app.get("/api/sample-voices/audio")
async def sample_voice_audio(name: str):
    try:
        return FileResponse(resolve_sample(settings.data_dir, name))
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.get("/api/sample-voices/prepare")
async def reference_preparation_status():
    return reference_preparation


async def prepare_reference(name, identifier, model):
    proc = None
    try:
        source = resolve_sample(settings.data_dir, name)
        digest = await asyncio.to_thread(lambda: hashlib.sha256(source.read_bytes()).hexdigest())
        folder = settings.data_dir / "audio" / "references"
        folder.mkdir(parents=True, exist_ok=True)
        seconds = reference_seconds(model)
        clip = folder / f"{digest}-{seconds}s.wav"
        transcript = folder / f"{digest}-{seconds}s-whisper-small-en.txt"
        if not clip.exists():
            await asyncio.to_thread(snapshot_sample, source, clip, exact=True, seconds=seconds)
        reference_preparation.update(audio_url=f"/audio/references/{clip.name}", progress=f"Transcribing the {seconds}-second excerpt locally; first use may download Whisper…")
        if not transcript.exists():
            temporary = transcript.with_suffix(".partial.txt")
            try:
                proc = await asyncio.create_subprocess_exec(str(runtime("chatterbox")), "-m", "backend.transcribe_reference", str(clip.resolve()), str(temporary.resolve()),
                    cwd=ROOT, env=dict(os.environ, HF_HUB_DISABLE_XET="1"), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
                output, _ = await asyncio.wait_for(proc.communicate(), timeout=1800)
                if proc.returncode:
                    raise RuntimeError("Local transcription failed: " + output.decode(errors="replace")[-1200:])
                if not temporary.read_text().strip():
                    raise ValueError("No transcript detected. Choose a recording that starts with speech.")
                temporary.replace(transcript)
            finally:
                if proc and proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                temporary.unlink(missing_ok=True)
        reference_preparation.update(status="complete", transcript=transcript.read_text(), progress="Excerpt ready. Listen and check the automatic transcript before generating audio.")
    except Exception as error:
        reference_preparation.update(status="error", error=str(error) or type(error).__name__)


@app.post("/api/sample-voices/prepare", status_code=202)
async def start_reference_preparation(body: PreviewSubmit):
    global task, reference_preparation
    async with lock:
        ensure_idle()
        try:
            resolve_sample(settings.data_dir, body.sample_voice)
            require_encoder()
        except (ValueError, RuntimeError) as error:
            raise HTTPException(400, str(error)) from error
        identifier = uuid.uuid4().hex
        reference_preparation = dict(id=identifier, status="running", sample_voice=body.sample_voice, progress=f"Preparing first {reference_seconds(body.model)} seconds…", transcript="", audio_url=None, error=None)
        task = asyncio.create_task(prepare_reference(body.sample_voice, identifier, body.model))
        return reference_preparation


@app.get("/api/voice-preview")
async def preview_status():
    return {"text": PREVIEW_TEXT, **preview}


async def render_preview(body, options, identifier):
    try:
        target = settings.data_dir / "audio" / "previews" / f"{identifier}.mp3"
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="book-voice-preview-") as folder:
            folder = Path(folder)
            source, wav = folder / "sample.txt", folder / "sample.wav"
            source.write_text(body.preview_text or PREVIEW_TEXT, encoding="utf-8")
            reference = None
            if body.sample_voice:
                reference = folder / "reference.wav"
                await asyncio.to_thread(snapshot_sample, resolve_sample(settings.data_dir, body.sample_voice), reference,
                                        exact=bool(MODELS[body.model].get("requires_reference_text")),
                                        seconds=reference_seconds(body.model) if MODELS[body.model].get("requires_reference_text") else 30)
            def update(message):
                preview["progress"] = message
            await generate_speech(body.model, body.narrator, source, wav, settings.data_dir / "models", update,
                                  reference=reference, advanced=options, reference_text=body.reference_text.strip())
            update("Encoding 10-second preview…")
            await asyncio.to_thread(export_mp3, wav, target, duration=10)
        preview.update(status="complete", progress="10-second preview ready.", audio_url=f"/audio/previews/{identifier}.mp3")
    except Exception as error:
        preview.update(status="error", error=str(error) or type(error).__name__)


@app.post("/api/voice-preview", status_code=202)
async def create_preview(body: PreviewSubmit):
    global task, preview
    async with lock:
        ensure_idle()
        try:
            validate_voice(body.model, body.narrator)
            options = validate_options(body.model, body.advanced)
            validate_reference(body.model, body.sample_voice, body.reference_text)
            if body.sample_voice:
                resolve_sample(settings.data_dir, body.sample_voice)
            require_encoder()
        except (ValueError, RuntimeError) as error:
            raise HTTPException(400, str(error)) from error
        if not available(body.model):
            raise HTTPException(503, "Selected speech runtime needs setup. See README.md.")
        identifier = uuid.uuid4().hex
        body.preview_text = (body.preview_text or "").strip() or PREVIEW_TEXT
        preview = dict(id=identifier, status="running", progress="Loading voice model…", audio_url=None, error=None, text=body.preview_text)
        task = asyncio.create_task(render_preview(body, options, identifier))
        return preview


@app.post("/api/book/cover")
async def upload_cover(file: UploadFile = File(...)):
    try:
        data = await file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "Cover image must be 5 MB or smaller.")
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 16000000:
                raise ValueError("Use a JPG, PNG, or WebP image, at most 16 megapixels.")
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((1200, 1200))
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            ident = uuid.uuid4().hex
            folder = settings.data_dir / "images" / "covers"
            folder.mkdir(parents=True, exist_ok=True)
            background.save(folder / f"{ident}.jpg", format="JPEG", quality=90)
        return {"id": ident, "url": f"/images/covers/{ident}.jpg"}
    except HTTPException:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(400, f"Cannot read cover image: {error}") from error
    finally:
        await file.close()


@app.post("/api/book/upload", response_model=BookManifest)
async def upload(files: list[UploadFile] = File(...)):
    async with lock:
        ensure_idle()
        if not files or len(files) > 1000:
            raise HTTPException(400, "Choose between 1 and 1,000 page images.")
        ident = uuid.uuid4().hex
        folder = settings.data_dir / "uploads" / ident
        preview = settings.data_dir / "images" / ident
        folder.mkdir(parents=True)
        names = set()
        total = 0
        try:
            for file in files:
                name = Path((file.filename or "").replace("\\", "/")).name
                if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS or name.casefold() in names:
                    raise HTTPException(400, "Use supported images with unique filenames (including subfolders).")
                names.add(name.casefold())
                size = 0
                with (folder / name).open("wb") as out:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > 30 * 1024 * 1024 or total > 1024 ** 3:
                            raise HTTPException(413, "Limit: 30 MB per image and 1 GB per folder.")
                        out.write(chunk)
            manifest = await asyncio.to_thread(discover_pages, folder, preview)
            manifest.source_dir = str(folder.resolve())
            manifest.title = (files[0].filename or "Book").replace("\\", "/").split("/")[0]
            for page in manifest.pages:
                page.preview_url = f"/images/{ident}/{page.id}.jpg"
            previous = store.load()
            if previous:
                atomic_write(settings.data_dir / "history" / f"{ident}.json", previous.model_dump_json(indent=2))
            return store.save(manifest)
        except Exception as error:
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(preview, ignore_errors=True)
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(400, f"Could not read the uploaded images: {error}") from error
        finally:
            for file in files:
                await file.close()


@app.post("/api/book/document", response_model=BookManifest)
async def upload_document(file: UploadFile = File(...)):
    async with lock:
        ensure_idle()
        ident = uuid.uuid4().hex
        folder = settings.data_dir / "uploads" / ident
        try:
            name = Path((file.filename or "").replace("\\", "/")).name
            suffix = Path(name).suffix.lower()
            if suffix not in {".pdf", ".docx"}:
                raise HTTPException(400, "Choose a PDF or Word .docx file. Save older .doc files as .docx first.")
            folder.mkdir(parents=True)
            source = folder / name
            size = 0
            with source.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 50 * 1024 * 1024:
                        raise HTTPException(413, "Document limit: 50 MB.")
                    output.write(chunk)
            sections = await asyncio.to_thread(extract_document, source)
            manifest = BookManifest(source_type=suffix[1:], source_name=name, source_dir=str(folder.resolve()),
                                    title=Path(name).stem, updated_at=utc_now(),
                                    progress="Document text extracted without OCR. Click Optimize text, then review the result.",
                                    pages=[Page(id=f"section-{i:04d}", page_number=i, filename=f"{'Page' if suffix == '.pdf' else 'Section'} {i}",
                                                preview_url="", text=text) for i, text in enumerate(sections, 1)])
            previous = store.load()
            if previous:
                atomic_write(settings.data_dir / "history" / f"{ident}.json", previous.model_dump_json(indent=2))
            return store.save(manifest)
        except Exception as error:
            shutil.rmtree(folder, ignore_errors=True)
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(400, f"Could not extract document text: {error}") from error
        finally:
            await file.close()


async def prepare(manifest):
    try:
        source = Path(manifest.source_dir) if manifest.source_dir else settings.book_images_dir
        for i, page in enumerate(manifest.pages, 1):
            if manifest.source_type != "images":
                page.status = "review"
                continue
            manifest.progress = f"Transcribing page {i} of {len(manifest.pages)}: {page.filename}"
            store.save(manifest)
            if page.ocr_version != 1 or not page.text:
                normalized = (settings.data_dir / page.preview_url.lstrip("/")) if manifest.source_dir else (settings.data_dir / "images" / f"{page.id}.jpg")
                await asyncio.to_thread(normalize_image, source / page.filename, normalized)
                encoded, mime = await asyncio.to_thread(image_payload, normalized)
                page.text = await ocr.extract(encoded, mime)
                page.status = "review"
                page.ocr_version = 1
                store.save(manifest)
        manifest.manuscript_text = (integrate([p.text for p in manifest.pages]) if manifest.source_type == "images"
                                    else "\n\n".join(p.text for p in manifest.pages if p.text.strip()))
        if not manifest.manuscript_text:
            raise ValueError("No narrative text was found in this source.")
        revision = uuid.uuid4().hex
        manifest.manuscript_url = write_text(f"{revision}-raw.txt", manifest.manuscript_text)
        manifest.book_status = "refining"
        store.save(manifest)
        if manifest.source_type == "pdf":
            if not manifest.source_name or Path(manifest.source_name).name != manifest.source_name:
                raise ValueError("PDF source file is unavailable. Upload the PDF again.")
            pdf = source / manifest.source_name
            fingerprint = await asyncio.to_thread(lambda: hashlib.sha256(pdf.read_bytes()).hexdigest())
            reports = []
            for i, page in enumerate(manifest.pages):
                manifest.progress = f"Analyzing PDF layout: page {i + 1} of {len(manifest.pages)}"
                store.save(manifest)
                report = await select_page(settings, pdf, i, fingerprint)
                reports.append(report)
                page.preview_url = report["preview_url"]
                if report["uncertain_ids"]:
                    manifest.review_warnings.append(f"PDF page {i + 1}: ambiguous text regions "
                        f"{', '.join(map(str, report['uncertain_ids']))} were retained. Check them against the page image.")
                # Save provenance incrementally; never treat a partial selection as a full manuscript.
                manifest.layout_report_url = write_text(f"{revision}-layout.json", json.dumps(reports, ensure_ascii=False, indent=2))
                store.save(manifest)
            manifest.selected_text = "\n\n".join(r["selected_text"] for r in reports if r["selected_text"].strip())
            if not manifest.selected_text.strip():
                raise ValueError("PDF layout analysis found no main narrative. Review the page images and layout report.")
            manifest.selected_text_url = write_text(f"{revision}-selected.txt", manifest.selected_text)
            store.save(manifest)
        parts = review_chunks(manifest.selected_text if manifest.source_type == "pdf" else manifest.manuscript_text)
        reviewed = []
        for i, part in enumerate(parts):
            manifest.progress = f"Optimizing narration: passage {i + 1} of {len(parts)}"
            store.save(manifest)
            try:
                result = await ocr.optimize(part, parts[i - 1][-500:] if i else "", parts[i + 1][:500] if i + 1 < len(parts) else "",
                                            **({"_selected": True} if manifest.source_type == "pdf" else {}))
            except Exception as error:
                manifest.book_status = "error"
                manifest.book_error = str(error)
                if can_review_with_warnings(manifest):
                    # Never offer a partial book or an unchecked candidate that may omit facts.
                    manifest.final_text = "\n\n".join(p for p in [*reviewed, *parts[i:]] if p.strip())
                    manifest.review_warnings += [
                        f"Passages {i + 1}–{len(parts)} use {'visually selected PDF' if manifest.source_type == 'pdf' else 'original extracted'} text, not optimized text. "
                        "Remove tables, captions and side notes manually and check narrative flow. "
                        "Earlier passages retain their prepared text.", str(error)]
                raise
            reviewed.append(result)
        manifest.final_text = "\n\n".join(part for part in reviewed if part.strip())
        if not manifest.final_text.strip():
            raise ValueError("No main narrative remains after excluding tables, figures and side material. Raw text is preserved for inspection.")
        manifest.final_text_url = write_text(f"{revision}-review.txt", manifest.final_text)
        manifest.review_ready = True
        manifest.book_status = "review"
        manifest.progress = "Review and edit the prepared text, then approve it for narration."
    except Exception as error:
        manifest.book_status = "error"
        manifest.progress = "Text preparation failed. Review the error below and retry optimization."
        manifest.book_error = str(error) or type(error).__name__
    finally:
        store.save(manifest)


@app.post("/api/book/prepare", status_code=202, response_model=BookManifest)
async def start_prepare():
    global task
    async with lock:
        ensure_idle()
        manifest = get_manifest()
        if not manifest.pages:
            raise HTTPException(400, "Upload page images, a PDF or a Word document first.")
        manifest.book_status = "assembling"
        manifest.review_ready = False
        manifest.review_fallback_available = False
        manifest.review_warnings = []
        manifest.selected_text = ""
        manifest.selected_text_url = None
        manifest.layout_report_url = None
        manifest.book_error = None
        manifest.final_text = ""
        manifest.final_text_url = None
        manifest.audio_url = None
        manifest.progress = "Starting image transcription" if manifest.source_type == "images" else "Starting document text optimization (no OCR)"
        store.save(manifest)
        task = asyncio.create_task(prepare(manifest))
        return manifest


@app.post("/api/book/review-with-warnings", response_model=BookManifest)
async def review_with_warnings():
    async with lock:
        ensure_idle()
        manifest = get_manifest()
        if not can_review_with_warnings(manifest):
            raise HTTPException(409, "Manual review is available only after a text validation failure with preserved source text.")
        if not manifest.review_warnings:
            manifest.review_warnings = [
                "This draft uses the complete original extracted text because the failed run did not save "
                "a prepared draft. It is not optimized. Remove tables, captions and side notes manually "
                "and check narrative flow.", manifest.book_error or "Text validation failed."]
            manifest.final_text = manifest.manuscript_text
        manifest.final_text_url = write_text(f"{uuid.uuid4().hex}-manual-review.txt", manifest.final_text)
        manifest.review_ready = True
        manifest.review_fallback_available = False
        manifest.book_status = "review"
        manifest.book_error = None
        manifest.audio_url = None
        manifest.progress = "Manual review required: optimization did not pass validation. Edit the draft before approval."
        return store.save(manifest)


@app.put("/api/book/text", response_model=BookManifest)
async def save_draft(body: ManuscriptUpdate):
    async with lock:
        ensure_idle()
        manifest = get_manifest()
        if not manifest.review_ready:
            raise HTTPException(409, "Prepare the text before reviewing it.")
        manifest.final_text = body.text
        manifest.final_text_url = write_text(f"{uuid.uuid4().hex}-review.txt", body.text)
        manifest.audio_url = None
        manifest.book_status = "review"
        manifest.book_error = None
        return store.save(manifest)


async def narrate(manifest, path):
    wav = settings.data_dir / "render" / path.with_suffix(".wav").name
    try:
        def update(message):
            manifest.progress = message
            store.save(manifest)
        source = settings.data_dir / "text" / Path(manifest.final_text_url).name
        extra = {"reference": Path(manifest.sample_snapshot)} if manifest.sample_snapshot else {}
        if manifest.advanced:
            extra["advanced"] = manifest.advanced
        if manifest.reference_text:
            extra["reference_text"] = manifest.reference_text
        await generate_speech(manifest.tts_model, manifest.narrator, source, wav,
                              settings.data_dir / "models", update, **extra)
        update("Encoding MP3" + (" and embedding cover artwork" if manifest.cover_id else ""))
        cover = settings.data_dir / "images/covers" / f"{manifest.cover_id}.jpg" if manifest.cover_id else None
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(export_mp3, wav, path, cover)
        manifest.audio_url = f"/audio/{path.name}"
        manifest.book_status = "complete"
        manifest.progress = "Audiobook ready. Narrated the exact text you approved."
    except Exception as error:
        manifest.book_status = "error"
        manifest.book_error = str(error) or type(error).__name__
    finally:
        wav.unlink(missing_ok=True)
        store.save(manifest)


@app.post("/api/book/audio", status_code=202, response_model=BookManifest)
async def submit(body: AudioSubmit):
    global task
    async with lock:
        ensure_idle()
        try:
            validate_voice(body.model, body.narrator)
            advanced = validate_options(body.model, body.advanced)
            validate_reference(body.model, body.sample_voice, body.reference_text)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        if not available(body.model):
            raise HTTPException(503, "Selected speech runtime is not installed. See README.md.")
        try:
            require_encoder()
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        if body.cover_id and not (settings.data_dir / "images/covers" / f"{body.cover_id}.jpg").is_file():
            raise HTTPException(400, "Cover image was not found. Upload it again or remove it.")
        manifest = get_manifest()
        if not manifest.review_ready or not body.text.strip():
            raise HTTPException(400, "Review the prepared text and submit a nonempty final manuscript.")
        if manifest.review_warnings and not body.acknowledge_review_warnings:
            raise HTTPException(409, "Acknowledge the text review warnings before approving audio generation.")
        revision = uuid.uuid4().hex
        sample_path = None
        if body.sample_voice:
            try:
                selected_sample = resolve_sample(settings.data_dir, body.sample_voice)
                sample_path = settings.data_dir / "references" / f"{revision}.wav"
                if MODELS[body.model].get("requires_reference_text"):
                    await asyncio.to_thread(snapshot_sample, selected_sample, sample_path, exact=True, seconds=reference_seconds(body.model))
                else:
                    await asyncio.to_thread(snapshot_sample, selected_sample, sample_path)
            except Exception as error:
                raise HTTPException(400, "Cannot use this sample voice. Choose a valid audio file with speech. " + str(error)) from error
        manifest.sample_voice = body.sample_voice
        manifest.advanced = advanced
        manifest.reference_text = body.reference_text.strip()
        manifest.sample_snapshot = str(sample_path.resolve()) if sample_path else None
        manifest.tts_model = body.model
        manifest.narrator = body.narrator
        manifest.cover_id = body.cover_id
        manifest.final_text = body.text
        manifest.final_text_url = write_text(f"{revision}-approved.txt", body.text)
        write_text(f"{revision}-narration.json", json.dumps({
            "model": body.model, "narrator": body.narrator,
            "format": "mp3", "cover_id": body.cover_id,
            "sample_voice": body.sample_voice, "sample_snapshot": manifest.sample_snapshot,
            "approved_text_file": Path(manifest.final_text_url).name,
            "advanced": advanced, "reference_text": manifest.reference_text,
        }, indent=2))
        manifest.audio_url = None
        manifest.book_status = "audio"
        manifest.book_error = None
        manifest.progress = "Generating audiobook from your approved text. This may take several minutes."
        store.save(manifest)
        task = asyncio.create_task(narrate(manifest, settings.data_dir / "audio" / f"book-{body.model}-{body.narrator}-{revision}.mp3"))
        return manifest
