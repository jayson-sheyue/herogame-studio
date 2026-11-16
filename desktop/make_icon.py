"""Render the shared original SVG to all macOS icon sizes with AppKit."""
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "studio/static/brand-icon.svg"


def main():
    target = Path(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="studio-icon-") as temporary:
        raster = Path(temporary) / "icon.png"
        subprocess.run(["/usr/bin/swift", "-module-cache-path", str(ROOT / "build/macos/swift-cache"),
                        str(ROOT / "desktop/render_icon.swift"), str(SOURCE), str(raster)], check=True)
        with Image.open(raster) as source:
            icon = source.convert("RGBA")
        if target.suffix.lower() == ".icns":
            iconset = Path(temporary) / "Studio.iconset"
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    pixels = size * scale
                    suffix = "@2x" if scale == 2 else ""
                    icon.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
                        iconset / f"icon_{size}x{size}{suffix}.png")
            subprocess.run(["/usr/bin/iconutil", "-c", "icns", str(iconset),
                            "--output", str(target.resolve())], check=True)
        else:
            icon.save(target, format="PNG")


if __name__ == "__main__":
    main()
