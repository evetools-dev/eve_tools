import unittest
import requests
from datetime import datetime
from yarl import URL

from eve_tools.ESI import ESIClient
from eve_tools.ESI.checker import ESIRequestChecker, ESIEndpointChecker
from eve_tools.ESI.formatter import ESIFormatter
from eve_tools.ESI.metadata import ESIRequest
from eve_tools.ESI.parser import ESIRequestParser, ETagEntry
from eve_tools.ESI.utils import _SessionRecord
from eve_tools.ESI.response import ESIResponse
from eve_tools.ESI.sso.utils import to_clipboard, read_clipboard
from eve_tools.exceptions import InvalidRequestError, ESIResponseError
from eve_tools.data import SqliteCache
from eve_tools.tests.utils import request_from_ESI
from eve_tools.log import getLogger
from .utils import internet_on, endpoint_on, TestInit

logger = getLogger("test_esi")


class TestFormatter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.formatter = ESIFormatter()

    def test_format_key(self):
        key_formatter = self.formatter._ESIFormatter__format_key
        key = "/characters/{character_id}/mail/"
        res = key_formatter(key)
        self.assertIsInstance(res, str)
        self.assertEqual(res, "characters_character_id_mail")


class TestSessionRecorder(unittest.TestCase):
    def setUp(self) -> None:
        ESIClient._clear_record()

    def test_clear_session(self):
        ESIClient._record = _SessionRecord(requests=123, timer=12.3, expires="future")
        self.assertIsInstance(ESIClient._record, _SessionRecord)
        self.assertFalse(ESIClient._record)  # empty
        self.assertTrue(ESIClient._record_session)  # does not stop record

        # _clear_record with specific field
        ESIClient._record = _SessionRecord(requests=123, timer=12.3, expires="future")
        ESIClient._clear_record(field="expires")
        self.assertIsNone(ESIClient._record.expires)
        self.assertEqual(ESIClient._record.requests, 123)

    @unittest.skipUnless(internet_on(), "no internet connection")
    def test_start_stop_recording(self):
        # Test: start & stop recording
        ESIClient.head("/universe/systems/")
        self.assertTrue(ESIClient._record)  # not empty
        record = _SessionRecord(
            ESIClient._record.requests,
            ESIClient._record.timer,
            ESIClient._record.expires,
            requests_blocked=ESIClient._record.requests_blocked,
            requests_failed=ESIClient._record.requests_failed,
            requests_succeed=ESIClient._record.requests_succeed,
        )  # copy
        self.assertGreater(record.timer, 0.0)
        self.assertGreater(record.requests, 0)
        self.assertIsNotNone(record.expires, None)

        ESIClient._stop_record()
        ESIClient.head("/universe/systems/")
        record2 = ESIClient._record
        self.assertFalse(ESIClient._record_session)
        self.assertEqual(record, record2)  # stop_record working

        ESIClient._start_record()
        ESIClient.head("/universe/systems/")
        self.assertEqual(ESIClient._record.requests, record.requests + 1)

    @unittest.skipUnless(internet_on(), "no internet connection")
    @unittest.skipUnless(endpoint_on("/markets/{region_id}/orders/"), "endpoint down")
    @unittest.skipUnless(endpoint_on("/alliances/"), "endpoint down")
    def test_api_session_recorder(self):
        # Test: records correctly
        ESIClient._start_record()
        expire_1 = ESIClient.head(
            "/markets/{region_id}/orders/", region_id=10000002, order_type="all"
        ).expires
        expire_2 = ESIClient.head("/alliances/").expires
        dt_format = "%a, %d %b %Y %H:%M:%S %Z"
        expired_t = min(datetime.strptime(expire_1, dt_format), datetime.strptime(expire_2, dt_format))
        expected_expires = datetime.strftime(expired_t, dt_format) + "GMT"
        self.assertEqual(expected_expires, ESIClient._record.expires)
        self.assertEqual(ESIClient._record.requests, 2)
        self.assertGreater(ESIClient._record.timer, 0.0001)
        self.assertEqual(ESIClient._record.requests_succeed, 2)

        # Test: failed and blocked
        ESIClient._clear_record()
        ESIClient.head(
            "/markets/{region_id}/orders/",
            region_id=10000002,
            order_type="all",
            type_id=12007,
            raises=False,
        )
        self.assertEqual(ESIClient._record.requests_blocked, 1)
        self.assertEqual(ESIClient._record.requests, 1)

        ESIClient.get(
            "/markets/{region_id}/orders/",
            async_loop=["type_id"],
            region_id=10000002,
            order_type="all",
            type_id=[12005, 12006],
            raises=False,
        )
        self.assertEqual(ESIClient._record.requests_blocked, 1)
        self.assertEqual(ESIClient._record.requests_failed, 0)
        self.assertEqual(ESIClient._record.requests_succeed, 2)


class TestESI(unittest.TestCase):
    def setUp(self) -> None:
        logger.debug("TEST running: %s", self.id())

    @unittest.skipUnless(internet_on(), "no internet connection")
    @unittest.skipUnless(endpoint_on("/markets/{region_id}/orders/"), "endpoint down")
    @unittest.skipUnless(endpoint_on("/universe/types/{type_id}/"), "endpoint down")
    def test_request_raises(self):
        """Test ESI.request(..., raises=True/False/None)."""
        # Make a correct request first
        resp = ESIClient.get("/markets/{region_id}/orders/", region_id=10000002, type_id=12005)
        self.assertIsInstance(resp, ESIResponse)
        self.assertTrue(resp.ok)

        resp = ESIClient.head("/markets/{region_id}/orders/", region_id=10000002, type_id=12005)
        self.assertIsInstance(resp, ESIResponse)

        # Test: raises = True
        with self.assertRaises(ESIResponseError):
            ESIClient.get("/markets/{region_id}/orders/", region_id=1, raises=True)
        with self.assertRaises(InvalidRequestError):
            ESIClient.get("/universe/types/{type_id}/", type_id=12007, raises=True)  # blocked
        with self.assertRaises(InvalidRequestError):
            ESIClient.get(
                "/universe/types/{type_id}/", async_loop=["type_id"], type_id=[12005, 12007], raises=True
            )  # blocked

        with self.assertRaises(ESIResponseError):
            ESIClient.head("/markets/{region_id}/orders/", region_id=1, raises=True)
        with self.assertRaises(InvalidRequestError):
            ESIClient.head("/universe/types/{type_id}/", type_id=12007, raises=True)  # blocked

        # Test: raises = False
        resp = ESIClient.get("/markets/{region_id}/orders/", region_id=1, raises=False)
        self.assertIsNone(resp)
        resp = ESIClient.get("/universe/types/{type_id}/", type_id=12007, raises=False)  # blocked
        self.assertIsNone(resp)
        resp = ESIClient.get(
            "/universe/types/{type_id}/", async_loop=["type_id"], type_id=[12005, 12007], raises=False
        )
        self.assertEqual(len(resp), 1)

        resp = ESIClient.head("/markets/{region_id}/orders/", region_id=1, raises=False)
        self.assertIsNone(resp)
        resp = ESIClient.head("/universe/types/{type_id}/", type_id=12007, raises=False)  # blocked
        self.assertIsNone(resp)

        # Test: raises = None
        resp = ESIClient.get("/markets/{region_id}/orders/", region_id=1, raises=None)
        self.assertIsInstance(resp, ESIResponse)

        resp: ESIResponse = ESIClient.get(
            "/universe/types/{type_id}/", type_id=12007, raises=None
        )  # blocked
        self.assertIsInstance(resp, ESIResponse)
        self.assertTrue(resp.request_info.blocked, True)

        resp = ESIClient.get(
            "/universe/types/{type_id}/", async_loop=["type_id"], type_id=[12005, 12007], raises=None
        )
        self.assertEqual(len(resp), 2)

        resp = ESIClient.head("/markets/{region_id}/orders/", region_id=1, raises=None)
        self.assertIsInstance(resp, ESIResponse)

        # raise when x_error_remain <= 5 can't be tested, as all requests regardless of success will update this value from ESI.
        # but it should be correct.
        self.assertTrue(True)

        # Test: If async_loop not given, default True.
        with self.assertRaises(ESIResponseError):
            ESIClient.get("/markets/{region_id}/orders/", region_id=1)
        with self.assertRaises(InvalidRequestError):
            ESIClient.get("/universe/types/{type_id}/", type_id=12007)  # blocked

        with self.assertRaises(ESIResponseError):
            ESIClient.head("/markets/{region_id}/orders/", region_id=1)

        # Test: If given, default None.
        resp = ESIClient.get(
            "/universe/types/{type_id}/", async_loop=["type_id"], type_id=[12005, 12007, 1], raises=None
        )
        self.assertEqual(len(resp), 3)


class TestEndpointChecker(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = ESIEndpointChecker()

    @unittest.skipUnless(internet_on(), "no internet connection")
    @unittest.skipUnless(endpoint_on("/characters/{character_id}/standings/"), "endpoint down")
    def test_checker(self):
        resp = requests.get(self.checker.target_url)
        status = resp.json()
        status_parsed = self.checker._parse_status_json(status)
        self.assertIn("/characters/{character_id}/standings/", status_parsed)

        self.assertTrue(self.checker("/characters/{character_id}/standings/"))
        self.assertTrue(self.checker("/characters/{character_id}/standings/"))  # assert again


class TestRequestChecker(unittest.TestCase, TestInit):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker_cache = SqliteCache(cls.TESTDB, "checker_cache")
        cls.checker = ESIRequestChecker(cls.checker_cache)

    @unittest.skipUnless(internet_on(), "no internet connection")
    @unittest.skipUnless(endpoint_on("/markets/{region_id}/orders/"), "endpoint down")
    def test_check_type_id(self):
        """Tests ESIRequestChecker.check_type_id()."""
        type_id = 12005
        res = request_from_ESI(self.checker.check_type_id, type_id, cache=self.checker_cache)
        self.assertTrue(res)
        # self.assertEqual(self.checker.requests, 1)

        type_id = 12007  # blocked: not a type_id
        res = request_from_ESI(self.checker.check_type_id, type_id, cache=self.checker_cache)
        self.assertFalse(res)
        # self.assertEqual(self.checker.requests, 1)

        type_id = 63715  # blocked: ESI endpoint
        res = request_from_ESI(self.checker.check_type_id, type_id, cache=self.checker_cache)
        self.assertFalse(res)
        # self.assertEqual(self.checker.requests, 2)  # request sent

        # Test: default raise behavior
        type_id = 12007
        with self.assertRaises(InvalidRequestError):
            ESIClient.get(
                "/markets/{region_id}/orders/",
                region_id=10000002,
                type_id=type_id,
                order_type="all",
            )

        self.assertIsNone(
            ESIClient.head(
                "/markets/{region_id}/orders/",
                region_id=10000002,
                type_id=type_id,
                order_type="all",
                raises=False,
            )
        )

        # Test: type_id on path
        type_id = 12007
        with self.assertRaises(InvalidRequestError):
            ESIClient.get("/universe/types/{type_id}/", type_id=type_id)

        resp = ESIClient.head("/universe/types/{type_id}/", type_id=12005)
        self.assertIsNotNone(resp)

        # Test: type_id = None but is ok
        type_id = None
        resp = ESIClient.head(
            "/markets/{region_id}/orders/",
            region_id=10000002,
            type_id=type_id,
            raises=False,
        )
        self.assertIsNotNone(resp)

        # Test: type_id not in ESIParams -> should be ignored
        type_id = 1234567890
        resp = ESIClient.head("/universe/categories/", type_id=type_id, raises=False)
        self.assertIsNotNone(resp)

        # Test: type_id used in different endpoints & params share the cache
        type_id = 12007
        res = request_from_ESI(self.checker.check_type_id, type_id, cache=self.checker_cache)
        hits, miss = self.checker_cache.hits, self.checker_cache.miss

        default_checker_cache = ESIClient.checker.cache
        ESIClient.checker.cache = self.checker_cache
        ESIClient.head("/universe/types/{type_id}/", type_id=type_id, raises=False)
        self.assertEqual(hits + 1, self.checker_cache.hits)
        self.assertEqual(miss, self.checker_cache.miss)

        ESIClient.head("/markets/{region_id}/orders/", region_id=10000002, type_id=12007, raises=False)
        self.assertEqual(miss, self.checker_cache.miss)
        self.assertEqual(hits + 2, self.checker_cache.hits)  # should be a hit

        ESIClient.head("/markets/{region_id}/orders/", region_id=10000003, type_id=12007, raises=False)
        self.assertEqual(miss, self.checker_cache.miss)
        self.assertEqual(hits + 3, self.checker_cache.hits)  # should be a hit

        hits, miss = self.checker_cache.hits, self.checker_cache.miss
        ESIClient.get(
            "/markets/{region_id}/orders/",
            region_id=10000002,
            async_loop=["type_id"],
            type_id=[12005, 12006, 12007],
        )
        self.assertEqual(miss + 1, self.checker_cache.miss)  # 12006 miss
        self.assertEqual(hits + 2, self.checker_cache.hits)  # 12005 & 12007 hit

        hits, miss = self.checker_cache.hits, self.checker_cache.miss
        ESIClient.get(
            "/markets/{region_id}/orders/",
            region_id=10000003,  # new region
            async_loop=["type_id"],
            type_id=[12006, 12007, 12005, 1405],
        )
        self.assertEqual(miss + 1, self.checker_cache.miss)  # 1405 miss
        self.assertEqual(hits + 3, self.checker_cache.hits)  # 12005 & 12006 & 12007 hit

        hits, miss = self.checker_cache.hits, self.checker_cache.miss
        ESIClient.get(
            "/markets/{region_id}/orders/",
            region_id=10000003,  # new region
            async_loop=["type_id"],
            type_id=[1405, 12007, 12006, 12005],
        )
        self.assertEqual(hits + 4, self.checker_cache.hits)

        # Test: change checker and still works
        checker = ESIRequestChecker(self.checker_cache)
        ESIClient.setChecker(checker)
        hits, miss = self.checker_cache.hits, self.checker_cache.miss
        ESIClient.get(
            "/markets/{region_id}/orders/",
            region_id=10000003,  # new region
            async_loop=["type_id"],
            type_id=[1405, 12007, 12006, 12005],
        )
        self.assertEqual(hits + 4, self.checker_cache.hits)
        self.assertEqual(miss, self.checker_cache.miss)

        ESIClient.checker.cache = default_checker_cache

    def tearDown(self) -> None:
        self.TESTDB.clear_db()
        self.checker_cache.buffer.clear()


class TestParser(unittest.TestCase, TestInit):
    @classmethod
    def setUpClass(cls) -> None:
        cls.etag_cache = SqliteCache(cls.TESTDB, "etag_cache")
        cls.parser = ESIRequestParser(ESIClient.apps, cls.etag_cache)

    def test_etag(self):
        req = ESIRequest("test key", "get", kwd={"cid": 123, "sid": 234})
        etag = "test_etag-123456"
        payload = 12005

        # Test: set_etag
        self.parser._set_etag(req.rid, etag, payload)

        entry: ETagEntry = self.etag_cache.get(req.rid)
        self.assertIsNotNone(entry)
        self.assertIsInstance(entry, ETagEntry)
        self.assertEqual(entry.etag, etag)
        self.assertEqual(entry.payload, payload)

        # Test: get_etag
        self.assertEqual(self.parser._get_etag(req.rid), etag)

        ret = self.parser._get_etag("some nonexisting rid")
        self.assertEqual(ret, "")  # "ETag" : "" is allowed in http

        # Test: get_etag_payload
        self.assertEqual(self.parser._get_etag_payload(req.rid), payload)

        ret = self.parser._get_etag_payload("some nonexisting rid")
        self.assertIsNone(ret)  # payload should be None if non-existing

    def tearDown(self) -> None:
        self.TESTDB.clear_table("etag_cache")
        self.etag_cache.buffer.clear()


class TestMetadata(unittest.TestCase):
    def test_request_info(self):
        """Test ESIRequest()."""
        req = ESIRequest("test key", "get", kwd={"cid": 123, "sid": 234})
        req2 = ESIRequest("test key", "get", kwd={"sid": 234, "cid": 123})
        self.assertEqual(req.rid, req2.rid)

        url = req.real_url
        self.assertEqual(url, URL())  # empty url


class TestSSO(unittest.TestCase):
    def test_pc_copy(self):
        """Verify pyperclip.copy() functionality"""
        # Testing check_call and other cmd are not necessary.
        # Only to make sure we can copy/paste correctly.
        msg = "ESI_TEST"
        self.assertIsNone(to_clipboard(msg))
        self.assertEqual(msg, read_clipboard())
