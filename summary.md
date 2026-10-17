# Local Audible — implementation summary

## Implemented capabilities

- Image OCR, embedded PDF/Word import, editable review, optional cover and explicit audio approval.
- Hybrid PDF images plus numbered regions: exact ID coverage, original-word assembly, uncertainty warnings, preserved raw text and downloadable classification reports.
- Audits compare PDF narration against selected text only. Failed validation offers explicit complete-draft manual review rather than silently approving a partial book.
- Kokoro, Piper, Chatterbox and optional local adapters; English voice selection; reference transcription; advanced controls; ten-second previews; passage progress and MP3 output.
- Separate image-OCR/Kokoro-WAV CLI and immutable web revisions.
- Public setup, architecture, model, security and contribution documentation; AGPL-3.0-only project licensing and separate dependency notices.

## Verification and limitations

Previously recorded verification: 79 backend tests, frontend build and browser workflow passed; editable package installation and both CLI entry points worked. Tests use synthetic fixtures and mocked models. Representative hybrid layout tests covered sidebar/body, table-only and diagram/body pages. These checks do not establish correctness for every document or model. Human review remains essential.

## October 17, 2026: publication privacy review

Reviewed the tracked files, both advertised public branches, and all objects reachable from those branches. Removed development-machine attribution, a workstation-specific model default, and personal maintenance/recovery notes. The example configuration now requires an explicitly selected vision-model tag. Existing private configuration and user data were not modified. Hardware compatibility requirements remain documented because they affect installation, not because they identify a particular machine.

The audit detected identifying author/committer metadata in published history. File edits alone do not remove it. Sensitive values are intentionally not repeated in this file.

Added contributor guidance on publication identities and commit-metadata review. Pattern scanning found no credential matches in the inspected tracked contents or reachable public objects; this is a heuristic result, not a guarantee. Hosting-provider caches, unreachable historical objects and third-party copies are outside this verification.

Public inspection covered 60 tracked files, two commits and 62 unique historical file blobs. The repository returned no issues, pull requests, releases, workflow runs or commit comments. Post-change verification: 81 backend tests passed, including new configuration-default and override tests; `git diff --check` passed. No frontend changes were made.

## Authorized sanitized-history publication

The owner authorized replacing both public branches, `main` and `master`, with sanitized root history. This release uses the neutral author and committer identity `Local Audible Contributors <maintainers@local-audible.invalid>`; the reserved `.invalid` address is an identity placeholder, not a contact address. Previous personal metadata and historical file versions are not parents of this release.

Publication uses an atomic push with exact expected-commit leases for both branches, followed by verification from a fresh public clone. The repository-local identity is also set to the neutral identity to prevent subsequent workstation-attributed commits. Global configuration, repository visibility and private runtime files are unchanged. Old local recovery objects, hosting-provider retention and third-party copies require separate handling; replacement branch history is not a guarantee of complete erasure.

Maintained behavior and setup live in README.md and docs/. Private source material, runtime data and local configuration must remain excluded from publication.
