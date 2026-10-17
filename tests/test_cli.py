import pytest
from PIL import Image

from backend import cli
from backend.ocr import OcrError


@pytest.mark.asyncio
async def test_transcription_resumes_and_invalidates_changed_images(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    for name in ["page10.jpg", "page2.jpg"]:
        Image.new("RGB", (4, 4), "white").save(images / name)
    output = tmp_path / "book.txt"
    calls = []

    async def health(self):
        return {"available": True, "model_found": True}

    async def extract(self, encoded, mime):
        calls.append(encoded)
        if len(calls) == 2:
            raise OcrError("interrupted")
        return f"Text {len(calls)}"

    monkeypatch.setattr(cli.OllamaOcr, "health", health)
    monkeypatch.setattr(cli.OllamaOcr, "extract", extract)
    with pytest.raises(OcrError, match="page10.jpg.*rerun to resume"):
        await cli.transcribe(images, output)
    assert not output.exists()
    assert (tmp_path / "book-pages/page2.jpg.json").exists()
    await cli.transcribe(images, output)
    assert len(calls) == 3
    assert output.read_text() == "Text 1\n\nText 3\n"
    Image.new("RGB", (4, 4), "black").save(images / "page2.jpg")
    await cli.transcribe(images, output)
    assert len(calls) == 4
    assert output.read_text() == "Text 4\n\nText 3\n"


@pytest.mark.asyncio
async def test_failed_ocr_preserves_previous_complete_manuscript(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (4, 4)).save(images / "page.jpg")
    output = tmp_path / "book.txt"
    output.write_text("Previously completed book")

    async def health(self):
        return {"available": True, "model_found": True}

    async def extract(self, encoded, mime):
        raise OcrError("ReadTimeout")

    monkeypatch.setattr(cli.OllamaOcr, "health", health)
    monkeypatch.setattr(cli.OllamaOcr, "extract", extract)
    with pytest.raises(OcrError, match="ReadTimeout"):
        await cli.transcribe(images, output)
    assert output.read_text() == "Previously completed book"


@pytest.mark.asyncio
async def test_empty_input_rejected_before_contacting_ollama(tmp_path):
    with pytest.raises(ValueError, match="No supported"):
        await cli.transcribe(tmp_path, tmp_path / "book.txt")
