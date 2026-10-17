import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import BookManifest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManifestStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "manifest.json"

    def load(self) -> BookManifest | None:
        if not self.path.exists():
            return None
        return BookManifest.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, manifest: BookManifest) -> BookManifest:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        manifest.updated_at = utc_now()
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        temporary_path.replace(self.path)
        return manifest
