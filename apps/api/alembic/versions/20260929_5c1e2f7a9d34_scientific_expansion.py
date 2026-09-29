# type: ignore
"""scientific expansion: land cover, temporal context, wildfire dNBR, measurement cache

Revision ID: 5c1e2f7a9d34
Revises: ae9c0e93a493
Create Date: 2026-09-29 16:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5c1e2f7a9d34"
down_revision: str | None = "ae9c0e93a493"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Existing analyses were all index time series; the server default records
    # that. `options` stays NULL for them, which parses to the pre-expansion
    # behaviour (no land-cover stratification, no temporal context).
    op.add_column(
        "analyses",
        sa.Column(
            "workflow",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'timeseries'"),
            comment="timeseries = index time series; wildfire_dnbr = pre/post-fire dNBR",
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "options",
            JSONB,
            nullable=True,
            comment="Validated AnalysisOptions snapshot (land cover, temporal context, "
            "wildfire windows); NULL for analyses that predate options",
        ),
    )
    op.create_index("ix_analyses_workflow", "analyses", ["workflow"])
    op.add_column(
        "regions",
        sa.Column(
            "event",
            JSONB,
            nullable=True,
            comment="Documented event context (e.g. a wildfire's dates and suggested "
            "pre/post windows); proposes defaults, never supplies results",
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=True,
            comment="pre_fire / post_fire in the wildfire workflow",
        ),
    )

    op.create_table(
        "observation_class_stats",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("observation_id", sa.UUID(), nullable=False),
        sa.Column("class_code", sa.Integer(), nullable=False),
        sa.Column("class_key", sa.String(length=40), nullable=False),
        sa.Column("class_name", sa.String(length=80), nullable=False),
        sa.Column("aoi_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("aoi_area_km2", sa.Float(), nullable=False),
        sa.Column("aoi_pct", sa.Float(), nullable=False),
        sa.Column("valid_pixel_count", sa.BigInteger(), nullable=False),
        sa.Column("valid_fraction", sa.Float(), nullable=False),
        sa.Column("index_mean", sa.Float(), nullable=True),
        sa.Column("index_median", sa.Float(), nullable=True),
        sa.Column("index_std", sa.Float(), nullable=True),
        sa.Column("index_min", sa.Float(), nullable=True),
        sa.Column("index_max", sa.Float(), nullable=True),
        sa.Column("index_p10", sa.Float(), nullable=True),
        sa.Column("index_p25", sa.Float(), nullable=True),
        sa.Column("index_p75", sa.Float(), nullable=True),
        sa.Column("index_p90", sa.Float(), nullable=True),
        sa.Column("quality_state", sa.String(length=32), nullable=False),
        sa.Column("quality", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observation_id", "class_code", name="uq_class_stats_observation_class"
        ),
    )
    op.create_index(
        "ix_observation_class_stats_analysis_id", "observation_class_stats", ["analysis_id"]
    )
    op.create_index(
        "ix_observation_class_stats_observation_id",
        "observation_class_stats",
        ["observation_id"],
    )

    op.create_table(
        "observation_anomalies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("observation_id", sa.UUID(), nullable=False),
        sa.Column("stratum", sa.String(length=40), nullable=False),
        sa.Column("class_code", sa.Integer(), nullable=True),
        sa.Column("observed", sa.Float(), nullable=True),
        sa.Column("expected", sa.Float(), nullable=True),
        sa.Column("absolute_anomaly", sa.Float(), nullable=True),
        sa.Column("relative_anomaly_pct", sa.Float(), nullable=True),
        sa.Column("robust_z", sa.Float(), nullable=True),
        sa.Column("baseline_n_samples", sa.Integer(), nullable=False),
        sa.Column("baseline_n_years", sa.Integer(), nullable=False),
        sa.Column("robust_sigma", sa.Float(), nullable=True),
        sa.Column("iqr_low", sa.Float(), nullable=True),
        sa.Column("iqr_high", sa.Float(), nullable=True),
        sa.Column("range_low", sa.Float(), nullable=True),
        sa.Column("range_high", sa.Float(), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("quality_state", sa.String(length=32), nullable=False),
        sa.Column("quality", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "stratum", name="uq_anomalies_observation_stratum"),
    )
    op.create_index(
        "ix_observation_anomalies_analysis_id", "observation_anomalies", ["analysis_id"]
    )
    op.create_index(
        "ix_observation_anomalies_observation_id", "observation_anomalies", ["observation_id"]
    )
    op.create_index(
        "ix_anomalies_analysis_classification",
        "observation_anomalies",
        ["analysis_id", "classification"],
    )

    op.create_table(
        "acquisition_measurements",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("grid_signature", sa.String(length=200), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("acquisition_key", sa.String(length=200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.Column("measurement", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )
    op.create_index(
        "ix_acquisition_measurements_grid_signature",
        "acquisition_measurements",
        ["grid_signature"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_acquisition_measurements_grid_signature", table_name="acquisition_measurements"
    )
    op.drop_table("acquisition_measurements")
    op.drop_index("ix_anomalies_analysis_classification", table_name="observation_anomalies")
    op.drop_index("ix_observation_anomalies_observation_id", table_name="observation_anomalies")
    op.drop_index("ix_observation_anomalies_analysis_id", table_name="observation_anomalies")
    op.drop_table("observation_anomalies")
    op.drop_index("ix_observation_class_stats_observation_id", table_name="observation_class_stats")
    op.drop_index("ix_observation_class_stats_analysis_id", table_name="observation_class_stats")
    op.drop_table("observation_class_stats")
    op.drop_column("scenes", "role")
    op.drop_column("regions", "event")
    op.drop_index("ix_analyses_workflow", table_name="analyses")
    op.drop_column("analyses", "options")
    op.drop_column("analyses", "workflow")
