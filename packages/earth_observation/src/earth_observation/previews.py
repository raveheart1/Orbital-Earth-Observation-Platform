"""PNG preview generation: colorized spectral-index and true-color composites.

The NDVI colormap is a small self-contained red→yellow→green ramp (no
matplotlib dependency in the production worker); NBR uses a similar fixed
brown→pale→green ramp. The DISPLAY range only affects previews — analytical
outputs (COG, statistics, CSV) always retain full calculated values.
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

#: Color stops for NBR display over the fixed range -1..+1: dark/brown for
#: low values (burned or bare surfaces) through pale to deep green for high
#: values (healthy vegetation is strongly NIR-reflective).
_NBR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.00, (69, 38, 10)),
    (0.25, (150, 96, 50)),
    (0.50, (235, 228, 205)),
    (0.75, (128, 176, 92)),
    (1.00, (14, 96, 40)),
]

#: Color stops for CHANGE display: ColorBrewer BrBG, a colorblind-safe
#: diverging ramp. Brown = NDVI loss, near-white = no change, blue-green =
#: gain; the center stop sits exactly at delta zero.
_CHANGE_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.00, (84, 48, 5)),
    (0.17, (191, 129, 45)),
    (0.33, (223, 194, 125)),
    (0.50, (245, 245, 245)),
    (0.67, (128, 205, 193)),
    (0.83, (53, 151, 143)),
    (1.00, (0, 60, 48)),
]

#: Masked-but-observed pixels (cloud, shadow, snow): transparent, so the
#: surrounding NDVI field reads normally through a comparison viewport.
MASKED_RGBA = (0, 0, 0, 0)

#: Pixels inside the AOI that NO source granule covered. Rendered as an opaque
#: neutral grey with a distinct hue rather than transparency or a low-NDVI
#: color, so "no imagery here" can never be mistaken for water, bare ground, or
#: unhealthy vegetation.
NODATA_RGBA = (104, 106, 114, 255)


def _interpolated_lut(
    stops: list[tuple[float, tuple[int, int, int]]],
) -> npt.NDArray[np.uint8]:
    lut = np.zeros((256, 3), dtype=np.uint8)
    positions = np.array([p for p, _ in stops])
    channels = np.array([c for _, c in stops], dtype=np.float64)
    xs = np.linspace(0.0, 1.0, 256)
    for band in range(3):
        lut[:, band] = np.clip(np.interp(xs, positions, channels[:, band]), 0, 255).astype(np.uint8)
    return lut


def ndvi_colormap_lut() -> npt.NDArray[np.uint8]:
    """256-entry RGB lookup table interpolated from the color stops."""
    return _interpolated_lut(_NDVI_STOPS)


def nbr_colormap_lut() -> npt.NDArray[np.uint8]:
    """256-entry RGB lookup table interpolated from the NBR color stops."""
    return _interpolated_lut(_NBR_STOPS)


def change_colormap_lut() -> npt.NDArray[np.uint8]:
    """256-entry RGB lookup table interpolated from the change color stops."""
    return _interpolated_lut(_CHANGE_STOPS)


def _downsample_factor(height: int, width: int, max_dim: int) -> int:
    longest = max(height, width)
    return max(1, int(np.ceil(longest / max_dim)))


def write_index_preview(
    path: Path,
    values: npt.NDArray[np.float32],
    *,
    lut: npt.NDArray[np.uint8],
    display_min: float,
    display_max: float,
    max_dim: int = 1024,
    aoi_mask: npt.NDArray[np.bool_] | None = None,
    covered_mask: npt.NDArray[np.bool_] | None = None,
) -> None:
    """Colorize a spectral-index array into an RGBA PNG on the caller's grid.

    The colormap uses a FIXED display range (never a per-scene stretch), so the
    same color means the same index value in every preview of an analysis.

    Three pixel states are visually distinct:

    * valid index value — colormap,
    * masked but observed (cloud/shadow/snow) — transparent,
    * inside the AOI but covered by no source granule — opaque grey
      (:data:`NODATA_RGBA`), so missing imagery cannot be confused with water
      or low vegetation.
    """
    if display_max <= display_min:
        raise ValueError("display_max must exceed display_min")
    factor = _downsample_factor(values.shape[0], values.shape[1], max_dim)
    data = values[::factor, ::factor]

    valid = np.isfinite(data)
    scaled = np.clip((data - display_min) / (display_max - display_min), 0.0, 1.0)
    scaled = np.nan_to_num(scaled, nan=0.0)
    indices = np.where(valid, (scaled * 255.0).astype(np.uint8), 0)

    rgb = lut[indices]
    alpha = np.where(valid, 255, MASKED_RGBA[3]).astype(np.uint8)

    if aoi_mask is not None and covered_mask is not None:
        missing = aoi_mask[::factor, ::factor] & ~covered_mask[::factor, ::factor]
        rgb = np.where(missing[..., None], np.array(NODATA_RGBA[:3], dtype=np.uint8), rgb)
        alpha = np.where(missing, NODATA_RGBA[3], alpha).astype(np.uint8)

    rgba = np.dstack([rgb, alpha])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", optimize=True)


def write_ndvi_preview(
    path: Path,
    ndvi: npt.NDArray[np.float32],
    *,
    display_min: float,
    display_max: float,
    max_dim: int = 1024,
    aoi_mask: npt.NDArray[np.bool_] | None = None,
    covered_mask: npt.NDArray[np.bool_] | None = None,
) -> None:
    """NDVI preview: :func:`write_index_preview` with the NDVI colormap."""
    write_index_preview(
        path,
        ndvi,
        lut=ndvi_colormap_lut(),
        display_min=display_min,
        display_max=display_max,
        max_dim=max_dim,
        aoi_mask=aoi_mask,
        covered_mask=covered_mask,
    )


def write_change_preview(
    path: Path,
    delta: npt.NDArray[np.float32],
    *,
    display_range: float,
    max_dim: int = 1024,
) -> None:
    """Colorize an NDVI change map into an RGBA PNG on the caller's grid.

    The diverging colormap is centered at delta zero with a FIXED symmetric
    range (±``display_range``), so the same color means the same change in
    every preview. Pixels with no defined change (invalid on either date, or
    outside the AOI) are transparent.
    """
    if display_range <= 0:
        raise ValueError("display_range must be positive")
    factor = _downsample_factor(delta.shape[0], delta.shape[1], max_dim)
    data = delta[::factor, ::factor]

    valid = np.isfinite(data)
    scaled = np.clip((data + display_range) / (2.0 * display_range), 0.0, 1.0)
    scaled = np.nan_to_num(scaled, nan=0.0)
    indices = np.where(valid, (scaled * 255.0).astype(np.uint8), 0)

    lut = change_colormap_lut()
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


def legend_spec(
    display_min: float,
    display_max: float,
    *,
    legend_type: str = "ndvi",
    colormap_stops: list[tuple[float, tuple[int, int, int]]] | None = None,
    note: str | None = None,
) -> dict[str, object]:
    """Legend description consumed by the web UI so map and chart legends match.

    The defaults reproduce the NDVI legend exactly; other indices pass their
    own colormap stops and note.
    """
    stops = [
        {
            "value": round(display_min + p * (display_max - display_min), 3),
            "color": f"#{r:02x}{g:02x}{b:02x}",
        }
        for p, (r, g, b) in (colormap_stops if colormap_stops is not None else _NDVI_STOPS)
    ]
    nr, ng, nb, _ = NODATA_RGBA
    return {
        "type": legend_type,
        "display_min": display_min,
        "display_max": display_max,
        "stops": stops,
        "masked_color": "transparent",
        "masked_label": "Cloud, shadow, or snow (observed, excluded)",
        "nodata_color": f"#{nr:02x}{ng:02x}{nb:02x}",
        "nodata_label": "No source imagery for this area",
        "note": note
        if note is not None
        else (
            "Fixed display range, identical for every observation in an analysis. "
            "Analytical outputs retain full NDVI values in [-1, 1]."
        ),
    }


def nbr_legend_spec(display_min: float, display_max: float) -> dict[str, object]:
    """Legend description for NBR previews, mirroring :func:`legend_spec`."""
    return legend_spec(
        display_min,
        display_max,
        legend_type="nbr",
        colormap_stops=_NBR_STOPS,
        note=(
            "Fixed display range, identical for every observation in an analysis. "
            "Analytical outputs retain full NBR values in [-1, 1]."
        ),
    )


def change_legend_spec(display_range: float) -> dict[str, object]:
    """Legend description for the change preview, mirroring :func:`legend_spec`."""
    stops = [
        {
            "value": round(-display_range + p * 2.0 * display_range, 3),
            "color": f"#{r:02x}{g:02x}{b:02x}",
        }
        for p, (r, g, b) in _CHANGE_STOPS
    ]
    return {
        "type": "ndvi_change",
        "display_min": -display_range,
        "display_max": display_range,
        "stops": stops,
        "masked_color": "transparent",
        "masked_label": "No valid observation on one or both dates",
        "note": (
            "Delta = later minus earlier NDVI; positive is greening. Fixed "
            "symmetric display range centered at zero. Individual 10 m pixels "
            "mix surfaces and shift slightly between dates, so single-pixel "
            "values deserve caution; the analytical COG retains full delta "
            "values."
        ),
    }
