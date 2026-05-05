from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from fastapi import Depends, Request
import redis.asyncio as aioredis

from app.config import Settings, get_settings


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """Yield an async DB session from the app engine."""
    engine = request.app.state.engine
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


async def get_redis(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[aioredis.Redis]:
    """Yield a Redis client."""
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
