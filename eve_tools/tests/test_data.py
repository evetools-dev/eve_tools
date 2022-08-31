import os
import unittest
from typing import Callable, List

from eve_tools.data import ESIDBManager, CacheDB, CacheStats, make_cache_key
from eve_tools.data.cache import SqliteCache
from eve_tools.log import getLogger

logger = getLogger("test_data")


def _test_cache_function(n: int, l: List, f: Callable):
    raise NotImplemented


def _plus_one(n: int):
    raise NotImplemented


class TestCache(unittest.TestCase):
    TESTDIR = os.path.realpath(os.path.dirname(__file__))
    TESTDB = ESIDBManager("test", parent_dir=TESTDIR, schema_name="cache")

    def setUp(self) -> None:
        logger.debug("TEST running: %s", self.id())

    def test_cache_record(self):
        """Test CacheStats and _CacheRecord"""
        cache = SqliteCache(self.TESTDB, table="api_cache")
        self.assertEqual(id(cache), cache.record.id)

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
        self.assertGreaterEqual(len(CacheStats.record), 1)
        self.assertEqual(len(CacheStats.record), len(CacheStats.instances))
        instance = None
        for _record in CacheStats.record:
            if _record.id == id(cache):
                instance = _record
        self.assertIsNotNone(instance)
        self.assertEqual(instance.hits, 1)
        self.assertEqual(instance.miss, 1)

        # Clean up
        cache.evict(key)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.TESTDB.clear_db()
