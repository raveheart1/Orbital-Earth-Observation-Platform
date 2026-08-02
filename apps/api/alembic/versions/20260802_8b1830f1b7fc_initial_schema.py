# type: ignore
"""initial schema

Revision ID: 8b1830f1b7fc
Revises:
Create Date: 2026-08-02 20:30:37.383139+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "8b1830f1b7fc"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostGIS must exist before any geometry column is created. On Azure
    # Database for PostgreSQL Flexible Server this requires POSTGIS in the
    # azure.extensions allowlist (handled by Terraform).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_geospatial_table(
        "regions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "bbox",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("is_predefined", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regions")),
        sa.UniqueConstraint("name", name=op.f("uq_regions_name")),
    )
    op.create_geospatial_index(
        "idx_regions_geometry",
        "regions",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_regions_slug"), "regions", ["slug"], unique=True)
    op.create_geospatial_table(
        "analyses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("region_id", sa.UUID(), nullable=True),
        sa.Column(
            "geometry",
            Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "bbox",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("collection", sa.String(length=80), nullable=False),
        sa.Column("max_cloud_cover_pct", sa.Float(), nullable=False),
        sa.Column("scene_limit", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column(
            "processing_config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.Column("git_commit_sha", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                name="analysis_status",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("status_message", sa.String(length=500), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failure_category",
            sa.Enum(
                "user_input",
                "data",
                "transient",
                "timeout",
                "internal",
                name="failure_category",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "failure_detail",
            sa.String(length=1000),
            nullable=True,
            comment="Sanitized; never raw exception dumps",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("output_prefix", sa.String(length=300), nullable=True),
        sa.Column(
            "summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["region_id"],
            ["regions.id"],
            name=op.f("fk_analyses_region_id_regions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_geospatial_index(
        "idx_analyses_geometry",
        "analyses",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_analyses_status"), "analyses", ["status"], unique=False)
    op.create_index(
        "ix_analyses_status_submitted", "analyses", ["status", "submitted_at"], unique=False
    )
    op.create_index(op.f("ix_analyses_submitted_at"), "analyses", ["submitted_at"], unique=False)
    op.create_geospatial_table(
        "scenes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("stac_collection", sa.String(length=80), nullable=False),
        sa.Column("stac_item_id", sa.String(length=120), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "geometry",
            Geometry(
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "bbox",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("cloud_cover_pct", sa.Float(), nullable=True),
        sa.Column("source_provider", sa.String(length=120), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=True),
        sa.Column(
            "instruments",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "assets",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            comment="Original unsigned asset hrefs by role",
        ),
        sa.Column(
            "selection_status",
            sa.Enum(
                "selected", "excluded", name="scene_selection_status", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("exclusion_reason", sa.String(length=120), nullable=True),
        sa.Column(
            "quality",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
            comment="aoi_overlap_pct, processing_baseline, unusable_reason, warnings",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_scenes_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenes")),
        sa.UniqueConstraint("analysis_id", "stac_item_id", name="uq_scenes_analysis_item"),
    )
    op.create_geospatial_index(
        "idx_scenes_geometry",
        "scenes",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(op.f("ix_scenes_analysis_id"), "scenes", ["analysis_id"], unique=False)
    op.create_index(
        "ix_scenes_analysis_observed", "scenes", ["analysis_id", "observed_at"], unique=False
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("scene_id", sa.UUID(), nullable=True),
        sa.Column(
            "artifact_type",
            sa.Enum(
                "ndvi_cog",
                "ndvi_preview",
                "true_color_preview",
                "scene_summary",
                "timeseries_csv",
                "analysis_summary",
                "provenance",
                name="artifact_type",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("container", sa.String(length=80), nullable=False),
        sa.Column("blob_path", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("crs", sa.String(length=40), nullable=True),
        sa.Column(
            "bbox",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "provenance",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_artifacts_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_artifacts_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
        sa.UniqueConstraint("analysis_id", "blob_path", name="uq_artifacts_analysis_path"),
    )
    op.create_index(op.f("ix_artifacts_analysis_id"), "artifacts", ["analysis_id"], unique=False)
    op.create_table(
        "observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("scene_id", sa.UUID(), nullable=False),
        sa.Column("ndvi_min", sa.Float(), nullable=True),
        sa.Column("ndvi_max", sa.Float(), nullable=True),
        sa.Column("ndvi_mean", sa.Float(), nullable=True),
        sa.Column("ndvi_median", sa.Float(), nullable=True),
        sa.Column("ndvi_std", sa.Float(), nullable=True),
        sa.Column("ndvi_p10", sa.Float(), nullable=True),
        sa.Column("ndvi_p25", sa.Float(), nullable=True),
        sa.Column("ndvi_p75", sa.Float(), nullable=True),
        sa.Column("ndvi_p90", sa.Float(), nullable=True),
        sa.Column("valid_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("masked_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("aoi_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("valid_pixel_pct", sa.Float(), nullable=False),
        sa.Column("zero_denominator_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "mask_scl_classes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "band_scaling",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "processing_params",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("processing_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_observations_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"],
            ["scenes.id"],
            name=op.f("fk_observations_scene_id_scenes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observations")),
        sa.UniqueConstraint("scene_id", name=op.f("uq_observations_scene_id")),
    )
    op.create_index(
        op.f("ix_observations_analysis_id"), "observations", ["analysis_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_observations_analysis_id"), table_name="observations")
    op.drop_table("observations")
    op.drop_index(op.f("ix_artifacts_analysis_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_scenes_analysis_observed", table_name="scenes")
    op.drop_index(op.f("ix_scenes_analysis_id"), table_name="scenes")
    op.drop_geospatial_index(
        "idx_scenes_geometry", table_name="scenes", postgresql_using="gist", column_name="geometry"
    )
    op.drop_geospatial_table("scenes")
    op.drop_index(op.f("ix_analyses_submitted_at"), table_name="analyses")
    op.drop_index("ix_analyses_status_submitted", table_name="analyses")
    op.drop_index(op.f("ix_analyses_status"), table_name="analyses")
    op.drop_geospatial_index(
        "idx_analyses_geometry",
        table_name="analyses",
        postgresql_using="gist",
        column_name="geometry",
    )
    op.drop_geospatial_table("analyses")
    op.drop_index(op.f("ix_regions_slug"), table_name="regions")
    op.drop_geospatial_index(
        "idx_regions_geometry",
        table_name="regions",
        postgresql_using="gist",
        column_name="geometry",
    )
    op.drop_geospatial_table("regions")
