"""
preprocess/processor.py
Image preprocessing before background removal.
Improves model accuracy for game sprites.
"""

from __future__ import annotations
from dataclasses import dataclass
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np


@dataclass
class PreprocessConfig:
    # Upscale small images before processing (rembg works better on bigger images)
    upscale: bool = True
    upscale_min_side: int = 512   # if smaller than this, upscale to this

    # Sharpen before removal (helps model see edges better)
    pre_sharpen: bool = True
    sharpen_amount: float = 1.4   # 1.0 = no change, 2.0 = strong

    # Contrast boost (helps separate fg/bg)
    pre_contrast: bool = False
    contrast_amount: float = 1.2


def preprocess(img: Image.Image, cfg: PreprocessConfig = PreprocessConfig()):
    img = img.convert("RGB")
    original_size = img.size
    was_upscaled = False

    if cfg.upscale:
        min_side = min(img.size)
        if min_side < cfg.upscale_min_side:
            scale = cfg.upscale_min_side / min_side
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            was_upscaled = True

    if cfg.pre_contrast:
        img = ImageEnhance.Contrast(img).enhance(cfg.contrast_amount)

    if cfg.pre_sharpen:
        img = ImageEnhance.Sharpness(img).enhance(cfg.sharpen_amount)

    return img, original_size, was_upscaled
