"""Optional browser check: python tests/browser_workflow.py (requires Playwright)."""
import json
import base64
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p, tempfile.TemporaryDirectory(prefix="book-reader-ui-") as folder:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Real server read-only smoke: never change the user's active manuscript.
        page.goto("http://127.0.0.1:5173")
        page.get_by_role("button", name="Choose image folder").wait_for()
        page.route("**/api/sample-voices/prepare", lambda route: route.fulfill(json={"id": "reference-test", "status": "complete", "progress": "Excerpt ready", "transcript": "Automatically transcribed reference.", "audio_url": "/audio/test-reference.wav", "error": None}))
        page.get_by_label("Speech model", exact=True).select_option("chatterbox")
        page.locator(".advanced-settings summary").click()
        assert page.get_by_label("Expressiveness / exaggeration").input_value() == "0.45"
        page.get_by_label("Expressiveness / exaggeration").fill("0.5")
        page.get_by_role("button", name="Reset model defaults").click()
        assert page.get_by_label("Expressiveness / exaggeration").input_value() == "0.45"
        page.get_by_label("Speech model", exact=True).select_option("fish")
        page.get_by_label("Sample voice", exact=True).select_option(index=1)
        assert page.get_by_label("Reference recording transcript").is_visible()
        from playwright.sync_api import expect
        expect(page.get_by_label("Reference recording transcript")).to_have_value("Automatically transcribed reference.")
        assert page.get_by_label("Narrator", exact=True).is_disabled()
        page.get_by_label("Speech model", exact=True).select_option("kokoro")
        assert page.get_by_role("button", name="Review text now").is_disabled()
        assert page.locator(".workflow > div > .eyebrow").all_text_contents() == ["01 / SOURCE", "02 / PREPARE", "03 / COVER · OPTIONAL", "04 / APPROVE"]
        assert page.locator(".workflow > div").nth(2).get_by_label("Upload cover image", exact=True).count() == 1
        page.screenshot(path=str(Path(folder) / "local-audible-desktop.png"), full_page=True)
        assert page.locator(".workspace").count() == 0
        assert page.locator(".player-bar").count() == 0
        assert page.get_by_role("button", name="Convert & optimize text").is_disabled()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(Path(folder) / "local-audible-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.close()

        # Exercise editing/submission using an isolated mocked API in a new tab.
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        state = {"title": "Browser test", "pages": [], "manuscript_text": "", "final_text": "", "manuscript_url": None,
                 "final_text_url": None, "audio_url": None, "book_status": "ready", "book_error": None,
                 "progress": "", "review_ready": False}
        submitted = []
        polls = [0]

        def handle(route):
            request = route.request
            path = request.url.split("5173")[-1]
            if path == "/api/voice-preview":
                if request.method == "POST":
                    assert request.post_data_json["model"] == "kokoro"
                    assert "text" not in request.post_data_json
                route.fulfill(json={"id": "preview-test", "status": "running" if request.method == "POST" else "complete", "progress": "Preview ready", "audio_url": None if request.method == "POST" else "/audio/preview.mp3", "error": None, "text": "A fixed comparison passage."})
                return
            if path == "/api/health":
                route.fulfill(json={"ollama": {"available": True, "model_found": True, "model": "test"}})
                return
            if path == "/api/voices":
                route.fulfill(json=[
                    {"id": "kokoro", "label": "Kokoro", "note": "US English", "available": True, "voices": [{"id": "af_heart", "label": "Heart"}, {"id": "am_michael", "label": "Michael"}]},
                    {"id": "piper", "label": "Piper", "note": "US English", "available": True, "voices": [{"id": "en_US-lessac-medium", "label": "Lessac"}]},
                    {"id": "chatterbox", "label": "Chatterbox", "note": "Default voice", "supports_reference": True, "available": True, "voices": [{"id": "default", "label": "Default"}]},
                ])
                return
            if path == "/api/sample-voices":
                route.fulfill(json=[{"id": "sample.mp3", "label": "sample.mp3"}])
                return
            if path == "/api/book/cover":
                route.fulfill(json={"id": "a" * 32, "url": "/test-cover.jpg"})
                return
            if path == "/api/book/upload":
                assert "page1.png" in request.post_data_buffer.decode("latin1")
                state["pages"] = [{"id": "page1", "filename": "page1.png", "preview_url": "/test-page.png"}]
            elif path == "/api/book/document":
                state.update(source_type="pdf", source_name="chapter.pdf", title="chapter", book_status="ready", review_ready=False,
                             manuscript_text="", final_text="", manuscript_url=None, final_text_url=None, audio_url=None,
                             progress="Document text extracted without OCR.",
                             pages=[{"id": "section-0001", "filename": "Page 1", "preview_url": "", "text": "Direct document text."}])
            elif path == "/api/book/prepare":
                state["book_status"] = "assembling"
                polls[0] = 0
            elif path == "/api/book/text":
                state["final_text"] = request.post_data_json["text"]
            elif path == "/api/book/audio":
                assert request.post_data_json["model"] == "piper"
                assert request.post_data_json["narrator"] == "en_US-lessac-medium"
                assert request.post_data_json["cover_id"] == "a" * 32
                assert request.post_data_json["sample_voice"] is None
                submitted.append(request.post_data_json["text"])
                state.update(final_text=submitted[-1], book_status="audio", progress="Narrating passage 1 of 2")
                polls[0] = 0
            elif path == "/api/book" and state["book_status"] in {"assembling", "audio"}:
                polls[0] += 1
                if polls[0] >= 2:
                    if state["book_status"] == "assembling":
                        state.update(book_status="review", manuscript_text="Raw narrative.", final_text="Reviewed narrative.", review_ready=True)
                        if state.get("source_type") == "pdf":
                            state.update(selected_text="Visually selected narrative.", selected_text_url="/files/selected.txt",
                                         layout_report_url="/files/layout.json")
                            state["pages"][0]["preview_url"] = "/test-page.png"
                    else:
                        state.update(book_status="complete", audio_url="/test.mp3")
            route.fulfill(status=202 if request.method == "POST" and path != "/api/book/upload" else 200, content_type="application/json", body=json.dumps(state))

        page.route("**/api/**", handle)
        page.goto("http://127.0.0.1:5173")
        assert page.get_by_role("button", name="Approve text & generate audio").is_disabled()
        page.get_by_role("button", name="Generate 10-second preview").click()
        page.get_by_label("Voice preview", exact=True).wait_for()
        assert page.get_by_role("button", name="Play", exact=True).is_enabled()
        assert page.get_by_label("Preview text", exact=True).input_value()
        assert state["pages"] == [] and not submitted
        page.get_by_label("Narrator", exact=True).select_option("am_michael")
        assert page.get_by_label("Voice preview", exact=True).count() == 0
        assert page.get_by_text("Settings changed. Generate a new preview to hear this selection.").is_visible()
        (Path(folder) / "page1.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII="))
        page.locator('input[webkitdirectory]').set_input_files(folder)
        page.get_by_role("button", name="Convert & optimize text").click()
        assert page.get_by_role("button", name="Review text now").is_disabled()
        editor = page.get_by_role("textbox", name="Narration text")
        from playwright.sync_api import expect
        expect(editor).to_be_enabled(timeout=15000)
        expect(editor).to_have_value("Reviewed narrative.")
        expect(page.locator(".ready-notice")).to_have_count(0)
        expect(page.locator(".workflow > div").nth(1).get_by_role("button", name="Review text now")).to_be_visible()
        page.get_by_role("button", name="Review text now").click()
        expect(editor).to_be_focused()
        page.get_by_label("Upload cover image", exact=True).set_input_files(str(Path(folder) / "page1.png"))
        page.get_by_role("button", name="Remove cover").wait_for()
        page.get_by_role("button", name="Remove cover").click()
        expect(page.get_by_alt_text("Selected MP3 cover")).to_have_count(0)
        page.get_by_label("Upload cover image", exact=True).set_input_files(str(Path(folder) / "page1.png"))
        page.get_by_role("button", name="Remove cover").wait_for()
        page.get_by_label("Speech model", exact=True).select_option("chatterbox")
        expect(page.get_by_label("Narrator", exact=True)).to_have_value("default")
        expect(page.get_by_label("Sample voice", exact=True)).to_have_value("")
        expect(page.locator(".workflow > div").nth(3).get_by_label("Sample voice", exact=True)).to_be_visible()
        page.get_by_label("Sample voice", exact=True).select_option("sample.mp3")
        expect(page.get_by_label("Narrator", exact=True)).to_be_disabled()
        page.get_by_label("Sample voice", exact=True).select_option("")
        expect(page.get_by_label("Narrator", exact=True)).to_be_enabled()
        page.get_by_label("Sample voice", exact=True).select_option("sample.mp3")
        expect(page.get_by_label("Narrator", exact=True)).to_be_disabled()
        page.get_by_label("Speech model", exact=True).select_option("piper")
        expect(page.get_by_label("Sample voice", exact=True)).to_have_count(0)
        expect(page.get_by_label("Narrator", exact=True)).to_have_value("en_US-lessac-medium")
        editor.fill("My final correction, with natural punctuation!")
        page.get_by_label("Preview text", exact=True).fill("")
        assert page.get_by_role("button", name="Approve text & generate audio").is_enabled()
        page.get_by_role("button", name="Approve text & generate audio").click()
        expect(page.locator(".command-bar")).to_contain_text("Narrating passage 1 of 2")
        expect(page.get_by_role("progressbar", name="Narration progress")).to_have_count(0)
        page.get_by_role("link", name="Download MP3").wait_for(timeout=15000)
        assert submitted == ["My final correction, with natural punctuation!"]
        page.get_by_label("PDF or Word document", exact=True).set_input_files({"name": "chapter.pdf", "mimeType": "application/pdf", "buffer": b"mock document"})
        expect(page.get_by_role("button", name="Optimize text", exact=True)).to_be_enabled()
        expect(page.locator(".document-source")).to_contain_text("Direct document text.")
        expect(page.locator(".player-bar")).to_have_count(0)
        expect(page.get_by_role("button", name="Review text now")).to_be_disabled()
        page.get_by_role("button", name="Optimize text", exact=True).click()
        expect(editor).to_be_enabled(timeout=15000)
        expect(page.get_by_text("Compare extracted document text", exact=True)).to_be_visible()
        page.get_by_text("PDF layout selection · inspect included text", exact=True).click()
        expect(page.get_by_role("link", name="Download region classification report")).to_be_visible()
        expect(page.get_by_role("link", name="Download selected text before optimization")).to_be_visible()
        expect(page.get_by_text("Visually selected narrative.", exact=True)).to_be_visible()
        # A failed page can fetch a recovered job without re-uploading or restarting it.
        failed = dict(state, book_status="error", review_ready=False, final_text="",
                      book_error="Text preparation failed.", progress="Preparation failed.")
        page.route("**/api/book/prepare", lambda route: route.fulfill(json=failed))
        page.get_by_role("button", name="Optimize text", exact=True).click()
        expect(page.get_by_role("button", name="Review text now")).to_be_disabled()
        state.update(book_status="review", review_ready=True, book_error=None,
                     final_text="Recovered optimized manuscript.")
        page.get_by_role("button", name="Check preparation status").click()
        expect(editor).to_have_value("Recovered optimized manuscript.")
        expect(page.get_by_role("button", name="Review text now")).to_be_enabled()
        failed["review_fallback_available"] = True
        page.get_by_role("button", name="Optimize text", exact=True).click()
        expect(editor).to_be_disabled()
        manual = dict(failed, review_ready=True, review_fallback_available=False,
                      book_status="review", book_error=None, final_text="Original text to check.",
                      review_warnings=["Original text is not optimized. Remove tables manually."])
        page.route("**/api/book/review-with-warnings", lambda route: route.fulfill(json=manual))
        page.get_by_role("button", name="Review text with warnings", exact=True).click()
        expect(editor).to_be_enabled()
        expect(editor).to_have_value("Original text to check.")
        expect(page.get_by_role("heading", name="Review required · warnings")).to_be_visible()
        expect(page.locator(".review-warnings")).to_contain_text("not optimized")
        expect(page.get_by_role("button", name="Approve text & generate audio")).to_be_enabled()
        assert not errors, errors
        browser.close()
        print("PASS: clean initial screen, responsive layout, folder upload, review gate, latest-text submission, audio controls; no JS errors.")


if __name__ == "__main__":
    main()
