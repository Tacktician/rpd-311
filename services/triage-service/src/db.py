"""asyncpg connection pool + boot-time migration.

The pool is created during the FastAPI lifespan (not at import time) so the module
can be imported by tests without a database. Handlers call get_pool().
"""
from __future__ import annotations

from pathlib import Path

import asyncpg

from .config import config
from .logging_conf import logger

_pool: asyncpg.Pool | None = None

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        host=config.postgres_host,
        port=config.postgres_port,
        user=config.postgres_user,
        password=config.postgres_password,
        database=config.postgres_db,
        min_size=1,
        max_size=10,
        command_timeout=10,
    )


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized.")
    return _pool


async def migrate() -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    async with _pool.acquire() as conn:
        await conn.execute(sql)
    logger.info("Database schema verified. Dispatch board online.")
