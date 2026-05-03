"""
remove_bg/remover.py
Enhanced background removal with alpha matting for sharp, game-ready sprites.
"""

from __future__ import annotations
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageChops
from rembg import remove, new_session


# ── Session cache (avoid reloading model on every call) ──────────────────────

_session_cache: dict[str, object] = {}


def get_session(model_name: str = "u2net"):
    if model_name not in _session_cache:
        _session_cache[model_name] = new_session(model_name)
    return _session_cache[model_name]


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class RemoverConfig:
    # Model: u2net | u2netp | u2net_human_seg | isnet-general-use | silueta
    model: str = "u2net"

    # Alpha matting – dramatically improves edge sharpness
    alpha_matting: bool = True
    alpha_matting_foreground_threshold: int = 240   # pixels brighter → foreground
    alpha_matting_background_threshold: int = 10    # pixels darker  → background
    alpha_matting_erode_size: int = 10              # erosion kernel before matting

    # Post-processing edge refinement
    edge_refine: bool = True
    edge_blur_radius: float = 0.6    # feather the alpha edge slightly
    edge_contract: int = 0           # shrink mask to remove fringe (px)
    edge_expand: int = 0             # expand mask to keep thin details (px)

    # Colour decontamination (removes background colour bleed on edges)
    decontaminate: bool = True
    decontaminate_strength: float = 0.5   # 0-1

    # Output
    output_format: str = "PNG"   # PNG | WEBP
    webp_quality: int = 90


# ── Core removal ──────────────────────────────────────────────────────────────

def remove_background(
    img: Image.Image,
    cfg: RemoverConfig = RemoverConfig(),
    progress_cb=None,
) -> Image.Image:
    """
    Full pipeline:
      1. rembg with optional alpha matting
      2. Edge refinement (contract/expand, feather, decontaminate)
    Returns RGBA image.
    """
    session = get_session(cfg.model)
    orig = img.convert("RGBA")

    if progress_cb:
        progress_cb(10, "Running AI model…")

    # ── Step 1: rembg ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    orig.save(buf, format="PNG")
    buf.seek(0)

    result_bytes = remove(
        buf.read(),
        session=session,
        alpha_matting=cfg.alpha_matting,
        alpha_matting_foreground_threshold=cfg.alpha_matting_foreground_threshold,
        alpha_matting_background_threshold=cfg.alpha_matting_background_threshold,
        alpha_matting_erode_size=cfg.alpha_matting_erode_size,
    )
    result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")

    if progress_cb:
        progress_cb(55, "Refining edges…")

    # ── Step 2: edge refinement ──────────────────────────────────────────────
    if cfg.edge_refine:
        result = _refine_edges(result, cfg)

    if progress_cb:
        progress_cb(80, "Decontaminating colours…")

    if cfg.decontaminate:
        result = _decontaminate_edges(orig, result, cfg.decontaminate_strength)

    if progress_cb:
        progress_cb(95, "Finalising…")

    return result


# ── Edge refinement helpers ───────────────────────────────────────────────────

def _refine_edges(rgba: Image.Image, cfg: RemoverConfig) -> Image.Image:
    r, g, b, a = rgba.split()
    alpha = np.array(a, dtype=np.float32)

    # Contract (remove background fringe)
    if cfg.edge_contract > 0:
        from PIL import ImageFilter as IF
        a_pil = Image.fromarray(alpha.astype(np.uint8))
        for _ in range(cfg.edge_contract):
            a_pil = a_pil.filter(IF.MinFilter(3))
        alpha = np.array(a_pil, dtype=np.float32)

    # Expand (recover thin details lost by contract)
    if cfg.edge_expand > 0:
        from PIL import ImageFilter as IF
        a_pil = Image.fromarray(alpha.astype(np.uint8))
        for _ in range(cfg.edge_expand):
            a_pil = a_pil.filter(IF.MaxFilter(3))
        alpha = np.array(a_pil, dtype=np.float32)

    # Feather the edge
    if cfg.edge_blur_radius > 0:
        a_pil = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8))
        a_pil = a_pil.filter(ImageFilter.GaussianBlur(cfg.edge_blur_radius))
        # Restore hard pixels (full opaque / full transparent stay sharp)
        orig_a = np.array(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
        blurred = np.array(a_pil, dtype=np.float32)
        mask = (orig_a > 245) | (orig_a < 10)
        blurred[mask] = orig_a[mask]
        alpha = blurred

    new_alpha = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8))
    return Image.merge("RGBA", (r, g, b, new_alpha))


def _decontaminate_edges(
    orig_rgba: Image.Image,
    result_rgba: Image.Image,
    strength: float,
) -> Image.Image:
    """
    Removes background colour bleed on semi-transparent edge pixels.
    Uses a simple nearest-foreground-colour technique.
    """
    orig = np.array(orig_rgba, dtype=np.float32)
    res = np.array(result_rgba, dtype=np.float32)
    alpha = res[:, :, 3:4] / 255.0

    # Where alpha is in the semi-transparent range, nudge colour away from bg
    is_semi = (alpha > 0.05) & (alpha < 0.95)
    # Attempt: approximate pure foreground colour by alpha un-premult
    safe_alpha = np.where(alpha > 0.01, alpha, 1.0)
    decontam = res.copy()
    decontam[:, :, :3] = np.clip(
        (res[:, :, :3] - (1 - safe_alpha) * (255 - orig[:, :, :3])),
        0, 255,
    )
    blend = strength * decontam[:, :, :3] + (1 - strength) * res[:, :, :3]
    res[:, :, :3] = np.where(is_semi, blend, res[:, :, :3])
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8), "RGBA")


# ── Batch helper ──────────────────────────────────────────────────────────────

SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


def collect_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_EXT else []
    return sorted(p for p in path.rglob("*") if p.suffix.lower() in SUPPORTED_EXT)
