import hashlib
import inspect
import os
import pickle
import re

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union, Callable, Coroutine, TYPE_CHECKING

from eve_tools.config import DATA_DIR
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


class InsertBuffer:
    """Buffers cache.set to avoid repetitive insert transaction."""

    def __init__(self, db: "ESIDBManager", cap: int = 50) -> None:
        self.db = db
    
        self.buffer: List[Tuple] = []  # [((key_hash, value, expires), table), ...]
        self.cap = cap

    def flush(self) -> None:
        """Flushes buffer payload to database file. Buffer payload is cleared after flushing."""
        self.db.execute("BEGIN")
        for entry in self.buffer:
            self.db.execute(f"INSERT OR REPLACE INTO {entry[1]} VALUES({','.join('?'*len(entry[0]))})", entry[0])
        self.db.commit()
        self.clear()
        logger.debug("Cache entries flushed")

    def insert(self, entry: Tuple, table: str) -> None:
        """Inserts db entry to buffer. Flushes if ``cap`` is reached.

        Args:
            entry: (key, value, expires)
                A database entry.
            table: str
                Insert entry to this table.
        """
        if len(self.buffer) >= self.cap:
            self.flush()

        self.buffer.append((entry, table))

    def select(self, key_hash) -> Tuple:
        """Selects value from buffer. Similar to cache.get.

        Args:
            key_hash: hash(key)
                A hashed key, which is retrieved from hash_key() function.
        """
        for b in self.buffer:
            if b[0][0] == key_hash:
                return b[0]
        return None

    def clear(self) -> None:
        """Clears buffer paylaod. Resets to empty list."""
        del self.buffer
        self.buffer = []

    def __contains__(self, key):
        _h = hash_key(key)
        for b in self.buffer:
            if b[0][0] == _h:
                return True
        return False

    def __len__(self):
        return len(self.buffer)


class srcodeBuffer:
    """Buffers inspect.getsource, which takes ~10s out of ~100s in a market history request with 10k type_ids."""

    payload: Dict = {}  # not a dataclass

    @classmethod
    def getsource(cls, func: Union[Callable, Coroutine]):
        key = func.__qualname__
        srcode = cls.payload.get(key)
        if srcode is None:
            srcode = inspect.getsource(func)
            cls.payload[key] = srcode
        return srcode


class _DeleteHandler:
    """Tracks ``expires`` time and deletes when the time has come."""

    def __init__(self, db: "ESIDBManager", table: str):
        self.db = db
        self.table = table

        self.schedule: List = []  # priority queue

        # Read from local cache
        db_dir = os.path.join(DATA_DIR, "db")
        if not os.path.exists(db_dir):
            # Race condition
            try:
                os.makedirs(db_dir)
            except FileExistsError:
                pass
        self.path = os.path.realpath(os.path.join(db_dir, f"{db.db_name}-{table}-delete_schedule.tmp"))
        if os.path.exists(self.path) and os.stat(self.path).st_size > 0:
            with open(self.path, "rb") as f:
                self.schedule = sorted(pickle.load(f))

        self.last_delete: datetime = None

    def update(self, expire: datetime) -> None:
        """Adds a new expire time to keep track on, and deletes if any delete time has passed.

        Args:
            expire: datetime
                A new expire time.
        """
        # Seperate two deletes by 5 minutes
        minute = expire.minute
        expire = expire.replace(minute=int(minute / 5) * 5, second=0, microsecond=0)
        expire += timedelta(minutes=5)  # round up 5 minutes

        if expire not in self.schedule:
            self.schedule.append(expire)
            self.schedule.sort()  # good enough for small list

        # Find the latest time that triggers a delete
        now = datetime.utcnow()
        latest_expire = None
        for i in range(len(self.schedule)):
            t = self.schedule[i]
            if t < now:
                latest_expire = t
            else:
                break

        if latest_expire is not None:
            # Only deletes from db.
            # If InsertBuffer entries expired, they will be dealt in later runs.
            self.db.execute(f"DELETE FROM {self.table} WHERE expires < ?", (latest_expire,))
            self.db.commit()
            logger.debug("Cache DELETE attempted")
            self.last_delete = datetime.utcnow()
            for _ in range(i):  # remove all time that's passed
                self.schedule.pop(0)

    def save(self) -> None:
        """Saves payload to local tmp file, serialize using pickle."""
        with open(self.path, "wb") as f:
            pickle.dump(self.schedule, f)


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
    source_code = srcodeBuffer.getsource(func)
    source_code = re.sub(r'"""[\w\W]+?"""\n', "", source_code)  # remove docstring
    return "esi_function-{}-{}".format(
        func.__qualname__,
        hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
    )


def hash_key(key) -> str:
    """Default hashing function for a key. Using sha256 as hash function."""
    name = key[-1]
    return f"esi_cache-{name}-" + hashlib.sha256(pickle.dumps(key)).hexdigest()
