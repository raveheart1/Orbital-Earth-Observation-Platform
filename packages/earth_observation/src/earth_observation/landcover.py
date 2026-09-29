"""Land-cover stratification: reference maps, grid alignment, class statistics.

An AOI-wide NDVI/NBR mean blends tree cover, grassland, cropland, built-up
land, water, wetlands, and bare ground into one number that describes none of
them. This module aligns a global 10 m land-cover map onto the analysis's
canonical grid and computes index statistics per class, so an analysis can
say *which surface type* a measurement describes.

Reference data
--------------
ESA WorldCover (10 m, global, CC-BY-4.0), accessed through the same
Microsoft Planetary Computer STAC API as Sentinel-2 (collection
``esa-worldcover``). Two products exist and BOTH are registered:

* 2021, product version 2.0.0 (algorithm v200) — the default;
* 2020, product version 1.0.0 (algorithm v100) — used when an analysis needs
  a map that predates a 2021 event (e.g. the August 2021 Evia fire).

ESA states that the two maps were produced with different algorithms, so a
difference between them mixes real change with algorithm change. They are
never differenced here; exactly one map is used per analysis and its
reference year is recorded and compared against every observation date.

A land-cover map is a *historical classification*, not contemporaneous
truth: its classes carry published accuracies (see
:data:`LAND_COVER_DATASETS`), and a surface may have changed since the
reference year. Both facts travel with every result.

Processing rules
----------------
* Only the map tiles intersecting the AOI are searched, and only the window
  covering the canonical grid is read (COG range reads).
* Class codes are reprojected onto the canonical grid with NEAREST-neighbour
  resampling — never bilinear/cubic, which would average codes into classes
  that were never mapped there (tree cover 10 beside built-up 50 would
  interpolate to grassland 30).
* Statistics use only pixels inside the AOI mask; classes that are too small,
  or whose valid (unmasked) share in an observation is too low, are reported
  with a structured quality state and ``None`` statistics, never zeros.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field

from earth_observation.geometry import BBox
from earth_observation.grid import CanonicalGrid
from earth_observation.quality import QualityInfo, QualityState, degraded, valid
from earth_observation.stac import sign_href
from earth_observation.types import ClassStats, LandCoverConfig

#: Bumped when the land-cover summary document or class-statistics semantics change.
LAND_COVER_SCHEMA_VERSION = "1.0.0"

#: Resampling used to align categorical land-cover codes to the canonical grid.
LAND_COVER_RESAMPLING = "nearest"

#: Code used on the aligned raster (and in COG/preview outputs) for "no class":
#: outside every map tile, map nodata, or outside the AOI.
LAND_COVER_NODATA = 0


@dataclass(frozen=True)
class LandCoverClass:
    """One class of a land-cover legend, with its published map accuracy.

    Accuracies are the product validation report's GLOBAL user's accuracy
    (1 - commission error: how often a pixel mapped as this class really is
    it) and producer's accuracy (1 - omission error), in percent, with their
    reported confidence half-widths. ``None`` when not published.
    """

    code: int
    key: str
    name: str
    color: str
    users_accuracy_pct: float | None = None
    users_accuracy_ci_pct: float | None = None
    producers_accuracy_pct: float | None = None
    producers_accuracy_ci_pct: float | None = None

    def rgb(self) -> tuple[int, int, int]:
        value = self.color.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


@dataclass(frozen=True)
class LandCoverDataset:
    """A registered reference land-cover product."""

    id: str
    title: str
    collection: str
    product_version: str
    reference_year: int
    classes: tuple[LandCoverClass, ...]
    overall_accuracy_pct: float | None
    overall_accuracy_ci_pct: float | None
    accuracy_source: str
    provider: str
    license: str
    license_url: str
    attribution: str
    citation: str
    doi: str
    documentation_url: str
    validation_report_url: str
    asset_key: str = "map"
    resolution_m: float = 10.0
    nodata: int = 0
    notes: tuple[str, ...] = ()

    def class_by_code(self, code: int) -> LandCoverClass | None:
        for cls in self.classes:
            if cls.code == code:
                return cls
        return None

    def palette(self) -> dict[int, tuple[int, int, int]]:
        return {cls.code: cls.rgb() for cls in self.classes}

    def legend(self) -> list[dict[str, Any]]:
        """Class legend for documents, the API, and the UI."""
        return [
            {
                "code": c.code,
                "key": c.key,
                "name": c.name,
                "color": c.color,
                "users_accuracy_pct": c.users_accuracy_pct,
                "users_accuracy_ci_pct": c.users_accuracy_ci_pct,
                "producers_accuracy_pct": c.producers_accuracy_pct,
                "producers_accuracy_ci_pct": c.producers_accuracy_ci_pct,
            }
            for c in self.classes
        ]

    def to_metadata(self) -> dict[str, Any]:
        """Dataset identity for provenance, summaries, and the API."""
        return {
            "id": self.id,
            "title": self.title,
            "collection": self.collection,
            "product_version": self.product_version,
            "reference_year": self.reference_year,
            "resolution_m": self.resolution_m,
            "asset_key": self.asset_key,
            "provider": self.provider,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "citation": self.citation,
            "doi": self.doi,
            "documentation_url": self.documentation_url,
            "validation_report_url": self.validation_report_url,
            "overall_accuracy_pct": self.overall_accuracy_pct,
            "overall_accuracy_ci_pct": self.overall_accuracy_ci_pct,
            "accuracy_source": self.accuracy_source,
            "notes": list(self.notes),
        }


#: Class-specific GLOBAL accuracies of WorldCover 2021 v200, transcribed from
#: the WorldCover Product Validation Report v2.0, Table 2 (confusion matrix
#: corrected by sample inclusion probabilities): (UA, UA ±, PA, PA ±), percent.
_WORLDCOVER_V200_ACCURACY: dict[int, tuple[float, float, float, float]] = {
    10: (80.0, 0.7, 91.9, 0.5),
    20: (49.1, 2.1, 46.9, 2.3),
    30: (71.9, 1.0, 66.7, 1.1),
    40: (80.6, 1.5, 79.3, 1.5),
    50: (65.9, 3.3, 73.2, 2.6),
    60: (92.1, 0.9, 82.5, 1.2),
    70: (93.0, 2.4, 99.1, 0.4),
    80: (89.4, 1.8, 86.4, 1.7),
    90: (30.5, 4.3, 44.6, 5.4),
    95: (74.1, 13.2, 46.2, 16.0),
    100: (57.5, 3.8, 46.4, 3.5),
}

#: (code, key, name, colour hint from the STAC classification extension).
_WORLDCOVER_LEGEND: tuple[tuple[int, str, str, str], ...] = (
    (10, "tree_cover", "Tree cover", "#006400"),
    (20, "shrubland", "Shrubland", "#ffbb22"),
    (30, "grassland", "Grassland", "#ffff4c"),
    (40, "cropland", "Cropland", "#f096ff"),
    (50, "built_up", "Built-up", "#fa0000"),
    (60, "bare_sparse", "Bare / sparse vegetation", "#b4b4b4"),
    (70, "snow_ice", "Snow and ice", "#f0f0f0"),
    (80, "permanent_water", "Permanent water bodies", "#0064c8"),
    (90, "herbaceous_wetland", "Herbaceous wetland", "#0096a0"),
    (95, "mangroves", "Mangroves", "#00cf75"),
    (100, "moss_lichen", "Moss and lichen", "#fae6a0"),
)


def _worldcover_classes(with_accuracy: bool) -> tuple[LandCoverClass, ...]:
    classes = []
    for code, key, name, color in _WORLDCOVER_LEGEND:
        acc = _WORLDCOVER_V200_ACCURACY.get(code) if with_accuracy else None
        classes.append(
            LandCoverClass(
                code=code,
                key=key,
                name=name,
                color=color,
                users_accuracy_pct=acc[0] if acc else None,
                users_accuracy_ci_pct=acc[1] if acc else None,
                producers_accuracy_pct=acc[2] if acc else None,
                producers_accuracy_ci_pct=acc[3] if acc else None,
            )
        )
    return tuple(classes)


_WORLDCOVER_COMMON: dict[str, Any] = {
    "collection": "esa-worldcover",
    "provider": "ESA WorldCover consortium, via Microsoft Planetary Computer",
    "license": "CC-BY-4.0",
    "license_url": "https://spdx.org/licenses/CC-BY-4.0.html",
    "asset_key": "map",
    "resolution_m": 10.0,
    "nodata": 0,
}

WORLDCOVER_2021 = LandCoverDataset(
    id="esa-worldcover-2021-v200",
    title="ESA WorldCover 10 m 2021 v200",
    product_version="2.0.0",
    reference_year=2021,
    classes=_worldcover_classes(with_accuracy=True),
    overall_accuracy_pct=76.7,
    overall_accuracy_ci_pct=0.5,
    accuracy_source=(
        "WorldCover Product Validation Report v2.0 (2021 v200), Table 2: global "
        "overall accuracy 76.7 +/- 0.5 %, with class user's/producer's accuracies; "
        "Table 3 gives continental figures (e.g. North America 74.6 %, Europe 77.9 %)"
    ),
    attribution="© ESA WorldCover project 2021 / Contains modified Copernicus "
    "Sentinel data (2021) processed by ESA WorldCover consortium",
    citation="Zanaga, D., Van De Kerchove, R., Daems, D., et al. (2022). ESA "
    "WorldCover 10 m 2021 v200. Zenodo.",
    doi="10.5281/zenodo.7254221",
    documentation_url="https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PUM_V2.0.pdf",
    validation_report_url="https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/docs/WorldCover_PVR_V2.0.pdf",
    notes=(
        "Produced with algorithm v200; differences from the 2020 v100 map mix real "
        "land-cover change with algorithm change and are not interpreted here.",
    ),
    **_WORLDCOVER_COMMON,
)

WORLDCOVER_2020 = LandCoverDataset(
    id="esa-worldcover-2020-v100",
    title="ESA WorldCover 10 m 2020 v100",
    product_version="1.0.0",
    reference_year=2020,
    # Class-specific accuracies are only transcribed for v200; v100 carries
    # its published overall accuracy alone rather than borrowed class figures.
    classes=_worldcover_classes(with_accuracy=False),
    overall_accuracy_pct=74.4,
    overall_accuracy_ci_pct=None,
    accuracy_source=(
        "Global overall accuracy of the 2020 v100 map (74.4 %) as stated in the "
        "WorldCover Product Validation Report v2.0, section 1.1; class-specific "
        "accuracies are published in the v1.1 validation report"
    ),
    attribution="© ESA WorldCover project 2020 / Contains modified Copernicus "
    "Sentinel data (2020) processed by ESA WorldCover consortium",
    citation="Zanaga, D., Van De Kerchove, R., De Keersmaecker, W., et al. (2021). "
    "ESA WorldCover 10 m 2020 v100. Zenodo.",
    doi="10.5281/zenodo.5571936",
    documentation_url="https://esa-worldcover.s3.amazonaws.com/v100/2020/docs/WorldCover_PUM_V1.0.pdf",
    validation_report_url="https://worldcover2020.esa.int/data/docs/WorldCover_PVR_V1.1.pdf",
    notes=(
        "Produced with algorithm v100; differences from the 2021 v200 map mix real "
        "land-cover change with algorithm change and are not interpreted here.",
    ),
    **_WORLDCOVER_COMMON,
)

#: Registered land-cover datasets, keyed by id.
LAND_COVER_DATASETS: dict[str, LandCoverDataset] = {
    d.id: d for d in (WORLDCOVER_2021, WORLDCOVER_2020)
}
DEFAULT_LAND_COVER_DATASET = WORLDCOVER_2021.id

#: Latitude band ESA WorldCover covers (collection spatial extent).
WORLDCOVER_LAT_RANGE = (-60.0, 82.75)


@dataclass(frozen=True)
class LandCoverItem:
    """One land-cover map tile intersecting the AOI (unsigned href)."""

    item_id: str
    href: str
    bbox: tuple[float, float, float, float]


@dataclass
class LandCoverLayer:
    """A land-cover map aligned onto one canonical grid.

    ``classes`` is uint8 with :data:`LAND_COVER_NODATA` where no class is
    available. Construct via :func:`load_land_cover` or :func:`layer_from_array`.
    """

    dataset: LandCoverDataset
    classes: npt.NDArray[np.uint8]
    items: list[LandCoverItem]
    grid_signature: str
    warnings: list[str] = field(default_factory=list)

    def cache_identity(self) -> dict[str, Any]:
        """What about this layer determines class statistics (for cache keys)."""
        return {
            "dataset_id": self.dataset.id,
            "product_version": self.dataset.product_version,
            "item_ids": sorted(i.item_id for i in self.items),
            "grid_signature": self.grid_signature,
            "resampling": LAND_COVER_RESAMPLING,
        }


class CompositionEntry(BaseModel):
    """Area share of one class within the AOI (map-level, observation-independent)."""

    class_code: int
    class_key: str
    class_name: str
    color: str
    pixel_count: int
    area_km2: float
    aoi_pct: float = Field(description="Percent of all AOI pixels")
    users_accuracy_pct: float | None = None
    producers_accuracy_pct: float | None = None


class LandCoverComposition(BaseModel):
    """Which classes the AOI contains and how much of it each occupies.

    Only classes present in the AOI are listed, in legend order. Unlabeled AOI
    pixels (outside every tile or map nodata) are counted separately and
    never assigned to a class.
    """

    aoi_pixel_count: int
    pixel_area_m2: float
    classes: list[CompositionEntry]
    unlabeled_pixel_count: int
    unlabeled_pct: float


class ReferenceYearAssessment(BaseModel):
    """How far observation dates are from the map's reference year."""

    reference_year: int
    observation_years: list[int]
    max_year_offset: int
    quality: QualityInfo


# --- dataset selection ------------------------------------------------------


def choose_land_cover_dataset(
    *,
    workflow: str,
    observation_start_year: int,
    event_year: int | None = None,
    requested_id: str | None = None,
) -> tuple[LandCoverDataset, str]:
    """Pick the reference map for an analysis; returns ``(dataset, reason)``.

    Rules (documented in docs/land-cover-stratification.md):

    * ``requested_id`` given → that dataset (``UserInputError`` if unknown).
    * ``workflow == "wildfire_dnbr"`` → the most recent map whose reference
      year is STRICTLY BEFORE ``event_year`` (the post-fire window's year), so
      the classes describe the pre-fire surface; if none qualifies, the
      earliest map, with a reason that says it post-dates the event.
    * otherwise → the most recent map (2021 v200).

    ``reason`` is a human-readable sentence recorded in provenance.
    """
    raise NotImplementedError


def assess_reference_year(
    dataset: LandCoverDataset, observation_years: list[int], config: LandCoverConfig
) -> ReferenceYearAssessment:
    """Flag ``reference_year_mismatch`` when any observation is more than
    ``config.max_reference_year_offset`` years from the map's reference year.

    The state stays ``valid`` (the stratification is still computed); the
    mismatch is a flag with the offsets in ``details``.
    """
    raise NotImplementedError


# --- data access ------------------------------------------------------------

SearchFn = Callable[[LandCoverDataset, BBox, str], list[LandCoverItem]]


def search_land_cover_items(
    dataset: LandCoverDataset,
    bbox: BBox,
    stac_endpoint: str,
) -> list[LandCoverItem]:
    """STAC search for the dataset's tiles intersecting ``bbox`` (WGS84).

    Filters on ``esa_worldcover:product_version == dataset.product_version``
    (the collection holds both years). Returns items sorted by id, hrefs
    UNSIGNED. Network faults raise :class:`TransientError` after retries.
    Raises :class:`DataError` when the bbox lies outside the dataset extent.
    """
    raise NotImplementedError


def load_land_cover(
    dataset: LandCoverDataset,
    grid: CanonicalGrid,
    items: list[LandCoverItem],
    *,
    sign: Callable[[str], str] = sign_href,
) -> LandCoverLayer:
    """Read the grid window of every item and mosaic it onto the canonical grid.

    Uses :func:`earth_observation.mosaic.mosaic_band` with
    ``categorical=True`` (nearest). Codes not in the dataset legend are
    treated as unlabeled (:data:`LAND_COVER_NODATA`) with a warning. Pixels
    outside the AOI mask are set to :data:`LAND_COVER_NODATA`.
    """
    raise NotImplementedError


def layer_from_array(
    dataset: LandCoverDataset,
    classes: npt.NDArray[np.integer],
    items: list[LandCoverItem],
    grid: CanonicalGrid,
) -> LandCoverLayer:
    """Rehydrate a layer from a cached aligned raster (shape must match the grid)."""
    raise NotImplementedError


# --- statistics ---------------------------------------------------------------


def _present_codes(
    layer: LandCoverLayer, aoi_mask: npt.NDArray[np.bool_]
) -> list[tuple[LandCoverClass, npt.NDArray[np.bool_], int]]:
    """Legend classes present inside the AOI, with their AOI masks and counts."""
    if layer.classes.shape != aoi_mask.shape:
        raise ValueError(
            f"Land-cover raster shape {layer.classes.shape} does not match the AOI mask "
            f"shape {aoi_mask.shape}"
        )
    present: list[tuple[LandCoverClass, npt.NDArray[np.bool_], int]] = []
    for cls in layer.dataset.classes:
        mask = aoi_mask & (layer.classes == cls.code)
        count = int(np.count_nonzero(mask))
        if count > 0:
            present.append((cls, mask, count))
    return present


def compute_composition(
    layer: LandCoverLayer,
    aoi_mask: npt.NDArray[np.bool_],
    pixel_area_m2: float,
) -> LandCoverComposition:
    """Class shares of the AOI (see :class:`LandCoverComposition`)."""
    aoi_pixels = int(np.count_nonzero(aoi_mask))
    entries: list[CompositionEntry] = []
    labeled = 0
    for cls, _mask, count in _present_codes(layer, aoi_mask):
        labeled += count
        entries.append(
            CompositionEntry(
                class_code=cls.code,
                class_key=cls.key,
                class_name=cls.name,
                color=cls.color,
                pixel_count=count,
                area_km2=count * pixel_area_m2 / 1.0e6,
                aoi_pct=round(100.0 * count / aoi_pixels, 4) if aoi_pixels else 0.0,
                users_accuracy_pct=cls.users_accuracy_pct,
                producers_accuracy_pct=cls.producers_accuracy_pct,
            )
        )
    unlabeled = aoi_pixels - labeled
    return LandCoverComposition(
        aoi_pixel_count=aoi_pixels,
        pixel_area_m2=pixel_area_m2,
        classes=entries,
        unlabeled_pixel_count=unlabeled,
        unlabeled_pct=round(100.0 * unlabeled / aoi_pixels, 4) if aoi_pixels else 0.0,
    )


def compute_class_stats(
    values: npt.NDArray[np.floating],
    layer: LandCoverLayer,
    aoi_mask: npt.NDArray[np.bool_],
    config: LandCoverConfig,
    pixel_area_m2: float,
) -> list[ClassStats]:
    """Per-class statistics of an index (or dNBR) array on the canonical grid.

    ``values`` uses the NaN-is-invalid convention. For every class PRESENT in
    the AOI (legend order): pixel counts, area, AOI share, valid count and
    fraction, and — when the class passes both thresholds — mean, median,
    population std, min, max, p10, p25, p75, p90 over the class's valid
    pixels. Quality states:

    * fewer than ``config.min_class_pixels`` AOI pixels →
      ``insufficient_samples`` / reason ``class_below_min_pixels``;
    * valid fraction below ``config.min_class_valid_fraction`` →
      ``insufficient_coverage`` / reason ``valid_fraction_below_threshold``.

    Statistics are ``None`` in both cases; counts are always reported.
    """
    if values.shape != aoi_mask.shape:
        raise ValueError(
            f"Value array shape {values.shape} does not match the AOI mask shape {aoi_mask.shape}"
        )
    aoi_pixels = int(np.count_nonzero(aoi_mask))
    finite = np.isfinite(values)
    out: list[ClassStats] = []
    for cls, mask, count in _present_codes(layer, aoi_mask):
        valid_mask = mask & finite
        valid_count = int(np.count_nonzero(valid_mask))
        fraction = valid_count / count
        base: dict[str, Any] = {
            "class_code": cls.code,
            "class_key": cls.key,
            "class_name": cls.name,
            "aoi_pixel_count": count,
            "aoi_area_km2": count * pixel_area_m2 / 1.0e6,
            "aoi_pct": round(100.0 * count / aoi_pixels, 4) if aoi_pixels else 0.0,
            "valid_pixel_count": valid_count,
            "valid_fraction": round(fraction, 6),
        }
        if count < config.min_class_pixels:
            out.append(
                ClassStats(
                    **base,
                    quality=degraded(
                        QualityState.INSUFFICIENT_SAMPLES,
                        "class_below_min_pixels",
                        f"{cls.name} covers {count} pixels of the AOI, fewer than the "
                        f"{config.min_class_pixels} required for class statistics.",
                        class_pixels=count,
                        min_class_pixels=config.min_class_pixels,
                    ),
                )
            )
            continue
        if fraction < config.min_class_valid_fraction:
            out.append(
                ClassStats(
                    **base,
                    quality=degraded(
                        QualityState.INSUFFICIENT_COVERAGE,
                        "valid_fraction_below_threshold",
                        f"Only {100.0 * fraction:.1f}% of {cls.name} pixels were valid in "
                        f"this observation (minimum "
                        f"{100.0 * config.min_class_valid_fraction:.0f}%); statistics withheld.",
                        valid_fraction=round(fraction, 6),
                        min_class_valid_fraction=config.min_class_valid_fraction,
                    ),
                )
            )
            continue
        data = values[valid_mask].astype(np.float64)
        p10, p25, p75, p90 = np.percentile(data, [10, 25, 75, 90])
        out.append(
            ClassStats(
                **base,
                mean=float(data.mean()),
                median=float(np.median(data)),
                std=float(data.std(ddof=0)),
                min=float(data.min()),
                max=float(data.max()),
                p10=float(p10),
                p25=float(p25),
                p75=float(p75),
                p90=float(p90),
                quality=valid(),
            )
        )
    return out


def land_cover_summary_document(
    *,
    layer: LandCoverLayer,
    composition: LandCoverComposition,
    reference_year: ReferenceYearAssessment,
    selection_reason: str,
    config: LandCoverConfig,
    observations: list[dict[str, Any]],
    operation: str,
) -> dict[str, Any]:
    """The machine-readable ``land_cover_summary.json`` artifact.

    ``observations`` is a list of ``{"acquisition_key", "primary_item_id",
    "observed_at", "classes": [ClassStats.model_dump(mode="json"), ...]}``.
    Shape documented in docs/land-cover-stratification.md.
    """
    raise NotImplementedError
