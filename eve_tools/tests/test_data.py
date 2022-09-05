import unittest
from typing import Callable, List

from .utils import TestInit
from eve_tools.data import ESIDBManager, CacheDB, CacheStats, make_cache_key
from eve_tools.data.cache import SqliteCache
from eve_tools.data.utils import hash_key
from eve_tools.log import getLogger

logger = getLogger("test_data")


def _test_cache_function(n: int, l: List, f: Callable):
    raise NotImplemented


def _plus_one(n: int):
    raise NotImplemented


class TestCache(unittest.TestCase, TestInit):
    def setUp(self) -> None:
        logger.debug("TEST running: %s", self.id())

    def test_insert_buffer(self):
        """Test InsertBuffer working with SqliteCache."""
        cache = SqliteCache(self.TESTDB, table="checker_cache")
        
        # Test: buffering
        key = make_cache_key(_test_cache_function, 1, [1, 2, 3], _plus_one)
        cache.set(key, 123, 60)
        self.assertIn(key, cache.buffer)
        v = cache.get(key)
        self.assertEqual(v, 123)
        db_rows = self.TESTDB.execute("SELECT * FROM checker_cache WHERE key=?", (hash_key(key), )).fetchall()
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
        db_rows = self.TESTDB.execute("SELECT * FROM checker_cache WHERE key=?", (hash_key(key), )).fetchall()
        self.assertEqual(len(db_rows), 1)
        n_rows_after = len(self.TESTDB.execute("SELECT * FROM checker_cache").fetchall())
        self.assertEqual(n_rows + 3, n_rows_after)

        # Test: auto flush
        cap = cache.buffer.cap
        for i in range(cap):
            key = make_cache_key(_plus_one, i)
            cache.set(key, i+1, 60)
        self.assertEqual(len(cache.buffer), cap)
        key = make_cache_key(_plus_one, cap+100)
        cache.set(key, cap+100, 60)  # flushed previous entries
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

    def tearDown(self) -> None:
        self.TESTDB.clear_db()
