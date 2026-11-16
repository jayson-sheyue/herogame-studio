"""Original code-drawn icon; no downloaded assets or user artwork."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw

image = Image.new("RGBA", (1024, 1024))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((30, 30, 994, 994), radius=220, fill="#141a23", outline="#455260", width=12)
draw.rounded_rectangle((174, 174, 850, 850), radius=115, fill="#efb455")
# Pixel canvas plus pencil: visible even at Dock sizes.
for x, y in [(285, 285), (435, 285), (285, 435), (435, 435)]:
    draw.rectangle((x, y, x + 110, y + 110), fill="#202936")
draw.polygon([(485, 690), (700, 475), (778, 553), (563, 768), (470, 785)], fill="#202936")
draw.polygon([(470, 785), (489, 703), (552, 766)], fill="#fff0d4")
image.save(Path(sys.argv[1]), format="ICNS")
