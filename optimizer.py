"""
optimize/optimizer.py
Lossless and lossy compression for game-ready sprites.
"""

from __future__ import annotations
import io
from dataclasses import dataclass
from pathlib import Path
from PIL import Image


@dataclass
class OptimizeConfig:
    format: str = "PNG"          # PNG | WEBP
    png_compress: int = 6        # 0-9, higher = smaller file but slower
    webp_quality: int = 90       # 1-100
    webp_lossless: bool = True   # True recommended for sprites


def save_optimized(
    img: Image.Image,
    output_path: Path,
    cfg: OptimizeConfig = OptimizeConfig(),
) -> int:
    """Save image and return file size in bytes."""
    output_path = Path(output_path)
    fmt = cfg.format.upper()

    if fmt == "WEBP":
        output_path = output_path.with_suffix(".webp")
        img.save(
            output_path,
            format="WEBP",
            quality=cfg.webp_quality,
            lossless=cfg.webp_lossless,
        )
    else:
        output_path = output_path.with_suffix(".png")
        img.save(
            output_path,
            format="PNG",
            optimize=True,
            compress_level=cfg.png_compress,
        )

    return output_path.stat().st_size


def estimate_size(img: Image.Image, cfg: OptimizeConfig = OptimizeConfig()) -> int:
    """Estimate output file size without writing to disk."""
    buf = io.BytesIO()
    fmt = cfg.format.upper()
    if fmt == "WEBP":
        img.save(buf, format="WEBP", quality=cfg.webp_quality, lossless=cfg.webp_lossless)
    else:
        img.save(buf, format="PNG", optimize=True, compress_level=cfg.png_compress)
    return buf.tell()
