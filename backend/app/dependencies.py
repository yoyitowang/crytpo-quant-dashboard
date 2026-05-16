from redis import asyncio as aioredis

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    return _redis


def set_redis(r: aioredis.Redis | None) -> None:
    global _redis
    _redis = r
