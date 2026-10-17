import json
from pathlib import Path

import httpx
import pytest

from backend.config import Settings
from backend.pdf_layout import LayoutError, classify_page, render_page, select_page, validate_selection
from test_documents import pdf_bytes


def regions():
    return [{"id": 1, "block": 0, "text": "A precise 10 mg fact."},
            {"id": 2, "block": 1, "text": "KEY FACT: sidebar."},
            {"id": 3, "block": 2, "text": "Another paragraph."}]


def test_selection_preserves_source_words_and_model_reading_order():
    result = {"groups": [{"kind": "main", "ids": [3, 1]}, {"kind": "sidebar", "ids": [2]}]}
    text, uncertain = validate_selection(regions(), result)
    assert text == "Another paragraph.\n\nA precise 10 mg fact."
    assert not uncertain
    result["groups"][1]["kind"] = "uncertain"
    text, uncertain = validate_selection(regions(), result)
    assert "KEY FACT" in text and uncertain == [2]


@pytest.mark.parametrize("result", [
    {"groups": [{"kind": "main", "ids": [1, 2]}]},
    {"groups": [{"kind": "main", "ids": [1, 2, 3, 3]}]},
    {"groups": [{"kind": "main", "ids": [1, 2, 4]}]},
    {"groups": [{"kind": "main", "ids": [True, 2, 3]}]},
    {"groups": [{"kind": "invented", "ids": [1, 2, 3]}]},
    {"groups": [{"kind": "main", "ids": [1, 2, 3], "text": "Replacement text"}]},
])
def test_invalid_classifications_fail_closed(result):
    with pytest.raises(LayoutError):
        validate_selection(regions(), result)


def test_entirely_excluded_page_is_valid():
    assert validate_selection(regions(), {"groups": [{"kind": "table", "ids": [1, 2, 3]}]}) == ("", [])


def test_pdf_render_and_regions(tmp_path):
    source, image = tmp_path / "source.pdf", tmp_path / "page.png"
    source.write_bytes(pdf_bytes("An exact 42 mg sentence."))
    page = render_page(source, 0, image)
    assert image.read_bytes().startswith(b"\x89PNG")
    assert page["regions"][0]["text"] == "An exact 42 mg sentence."
    assert all(0 <= v <= 1000 for v in page["regions"][0]["bbox"])


@pytest.mark.asyncio
async def test_vision_receives_image_and_retries_missing_ids(monkeypatch, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"image bytes")
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            assert json["messages"][0]["images"]
            assert "untrusted" in json["messages"][0]["content"]
            ids = [1] if len(calls) == 1 else [1, 2, 3]
            return httpx.Response(200, json={"message": {"content": __import__('json').dumps({"groups": [{"kind": "main", "ids": ids}]})}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    result = await classify_page(Settings(), image, regions())
    assert len(calls) == 2 and result["groups"][0]["ids"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_page_cache_is_validated_and_keyed_by_source(monkeypatch, tmp_path):
    from backend import pdf_layout
    source = tmp_path / "book.pdf"
    source.write_bytes(pdf_bytes())
    calls = []
    async def classify(settings, image, regions):
        calls.append(1)
        return {"groups": [{"kind": "main", "ids": [r["id"] for r in regions]}]}
    monkeypatch.setattr(pdf_layout, "classify_page", classify)
    settings = Settings(data_dir=tmp_path)
    first = await select_page(settings, source, 0, "digest-one")
    assert (await select_page(settings, source, 0, "digest-one")) == first
    assert len(calls) == 1
    await select_page(settings, source, 0, "digest-two")
    assert len(calls) == 2
    cache = tmp_path / first["preview_url"].lstrip("/")
    cache.with_name("selection.json").write_text('{"regions": []}')
    await select_page(settings, source, 0, "digest-one")
    assert len(calls) == 3
