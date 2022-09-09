from .db import ESIDBManager
from .cache import SqliteCache
from .utils import make_cache_key, function_hash, CacheStats

ESIDB = ESIDBManager("esi")
CacheDB = ESIDBManager("cache")
api_cache = SqliteCache(CacheDB, table="api_cache")
