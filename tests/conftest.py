"""Pytest fixtures: ephemeral Postgres testcontainer + per-test session with rollback."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from gateway.db import models  # noqa: F401  registers tables on Base.metadata
from gateway.db.base import Base


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container: PostgresContainer) -> str:
    raw = pg_container.get_connection_url()
    # testcontainers returns psycopg2 url; switch to asyncpg
    return raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest_asyncio.fixture(scope="session")
async def db_engine(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION audit_log_no_modify_fn() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_log is append-only'; END;
            $$ LANGUAGE plpgsql;
            """
        )
        await conn.exec_driver_sql(
            """
            DROP TRIGGER IF EXISTS audit_log_no_modify ON audit_log;
            CREATE TRIGGER audit_log_no_modify
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify_fn();
            """
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    """Transactional fixture — every test rolls back."""
    async with db_engine.connect() as conn:
        trans = await conn.begin()
        sess = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield sess
        finally:
            await sess.close()
            await trans.rollback()
