from .db import ESIDBManager
from .cache import SqliteCache

ESIDB = ESIDBManager("esi")
CacheDB = ESIDBManager("cache")
api_cache = SqliteCache(CacheDB)
