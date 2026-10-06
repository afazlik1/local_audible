from pathlib import Path

from backend.schemas import BookManifest, Page
from backend.storage import ManifestStore


def test_manifest_store_round_trips_atomically(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path / "data")
    manifest = BookManifest(
        updated_at="now",
        pages=[Page(id="page-0001", page_number=1, filename="page.heic", preview_url="/image")],
    )

    store.save(manifest)
    loaded = store.load()

    assert loaded is not None
    assert loaded.pages[0].filename == "page.heic"
    assert not (tmp_path / "data" / "manifest.tmp").exists()
