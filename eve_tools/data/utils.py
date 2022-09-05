import hashlib
import inspect
import pickle
import re

from dataclasses import dataclass, field
from typing import List, Tuple, Union, Callable, Coroutine, TYPE_CHECKING

from eve_tools.log import getLogger

logger = getLogger(__name__)

if TYPE_CHECKING:
    from eve_tools.data.db import ESIDBManager


# ---- Cache Utility classes ---- #


class _CacheRecordBaseClass:
    """Base class holding all cache instances.
    Provides stats over all instances."""

    instances = set()

    @property
    def record(self):
        """Returns a list of record, one for each cache instance."""
        ret = [_cache.record for _cache in self.instances]
        return ret


CacheStats = _CacheRecordBaseClass()


@dataclass
class _CacheRecord:
    """Records hits and misses of a cache instance."""

    db_name: str
    table: str
    caller: str = None
    hits: int = 0
    miss: int = 0


@dataclass
class InsertBuffer:

    db: "ESIDBManager"
    table: str
    buffer: List[Tuple] = field(default_factory=list)  # [(key_hash, value, expires), ...]
    cap: int = 50

    def flush(self):
        self.db.execute("BEGIN")
        for param in self.buffer:
            self.db.execute(f"INSERT OR REPLACE INTO {self.table} VALUES(?,?,?)", param)
        self.db.commit()
        self.clear()
        logger.debug("Cache entries flushed")

    def insert(self, entry: Tuple):
        if len(self.buffer) >= self.cap:
            self.flush()

        self.buffer.append(entry)

    def select(self, key_hash):
        for b in self.buffer:
            if b[0] == key_hash:
                return b
        return None

    def clear(self):
        del self.buffer
        self.buffer = []

    def __contains__(self, key):
        _h = hash_key(key)
        for b in self.buffer:
            if b[0] == _h:
                return True
        return False

    def __len__(self):
        return len(self.buffer)


# ---- Utility functions ---- #


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

    ret = (_h, pickle.dumps(func_args), pickle.dumps(func_kwd), func.__qualname__)
    return ret


def function_hash(func: Union[Callable, Coroutine]):
    """Hashes a function.

    Hashes a function based on its source code. If the source code is modified in any way,
    this function hashes to a different value. If docstring is changed, hash should remain intact.
    """
    source_code = inspect.getsource(func)
    source_code = re.sub(r'"""[\w\W]+?"""\n', "", source_code)
    return "esi_function-{}-{}".format(
        func.__qualname__,
        hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
    )


def hash_key(key) -> str:
    """Default hashing function for a key. Using sha256 as hash function."""
    name = key[-1]
    return f"esi_cache-{name}-" + hashlib.sha256(pickle.dumps(key)).hexdigest()
