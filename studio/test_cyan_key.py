"""Regression coverage for safe cyan-keying of portrait and sprite sheets."""

from __future__ import annotations

import unittest
from io import BytesIO

from PIL import Image

from score import cyan_key_png


def keyed(image: Image.Image, *, frames: int = 1) -> Image.Image:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return Image.open(BytesIO(cyan_key_png(buf.getvalue(), frames=frames, strict=True))).convert("RGBA")


class CyanKeyTests(unittest.TestCase):
    def test_removes_exact_and_near_cyan_background(self) -> None:
        image = Image.new("RGBA", (18, 18), (0, 255, 255, 255))
        # A slightly tinted background fringe must join the same outside flood.
        image.putpixel((1, 1), (32, 232, 229, 255))
        image.putpixel((9, 9), (35, 35, 48, 255))
        out = keyed(image)
        self.assertEqual(out.getpixel((0, 0))[3], 0)
        self.assertEqual(out.getpixel((1, 1))[3], 0)
        self.assertEqual(out.getpixel((9, 9))[3], 255)

    def test_preserves_enclosed_cyan_wing_facet(self) -> None:
        image = Image.new("RGBA", (22, 22), (0, 255, 255, 255))
        # One-pixel dark outline around a bright cyan wing/gem detail.
        for x in range(5, 17):
            image.putpixel((x, 5), (30, 35, 42, 255))
            image.putpixel((x, 16), (30, 35, 42, 255))
        for y in range(5, 17):
            image.putpixel((5, y), (30, 35, 42, 255))
            image.putpixel((16, y), (30, 35, 42, 255))
        out = keyed(image)
        self.assertEqual(out.getpixel((10, 10))[3], 255)
        self.assertEqual(out.getpixel((10, 10))[:3], (0, 255, 255))

    def test_preserves_noncyan_teal_subject_at_canvas_edge(self) -> None:
        image = Image.new("RGBA", (18, 18), (0, 255, 255, 255))
        # Emerald/teal clothing can touch the crop edge and must survive.
        for y in range(5, 13):
            image.putpixel((0, y), (23, 139, 112, 255))
            image.putpixel((1, y), (23, 139, 112, 255))
        out = keyed(image)
        self.assertEqual(out.getpixel((0, 8))[3], 255)

    def test_clears_diagonal_background_gap(self) -> None:
        image = Image.new("RGBA", (16, 16), (0, 255, 255, 255))
        # A diagonal-only gap should remain connected to the background.
        for i in range(4, 12):
            image.putpixel((i, i), (25, 25, 30, 255))
        out = keyed(image)
        self.assertEqual(out.getpixel((3, 4))[3], 0)

    def test_preserves_existing_transparent_subject_hole(self) -> None:
        image = Image.new("RGBA", (18, 18), (0, 255, 255, 255))
        image.putpixel((9, 9), (255, 255, 255, 0))
        image.putpixel((8, 9), (40, 40, 50, 255))
        out = keyed(image)
        self.assertEqual(out.getpixel((9, 9))[3], 0)
        self.assertEqual(out.getpixel((8, 9))[3], 255)

    def test_multiple_frames_do_not_leave_cyan_separator(self) -> None:
        image = Image.new("RGBA", (24, 12), (0, 255, 255, 255))
        image.putpixel((4, 6), (35, 35, 48, 255))
        image.putpixel((18, 6), (35, 35, 48, 255))
        out = keyed(image, frames=2)
        self.assertEqual(out.getpixel((12, 6))[3], 0)
        self.assertEqual(out.getpixel((4, 6))[3], 255)
        self.assertEqual(out.getpixel((18, 6))[3], 255)


if __name__ == "__main__":
    unittest.main()
