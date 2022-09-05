"""Implementation ideas referenced from ESIPy under BSD-3-Clause License"""
import atexit
import inspect
import pickle
from email.utils import parsedate
from datetime import datetime, timedelta
from typing import Union

from .utils import _CacheRecordBaseClass, _CacheRecord, InsertBuffer, hash_key
from eve_tools.data import ESIDBManager
from eve_tools.log import getLogger

logger = getLogger(__name__)


class BaseCache(_CacheRecordBaseClass):
    """Specifies BaseCache object used by other caching implimentation.

    Requires set and get method for api(s) to access the cache.
    evict is useful for testing. Expired entries should be deleted in get or set,
    so user would not be required to call evict all the time.
    User of BaseCache should call super().__init__() to register instance under cache stats.
    """

    def __init__(self, esidb: ESIDBManager, table: str):
        self.__class__.instances.add(self)
        module = inspect.getmodule(inspect.stack(0)[2][0])
        if module is not None:
            module = module.__name__
        self._record = _CacheRecord(esidb.db_name, table, module)

    def set(self, key, value, expires):
        raise NotImplementedError

    def get(self, key, default):
        raise NotImplementedError

    def evict(self, key):
        raise NotImplementedError

    @property
    def record(self):
        return self._record

    @property
    def hits(self):
        return self._record.hits

    @property
    def miss(self):
        return self._record.miss

    @hits.setter
    def hits(self, val):
        self._record.hits = val

    @miss.setter
    def miss(self, val):
        self._record.miss = val


class SqliteCache(BaseCache):
    """A Sqlite implementation of cache.

    Each api cache entry is stored in a single line in cache.db.
    The value is serialized/deserialized using pickle.
    Expired entries are deleted in get().
    """

    def __init__(self, esidb: ESIDBManager, table: str):
        self.c = esidb
        self.table = table
        self.buffer = InsertBuffer(self.c, self.table)
        atexit.register(self.buffer.flush)

        self._last_used = None  # used for testing
        super().__init__(esidb, table)
        logger.info("SqliteCache initiated: %s-%s", esidb.db_name, table)

    def set(self, key, value, expires: Union[str, int] = None):
        """Sets k/v pair with expires.

        Args:
            key: An object returned from make_cache_key(), which is pickled and hashed using hash_key().
            value: An object to put into cache. Needs to be pickle(able).
            expires: A str or int.
                If a string is provided, it should be in any standard datetime format.
                ESI returns a datetime string in RFC7231 format.
                If an int is provided, it should be a custom expire threshold in seconds, such as 1200 for 20 minutes.
                If not provided, default expire in 20 minutes.
        """
        if not expires:
            expires = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=1200)
        elif isinstance(expires, int):
            expires = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=expires)
        else:
            expires = datetime(*parsedate(expires)[:6])

        _h = hash_key(key)
        entry = (_h, pickle.dumps(value), expires)
        self.buffer.insert(entry)
        logger.debug("Cache entry set: %s", _h)

    def get(self, key, default=None):
        """Gets the value from cache.

        Attempts to return value with key from cache. A default value is returned if unsuccessful.
        Checks if db entry is expired and delete if necessary.

        Args:
            key: An object returned from make_cache_key(), which is pickled and hashed using hash_key().
            default: If cache returns nothing, returns a default value. Default None.
        """
        _h = hash_key(key)
        row = self.c.execute(f"SELECT * FROM {self.table} WHERE key=?", (_h,)).fetchone()  # should use fetchall and check
        if not row:
            row = self.buffer.select(_h)
        if not row:
            logger.debug("Cache MISS: %s", _h)
            self.miss += 1
            return default

        expires = row[2]
        if isinstance(expires, str):  # expires selected from DB is str, selected from buffer is datatime
            expires = datetime.strptime(expires, "%Y-%m-%d %H:%M:%S")

        if datetime.utcnow() > expires:
            logger.debug("Cache EXPIRED: %s", _h)
            self.miss += 1
            self.c.execute(f"DELETE FROM {self.table} WHERE key=?", (_h,))
            self.c.commit()
            return default  # expired
        else:
            self._last_used = _h
            logger.debug("Cache HIT: %s", _h)
            self.hits += 1
            return pickle.loads(row[1])  # value

    def evict(self, key):
        """Deletes cache entry with key. Useful in testing."""
        _h = hash_key(key)
        self.c.execute(f"DELETE FROM {self.table} WHERE key=?", (_h,))
        self.c.commit()
        logger.debug("Cache entry evicted: %s", _h)
