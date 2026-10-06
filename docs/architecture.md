# Architecture and configuration

## Components

- `src/`: React/Vite UI, background-job polling and explicit approval.
- `backend/main.py`: FastAPI routes, in-process serialization and persisted revisions.
- `backend/pdf_layout.py`: bounded rendering, numbered-region extraction, strict classification and caching.
- `backend/ocr.py`: Ollama image OCR, narration editing and audits.
- `backend/documents.py`: embedded PDF/Word text extraction and limits.
- `backend/narration.py`: integration, chunking and paragraph pauses.
- `backend/speech*.py`, `voices.py`, `tts_options.py`: registry, validated settings, subprocess workers and service adapters.
- `backend/reference_voice.py`, `transcribe_reference.py`: references, snapshots and local transcription.
- `backend/mp3.py`: encoding, cover metadata and output validation.
- `backend/cli.py`, `tts.py`: independent image-OCR/Kokoro-WAV CLI.

## Preparation and approval

Images use OCR and integration; Word uses embedded text. PDFs keep raw extraction, then classify line-sized regions using page images and coordinates. Every ID must appear exactly once. Unknown, duplicate or missing IDs fail after a bounded retry. Uncertain regions are retained with warnings. The model chooses IDs; assembly retains original words in selected reading order.

PDF editing/audits receive only selected text, not discarded sidebars/tables. Every PDF passage is audited. Other sources use deletion-triggered audits. Editing repairs wraps, punctuation and pacing without intentional paraphrasing. Bounded correction attempts do not convert persistent failures into success.

Manual review explicitly combines validated earlier passages with source text for all remaining passages, never a partial book. Older failures can open full raw extraction. Warnings require acknowledgment at the audio endpoint. The exact current editor text is saved and narrated without further LLM editing.

Reports include excluded text and coordinates. Structural validation is not proof of correct classification; inspect source page images.

## Runtime and configuration

Run **one API process/worker**. Locks/job state are in-process, not distributed. Restart marks interrupted work for retry. Vite proxies /api, /audio, /images and /files to port 8000. There is no multi-user isolation, authentication or production deployment configuration.

Copy .env.example to .env. Defaults retain compatibility with the development setup:

| Variable | Purpose |
| --- | --- |
| OLLAMA_BASE_URL | Default loopback:11434; remote values send inputs to that server |
| OLLAMA_MODEL | Exact installed vision-model tag |
| OCR_TIMEOUT | Per-request seconds, default 1800 |
| BOOK_IMAGES_DIR | Legacy server-side image discovery directory |
| DATA_DIR | Local workspace, default data |
| TTS_PROVIDER | Legacy CLI setting; web model is explicit |
| KOKORO_VOICE | CLI voice default, af_heart |
| KOKORO_LANG_CODE | CLI language default, a |

External service opt-ins are exported process variables documented in models.md. Speech workers are disposable subprocesses; first-use downloads use engine-specific caches. Keep speech environments separate.

## Limits and persistence

Documents: 50 MB uploaded, 500 PDF pages, two million characters, 100 MB expanded DOCX. Encrypted/malformed/scanned PDFs are rejected. Images: 1,000 files, 30 MB each, 1 GB total. Covers: 5 MB / 16 megapixels. References: 50 MB.

PDF images are rendered up to twice page-point resolution, bounded to 2200 pixels on the longest side. A page over 350 regions or 28,000 characters fails instead of truncating context. Classification caches include source hash, page, model name and policy version; replacing weights under the same model name is not detected automatically.

Raw, selected, reviewed and approved revisions are separate. Originals, histories, reports and recordings remain until manually removed. Stop processing and back up important material before cleaning data/. Initial UI state intentionally does not reopen the previous book.

Tests use synthetic fixtures and mocked models. Optional browser tests mock workflow writes. Live layout checks covered representative sidebar/table/figure pages, not every document or engine.
