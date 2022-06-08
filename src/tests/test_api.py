from typing import Callable
import pandas as pd
import time
import unittest

from src import api_cache
from src.api.market import get_market_history, get_region_market, get_region_types, get_type_history
from src.api.utils import make_cache_key, reduce_volume
from src.data.cache import hash_key


class TestMarket(unittest.TestCase):
    @staticmethod
    def request_from_ESI(esi_api: Callable, *args, **kwd):
        resp = esi_api(*args, **kwd)
        key = make_cache_key(esi_api, *args, **kwd)
        if api_cache._last_used and api_cache._last_used == hash_key(key):
            # resp returned from cache: evit it
            api_cache.evit(key)
            resp = esi_api(*args, **kwd)  # retrieve from ESI
        return resp

    def test_get_region_types_esi(self):
        resp = self.request_from_ESI(get_region_types, 10000002, "esi")
        resp_cache = get_region_types(10000002, "esi")

        # Test: api returns correct value
        self.assertIn(12005, resp)
        self.assertNotIn(1, resp)

        # Test: cache returns correctly
        self.assertEqual(len(resp), len(resp_cache))
        self.assertEqual(set(resp), set(resp_cache))

        # Test: incorrect usage
        with self.assertRaises(ValueError):
            self.request_from_ESI(get_region_types, "region not exists", "esi")

    # test_get_region_types_db(self)

    def test_get_type_history_no_reduce(self):
        resp: pd.DataFrame = self.request_from_ESI(get_type_history, 10000002, 12005)
        resp_cache: pd.DataFrame = get_type_history(10000002, 12005)

        # Test: api returns correct value
        self.assertEqual(
            set(resp.columns),
            set(
                [
                    "type_id",
                    "region_id",
                    "date",
                    "average",
                    "highest",
                    "lowest",
                    "order_count",
                    "volume",
                ]
            ),
        )
        self.assertTrue(
            (resp["region_id"] == 10000002).all()
        )  # all have region_id=10000002
        self.assertTrue((resp["type_id"] == 12005).all())  # all have type_id=12005
        self.assertGreater(len(resp), 100)

        # Test: cache returns correctly
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

    def test_get_type_history_with_reduce(self):
        resp: pd.DataFrame = self.request_from_ESI(
            get_type_history, 10000002, 12005, reduce_volume
        )
        resp_cache: pd.DataFrame = get_type_history(10000002, 12005, reduce_volume)

        # Test: api returns correct value
        self.assertEqual(len(resp), 1)
        self.assertEqual(
            set(resp.columns),
            set(["volume_seven_days", "volume_thirty_days", "type_id", "region_id"]),
        )
        self.assertEqual(len(resp["volume_seven_days"].values), 1)
        self.assertGreater(resp["volume_seven_days"].values[0], 1)

        # Test: cache returns correctly
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

    def test_get_market_history(self):
        _s = time.time()
        resp: pd.DataFrame = get_market_history("The Forge", reduces=reduce_volume)
        resp_time = time.time() - _s

        _s = time.time()
        resp_cache: pd.DataFrame = get_market_history(
            "The Forge", reduces=reduce_volume
        )
        resp_cache_time = time.time() - _s

        if resp_time > 10:  # retrieved from ESI
            self.assertGreater(resp_time, resp_cache_time)

        # Test: api returns correct value:
        self.assertGreater(len(resp), 10000)  # at least 10k types in Jita
        self.assertLess(len(resp), 100000)  # should correctly reduce # columns
        self.assertIn(12005, resp["type_id"].values)
        self.assertGreater(resp["volume_seven_days"].values[0], 1)

        # Test: cache returns correctly
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

        # Test: custom type_ids yields correct behavior
        resp = get_market_history(
            "The Forge", type_ids=[12005, 979], reduces=reduce_volume
        )
        resp_cache = get_market_history(
            "The Forge", type_ids=[12005, 979], reduces=reduce_volume
        )
        self.assertEqual(len(resp), 2)
        self.assertIn(12005, resp["type_id"].values)
        self.assertIn(979, resp["type_id"].values)
        self.assertTrue(resp.equals(resp_cache))

    def test_get_station_market(self):
        return
