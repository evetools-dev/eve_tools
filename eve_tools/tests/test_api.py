import pandas as pd
import time
import unittest


from eve_tools.api import *
from eve_tools.api.search import InvType, SolarSystem, Station, Structure
from eve_tools.api.utils import reduce_volume
from .utils import TestInit, request_from_ESI


class TestMarket(unittest.TestCase, TestInit):
    def test_get_structure_types(self):
        resp = request_from_ESI(get_structure_types, self.structure_name, self.cname)
        resp_cache = get_structure_types(self.structure_name, self.cname)

        # Test: api returns correct value
        self.assertGreater(len(resp), 2)  # resp contains some type_id(s)
        self.assertNotIn(1, resp)
        if len(resp) > 1000:  # structure has a big market
            self.assertIn(1405, resp)  # 1405: inertial stabilizer

        # Test: if sid given, cname is optional
        sid = search_structure_id(self.structure_name, self.cname)
        resp_sid = request_from_ESI(get_structure_types, sid, "some weird cname")
        self.assertEqual(set(resp), set(resp_sid))

        # Test: cache returns correctly
        self.assertEqual(len(resp), len(resp_cache))
        self.assertEqual(set(resp), set(resp_cache))

    def test_get_region_types_esi(self):
        resp = request_from_ESI(get_region_types, 10000002, "esi")
        resp_cache = get_region_types(10000002, "esi")

        # Test: api returns correct value
        self.assertIn(12005, resp)
        self.assertNotIn(1, resp)

        # Test: cache returns correctly
        self.assertEqual(len(resp), len(resp_cache))
        self.assertEqual(set(resp), set(resp_cache))

        # Test: incorrect usage
        with self.assertRaises(ValueError):
            request_from_ESI(get_region_types, "region not exists", "esi")

    # test_get_region_types_db(self)

    def test_get_type_history_no_reduce(self):
        resp: pd.DataFrame = request_from_ESI(get_type_history, 10000002, 12005)
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
        resp: pd.DataFrame = request_from_ESI(
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

    # def test_get_market_history(self):
    #     _s = time.time()
    #     resp: pd.DataFrame = get_market_history("The Forge", reduces=reduce_volume)
    #     resp_time = time.time() - _s

    #     _s = time.time()
    #     resp_cache: pd.DataFrame = get_market_history(
    #         "The Forge", reduces=reduce_volume
    #     )
    #     resp_cache_time = time.time() - _s

    #     if resp_time > 10:  # retrieved from ESI
    #         self.assertGreater(resp_time, resp_cache_time)

    #     # Test: api returns correct value:
    #     self.assertGreater(len(resp), 10000)  # at least 10k types in Jita
    #     self.assertLess(len(resp), 100000)  # should correctly reduce # columns
    #     self.assertIn(12005, resp["type_id"].values)
    #     ishtar = resp.loc[resp["type_id"] == 12005]
    #     self.assertGreater(int(ishtar["volume_seven_days"]), 1)

    #     # Test: cache returns correctly
    #     self.assertTrue(resp.equals(resp_cache))
    #     self.assertEqual(set(resp.columns), set(resp_cache.columns))

    #     # Test: custom type_ids yields correct behavior
    #     resp = get_market_history(
    #         "The Forge", type_ids=[12005, 979], reduces=reduce_volume
    #     )
    #     resp_cache = get_market_history(
    #         "The Forge", type_ids=[12005, 979], reduces=reduce_volume
    #     )
    #     self.assertEqual(len(resp), 2)
    #     self.assertIn(12005, resp["type_id"].values)
    #     self.assertIn(979, resp["type_id"].values)
    #     self.assertTrue(resp.equals(resp_cache))

    def test_get_station_market_one_type(self):
        station_name = "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
        resp: pd.DataFrame = request_from_ESI(
            get_station_market, station_name, order_type="all", type_id=12005
        )
        resp_cache = get_station_market(station_name, order_type="all", type_id=12005)

        # Test: api returns correct value
        self.assertGreater(len(resp), 2)
        self.assertTrue((resp["type_id"] == 12005).all())

        # Test: buy/sell flag correct
        resp_sell: pd.DataFrame = request_from_ESI(
            get_station_market, station_name, order_type="sell", type_id=12005
        )
        resp_buy: pd.DataFrame = request_from_ESI(
            get_station_market, station_name, order_type="buy", type_id=12005
        )
        self.assertGreater(len(resp), len(resp_sell))
        self.assertGreater(len(resp), len(resp_buy))
        self.assertTrue((resp_sell["is_buy_order"] == 0).all())
        self.assertTrue((resp_buy["is_buy_order"] == 1).all())
        self.assertEqual(
            len(resp_sell.merge(resp).drop_duplicates()),
            len(resp_sell.drop_duplicates()),
        )  # sell/buy is a subset of "all" orders
        self.assertEqual(
            len(resp_buy.merge(resp).drop_duplicates()), len(resp_buy.drop_duplicates())
        )

        # Test: cache return matches ESI return
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

    def test_get_station_market_multiple_types(self):
        station_name = "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
        resp: pd.DataFrame = request_from_ESI(get_station_market, station_name)
        resp_cache = get_station_market(station_name)

        # Test: api returns correct value
        self.assertGreater(len(resp), 1000)  # Jita should have > 1000 active orders
        self.assertTrue((resp["location_id"] == resp["location_id"][0]).all())
        self.assertTrue((resp["region_id"] == resp["region_id"][0]).all())
        self.assertIn(12005, resp["type_id"].values)

        # Test: buy/sell flag correct
        resp_sell: pd.DataFrame = get_station_market(station_name, order_type="sell")
        resp_buy: pd.DataFrame = get_station_market(station_name, order_type="buy")
        self.assertEqual(len(resp), len(resp_sell) + len(resp_buy))
        self.assertTrue((resp_sell["is_buy_order"] == 0).all())
        self.assertTrue((resp_buy["is_buy_order"] == 1).all())
        self.assertEqual(
            len(resp_sell.merge(resp).drop_duplicates()),
            len(resp_sell.drop_duplicates()),
        )  # sell/buy is a subset of "all" orders
        self.assertEqual(
            len(resp_buy.merge(resp).drop_duplicates()), len(resp_buy.drop_duplicates())
        )

        # Test: cache return matches ESI return
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

    def test_get_region_market(self):
        resp: pd.DataFrame = request_from_ESI(get_region_market, "The Forge")
        resp_cache = get_region_market("The Forge")

        # Test: api returns correct value
        self.assertGreater(len(resp), 1000)
        self.assertTrue((resp["region_id"] == resp["region_id"][0]).all())
        self.assertIn(12005, resp["type_id"].values)

        # Test: cache return matches ESI return
        self.assertTrue(resp.equals(resp_cache))
        self.assertEqual(set(resp.columns), set(resp_cache.columns))

    def test_get_structure_market(self):
        resp: pd.DataFrame = request_from_ESI(
            get_structure_market, self.structure_name, self.cname
        )
        resp_cache = get_structure_market(self.structure_name, self.cname)

        # Test: api returns correct value
        self.assertGreater(len(resp), 2)  # resp contains some orders
        if len(resp) > 1000:  # structure has a big market
            self.assertTrue((resp["location_id"] == resp["location_id"][0]).all())
            self.assertTrue((resp["region_id"] == resp["region_id"][0]).all())
            self.assertIn(1405, resp["type_id"].values)  # 1405: inertial stabilizer

        # Test: cname is optional
        sid = search_structure_id(self.structure_name, self.cname)
        resp_sid = request_from_ESI(get_structure_market, sid, "some weird cname")
        self.assertEqual(set(resp), set(resp_sid))

        # Test: cache returns correctly
        self.assertEqual(len(resp), len(resp_cache))
        self.assertEqual(set(resp), set(resp_cache))


class TestSearch(unittest.TestCase, TestInit):
    def test_search_id(self):
        """Only test categories not defined in other search functions."""
        # Test: invalid category
        with self.assertRaises(ValueError):
            request_from_ESI(search_id, "abc", "category not exist")
        
        # Test: no record
        with self.assertRaises(ValueError):
            request_from_ESI(search_id, "Hanbie Seri", "character")

        # Test: search character_id
        resp = request_from_ESI(search_id, "Hanbie Serine", "character")
        resp_cache = search_id("Hanbie Serine", "character")
        self.assertEqual(resp, 2116658732)
        self.assertEqual(resp, resp_cache)

        # Test: search alliance_id
        resp = request_from_ESI(search_id, "Fraternity.", "alliance")
        resp_cache = search_id("Fraternity.", "alliance")
        self.assertEqual(resp, 99003581)
        self.assertEqual(resp, resp_cache)

    def test_search_structure_id(self):
        resp = request_from_ESI(search_structure_id, self.structure_name, self.cname)
        resp_cache = search_structure_id(self.structure_name, self.cname)
        self.assertEqual(resp, resp_cache)
        self.assertGreater(resp, 1000000000000)
    
    def test_search_structure(self):
        sid = search_structure_id(self.structure_name, self.cname)
        resp: Structure = request_from_ESI(search_structure, sid)
        resp_cache = search_structure(sid)
        self.assertEqual(resp, resp_cache)

    def test_search_station(self):
        resp: Station = request_from_ESI(search_station, 60000016)
        resp_cache = search_station(60000016)

        self.assertIsInstance(resp, Station)
        self.assertEqual(
            resp.name, "Tasabeshi VIII - Moon 13 - CBD Corporation Storage"
        )
        self.assertEqual(resp.region_id, 10000033)
        self.assertEqual(resp, resp_cache)

    def test_search_station_region_id(self):
        resp = request_from_ESI(search_station_region_id, 60000004)
        resp_cache = search_station_region_id(60000004)
        self.assertEqual(resp, 10000033)
        self.assertEqual(resp, resp_cache)
        with self.assertRaises(ValueError):
            request_from_ESI(search_station_region_id, 123456789)

    def test_search_region_id(self):
        resp = request_from_ESI(search_region_id, "The Forge")
        resp_cache = search_region_id("The Forge")

        self.assertEqual(resp, 10000002)
        self.assertEqual(resp, resp_cache)

        with self.assertRaises(ValueError):
            request_from_ESI(search_region_id, "region not exists")

    def test_search_system(self):
        resp: SolarSystem = request_from_ESI(search_system, 30000142)
        resp_cache = search_system(30000142)
        self.assertEqual(resp.name, "Jita")
        self.assertEqual(resp.region_id, 10000002)
        self.assertEqual(resp, resp_cache)

    def test_search_system_id(self):
        resp = request_from_ESI(search_system_id, "Jita")
        resp_cache = search_system_id("Jita")
        self.assertEqual(resp, 30000142)
        self.assertEqual(resp, resp_cache)

    def test_search_type(self):
        resp: InvType = request_from_ESI(search_type, 12005)
        resp_cache = search_type(12005)
        self.assertEqual(resp.type_name, "Ishtar")
        self.assertTrue(resp.published)
        self.assertEqual(resp, resp_cache)

    def test_search_type_id(self):
        resp = request_from_ESI(search_type_id, "Ishtar")
        resp_cache = search_type_id("Ishtar")
        self.assertEqual(resp, 12005)
        self.assertEqual(resp, resp_cache)