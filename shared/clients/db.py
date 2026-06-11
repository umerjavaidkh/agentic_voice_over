# shared/clients/db.py

from contextlib import asynccontextmanager

import asyncpg


class DatabasePool:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
            command_timeout=5.0,  # hard 5s query timeout
            server_settings={
                "application_name": "voice-agent",
            },
        )

    @asynccontextmanager
    async def acquire(self):
        async with self.pool.acquire() as conn:
            yield conn

    async def close(self):
        await self.pool.close()
