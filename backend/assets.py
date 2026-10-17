import base64
import io
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from .schemas import BookManifest, Page
from .storage import utc_now

try:
    from pillow_heif import register_heif_opener
except ImportError:
    register_heif_opener = None
else:
    register_heif_opener()

SUPPORTED_EXTENSIONS = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp"}


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def discover_pages(images_dir: Path, converted_dir: Path | None = None) -> BookManifest:
    paths = (
        sorted(
            (path for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
            key=natural_key,
        )
        if images_dir.exists()
        else []
    )
    pages = []
    for index, path in enumerate(paths, start=1):
        preview_url = f"/api/pages/{index}/image"
        if converted_dir is not None:
            normalize_image(path, converted_dir / f"page-{index:04d}.jpg")
            preview_url = f"/images/page-{index:04d}.jpg"
        pages.append(Page(id=f"page-{index:04d}", page_number=index, filename=path.name, preview_url=preview_url))
    return BookManifest(updated_at=utc_now(), pages=pages)


def normalize_image(path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_mtime >= path.stat().st_mtime:
        return output_path
    source_path = path
    temporary_path: Path | None = None
    if path.suffix.lower() in {".heic", ".heif"} and register_heif_opener is None:
        temporary_directory = Path(tempfile.mkdtemp(prefix="book-reader-heic-"))
        temporary_path = temporary_directory / "page.jpg"
        try:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(path), "--out", str(temporary_path)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError("HEIC conversion requires macOS sips or the pillow-heif package.") from error
        source_path = temporary_path
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2200, 2200))
        image.convert("RGB").save(output_path, format="JPEG", quality=88)
    if temporary_path:
        temporary_path.unlink(missing_ok=True)
        temporary_path.parent.rmdir()
    return output_path


def image_payload(path: Path) -> tuple[str, str]:
    output = io.BytesIO()
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2200, 2200))
        image.convert("RGB").save(output, format="JPEG", quality=88)
    return base64.b64encode(output.getvalue()).decode("ascii"), "image/jpeg"
