"""Render the shared original SVG to all macOS icon sizes with AppKit."""
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "studio/static/brand-icon.svg"
# Apple icon pixel sizes (1x and 2x of 16/32/128/256/512).
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)


def write_icns(icon: Image.Image, target: Path) -> None:
    """Write a multi-resolution .icns. Prefer Pillow; fall back to iconutil."""
    variants = [icon.resize((size, size), Image.Resampling.LANCZOS) for size in ICNS_SIZES]
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        variants[0].save(target, format="ICNS", append_images=variants[1:])
        if target.is_file() and target.stat().st_size > 0:
            return
    except Exception:
        pass
    with tempfile.TemporaryDirectory(prefix="studio-iconset-") as temporary:
        iconset = Path(temporary) / "Studio.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                suffix = "@2x" if scale == 2 else ""
                icon.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
                    iconset / f"icon_{size}x{size}{suffix}.png"
                )
        subprocess.run(
            ["/usr/bin/iconutil", "-c", "icns", str(iconset), "--output", str(target.resolve())],
            check=True,
        )


def main():
    target = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="studio-icon-") as temporary:
        raster = Path(temporary) / "icon.png"
        subprocess.run(
            [
                "/usr/bin/swift",
                "-module-cache-path",
                str(ROOT / "build/macos/swift-cache"),
                str(ROOT / "desktop/render_icon.swift"),
                str(SOURCE),
                str(raster),
            ],
            check=True,
        )
        with Image.open(raster) as source:
            icon = source.convert("RGBA")
        if target.suffix.lower() == ".icns":
            write_icns(icon, target.resolve())
        else:
            icon.save(target, format="PNG")


if __name__ == "__main__":
    main()
