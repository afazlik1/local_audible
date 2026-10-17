import asyncio
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import main
from backend.narration import integrate, review_chunks
from backend.storage import ManifestStore


def photo():
    out = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(out, format="PNG")
    return out.getvalue()


def test_voice_preview_is_independent_and_uses_fixed_text(client, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(main, "available", lambda model: True)
    async def generate(model, narrator, source, output, cache, update, **kwargs):
        calls.append((source.read_text(), kwargs["advanced"]))
        await asyncio.sleep(.08)
        output.write_bytes(b"wav")
    def export(source, target, duration=None):
        assert duration == 10
        target.write_bytes(b"mp3")
    monkeypatch.setattr(main, "generate_speech", generate)
    monkeypatch.setattr(main, "export_mp3", export)
    assert main.store.load() is None
    for speed, passage in [(1.0, ""), (1.2, "A custom preview passage.")]:
        response = client.post("/api/voice-preview", json={"model": "kokoro", "narrator": "af_heart", "advanced": {"speed": speed}, "preview_text": passage, "text": "Must not be used."})
        assert response.status_code == 202
        assert client.post("/api/voice-preview", json={}).status_code == 409
        for _ in range(100):
            result = client.get("/api/voice-preview").json()
            if result["status"] != "running":
                break
            time.sleep(.01)
        assert result["status"] == "complete"
        assert result["audio_url"].startswith("/audio/previews/")
        assert main.store.load() is None
    assert calls == [(main.PREVIEW_TEXT, {"speed": 1.0}), ("A custom preview passage.", {"speed": 1.2})]


def test_reference_playback_is_allowlisted(client, tmp_path):
    folder = tmp_path / "sample_voice"
    folder.mkdir()
    (folder / "voice.mp3").write_bytes(b"reference audio")
    assert client.get("/api/sample-voices/audio", params={"name": "voice.mp3"}).content == b"reference audio"
    assert client.get("/api/sample-voices/audio", params={"name": "../outside.mp3"}).status_code == 404


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_document_upload_skips_ocr_but_requires_optimization(client, monkeypatch, extension):
    from test_documents import pdf_bytes, word_bytes
    calls = []
    async def forbidden(*args):
        raise AssertionError("OCR must never be called for document imports")
    async def optimize(text, before, after, **kwargs):
        assert kwargs.get("_selected", False) == (extension == "pdf")
        calls.append(text)
        return text + " Optimized."
    monkeypatch.setattr(main.ocr, "extract", forbidden)
    monkeypatch.setattr(main.ocr, "optimize", optimize)
    data = pdf_bytes() if extension == "pdf" else word_bytes()
    response = client.post("/api/book/document", files={"file": (f"Book.{extension}", data)})
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["source_type"] == extension and not manifest["review_ready"]
    assert manifest["pages"][0]["text"] and manifest["pages"][0]["preview_url"] == ""
    assert client.post("/api/book/audio", json={"text": "Not yet reviewed"}).status_code == 400
    assert client.post("/api/book/prepare").status_code == 202
    prepared = wait(client)
    assert prepared["book_status"] == "review" and prepared["review_ready"]
    assert calls and prepared["final_text"].endswith("Optimized.")
    assert client.post("/api/book/document", files={"file": ("bad.pdf", b"not a pdf")}).status_code == 400
    assert client.get("/api/book").json()["final_text"] == prepared["final_text"]
    assert client.post("/api/book/document", files={"file": ("old.doc", b"legacy")}).status_code == 400


def test_reference_preparation_caches_transcript_and_preserves_book(client, tmp_path, monkeypatch):
    folder = tmp_path / "sample_voice"
    folder.mkdir()
    source = folder / "voice.mp3"
    source.write_bytes(b"original recording")
    calls = []
    def snapshot(source, target, exact=False, seconds=None):
        assert exact
        target.write_bytes(b"excerpt")
    async def process(*args, **kwargs):
        calls.append(args)
        Path(args[-1]).write_text("The actual sample words.")
        class Process:
            returncode = 0
            async def communicate(self):
                return b"", None
        return Process()
    monkeypatch.setattr(main, "snapshot_sample", snapshot)
    monkeypatch.setattr(main.asyncio, "create_subprocess_exec", process)
    for _ in range(2):
        assert client.post("/api/sample-voices/prepare", json={"sample_voice": "voice.mp3"}).status_code == 202
        for _ in range(100):
            result = client.get("/api/sample-voices/prepare").json()
            if result["status"] != "running":
                break
            time.sleep(.01)
        assert result["status"] == "complete"
        assert result["transcript"] == "The actual sample words."
    assert len(calls) == 1
    assert main.store.load() is None
    assert source.read_bytes() == b"original recording"


def test_voice_preview_validation_and_failure(client, monkeypatch):
    monkeypatch.setattr(main, "available", lambda model: True)
    assert client.post("/api/voice-preview", json={"advanced": {"speed": 100}}).status_code == 400
    assert client.post("/api/voice-preview", json={"model": "fish", "narrator": "default"}).status_code == 400
    async def fail(*args, **kwargs):
        raise RuntimeError("Preview model failed")
    monkeypatch.setattr(main, "generate_speech", fail)
    assert client.post("/api/voice-preview", json={}).status_code == 202
    for _ in range(100):
        result = client.get("/api/voice-preview").json()
        if result["status"] != "running":
            break
        time.sleep(.01)
    assert result["status"] == "error" and result["audio_url"] is None
    assert result["error"] == "Preview model failed"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"data_dir": tmp_path, "book_images_dir": tmp_path / "source"}))
    monkeypatch.setattr(main, "store", ManifestStore(tmp_path))
    monkeypatch.setattr(main, "task", None)
    monkeypatch.setattr(main, "lock", asyncio.Lock())
    async def select(settings, source, index, fingerprint):
        return {"page": index + 1, "selected_text": main.extract_document(source)[index],
                "uncertain_ids": [], "preview_url": "/images/test-layout.png"}
    monkeypatch.setattr(main, "select_page", select)
    with TestClient(main.app) as client:
        yield client


def wait(client):
    for _ in range(200):
        book = client.get("/api/book").json()
        if book["book_status"] not in {"assembling", "refining", "audio"}:
            return book
        time.sleep(.01)
    pytest.fail("Background task did not finish")


def test_full_workflow_uses_exact_approved_editor_text(client, monkeypatch, tmp_path):
    calls = []
    async def extract(*args):
        return "A narra-\ntive sentence."
    async def optimize(text, before, after):
        return text + " Reviewed."
    async def generate(model, narrator, source, path, cache, update, advanced=None):
        assert advanced == {"speed": 1.0}
        calls.append((model, narrator, source.read_text()))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mock audio")
    monkeypatch.setattr(main.ocr, "extract", extract)
    monkeypatch.setattr(main.ocr, "optimize", optimize)
    monkeypatch.setattr(main, "generate_speech", generate)
    monkeypatch.setattr(main, "export_mp3", lambda wav, output, cover: output.write_bytes(b"mock mp3"))
    response = client.post("/api/book/upload", files=[("files", ("My Book/page10.png", photo(), "image/png")), ("files", ("My Book/page2.png", photo(), "image/png"))])
    assert response.status_code == 200
    assert [p["filename"] for p in response.json()["pages"]] == ["page2.png", "page10.png"]
    assert client.post("/api/book/audio", json={"text": "Not reviewed"}).status_code == 400
    assert client.post("/api/book/prepare").status_code == 202
    book = wait(client)
    assert book["book_status"] == "review"
    assert "narrative" in book["final_text"]
    assert calls == []
    assert list((tmp_path / "text").glob("*-raw.txt"))
    assert client.put("/api/book/text", json={"text": "Saved draft."}).status_code == 200
    approved = "New unsaved correction — read THIS text!"
    assert client.post("/api/book/audio", json={"text": approved, "model": "kokoro", "narrator": "am_michael"}).status_code == 202
    book = wait(client)
    assert book["book_status"] == "complete"
    assert book["audio_url"].endswith(".mp3")
    assert calls == [("kokoro", "am_michael", approved)]
    assert book["tts_model"] == "kokoro" and book["narrator"] == "am_michael"
    assert (tmp_path / "text" / Path(book["final_text_url"]).name).read_text() == approved


def test_bad_upload_preserves_active_book(client):
    client.post("/api/book/upload", files={"files": ("valid.png", photo(), "image/png")})
    previous = client.get("/api/book").json()
    assert client.post("/api/book/upload", files={"files": ("bad.png", b"not an image", "image/png")}).status_code == 400
    assert client.get("/api/book").json() == previous
    assert client.post("/api/book/upload", files=[("files", ("x/page.png", photo())), ("files", ("y/page.png", photo()))]).status_code == 400


def test_failure_retry_and_busy_guard(client, monkeypatch):
    count = 0
    async def extract(*args):
        nonlocal count
        count += 1
        await asyncio.sleep(.05)
        return "A narrative passage."
    async def fail(*args):
        raise RuntimeError("Review unavailable")
    monkeypatch.setattr(main.ocr, "extract", extract)
    monkeypatch.setattr(main.ocr, "optimize", fail)
    client.post("/api/book/upload", files={"files": ("page.png", photo())})
    client.post("/api/book/prepare")
    assert client.post("/api/book/prepare").status_code == 409
    assert client.put("/api/book/text", json={"text": "overwrite"}).status_code == 409
    book = wait(client)
    assert book["book_status"] == "error" and not book["review_ready"]
    assert book["manuscript_text"] == "A narrative passage."
    async def optimize(text, *args, **kwargs):
        return text
    monkeypatch.setattr(main.ocr, "optimize", optimize)
    client.post("/api/book/prepare")
    assert wait(client)["review_ready"]
    assert count == 1


def test_manual_review_preserves_complete_book_and_requires_warning_approval(client, monkeypatch):
    from backend.ocr import NarrativePreservationError
    from test_documents import pdf_bytes
    client.post("/api/book/document", files={"file": ("book.pdf", pdf_bytes())})
    monkeypatch.setattr(main, "review_chunks", lambda text: ["First source.", "Failed source.", "Last source."])
    async def optimize(text, *args, **kwargs):
        if text == "First source.":
            return "First optimized."
        raise NarrativePreservationError("{}", "A main-text sentence may be missing.")
    monkeypatch.setattr(main.ocr, "optimize", optimize)
    client.post("/api/book/prepare")
    failed = wait(client)
    assert failed["review_fallback_available"] and not failed["review_ready"]
    original = failed["manuscript_text"]
    result = client.post("/api/book/review-with-warnings")
    assert result.status_code == 200
    review = result.json()
    assert review["final_text"] == "First optimized.\n\nFailed source.\n\nLast source."
    assert review["review_ready"] and review["review_warnings"]
    assert review["manuscript_text"] == original and review["audio_url"] is None
    assert client.post("/api/book/review-with-warnings").status_code == 409
    saved = client.put("/api/book/text", json={"text": "My corrected manuscript."}).json()
    assert saved["review_warnings"] == review["review_warnings"]
    monkeypatch.setattr(main, "available", lambda model: True)
    monkeypatch.setattr(main, "require_encoder", lambda: None)
    async def narrate(manifest, path):
        assert manifest.final_text == "My corrected manuscript."
        manifest.book_status = "complete"
        main.store.save(manifest)
    monkeypatch.setattr(main, "narrate", narrate)
    assert client.post("/api/book/audio", json={"text": "My corrected manuscript."}).status_code == 409
    assert client.post("/api/book/audio", json={"text": "My corrected manuscript.", "acknowledge_review_warnings": True}).status_code == 202
    assert wait(client)["book_status"] == "complete"


def test_pdf_optimization_uses_only_visually_selected_source(client, monkeypatch):
    from test_documents import pdf_bytes
    client.post("/api/book/document", files={"file": ("book.pdf", pdf_bytes("Main narrative. Table cells."))})
    async def select(*args):
        return {"page": 1, "selected_text": "Main narrative.", "uncertain_ids": [1],
                "preview_url": "/images/layout.png"}
    async def optimize(text, before, after, **kwargs):
        assert text == "Main narrative." and kwargs == {"_selected": True}
        return text
    monkeypatch.setattr(main, "select_page", select)
    monkeypatch.setattr(main.ocr, "optimize", optimize)
    client.post("/api/book/prepare")
    book = wait(client)
    assert book["book_status"] == "review"
    assert book["selected_text"] == book["final_text"] == "Main narrative."
    assert "Table cells" in book["manuscript_text"]
    assert book["layout_report_url"] and book["selected_text_url"]
    assert book["review_warnings"] and book["pages"][0]["preview_url"]


def test_incomplete_pdf_layout_never_opens_partial_book(client, monkeypatch):
    from test_documents import pdf_bytes
    from backend.pdf_layout import LayoutError
    client.post("/api/book/document", files={"file": ("book.pdf", pdf_bytes())})
    async def select(*args):
        raise LayoutError("PDF layout classification omitted region IDs")
    monkeypatch.setattr(main, "select_page", select)
    client.post("/api/book/prepare")
    book = wait(client)
    assert book["book_status"] == "error" and not book["review_ready"]
    assert not book["final_text"] and book["manuscript_text"]


def test_legacy_validation_failure_can_open_full_original_but_other_errors_cannot(client):
    from test_documents import pdf_bytes
    client.post("/api/book/document", files={"file": ("book.pdf", pdf_bytes())})
    manifest = main.store.load()
    manifest.manuscript_text = "Complete original source."
    manifest.book_status = "error"
    manifest.book_error = "Text optimization could not verify that all main narrative was preserved."
    main.store.save(manifest)
    assert client.get("/api/book").json()["review_fallback_available"]
    review = client.post("/api/book/review-with-warnings").json()
    assert review["final_text"] == manifest.manuscript_text
    assert "not optimized" in review["review_warnings"][0]
    manifest.book_error = "Ollama OCR failed: Connection refused"
    main.store.save(manifest)
    assert not client.get("/api/book").json()["review_fallback_available"]
    assert client.post("/api/book/review-with-warnings").status_code == 409
    manifest.book_error = "Text optimization could not verify narrative."
    manifest.manuscript_text = ""
    main.store.save(manifest)
    assert client.post("/api/book/review-with-warnings").status_code == 409


def test_cleanup_and_lossless_chunks():
    assert integrate(["A narra-\ntive with 1984", "and a contin-", "uation.", "[NO NARRATIVE]"]) == "A narrative with 1984 and a continuation."
    text = "A sentence.\n\nAnother paragraph with words. " * 500
    chunks = review_chunks(text, 100)
    assert "".join(chunks) == text
    assert max(map(len, chunks)) <= 100


def test_cross_origin_rejected(client):
    assert client.post("/api/book/prepare", headers={"Origin": "https://example.com"}).status_code == 403


def test_audio_selection_rejects_british_and_unknown_voices(client):
    for model, narrator in [("kokoro", "bf_emma"), ("piper", "en_GB-alan-medium"), ("chatterbox", "heart-reference")]:
        assert client.post("/api/book/audio", json={"text": "Test", "model": model, "narrator": narrator}).status_code == 400
    models = client.get("/api/voices").json()
    assert {m["id"] for m in models} == {"kokoro", "piper", "chatterbox", "fish", "f5", "gpt_sovits", "cosyvoice", "orpheus", "csm", "chattts"}


def test_optional_cover_upload_validation(client, tmp_path):
    response = client.post("/api/book/cover", files={"file": ("logo.png", photo(), "image/png")})
    assert response.status_code == 200
    ident = response.json()["id"]
    with Image.open(tmp_path / "images/covers" / f"{ident}.jpg") as image:
        assert image.format == "JPEG"
    assert client.post("/api/book/cover", files={"file": ("bad.png", b"not an image")}).status_code == 400
    assert client.post("/api/book/cover", files={"file": ("big.png", b"x" * (5 * 1024 * 1024 + 1))}).status_code == 413
    assert client.post("/api/book/audio", json={"text": "text", "cover_id": "../outside"}).status_code == 422
    assert client.post("/api/book/audio", json={"text": "text", "cover_id": "0" * 32}).status_code == 400


def test_optional_sample_voice_snapshot_and_model_guard(client, tmp_path, monkeypatch):
    from backend.schemas import BookManifest
    main.store.save(BookManifest(updated_at="now", review_ready=True, book_status="review", final_text="Ready"))
    folder = tmp_path / "sample_voice"
    folder.mkdir()
    (folder / "sample.mp3").write_bytes(b"reference")
    monkeypatch.setattr(main, "available", lambda model: True)
    monkeypatch.setattr(main, "snapshot_sample", lambda source, target: (target.parent.mkdir(parents=True, exist_ok=True), target.write_bytes(source.read_bytes())))
    captured = []
    async def speech(model, narrator, source, output, cache, update, reference=None, advanced=None):
        assert advanced["exaggeration"] == 0.45
        captured.append(reference.read_bytes() if reference else None)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"wav")
    monkeypatch.setattr(main, "generate_speech", speech)
    monkeypatch.setattr(main, "export_mp3", lambda wav, target, cover: target.write_bytes(b"mp3"))
    assert client.get("/api/sample-voices").json()[0]["id"] == "sample.mp3"
    body = {"text": "Approved", "model": "chatterbox", "narrator": "default", "sample_voice": "sample.mp3"}
    assert client.post("/api/book/audio", json={**body, "model": "kokoro", "narrator": "af_heart"}).status_code == 400
    assert client.post("/api/book/audio", json={**body, "sample_voice": "../outside.mp3"}).status_code == 400
    assert client.post("/api/book/audio", json=body).status_code == 202
    assert wait(client)["book_status"] == "complete"
    assert captured == [b"reference"]
    assert client.post("/api/book/audio", json={**body, "sample_voice": None}).status_code == 202
    assert wait(client)["sample_snapshot"] is None
    assert captured == [b"reference", None]
