"""Tests for the index registry, NBR math, and registry-driven processing.

Covers: analytically known NBR values on synthetic arrays, the registry
lookup contract, STAC required-asset validation driven by the index's roles,
and an end-to-end NBR ``process_acquisition`` run over synthetic granule
GeoTIFFs whose SWIR band is natively 20 m (proving the 20 m -> 10 m reproject
path). Synthetic data only; no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from pystac import Asset, Item
from rasterio.transform import from_origin

from earth_observation.acquisition import group_acquisitions
from earth_observation.errors import AssetKeysError, UserInputError
from earth_observation.grid import CanonicalGrid
from earth_observation.indices import INDICES, IndexDefinition, get_index
from earth_observation.ndvi import compute_nbr, compute_ndvi
from earth_observation.previews import (
    legend_spec,
    nbr_colormap_lut,
    nbr_legend_spec,
    write_index_preview,
)
from earth_observation.processing import process_acquisition
from earth_observation.stac import candidate_from_item
from earth_observation.testing import (
    NODATA_DN,
    ORIGIN_X,
    ORIGIN_Y,
    RES,
    SIZE,
    utm_box_to_wgs84_geojson,
    write_raster,
)
from earth_observation.testing import (
    make_file_candidate as make_candidate,
)
from earth_observation.types import AssetKeys, ProcessingConfig

IDENTITY = str  # "signing" for local files is the identity function

CONFIG = ProcessingConfig(min_valid_pixel_pct=10.0, preview_max_dim=256)


class TestComputeNbr:
    def test_known_values(self):
        nir = np.array([[0.4, 0.2]], dtype=np.float64)
        swir = np.array([[0.1, 0.2]], dtype=np.float64)
        nbr, zeros = compute_nbr(nir, swir)
        assert nbr[0, 0] == pytest.approx(0.6, abs=1e-6)
        assert nbr[0, 1] == pytest.approx(0.0, abs=1e-6)
        assert zeros == 0
        assert nbr.dtype == np.float32

    def test_burned_surface_is_negative(self):
        """Fresh burn: NIR drops, SWIR rises -> strongly negative NBR."""
        nir = np.array([[0.1]], dtype=np.float64)
        swir = np.array([[0.3]], dtype=np.float64)
        nbr, _ = compute_nbr(nir, swir)
        assert nbr[0, 0] == pytest.approx(-0.5, abs=1e-6)

    def test_zero_denominator_is_nan_and_counted(self):
        nir = np.array([[0.0, 0.4]], dtype=np.float64)
        swir = np.array([[0.0, 0.1]], dtype=np.float64)
        nbr, zeros = compute_nbr(nir, swir)
        assert np.isnan(nbr[0, 0])
        assert nbr[0, 1] == pytest.approx(0.6, abs=1e-6)
        assert zeros == 1

    def test_negative_reflectance_clipped_keeps_nbr_bounded(self):
        """Retrieval artifacts (refl < 0) must never produce |NBR| > 1."""
        nir = np.array([[-0.05, 0.2, 0.001]], dtype=np.float64)
        swir = np.array([[0.2, -0.1, -0.001]], dtype=np.float64)
        nbr, zeros = compute_nbr(nir, swir)
        assert nbr[0, 0] == pytest.approx(-1.0)
        assert nbr[0, 1] == pytest.approx(1.0)
        assert nbr[0, 2] == pytest.approx(1.0)
        assert zeros == 0
        finite = nbr[np.isfinite(nbr)]
        assert (np.abs(finite) <= 1.0).all()

    def test_nodata_propagates_as_nan(self):
        nir = np.array([[np.nan, 0.4]], dtype=np.float64)
        swir = np.array([[0.1, np.nan]], dtype=np.float64)
        nbr, zeros = compute_nbr(nir, swir)
        assert np.isnan(nbr).all()
        assert zeros == 0

    def test_mask_excludes_pixels(self):
        nir = np.full((2, 2), 0.4)
        swir = np.full((2, 2), 0.1)
        mask = np.array([[True, False], [False, True]])
        nbr, _ = compute_nbr(nir, swir, mask)
        assert nbr[0, 0] == pytest.approx(0.6, abs=1e-6)
        assert np.isnan(nbr[0, 1])
        assert np.isnan(nbr[1, 0])

    def test_masked_zero_denominator_not_counted(self):
        nir = np.zeros((1, 2))
        swir = np.zeros((1, 2))
        nbr, zeros = compute_nbr(nir, swir, np.array([[False, True]]))
        assert np.isnan(nbr[0, 0])
        assert zeros == 1  # only the unmasked zero-denominator pixel counts

    def test_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="shapes differ"):
            compute_nbr(np.zeros((2, 2)), np.zeros((3, 3)))

    def test_mask_shape_mismatch_rejected(self):
        with pytest.raises(ValueError, match="Mask shape"):
            compute_nbr(np.zeros((2, 2)), np.zeros((2, 2)), np.ones((3, 3), dtype=bool))


class TestRegistry:
    def test_lookup_returns_registered_definitions(self):
        assert get_index("ndvi") is INDICES["ndvi"]
        assert get_index("nbr") is INDICES["nbr"]

    def test_ndvi_definition_shape(self):
        ndvi = INDICES["ndvi"]
        assert ndvi.operation == "ndvi"
        assert ndvi.required_band_roles == ("red", "nir")
        assert ndvi.cog_basename == "ndvi.tif"
        assert ndvi.preview_basename == "ndvi_preview.png"
        assert ndvi.display_min < ndvi.display_max
        # "scl" is never a band role: masking requires it separately.
        assert "scl" not in ndvi.required_band_roles

    def test_nbr_definition_shape(self):
        nbr = INDICES["nbr"]
        assert nbr.operation == "nbr"
        assert nbr.required_band_roles == ("nir", "swir")
        assert nbr.cog_basename == "nbr.tif"
        assert nbr.preview_basename == "nbr_preview.png"
        assert (nbr.display_min, nbr.display_max) == (-1.0, 1.0)
        assert nbr.change_display_range > 0 and nbr.change_delta_threshold > 0
        assert any("SWIR" in w for w in nbr.processing_warnings)

    def test_unknown_operation_raises_clear_error(self):
        with pytest.raises(UserInputError, match="Unknown operation 'evi'"):
            get_index("evi")

    def test_ndvi_legend_spec_identical_to_legacy_output(self):
        """The registry's NDVI legend must match the long-standing endpoint field."""
        assert INDICES["ndvi"].legend_spec() == legend_spec(-0.2, 0.9)

    def test_nbr_legend_spec_uses_nbr_stops_and_range(self):
        spec = INDICES["nbr"].legend_spec()
        assert spec["type"] == "nbr"
        assert spec["display_min"] == -1.0
        assert spec["display_max"] == 1.0
        stops = spec["stops"]
        assert isinstance(stops, list)
        # Brown/dark at the low end (burned, bare), deep green at the high end.
        assert stops[0]["value"] == -1.0 and stops[0]["color"] == "#45260a"
        assert stops[-1]["value"] == 1.0 and stops[-1]["color"] == "#0e6028"
        assert "NBR" in str(spec["note"])

    def test_ndvi_definition_reproduces_compute_ndvi(self):
        rng = np.random.default_rng(7)
        red = rng.random((8, 8)) * 0.3
        nir = rng.random((8, 8)) * 0.6
        mask = rng.random((8, 8)) > 0.2
        via_registry, zeros_registry = INDICES["ndvi"].compute(red, nir, mask)
        direct, zeros_direct = compute_ndvi(red, nir, mask)
        np.testing.assert_array_equal(via_registry, direct)
        assert zeros_registry == zeros_direct

    def test_definitions_require_exactly_two_roles(self):
        with pytest.raises(ValueError, match="exactly 2 band roles"):
            IndexDefinition(
                operation="bad",
                title="bad",
                formula="(a - b) / (a + b)",
                required_band_roles=("red", "nir", "blue"),
                compute=compute_ndvi,
                display_min=-1.0,
                display_max=1.0,
                change_display_range=0.4,
                change_delta_threshold=0.1,
                interpretation="",
                change_note="",
                cog_basename="bad.tif",
                preview_basename="bad_preview.png",
                colormap_lut=nbr_colormap_lut,
                legend_builder=nbr_legend_spec,
            )


_GEOMETRY = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def _stac_item(asset_keys: list[str]) -> Item:
    return Item(
        id="S2_TEST_ITEM",
        geometry=_GEOMETRY,
        bbox=[0.0, 0.0, 1.0, 1.0],
        datetime=datetime(2024, 7, 1, tzinfo=UTC),
        properties={"s2:processing_baseline": "05.00"},
        assets={key: Asset(href=f"https://example.test/{key}.tif") for key in asset_keys},
    )


class TestStacRequiredRoles:
    def test_default_roles_match_legacy_behavior(self):
        """Without explicit roles the red/nir/scl set is required, as before."""
        candidate = candidate_from_item(_stac_item(["B04", "B08", "SCL"]), AssetKeys())
        assert set(candidate.assets) == {"red", "nir", "scl"}
        with pytest.raises(AssetKeysError, match="red=B04"):
            candidate_from_item(_stac_item(["B08", "SCL"]), AssetKeys())

    def test_nbr_roles_require_swir(self):
        item = _stac_item(["B04", "B08", "SCL"])  # no B12
        with pytest.raises(AssetKeysError, match="swir=B12"):
            candidate_from_item(item, AssetKeys(), ("nir", "swir"))

    def test_nbr_roles_accept_item_with_b12(self):
        item = _stac_item(["B08", "B12", "SCL"])
        candidate = candidate_from_item(item, AssetKeys(), ("nir", "swir"))
        assert candidate.assets["swir"].endswith("B12.tif")
        assert candidate.assets["nir"].endswith("B08.tif")
        assert "red" not in candidate.assets  # only required roles are kept

    def test_scl_always_required(self):
        item = _stac_item(["B08", "B12"])  # no SCL
        with pytest.raises(AssetKeysError, match="scl=SCL"):
            candidate_from_item(item, AssetKeys(), ("nir", "swir"))

    def test_unknown_role_rejected(self):
        with pytest.raises(AssetKeysError, match="Unknown asset role"):
            candidate_from_item(_stac_item(["B04", "B08", "SCL"]), AssetKeys(), ("red", "pan"))


def build_nbr_scene(scene_dir: Path) -> dict:
    """Synthetic scene with analytically known NBR, SWIR natively at 20 m.

    Reflectance encoding uses baseline >= 04.00 semantics
    (``reflectance = DN * 1e-4 - 0.1``).

    Layout on the 40x40 grid (10 m pixels):
      - Background: NIR refl 0.4 (DN 5000), SWIR refl 0.1 (DN 2000) -> NBR 0.6
      - Rows 14-17, cols 14-17 (in-AOI): NIR 0.1 / SWIR 0.3 -> NBR -0.5 (burned)
      - Rows 20-21, cols 20-23 (in-AOI): SCL=9 (cloud, masked)
    SWIR is written at 20 m (20x20 cells), so a correct run must reproject it
    onto the 10 m canonical grid. AOI: rows 10..30, cols 10..30.
    """
    scene_dir.mkdir(parents=True, exist_ok=True)

    nir_dn = np.full((SIZE, SIZE), 5000, dtype=np.uint16)
    swir_dn = np.full((SIZE // 2, SIZE // 2), 2000, dtype=np.uint16)
    scl = np.full((SIZE // 2, SIZE // 2), 4, dtype=np.uint8)  # 20 m: vegetation

    nir_dn[14:18, 14:18] = 2000
    swir_dn[7:9, 7:9] = 4000  # 20 m cells covering 10 m rows/cols 14-17

    scl[10, 10:12] = 9

    write_raster(scene_dir / "nir.tif", nir_dn, nodata=NODATA_DN)
    write_raster(
        scene_dir / "swir.tif",
        swir_dn,
        transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
        nodata=NODATA_DN,
    )
    write_raster(
        scene_dir / "scl.tif",
        scl,
        transform=from_origin(ORIGIN_X, ORIGIN_Y, RES * 2, RES * 2),
        nodata=0,
    )

    # Only the roles NBR needs: red and visual are deliberately absent so a
    # regression that reads them fails loudly.
    candidate = make_candidate(scene_dir, with_visual=False).model_copy(
        update={
            "assets": {
                "nir": str(scene_dir / "nir.tif"),
                "swir": str(scene_dir / "swir.tif"),
                "scl": str(scene_dir / "scl.tif"),
            }
        }
    )
    aoi_geojson = utm_box_to_wgs84_geojson(
        ORIGIN_X + 10 * RES,
        ORIGIN_Y - 30 * RES,
        ORIGIN_X + 30 * RES,
        ORIGIN_Y - 10 * RES,
    )
    return {"candidate": candidate, "aoi_geojson": aoi_geojson}


class TestNbrProcessing:
    @pytest.fixture
    def result(self, tmp_path):
        scene = build_nbr_scene(tmp_path / "nbr_scene")
        acquisition = group_acquisitions([scene["candidate"]], scene["aoi_geojson"])[0]
        grid = CanonicalGrid.from_aoi(scene["aoi_geojson"], resolution_m=10.0)
        return process_acquisition(
            acquisition, grid, CONFIG, tmp_path / "out", sign=IDENTITY, index=INDICES["nbr"]
        )

    def test_scene_usable_with_known_nbr_values(self, result):
        assert result.usable, result.unusable_reason
        stats = result.stats
        assert stats is not None
        # Only the 8 cloud pixels are excluded; the 20 m SWIR resample must
        # leave every other AOI pixel finite.
        assert stats.masked_pixel_count == 8
        assert stats.valid_pixel_count == stats.aoi_pixel_count - 8
        assert stats.ndvi_max == pytest.approx(0.6, abs=1e-2)
        assert stats.ndvi_min == pytest.approx(-0.5, abs=1e-2)

    def test_artifacts_named_by_operation(self, result):
        outputs = result.outputs
        assert outputs is not None
        assert outputs.ndvi_cog.endswith("nbr.tif")
        assert outputs.ndvi_preview.endswith("nbr_preview.png")
        assert Path(outputs.ndvi_cog).exists()
        assert Path(outputs.ndvi_preview).exists()

    def test_summary_records_operation(self, result):
        assert result.outputs is not None
        summary = json.loads(Path(result.outputs.scene_summary).read_text())
        assert summary["operation"] == "nbr"

    def test_swir_resampling_warning_recorded(self, result):
        assert any("SWIR" in w and "20 m" in w for w in result.warnings)


class TestNbrPreview:
    def test_nbr_ramp_brown_low_green_high(self):
        lut = nbr_colormap_lut()
        low, high = lut[0], lut[255]
        assert low[0] > low[1]  # brownish at low NBR (burned/bare)
        assert high[1] > high[0]  # green dominates at high NBR

    def test_index_preview_with_nbr_ramp(self, tmp_path):
        nbr = np.full((10, 10), 0.6, dtype=np.float32)
        nbr[0, 0] = np.nan
        path = tmp_path / "nbr_preview.png"
        write_index_preview(path, nbr, lut=nbr_colormap_lut(), display_min=-1.0, display_max=1.0)
        from PIL import Image

        with Image.open(path) as img:
            arr = np.asarray(img)
        assert arr[0, 0, 3] == 0  # invalid -> transparent
        assert arr[5, 5, 3] == 255
        assert arr[5, 5, 1] > arr[5, 5, 0]  # healthy vegetation renders green


class TestDefaultIndexUnchanged:
    def test_default_index_is_ndvi(self, synthetic_scene, tmp_path):
        """process_acquisition without an index argument keeps NDVI behavior."""
        scene = synthetic_scene
        acquisition = group_acquisitions([scene["candidate"]], scene["aoi_geojson"])[0]
        grid = CanonicalGrid.from_aoi(scene["aoi_geojson"], resolution_m=10.0)
        result = process_acquisition(acquisition, grid, CONFIG, tmp_path / "out", sign=IDENTITY)
        assert result.usable, result.unusable_reason
        assert result.outputs is not None
        assert result.outputs.ndvi_cog.endswith("ndvi.tif")
        assert result.outputs.ndvi_preview.endswith("ndvi_preview.png")
        summary = json.loads(Path(result.outputs.scene_summary).read_text())
        assert summary["operation"] == "ndvi"
        assert result.stats is not None
        assert result.stats.ndvi_max == pytest.approx(0.5, abs=1e-3)
