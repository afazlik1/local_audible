import httpx
import pytest

from backend.config import Settings
from backend.ocr import OllamaOcr, OcrError


@pytest.mark.asyncio
async def test_selected_pdf_text_has_no_second_exclusion_pass(monkeypatch):
    import json as jsonlib
    calls = []
    source = "Neurotransmitters. A main-text fact."
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            prompt = json["messages"][0]["content"]
            assert source in prompt
            if "format" in json:
                assert "SOURCE is NOT the raw PDF" in prompt
                assert "do not permit further region removal" in prompt
                content = jsonlib.dumps({"safe": True, "reason": "All selected text preserved.", "missing_narrative": [], "changed_facts": []})
            else:
                assert "Do not reclassify or remove" in prompt
                content = source
            return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert await OllamaOcr(Settings()).optimize(source, _selected=True) == source
    assert len(calls) == 2  # Every selected-text passage is audited, even without a size reduction.


@pytest.mark.asyncio
@pytest.mark.parametrize("recover", [True, False])
async def test_truncated_audit_has_one_bounded_retry(monkeypatch, recover):
    import json as jsonlib
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            assert json["format"]["properties"]["missing_narrative"]["maxItems"] == 5
            result = {"done_reason": "length", "message": {"content": "{}"}}
            if recover and len(calls) == 2:
                result = {"message": {"content": jsonlib.dumps({"safe": True, "reason": "Narrative preserved.", "missing_narrative": [], "changed_facts": []})}}
            return httpx.Response(200, json=result, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    if recover:
        await OllamaOcr(Settings()).audit_narrative("Narrative", "Narrative")
    else:
        with pytest.raises(OcrError, match="truncated audit"):
            await OllamaOcr(Settings()).audit_narrative("Narrative", "Narrative")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_table_navigation_exclusion_is_shared_by_optimizer_and_auditor(monkeypatch):
    import json as jsonlib
    from backend.ocr import REFERENCE_POLICY
    calls = []
    narrative = "Neurotransmitters carry signals between neurons (see Figure 3.1)."
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            assert REFERENCE_POLICY in json["messages"][0]["content"]
            content = narrative if "format" not in json else jsonlib.dumps({
                "safe": True, "reason": "Only table cells and a navigation-only pointer removed.",
                "missing_narrative": [], "changed_facts": []})
            return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    source = narrative + "\nSee Table 3.4 for examples of classes of neurotransmitters.\nTABLE 3.4\n" + "cell value " * 100
    assert await OllamaOcr(Settings()).optimize(source) == narrative
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    {"done_reason": "length", "message": {"content": "Partial text"}},
    {"message": {"content": ""}},
    {"message": {"content": "Summary"}},
])
async def test_review_rejects_truncated_empty_and_short_outputs(monkeypatch, result):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json):
            assert json["think"] is False
            assert json["options"]["temperature"] == 0
            prompt = json["messages"][0]["content"]
            assert "Omit standalone navigation-only pointers" in prompt
            assert "preserve any sentence that itself states a substantive fact" in prompt
            if "format" not in json:
                for instruction in ["Exclude entire tables", "figure/image", "side notes", "KEY FACT", "footnotes/endnotes", "Do not summarize or convert any excluded material"]:
                    assert instruction in prompt
            return httpx.Response(200, json=result, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(OcrError):
        await OllamaOcr(Settings()).optimize("The author wrote a complete narrative that must not be summarized.")


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate,safe,missing,changed,passes", [
    ("Main narrative stays intact.", True, [], [], True),
    ("[NO NARRATIVE]", True, [], [], True),
    ("A summary.", False, ["Missing paragraph"], [], False),
    ("Altered narrative.", True, [], ["Changed dose"], False),
    ("A summary.", True, ["Missing paragraph"], [], False),
    ("[NO NARRATIVE]", False, ["Main narrative"], [], False),
])
async def test_large_removals_require_content_audit(monkeypatch, candidate, safe, missing, changed, passes):
    import json as jsonlib
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            content = candidate if "format" not in json else jsonlib.dumps({"safe": safe, "reason": "Table rows were excluded.", "missing_narrative": missing, "changed_facts": changed})
            return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    source = "Main narrative stays intact.\nTABLE 1\n" + "cell value " * 100
    if passes:
        assert await OllamaOcr(Settings()).optimize(source) == ("" if candidate == "[NO NARRATIVE]" else candidate)
    else:
        with pytest.raises(OcrError):
            await OllamaOcr(Settings()).optimize(source)
    assert len(calls) == (2 if passes else 6) and "format" in calls[1]


@pytest.mark.asyncio
async def test_preservation_retry_restores_missing_narrative(monkeypatch):
    import json as jsonlib
    reports = iter([
        {"message": {"content": "Incomplete."}},
        {"message": {"content": jsonlib.dumps({"safe": False, "reason": "A sentence is missing", "missing_narrative": ["The narrative must remain complete."], "changed_facts": []})}},
        {"message": {"content": "The narrative must remain complete."}},
        {"message": {"content": jsonlib.dumps({"safe": True, "reason": "Only table rows removed", "missing_narrative": [], "changed_facts": []})}},
    ])
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json):
            calls.append(json)
            return httpx.Response(200, json=next(reports), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    assert await OllamaOcr(Settings()).optimize("The narrative must remain complete.\nTABLE 1\n" + "row data " * 50) == "The narrative must remain complete."
    assert len(calls) == 4 and "audit rejected" in calls[2]["messages"][0]["content"]
