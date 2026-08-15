"""Server-side constraint enforcement tests (no database required)."""

from __future__ import annotations

import math
import uuid
from datetime import date

import pytest

from earth_observation.errors import UserInputError
from earth_observation.geometry import bbox_polygon, geodesic_area_km2
from oeop_api.problem import ProblemException
from oeop_api.rate_limit import SubmissionRateLimiter
from oeop_api.schemas import AnalysisCreateRequest
from oeop_api.services.analysis_service import (
    _validate_dates,
    _validate_scene_limit,
    create_analysis,
)
from oeop_api.services.serializers import geometry_to_geojson
from oeop_core.settings import Settings


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def request_for(start: str, end: str, scene_limit: int | None = None, **overrides):
    return AnalysisCreateRequest(
        bbox=(-83.3, 42.5, -83.2, 42.6),
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        scene_limit=scene_limit,
        **overrides,
    )


class TestDateValidation:
    def test_valid_range_passes(self):
        _validate_dates(request_for("2024-05-01", "2024-09-01"), make_settings())

    def test_reversed_dates_rejected(self):
        with pytest.raises(UserInputError, match="on or after"):
            _validate_dates(request_for("2024-09-01", "2024-05-01"), make_settings())

    def test_pre_archive_dates_rejected(self):
        with pytest.raises(UserInputError, match="archive"):
            _validate_dates(request_for("2001-01-01", "2001-06-01"), make_settings())

    def test_future_start_rejected(self):
        with pytest.raises(UserInputError, match="future"):
            _validate_dates(request_for("2099-01-01", "2099-06-01"), make_settings())

    def test_span_limit_enforced(self):
        with pytest.raises(UserInputError, match="exceeds the maximum"):
            _validate_dates(
                request_for("2018-01-01", "2024-01-01"),
                make_settings(max_date_span_days=365),
            )

    def test_demo_mode_tightens_span(self):
        settings = make_settings(demo_mode=True, demo_max_date_span_days=100)
        with pytest.raises(UserInputError):
            _validate_dates(request_for("2024-01-01", "2024-06-30"), settings)


class TestSceneLimit:
    def test_default_applied(self):
        settings = make_settings()
        assert (
            _validate_scene_limit(request_for("2024-05-01", "2024-06-01"), settings)
            == settings.default_scene_limit
        )

    def test_over_limit_rejected(self):
        settings = make_settings(max_scene_limit=8)
        with pytest.raises(UserInputError, match="maximum"):
            _validate_scene_limit(request_for("2024-05-01", "2024-06-01", scene_limit=50), settings)


class TestRateLimiter:
    def test_allows_up_to_limit_then_429(self):
        limiter = SubmissionRateLimiter(3)
        for _ in range(3):
            limiter.check("1.2.3.4")
        with pytest.raises(ProblemException) as excinfo:
            limiter.check("1.2.3.4")
        assert excinfo.value.status_code == 429

    def test_clients_are_independent(self):
        limiter = SubmissionRateLimiter(1)
        limiter.check("1.1.1.1")
        limiter.check("2.2.2.2")  # different client unaffected


class TestCustomAreaLimits:
    """Drawn areas are capped far tighter than predefined regions.

    Predefined regions are curated and run at ~84-137 km²; arbitrary public
    submissions are bounded to a few km² so processing stays cheap. Conflating
    the two limits would either break every region or remove the cost control.
    """

    def test_custom_limit_default_is_calibrated_to_measured_cost(self):
        """Outputs run ~0.06 MB/scene/km2 against a 200 MB per-analysis cap, so
        storage binds near 417 km2 at 8 scenes. The default keeps margin."""
        limit = make_settings().effective_max_custom_aoi_area_km2()
        assert limit == 250.0
        assert limit < 417, "must stay under the storage ceiling at 8 scenes"

    def test_custom_limit_does_not_exceed_the_region_limit(self):
        settings = make_settings()
        assert settings.effective_max_custom_aoi_area_km2() <= settings.max_aoi_area_km2

    def test_custom_limit_never_exceeds_the_global_ceiling(self):
        settings = make_settings(max_aoi_area_km2=1.0, max_custom_aoi_area_km2=50.0)
        assert settings.effective_max_custom_aoi_area_km2() == 1.0

    def test_custom_limit_is_configurable(self):
        settings = make_settings(max_custom_aoi_area_km2=25.0)
        assert settings.effective_max_custom_aoi_area_km2() == 25.0

    def test_custom_areas_enabled_by_default_even_in_demo_mode(self):
        assert make_settings(demo_mode=True).allow_custom_areas is True

    def test_custom_areas_can_be_switched_off(self):
        assert make_settings(allow_custom_areas=False).allow_custom_areas is False


#: Non-rectangular drawn AOI: the L covers three quadrants of its bounding box.
L_SHAPED_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-83.30, 42.50],
            [-83.20, 42.50],
            [-83.20, 42.55],
            [-83.25, 42.55],
            [-83.25, 42.60],
            [-83.30, 42.60],
            [-83.30, 42.50],
        ]
    ],
}


def regular_polygon(vertices: int) -> dict:
    """Regular ``vertices``-gon near Detroit, closing vertex appended."""
    ring = [
        [
            -83.25 + 0.02 * math.cos(2 * math.pi * i / vertices),
            42.55 + 0.02 * math.sin(2 * math.pi * i / vertices),
        ]
        for i in range(vertices)
    ]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def polygon_request(geometry: dict, **overrides):
    fields: dict = {
        "geometry": geometry,
        "start_date": date.fromisoformat("2024-05-01"),
        "end_date": date.fromisoformat("2024-09-01"),
    }
    fields.update(overrides)
    return AnalysisCreateRequest(**fields)


class FakeSession:
    """Just enough of the AsyncSession surface for create_analysis; no database."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        # A real refresh reads back the server-generated primary key.
        if obj.id is None:
            obj.id = uuid.uuid4()


class FakeQueue:
    def __init__(self):
        self.sent = []

    def send_analysis(self, analysis_id: str) -> None:
        self.sent.append(analysis_id)


async def submit(request: AnalysisCreateRequest, settings: Settings | None = None):
    return await create_analysis(
        session=FakeSession(),
        queue=FakeQueue(),
        settings=settings or make_settings(),
        request=request,
    )


class TestPolygonSubmissions:
    """Freeform GeoJSON polygons are accepted alongside bbox rectangles.

    Drawn polygons get a restricted grammar — one Polygon, exterior ring only,
    bounded vertex count — so arbitrary public submissions stay cheap and
    predictable; area caps, storage, and serialization follow the bbox path.
    """

    async def test_l_shaped_polygon_accepted(self):
        session, queue = FakeSession(), FakeQueue()
        analysis = await create_analysis(
            session=session,
            queue=queue,
            settings=make_settings(),
            request=polygon_request(L_SHAPED_POLYGON),
        )
        # The stored bbox is derived from the polygon's bounds, but the area
        # is the geodesic area of the polygon itself: the L covers three
        # quadrants of its bounding box, so it measures ~3/4 of the box.
        assert analysis.bbox == [-83.3, 42.5, -83.2, 42.6]
        box_area = geodesic_area_km2(bbox_polygon((-83.3, 42.5, -83.2, 42.6)))
        assert analysis.area_km2 == pytest.approx(0.75 * box_area, rel=1e-3)
        assert analysis.region_id is None
        # The response serializer echoes exactly the polygon that was drawn.
        assert geometry_to_geojson(analysis.geometry) == L_SHAPED_POLYGON
        assert queue.sent == [str(analysis.id)]

    async def test_bbox_path_still_accepts_rectangles(self):
        analysis = await submit(request_for("2024-05-01", "2024-09-01"))
        assert analysis.bbox == [-83.3, 42.5, -83.2, 42.6]
        assert geometry_to_geojson(analysis.geometry)["type"] == "Polygon"

    async def test_feature_wrapper_rejected(self):
        feature = {"type": "Feature", "properties": {}, "geometry": L_SHAPED_POLYGON}
        with pytest.raises(UserInputError, match="not a Feature"):
            await submit(polygon_request(feature))

    async def test_multipolygon_rejected(self):
        multi = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[-83.3, 42.5], [-83.28, 42.5], [-83.28, 42.52], [-83.3, 42.52], [-83.3, 42.5]]],
                [[[-83.2, 42.5], [-83.18, 42.5], [-83.18, 42.52], [-83.2, 42.52], [-83.2, 42.5]]],
            ],
        }
        with pytest.raises(UserInputError, match="single Polygon"):
            await submit(polygon_request(multi))

    async def test_polygon_with_hole_rejected(self):
        holed = {
            "type": "Polygon",
            "coordinates": [
                [[-83.3, 42.5], [-83.2, 42.5], [-83.2, 42.6], [-83.3, 42.6], [-83.3, 42.5]],
                [
                    [-83.27, 42.53],
                    [-83.23, 42.53],
                    [-83.23, 42.57],
                    [-83.27, 42.57],
                    [-83.27, 42.53],
                ],
            ],
        }
        with pytest.raises(UserInputError, match="holes"):
            await submit(polygon_request(holed))

    async def test_self_intersecting_bowtie_rejected(self):
        bowtie = {
            "type": "Polygon",
            "coordinates": [
                [[-83.3, 42.5], [-83.2, 42.6], [-83.3, 42.6], [-83.2, 42.5], [-83.3, 42.5]]
            ],
        }
        with pytest.raises(UserInputError, match="Self-intersection"):
            await submit(polygon_request(bowtie))

    async def test_vertex_count_at_the_ceiling_accepted(self):
        analysis = await submit(polygon_request(regular_polygon(256)))
        assert analysis.area_km2 > 0

    async def test_vertex_count_over_the_ceiling_rejected(self):
        with pytest.raises(UserInputError, match="300 vertices, exceeding the maximum of 256"):
            await submit(polygon_request(regular_polygon(300)))

    async def test_over_area_polygon_rejected_with_polygon_wording(self):
        settings = make_settings(max_custom_aoi_area_km2=10.0)
        with pytest.raises(UserInputError, match="Draw a smaller polygon"):
            await submit(polygon_request(L_SHAPED_POLYGON), settings)

    async def test_geometry_and_bbox_together_rejected(self):
        request = polygon_request(L_SHAPED_POLYGON, bbox=(-83.3, 42.5, -83.2, 42.6))
        with pytest.raises(UserInputError, match="exactly one"):
            await submit(request)

    async def test_geometry_and_region_id_together_rejected(self):
        request = polygon_request(L_SHAPED_POLYGON, region_id=uuid.uuid4())
        with pytest.raises(UserInputError, match="exactly one"):
            await submit(request)


class TestOperation:
    """The operation selects the spectral index; unknown names never enqueue."""

    async def test_default_operation_is_ndvi(self):
        analysis = await submit(request_for("2024-05-01", "2024-09-01"))
        assert analysis.operation == "ndvi"

    async def test_nbr_operation_persisted(self):
        analysis = await submit(request_for("2024-05-01", "2024-09-01", operation="nbr"))
        assert analysis.operation == "nbr"

    async def test_unknown_operation_rejected_with_supported_list(self):
        with pytest.raises(UserInputError, match=r"Unknown operation 'ndwi'.*nbr.*ndvi"):
            await submit(request_for("2024-05-01", "2024-09-01", operation="ndwi"))
