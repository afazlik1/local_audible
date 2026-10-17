# Contributing

Follow README.md setup, keep changes focused, and add regression tests. Never attach private books, recordings, transcripts, model weights, credentials or .env files.

```sh
.venv312/bin/python -m pytest -q
npm run build
git diff --check
```

Optional browser tests require the API/UI running:

```sh
.venv312/bin/python -m pip install playwright
.venv312/bin/python -m playwright install chromium
.venv312/bin/python tests/browser_workflow.py
```

Browser workflow writes are mocked. Use synthetic documents in tests. Clearly distinguish implemented adapters from verified model/platform combinations.

Preserve source text and approved edits. Do not bypass layout completeness, warning acknowledgment, voice validation or strict weight checks to hide errors. Keep UI changes accessible and responsive. Review THIRD_PARTY.md before adding dependencies.

Do not rewrite history, force-push, change visibility or publish local data as part of routine development. See SECURITY.md for sensitive reporting.

Before committing, check both the author and committer identity. Use a project identity or your GitHub-provided no-reply email rather than an automatically generated workstation address. Review commit metadata as well as staged files; `.gitignore` does not protect commit identities.
