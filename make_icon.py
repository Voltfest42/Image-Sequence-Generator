"""Generate assets/icon.ico (a stack of three frames). Run once; the result is committed."""

import os

from PIL import Image, ImageDraw

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=96, fill=(30, 34, 44, 255))
colors = [(70, 90, 140, 255), (50, 140, 220, 255), (240, 245, 255, 255)]
for i, c in enumerate(colors):
    off = i * 56
    box = (96 + off - 56, 168 - off + 56, 96 + off + 232, 168 - off + 56 + 232)
    d.rounded_rectangle(box, radius=24, fill=c, outline=(15, 17, 24, 255), width=6)

os.makedirs("assets", exist_ok=True)
img.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("assets/icon.ico written")
