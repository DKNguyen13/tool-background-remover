"""
postprocess/refiner.py
Post-processing after background removal.
Game-dev focused: trim, padding, power-of-two resize, spritesheet utils.
"""

from __future__ import annotations
from dataclasses import dataclass
from PIL import Image
import numpy as np


@dataclass
class PostprocessConfig:
    # Resize back to original dimensions if we upscaled
    restore_original_size: bool = True

    # Trim transparent border
    auto_trim: bool = True

    # Add padding around sprite (px)
    padding: int = 2

    # Resize to nearest power-of-two (for game engines)
    power_of_two: bool = False
    max_pow2_side: int = 2048

    # Force exact output size (overrides power_of_two if set)
    output_size: tuple[int, int] | None = None

    # Threshold: alpha below this → fully transparent (cleans up noise)
    alpha_threshold: int = 10


def postprocess(
    rgba: Image.Image,
    original_size: tuple[int, int] | None = None,
    cfg: PostprocessConfig = PostprocessConfig(),
) -> Image.Image:
    # 1. Clean up near-zero alpha noise
    rgba = _threshold_alpha(rgba, cfg.alpha_threshold)

    # 2. Restore original size if we upscaled
    if cfg.restore_original_size and original_size and rgba.size != original_size:
        rgba = rgba.resize(original_size, Image.LANCZOS)
        rgba = _threshold_alpha(rgba, cfg.alpha_threshold)

    # 3. Trim transparent border
    if cfg.auto_trim:
        rgba = _trim(rgba)

    # 4. Add padding
    if cfg.padding > 0:
        rgba = _add_padding(rgba, cfg.padding)

    # 5. Force output size
    if cfg.output_size:
        rgba = rgba.resize(cfg.output_size, Image.LANCZOS)
    elif cfg.power_of_two:
        rgba = _resize_pow2(rgba, cfg.max_pow2_side)

    return rgba


# ── Helpers ───────────────────────────────────────────────────────────────────

def _threshold_alpha(rgba: Image.Image, thresh: int) -> Image.Image:
    arr = np.array(rgba)
    arr[:, :, 3] = np.where(arr[:, :, 3] < thresh, 0, arr[:, :, 3])
    return Image.fromarray(arr, "RGBA")


def _trim(rgba: Image.Image) -> Image.Image:
    """Crop to bounding box of non-transparent pixels."""
    arr = np.array(rgba)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any():
        return rgba
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    return Image.fromarray(arr[rmin:rmax+1, cmin:cmax+1], "RGBA")


def _add_padding(rgba: Image.Image, px: int) -> Image.Image:
    w, h = rgba.size
    padded = Image.new("RGBA", (w + px*2, h + px*2), (0, 0, 0, 0))
    padded.paste(rgba, (px, px))
    return padded


def _pow2_ceil(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def _resize_pow2(rgba: Image.Image, max_side: int) -> Image.Image:
    w, h = rgba.size
    pw = min(_pow2_ceil(w), max_side)
    ph = min(_pow2_ceil(h), max_side)
    if (pw, ph) != (w, h):
        rgba = rgba.resize((pw, ph), Image.LANCZOS)
    return rgba


# ── Spritesheet packer ──────────────────────────────────

def pack_spritesheet(
    images: list[Image.Image],
    cols: int = 4,
    cell_w: int | None = None,
    cell_h: int | None = None,
) -> tuple[Image.Image, list[dict]]:
    """
    Pack a list of RGBA sprites into a spritesheet.
    Returns (sheet_image, list of frame rects {x, y, w, h}).
    """
    if cell_w is None:
        cell_w = max(img.width for img in images)
    if cell_h is None:
        cell_h = max(img.height for img in images)

    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (0, 0, 0, 0))
    rects = []

    for i, img in enumerate(images):
        col = i % cols
        row = i // cols
        x = col * cell_w
        y = row * cell_h
        # Centre in cell
        ox = (cell_w - img.width) // 2
        oy = (cell_h - img.height) // 2
        sheet.paste(img, (x + ox, y + oy), img)
        rects.append({"x": x + ox, "y": y + oy, "w": img.width, "h": img.height})

    return sheet, rects
