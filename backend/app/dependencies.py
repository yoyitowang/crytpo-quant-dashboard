from redis import asyncio as aioredis
from backend.app.services.symbol_inventory import SymbolInventory
from typing import Optional

_redis: Optional[aioredis.Redis] = None
_symbol_inventory: Optional[SymbolInventory] = None


def get_redis() -> Optional[aioredis.Redis]:
    return _redis


def set_redis(r: Optional[aioredis.Redis]) -> None:
    global _redis
    _redis = r


def get_symbol_inventory() -> Optional[SymbolInventory]:
    return _symbol_inventory


def set_symbol_inventory(si: SymbolInventory) -> None:
    global _symbol_inventory
    _symbol_inventory = si
