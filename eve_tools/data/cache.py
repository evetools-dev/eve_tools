"""Implementation referenced from ESIPy under BSD-3-Clause License"""
import hashlib
import inspect
import logging
import pickle
from email.utils import parsedate
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Coroutine, Union, Callable

from eve_tools.data.db import ESIDBManager

logger = logging.getLogger(__name__)


def hash_key(key) -> str:
    """Default hashing function for a key. Using sha256 as hash function."""
    return "esi_cache-" + hashlib.sha256(pickle.dumps(key)).hexdigest()


class _CacheRecordBaseClass:
    """Base class holding all cache instances.
    Provides stats over all instances."""

    instances = set()

    @property
    def record(self):
        ret = [_cache.record for _cache in self.instances]
        return ret


CacheStats = _CacheRecordBaseClass()


@dataclass
class _CacheRecord:
    """Records hits and misses of a cache instance."""

    caller: str = None
    id: int = 0
    hits: int = 0
    miss: int = 0


class BaseCache(_CacheRecordBaseClass):
    """Specifies BaseCache object used by other caching implimentation.

    Requires set and get method for api(s) to access the cache.
    evict is useful for testing. Expired entries should be deleted in get or set,
    so user would not be required to call evict all the time.
    User of BaseCache should call super().__init__() to register instance under cache stats.
    """

    def __init__(self):
        self.__class__.instances.add(self)
        self._record = _CacheRecord()
        module = inspect.getmodule(inspect.stack(0)[2][0])
        if module is not None:
            module = module.__name__
        self._record.caller = module
        self._record.id = id(self)

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

        self._last_used = None  # used for testing
        super().__init__()

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
            expires = datetime.utcnow().replace(microsecond=0) + timedelta(
                seconds=expires
            )
        else:
            expires = datetime(*parsedate(expires)[:6])

        _h = hash_key(key)
        self.c.cursor.execute(
            f"INSERT OR REPLACE INTO {self.table} VALUES(?,?,?)",
            (_h, pickle.dumps(value), expires),
        )
        self.c.conn.commit()
        logger.info("Cache entry set: %s", _h)

    def get(self, key, default=None):
        """Gets the value from cache.

        Attempts to return value with key from cache. A default value is returned if unsuccessful.
        Deletes all expired keys everytime get() is called.

        Args:
            key: An object returned from make_cache_key(), which is pickled and hashed using hash_key().
            default: If cache returns nothing, returns a default value. Default None.
        """
        self.c.cursor.execute(f"DELETE FROM {self.table} WHERE expires < DATE('now')")
        self.c.conn.commit()

        _h = hash_key(key)
        row = self.c.cursor.execute(
            f"SELECT * FROM {self.table} WHERE key=?", (_h,)
        ).fetchone()
        if not row:
            logger.info("Cache MISS: %s", _h)
            self.miss += 1
            return default

        expires = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() > expires:
            logger.info("Cache MISS: %s", _h)
            self.miss += 1
            return default  # expired
        else:
            self._last_used = _h
            logger.info("Cache HIT: %s", _h)
            self.hits += 1
            return pickle.loads(row[1])  # value

    def evict(self, key):
        """Deletes cache entry with key. Useful in testing."""
        _h = hash_key(key)
        self.c.cursor.execute(f"DELETE FROM {self.table} WHERE key=?", (_h,))
        self.c.conn.commit()
        logger.info("Cache entry evicted: %s", _h)


def make_cache_key(func: Union[Callable, Coroutine], *args, **kwd):
    """Hashes a function and its arguments using sha256.

    The function is hashed using function_hash() to a string.
    The args and kwds are pickled to bytes.
    If any of args or kwd is a function, this function encodes them by inspecting source code.
    If the source code is changed, this function encodes a different value.

    Args:
        func: A function or a coroutine.
        args: Argument passed to the api function in argument form.
        kwd: Keyword arguments passed to the api function.

    Returns:
        A set containing (function_hash, str(args), str(kwd))

    Examples:
    >>> # Encode: get_market_history("The Forge", reduces=reduce_volume)
    >>> key_before = make_cache_key(get_market_history, "The Forge", reduce_volume)
    >>> # If reduce_volume is changed, even if a space or an extra line is added
    >>> key_after = make_cache_key(get_market_history, "The Forge", reduce_volume)
    >>> assert key_before != key_after
    """
    func_args = list(args)
    func_kwd = kwd.copy()
    for i in range(len(func_args)):
        if isinstance(func_args[i], Callable):
            func_args[i] = function_hash(func_args[i])
        if isinstance(func_args[i], list):
            func_args[i] = list(set(func_args[i]))
    for k in func_kwd:
        if isinstance(func_kwd[k], Callable):
            func_kwd[k] = function_hash(func_kwd[k])
        if isinstance(func_kwd[k], list):
            func_kwd[k] = list(set(func_kwd[k]))
    _h = function_hash(func)

    ret = (_h, pickle.dumps(func_args), pickle.dumps(func_kwd))
    logger.info("Making cache key for %s", func.__qualname__)
    return ret


def function_hash(func: Union[Callable, Coroutine]):
    """Hashes a function.

    Hashes a function based on its source code. If the source code is modified in any way,
    this function hashes to a different value.
    """
    return "esi_function-{}-{}".format(
        func.__qualname__,
        hashlib.sha256(inspect.getsource(func).encode("utf-8")).hexdigest(),
    )
