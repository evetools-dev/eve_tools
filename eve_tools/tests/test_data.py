from ctypes.wintypes import HMODULE
import inspect
import unittest
from datetime import datetime, timedelta
from typing import Callable, List

from .utils import TestInit
from eve_tools.data import ESIDBManager, CacheDB, CacheStats, make_cache_key
from eve_tools.data.cache import SqliteCache
from eve_tools.data.utils import hash_key, function_hash, srcodeBuffer, _DeleteHandler
from eve_tools.log import getLogger

logger = getLogger("test_data")


def _test_cache_function(n: int, l: List, f: Callable):
    raise NotImplemented


def _plus_one(n: int):
    raise NotImplemented


class TestCache(unittest.TestCase, TestInit):
    def setUp(self) -> None:
        logger.debug("TEST running: %s", self.id())

    def test_delete_handler(self):
        handler = _DeleteHandler(self.TESTDB, "checker_cache")
        self.assertIsInstance(handler.schedule, list)

        # Test: priority
        if len(handler.schedule) > 1:
            for i in range(len(handler.schedule) - 1):
                self.assertLess(handler.schedule[i], handler.schedule[i + 1])
                self.assertEqual(handler.schedule[i].minute % 5, 0)

        handler.schedule = []  # remove all for testing

        # Test: round up
        t1 = datetime.utcnow()
        handler.update(t1 + timedelta(minutes=20))
        self.assertEqual(len(handler.schedule), 1)
        self.assertIsInstance(handler.schedule[0], datetime)
        self.assertEqual(handler.schedule[0].minute % 5, 0)
        handler.schedule = []
        t1 = t1.replace(minute=32)
        handler.update(t1 + timedelta(hours=1))
        self.assertEqual(handler.schedule[0].minute, 35)
        self.assertIsNone(handler.last_delete)

        if t1.minute < 59:
            handler.schedule = []
            t1 = t1.replace(minute=59)
            handler.update(t1)  # should be fine
            self.assertEqual(handler.schedule[0].minute, 0)
            self.assertIsNone(handler.last_delete)

        # Test: duplicate
        handler.schedule = []
        t1 = datetime.utcnow() + timedelta(minutes=10)
        handler.update(t1)
        self.assertEqual(len(handler.schedule), 1)
        handler.update(t1)
        handler.update(t1)
        self.assertEqual(len(handler.schedule), 1)
        self.assertIsNone(handler.last_delete)

        # Test: priority
        handler.schedule = []
        t1 = datetime.utcnow() + timedelta(minutes=10)
        t = [t1 + timedelta(minutes=i) for i in range(0, 50, 5)]
        t.reverse()
        for expire in t:
            handler.update(expire)
        self.assertEqual(len(handler.schedule), len(t))
        for i in range(len(handler.schedule) - 1):
            self.assertLess(handler.schedule[i], handler.schedule[i + 1])
        self.assertIsNone(handler.last_delete)

        # Should test _DeleteHandler working with cache

    def test_insert_buffer(self):
        """Test InsertBuffer working with SqliteCache."""
        cache = SqliteCache(self.TESTDB, table="checker_cache")

        # Test: buffering
        key = make_cache_key(_test_cache_function, 1, [1, 2, 3], _plus_one)
        cache.set(key, 123, 60)
        self.assertIn(key, cache.buffer)
        v = cache.get(key)
        self.assertEqual(v, 123)
        db_rows = self.TESTDB.execute(
            "SELECT * FROM checker_cache WHERE key=?", (hash_key(key),)
        ).fetchall()
        self.assertEqual(len(db_rows), 0)

        # Test: flush
        key = make_cache_key(_test_cache_function, 2, [1, 2, 3], _plus_one)
        cache.set(key, 234, 60)
        key = make_cache_key(_test_cache_function, 3, [1, 2, 3], _plus_one)
        cache.set(key, 234, 60)
        self.assertEqual(len(cache.buffer), 3)
        n_rows = len(self.TESTDB.execute("SELECT * FROM checker_cache").fetchall())
        cache.buffer.flush()
        self.assertEqual(len(cache.buffer), 0)
        db_rows = self.TESTDB.execute(
            "SELECT * FROM checker_cache WHERE key=?", (hash_key(key),)
        ).fetchall()
        self.assertEqual(len(db_rows), 1)
        n_rows_after = len(self.TESTDB.execute("SELECT * FROM checker_cache").fetchall())
        self.assertEqual(n_rows + 3, n_rows_after)

        # Test: auto flush
        cap = cache.buffer.cap
        for i in range(cap):
            key = make_cache_key(_plus_one, i)
            cache.set(key, i + 1, 60)
        self.assertEqual(len(cache.buffer), cap)
        key = make_cache_key(_plus_one, cap + 100)
        cache.set(key, cap + 100, 60)  # flushed previous entries
        self.assertEqual(len(cache.buffer), 1)
        self.assertIn(key, cache.buffer)

        cache.buffer.clear()

    def test_cache_record(self):
        """Test CacheStats and _CacheRecord"""
        cache = SqliteCache(self.TESTDB, table="api_cache")
        self.assertEqual(cache.record.db_name, "test")
        self.assertEqual(cache.record.table, "api_cache")

        # Test: miss/hits setter & getter
        cache.hits += 1
        self.assertEqual(cache.hits, 1)
        cache.miss += 1
        self.assertEqual(cache.miss, 1)

        cache.hits = 0
        cache.miss = 0
        self.assertEqual(cache.record.hits, 0)
        self.assertEqual(cache.record.miss, 0)

        # Test: cache get & set
        key = make_cache_key(_test_cache_function, 1, [1, 2, 3], _plus_one)
        res = cache.get(key)  # miss
        self.assertIsNone(res)
        self.assertEqual(cache.miss, 1)

        cache.set(key, 123, expires=60)
        res = cache.get(key)  # hit
        self.assertEqual(res, 123)
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.miss, 1)

        # Test: CacheStats
        record = CacheStats.record
        self.assertGreaterEqual(len(record), 1)
        self.assertEqual(len(record), len(record))
        self.assertIn(cache._record, record)

        # Clean up
        cache.buffer.clear()

    def test_srcode_buffer(self):
        """Test srcodeBuffer working with function_hash()."""

        def f1(x):
            return x + str(self.__dict__) + str(1234)

        def f2(y):
            return y * 2 if y > 0 else y + 1

        src1, src2 = inspect.getsource(f1), inspect.getsource(f2)
        k1, k2 = f1.__qualname__, f2.__qualname__
        self.assertNotEqual(k1, k2)
        buffer = srcodeBuffer

        function_hash(f1)
        self.assertIn(k1, buffer.payload)
        self.assertEqual(src1, buffer.payload.get(k1))

        function_hash(f2)
        self.assertIn(k2, buffer.payload)
        self.assertIn(k1, buffer.payload)
        self.assertEqual(src2, buffer.payload.get(k2))

    def tearDown(self) -> None:
        self.TESTDB.clear_db()
