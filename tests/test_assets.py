from pathlib import Path

from backend.assets import natural_key


def test_natural_key_orders_camera_pages_numerically() -> None:
    paths = [Path("IMG_0882.HEIC"), Path("IMG_0880.HEIC"), Path("IMG_08810.HEIC")]
    assert [path.name for path in sorted(paths, key=natural_key)] == [
        "IMG_0880.HEIC",
        "IMG_0882.HEIC",
        "IMG_08810.HEIC",
    ]
