"""Alembic environment: sync psycopg connection, GeoAlchemy2-aware autogenerate."""

from __future__ import annotations

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

from oeop_core.db import models  # noqa: F401  (register all tables on Base.metadata)
from oeop_core.db.base import Base
from oeop_core.settings import get_settings

config = context.config
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Restrict autogenerate to tables this application owns.

    PostGIS support schemas (tiger geocoder, topology) appear on the local
    image's search path; without this filter autogenerate would try to drop
    them. Delegates to GeoAlchemy2's helper for spatial-index handling.
    """
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    return bool(alembic_helpers.include_object(obj, name, type_, reflected, compare_to))


def get_url() -> str:
    # Migrations run over the sync psycopg driver.
    return get_settings().database_url.replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
