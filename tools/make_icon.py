"""프로그램 아이콘(src/xrdcheck/data/icon.ico)을 만든다: 넓은 halo 위에 좁은 결정 피크 하나.

    python tools/make_icon.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "xrdcheck" / "data" / "icon.ico"


def draw(size: int = 256) -> Image.Image:
    s = 4 * size  # 크게 그린 뒤 줄여서 계단 현상 줄임
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = s * 0.06
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.18, fill=(38, 50, 72, 255))
    x = np.linspace(-1, 1, 400)
    y = 0.62 * np.exp(-(x / 0.42) ** 2) + 0.38 * np.exp(-((x - 0.02) / 0.035) ** 2)
    px = pad * 1.9 + (x + 1) / 2 * (s - 3.8 * pad)
    base = s - pad * 2.6
    py = base - y * (s - 5.2 * pad)
    pts = list(zip(px, py))
    d.polygon(pts + [(px[-1], base), (px[0], base)], fill=(106, 27, 154, 150))
    d.line(pts, fill=(255, 255, 255, 255), width=int(s * 0.035), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUT)
