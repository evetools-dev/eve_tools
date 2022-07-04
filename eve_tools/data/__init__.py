from .db import ESIDBManager
from .cache import SqliteCache, make_cache_key, function_hash

ESIDB = ESIDBManager("esi")
CacheDB = ESIDBManager("cache")
api_cache = SqliteCache(CacheDB)
