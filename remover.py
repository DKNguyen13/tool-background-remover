"""
remove_bg/remover.py
Enhanced background removal with alpha matting for sharp, game-ready sprites.
v2: Added white-BG cleanup, colour despill, and solid-BG detection.
"""

from __future__ import annotations
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from rembg import remove, new_session


# ── Session cache ─────────────────────────────────────────────────────────────

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
    alpha_matting_foreground_threshold: int = 240
    alpha_matting_background_threshold: int = 10
    alpha_matting_erode_size: int = 10

    # Post-processing edge refinement
    edge_refine: bool = True
    edge_blur_radius: float = 0.6
    edge_contract: int = 0
    edge_expand: int = 0

    # ── NEW: White / solid BG cleanup ────────────────────────────────────────
    # Kills residual bright pixels left after AI removal (white bg remnants)
    white_bg_cleanup: bool = True
    white_bg_threshold: int = 220       # RGB brightness above this → kill alpha
    white_bg_kill_semi: bool = True     # also kill semi-transparent bright pixels

    # Recover true sprite colour by un-premultiplying against background colour
    despill: bool = True
    despill_bg_color: tuple[int, int, int] = (255, 255, 255)  # white by default
    despill_strength: float = 0.85      # 0–1

    # Auto-detect background colour from image corners
    auto_detect_bg_color: bool = True

    # Colour decontamination (generic, any bg)
    decontaminate: bool = True
    decontaminate_strength: float = 0.5

    # Output
    output_format: str = "PNG"
    webp_quality: int = 90


# ── Core removal ──────────────────────────────────────────────────────────────

def remove_background(
    img: Image.Image,
    cfg: RemoverConfig = RemoverConfig(),
    progress_cb=None,
) -> Image.Image:
    """
    Full pipeline:
      0. Auto-detect BG colour
      1. rembg with optional alpha matting
      2. White/solid BG cleanup  ← NEW
      3. Colour despill          ← NEW
      4. Edge refinement
      5. Generic decontamination
    Returns RGBA image.
    """
    orig = img.convert("RGBA")
    session = get_session(cfg.model)

    # ── Step 0: detect BG colour ─────────────────────────────────────────────
    bg_color = cfg.despill_bg_color
    if cfg.auto_detect_bg_color:
        bg_color = _detect_bg_color(orig)

    if progress_cb:
        progress_cb(8, "Running AI model…")

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
        progress_cb(50, "Cleaning up BG remnants…")

    # ── Step 2: white/solid BG cleanup ───────────────────────────────────────
    if cfg.white_bg_cleanup:
        result = _cleanup_solid_bg(result, bg_color, cfg)

    if progress_cb:
        progress_cb(65, "Despilling colours…")

    # ── Step 3: colour despill ───────────────────────────────────────────────
    if cfg.despill:
        result = _despill(result, bg_color, cfg.despill_strength)

    if progress_cb:
        progress_cb(75, "Refining edges…")

    # ── Step 4: edge refinement ───────────────────────────────────────────────
    if cfg.edge_refine:
        result = _refine_edges(result, cfg)

    if progress_cb:
        progress_cb(88, "Decontaminating colours…")

    if cfg.decontaminate:
        result = _decontaminate_edges(orig, result, cfg.decontaminate_strength)

    if progress_cb:
        progress_cb(97, "Finalising…")

    return result


# ── BG colour detection ───────────────────────────────────────────────────────

def _detect_bg_color(rgba: Image.Image) -> tuple[int, int, int]:
    """
    Sample the four corners of the image (5% area each) to guess BG colour.
    Returns (r, g, b).
    """
    arr = np.array(rgba.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    margin_y = max(1, h // 20)
    margin_x = max(1, w // 20)

    corners = [
        arr[:margin_y, :margin_x],           # top-left
        arr[:margin_y, w-margin_x:],          # top-right
        arr[h-margin_y:, :margin_x],          # bottom-left
        arr[h-margin_y:, w-margin_x:],        # bottom-right
    ]
    samples = np.concatenate([c.reshape(-1, 3) for c in corners], axis=0)
    median = np.median(samples, axis=0)
    return (int(median[0]), int(median[1]), int(median[2]))


def bg_color_is_bright(bg: tuple[int, int, int], threshold: int = 180) -> bool:
    return sum(bg) / 3 > threshold


# ── White / solid BG cleanup ─────────────────────────────────────────────────

def _cleanup_solid_bg(
    rgba: Image.Image,
    bg_color: tuple[int, int, int],
    cfg: RemoverConfig,
) -> Image.Image:
    """
    Two-pass cleanup for solid-colour BG remnants:
    Pass A – colour-distance kill: pixels close to bg_color AND semi-transparent → alpha = 0
    Pass B – brightness kill (for white BG): bright semi-transparent pixels → reduce alpha
    """
    arr = np.array(rgba, dtype=np.float32)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
    bg_r, bg_g, bg_b = float(bg_color[0]), float(bg_color[1]), float(bg_color[2])

    # ── Pass A: colour-distance ──────────────────────────────────────────────
    # How close is each pixel to the detected BG colour?
    dist = np.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
    max_dist = 441.67  # sqrt(255^2 * 3)
    similarity = 1.0 - dist / max_dist  # 1 = identical to BG, 0 = fully different

    # Pixels very close to BG colour AND not fully opaque → kill
    close_to_bg  = similarity > 0.92    # within ~8% of BG colour
    semi_or_low  = a < 240

    # Scale alpha by (1 - similarity) for semi-transparent BG-like pixels
    alpha_scale = np.clip(1.0 - (similarity - 0.75) / 0.25, 0, 1)
    new_a = np.where(close_to_bg & semi_or_low,
                     np.minimum(a, a * alpha_scale),
                     a)

    # ── Pass B: absolute brightness kill (white BG specific) ─────────────────
    if cfg.white_bg_kill_semi and bg_color_is_bright(bg_color):
        brightness = (r + g + b) / 3.0
        is_bright  = brightness > cfg.white_bg_threshold
        is_semi    = new_a < 245

        # Smoothly reduce alpha for bright semi-transparent pixels
        t = np.clip((brightness - cfg.white_bg_threshold) / (255 - cfg.white_bg_threshold), 0, 1)
        kill_alpha = new_a * (1.0 - t)
        new_a = np.where(is_bright & is_semi, kill_alpha, new_a)

    arr[:,:,3] = np.clip(new_a, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


# ── Colour despill ────────────────────────────────────────────────────────────

def _despill(
    rgba: Image.Image,
    bg_color: tuple[int, int, int],
    strength: float,
) -> Image.Image:
    """
    Un-premultiply edge pixels against the detected background colour to recover
    the true foreground colour.

    Assuming straight-alpha compositing:
        blended = fg * a + bg * (1 - a)
        fg = (blended - bg * (1 - a)) / a
    """
    arr = np.array(rgba, dtype=np.float32)
    a = arr[:,:,3:4] / 255.0
    bg = np.array(bg_color, dtype=np.float32).reshape(1, 1, 3)

    # Only process semi-transparent pixels (the edge zone)
    is_semi = (a > 0.03) & (a < 0.97)
    safe_a = np.where(a > 0.005, a, 1.0)

    fg = (arr[:,:,:3] - bg * (1.0 - safe_a)) / safe_a
    fg = np.clip(fg, 0, 255)

    blended = strength * fg + (1.0 - strength) * arr[:,:,:3]
    arr[:,:,:3] = np.where(is_semi, blended, arr[:,:,:3])

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ── Edge refinement ───────────────────────────────────────────────────────────

def _refine_edges(rgba: Image.Image, cfg: RemoverConfig) -> Image.Image:
    r, g, b, a = rgba.split()
    alpha = np.array(a, dtype=np.float32)

    if cfg.edge_contract > 0:
        a_pil = Image.fromarray(alpha.astype(np.uint8))
        for _ in range(cfg.edge_contract):
            a_pil = a_pil.filter(ImageFilter.MinFilter(3))
        alpha = np.array(a_pil, dtype=np.float32)

    if cfg.edge_expand > 0:
        a_pil = Image.fromarray(alpha.astype(np.uint8))
        for _ in range(cfg.edge_expand):
            a_pil = a_pil.filter(ImageFilter.MaxFilter(3))
        alpha = np.array(a_pil, dtype=np.float32)

    if cfg.edge_blur_radius > 0:
        a_pil = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8))
        a_pil = a_pil.filter(ImageFilter.GaussianBlur(cfg.edge_blur_radius))
        orig_a = np.array(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
        blurred = np.array(a_pil, dtype=np.float32)
        mask = (orig_a > 245) | (orig_a < 10)
        blurred[mask] = orig_a[mask]
        alpha = blurred

    new_alpha = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8))
    return Image.merge("RGBA", (r, g, b, new_alpha))


# ── Generic decontamination ───────────────────────────────────────────────────

def _decontaminate_edges(
    orig_rgba: Image.Image,
    result_rgba: Image.Image,
    strength: float,
) -> Image.Image:
    orig = np.array(orig_rgba, dtype=np.float32)
    res  = np.array(result_rgba, dtype=np.float32)
    alpha = res[:, :, 3:4] / 255.0
    is_semi = (alpha > 0.05) & (alpha < 0.95)
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
