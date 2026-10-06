# Local Audible — implementation summary

## October 6, 2026: remote history cleanup

After explicit authorization, replaced the old remote main branch with the clean root history from master, using an exact-commit force-with-lease guard. Both branches now use the image-free release history. GitHub's default branch remains main; repository visibility and name were not changed. No remote tags or pull-request refs were advertised during inspection. Updated the security notes and synchronized this documentation to both branches.

This supersedes the publication holds and unchanged-remote statements in the historical entries below. Old commits are no longer reachable from the inspected branches; this does not certify deletion of hosting-provider caches, hidden refs, forks, existing clones or the local recovery archive. Those require separate verification or host support if complete erasure is required.

## October 6, 2026: clean master publication

The owner authorized publishing the cleaned project. Prepared a new root commit on master containing source, tests, documentation and AGPL-3.0-only licensing, with local data, recordings, environments and generated files excluded. Publication targets the existing book_reader repository without force-pushing or deleting main. The old remote main/history still needs separate handling before making the repository public; publishing a clean master does not erase those objects or change the default branch.

## October 6, 2026: local history reset and source-image cleanup

At the owner's request, removed the local book images directory and old Git metadata from the project into an external temporary recovery archive. Initialized a new empty master branch, retaining only the existing origin URL; no old commits were fetched, no commit was created and nothing was pushed. Removed regenerated Python cache files. Preserved application source, documentation, user documents/manuscripts/audio, model assets and active dependency environments.

This supersedes the earlier decision to retain local Git history. GitHub's existing main branch/history is unchanged and may still expose historical book images if made public. Remote history cleanup/publication requires a separate explicit action. Copies of user images may also remain in ignored runtime upload/preview directories; these were not treated as disposable originals or deleted blindly.

## October 6, 2026: README system diagram

Added a GitHub-renderable Mermaid architecture diagram near the top of the README. It separates image/PDF/Word preparation, visual PDF selection, narration optimization and validation, explicit human review, and local speech/MP3 output. Includes manual-review fallback, reference/settings inputs and optional artwork. Supporting notes clarify selected-text auditing, independent previews, local storage and remote-endpoint caveats. Documentation-only change; publication remains paused.

## October 6, 2026: public-repository preparation

Renamed the app, frontend package and Python distribution to Local Audible. Kept the old CLI entry point and service opt-in names for compatibility. Replaced workstation-specific development notes with public setup, model, architecture, security and contribution documentation. Project license: AGPL-3.0-only.

Removed unused legacy schemas/refinement code. Moved the obsolete .venv, legacy egg metadata, compiled/test caches, OS metadata and generated frontend build into a recoverable local cleanup archive (about 72 MB including documentation backups). Original development notes are preserved there. User books, recordings, manuscripts, model assets and working environments remain private and ignored. Replaced the private-document test dependency with a synthetic multi-page PDF and made browser screenshot paths portable.

Publication was initially paused because Git history contains book-page images. The later local reset is recorded above; remote publication remains paused. Repository renaming was skipped at the owner's request. No remote history rewrite, branch deletion, force-push or visibility change has been performed.

## Implemented capabilities

- Image OCR, embedded PDF/Word import, editable review, optional cover and explicit audio approval.
- Hybrid PDF images plus numbered regions: exact ID coverage, original-word assembly, uncertainty warnings, preserved raw text and downloadable classification reports.
- Audits compare PDF narration against selected text only. Failed validation offers explicit complete-draft manual review rather than silently approving a partial book.
- Kokoro, Piper, Chatterbox and optional local adapters; English voice selection; reference transcription; advanced controls; ten-second previews; passage progress and MP3 output.
- Separate image-OCR/Kokoro-WAV CLI and immutable web revisions.

## Verification and limitations

Post-cleanup verification: 79 backend tests passed, frontend build and browser workflow passed, editable Python package installation succeeded, and both local-audible and book-reader CLI help commands worked. Common credential-pattern scans found no matches in the scanned source/history; this is not a guarantee of complete secret detection. Historical book images remain the publication blocker. Live hybrid tests previously covered sidebar/body, table-only and diagram/body pages. This does not establish correctness for every document/model. Human review remains essential.

Maintained behavior and setup live in README.md and docs/. Personal sample filenames, absolute workstation paths and generated content are intentionally excluded from public documentation.
