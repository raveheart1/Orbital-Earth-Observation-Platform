"""PNG preview generation: colorized NDVI and true-color composites.

The NDVI colormap is a small self-contained red→yellow→green ramp (no
matplotlib dependency in the production worker). The DISPLAY range only
affects previews — analytical outputs (COG, statistics, CSV) always retain
full calculated values.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

#: Color stops for NDVI display: (position 0..1, (r, g, b)).
#: Brown/red for bare or stressed surfaces through yellow to deep green.
_NDVI_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.00, (120, 69, 25)),
    (0.20, (179, 116, 44)),
    (0.40, (226, 190, 100)),
    (0.55, (247, 237, 138)),
    (0.70, (173, 204, 92)),
    (0.85, (90, 160, 56)),
    (1.00, (16, 105, 34)),
]

#: Color used for masked / invalid pixels (transparent in RGBA output).
MASKED_RGBA = (0, 0, 0, 0)


def ndvi_colormap_lut() -> npt.NDArray[np.uint8]:
    """256-entry RGB lookup table interpolated from the color stops."""
    lut = np.zeros((256, 3), dtype=np.uint8)
    positions = np.array([p for p, _ in _NDVI_STOPS])
    channels = np.array([c for _, c in _NDVI_STOPS], dtype=np.float64)
    xs = np.linspace(0.0, 1.0, 256)
    for band in range(3):
        lut[:, band] = np.clip(np.interp(xs, positions, channels[:, band]), 0, 255).astype(np.uint8)
    return lut


def _downsample_factor(height: int, width: int, max_dim: int) -> int:
    longest = max(height, width)
    return max(1, int(np.ceil(longest / max_dim)))


def write_ndvi_preview(
    path: Path,
    ndvi: npt.NDArray[np.float32],
    *,
    display_min: float,
    display_max: float,
    max_dim: int = 1024,
) -> None:
    """Colorize NDVI into an RGBA PNG; invalid pixels are fully transparent."""
    if display_max <= display_min:
        raise ValueError("display_max must exceed display_min")
    factor = _downsample_factor(ndvi.shape[0], ndvi.shape[1], max_dim)
    data = ndvi[::factor, ::factor]

    valid = np.isfinite(data)
    scaled = np.clip((data - display_min) / (display_max - display_min), 0.0, 1.0)
    scaled = np.nan_to_num(scaled, nan=0.0)
    indices = np.where(valid, (scaled * 255.0).astype(np.uint8), 0)

    lut = ndvi_colormap_lut()
    rgb = lut[indices]
    alpha = np.where(valid, 255, MASKED_RGBA[3]).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", optimize=True)


def write_true_color_preview(
    path: Path,
    rgb: npt.NDArray[np.uint8],
    *,
    valid_mask: npt.NDArray[np.bool_] | None = None,
    max_dim: int = 1024,
) -> None:
    """Write an (H, W, 3) uint8 true-color array as PNG, optionally alpha-masked."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"Expected (H, W, 3) RGB array, got shape {rgb.shape}")
    factor = _downsample_factor(rgb.shape[0], rgb.shape[1], max_dim)
    data = rgb[::factor, ::factor]
    if valid_mask is not None:
        mask = valid_mask[::factor, ::factor]
        alpha = np.where(mask, 255, 0).astype(np.uint8)
        image = Image.fromarray(np.dstack([data, alpha]), mode="RGBA")
    else:
        image = Image.fromarray(data, mode="RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def legend_spec(display_min: float, display_max: float) -> dict[str, object]:
    """Legend description consumed by the web UI so map and chart legends match."""
    stops = [
        {
            "value": round(display_min + p * (display_max - display_min), 3),
            "color": f"#{r:02x}{g:02x}{b:02x}",
        }
        for p, (r, g, b) in _NDVI_STOPS
    ]
    return {
        "type": "ndvi",
        "display_min": display_min,
        "display_max": display_max,
        "stops": stops,
        "masked_color": "transparent",
        "note": ("Display range only. Analytical outputs retain full NDVI values in [-1, 1]."),
    }
