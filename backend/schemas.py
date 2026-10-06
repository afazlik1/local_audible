from typing import Literal

from pydantic import BaseModel, Field


PageStatus = Literal["ready", "processing", "review", "audio", "error"]


class Page(BaseModel):
    ocr_version: int = 0
    id: str
    page_number: int
    filename: str
    preview_url: str
    text: str = ""
    status: PageStatus = "ready"
    error: str | None = None
    audio_url: str | None = None


class BookManifest(BaseModel):
    source_type: Literal["images", "pdf", "docx"] = "images"
    source_name: str | None = None
    advanced: dict = Field(default_factory=dict)
    reference_text: str = ""
    sample_voice: str | None = None
    sample_snapshot: str | None = None
    cover_id: str | None = None
    tts_model: str = "kokoro"
    narrator: str = "af_heart"
    source_dir: str | None = None
    progress: str = ""
    review_ready: bool = False
    review_fallback_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    selected_text: str = ""
    selected_text_url: str | None = None
    layout_report_url: str | None = None
    title: str = "Untitled book"
    pages: list[Page] = Field(default_factory=list)
    manuscript_text: str = ""
    final_text: str = ""
    manuscript_url: str | None = None
    final_text_url: str | None = None
    audio_url: str | None = None
    book_status: Literal["ready", "assembling", "refining", "review", "audio", "complete", "error"] = "ready"
    book_error: str | None = None
    updated_at: str


class ManuscriptUpdate(BaseModel):
    text: str


class AudioSubmit(ManuscriptUpdate):
    acknowledge_review_warnings: bool = False
    advanced: dict = Field(default_factory=dict)
    reference_text: str = Field(default="", max_length=4000)
    sample_voice: str | None = None
    cover_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    model: str = "kokoro"
    narrator: str = "af_heart"


class PreviewSubmit(AudioSubmit):
    text: str = ""
    preview_text: str | None = Field(default=None, max_length=2000)
