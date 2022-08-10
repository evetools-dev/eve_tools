from .db import ESIDBManager
from .cache import SqliteCache, make_cache_key, function_hash, CacheStats

ESIDB = ESIDBManager("esi")
CacheDB = ESIDBManager("cache")
api_cache = SqliteCache(CacheDB, table="api_cache")
