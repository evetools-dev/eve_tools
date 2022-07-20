import unittest
from aiohttp import ClientResponseError
from datetime import datetime

from eve_tools.ESI import ESIClient
from eve_tools.ESI.metadata import ESIMetadata, ESIRequest
from eve_tools.ESI.utils import _SessionRecord, ESIRequestError
from eve_tools.ESI.esi import _RequestChecker
from eve_tools.ESI.sso.utils import to_clipboard, read_clipboard
from eve_tools.data import CacheDB
from eve_tools.data.cache import SqliteCache
from eve_tools.tests.utils import request_from_ESI


class TestESI(unittest.TestCase):
    def test_api_session_recorder(self):
        """Tests ESI._start_api_session, ESI._end_api_session, ESI._clear_api_record, ESI._api_session_record"""
        # Test: clear session
        ESIClient._record = _SessionRecord(requests=123, timer=12.3, expires="future")
        ESIClient._clear_record()
        self.assertIsInstance(ESIClient._record, _SessionRecord)
        self.assertFalse(ESIClient._record)  # empty
        self.assertTrue(ESIClient._record_session)  # does not stop record

        ESIClient._record = _SessionRecord(requests=123, timer=12.3, expires="future")
        ESIClient._clear_record(field="expires")
        self.assertIsNone(ESIClient._record.expires)
        self.assertEqual(ESIClient._record.requests, 123)

        # Test: start & stop recording
        ESIClient._clear_record()
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

        # Test: records correctly
        ESIClient._clear_record()
        ESIClient._start_record()
        expire_1 = ESIClient.head(
            "/markets/{region_id}/orders/", region_id=10000002, order_type="all"
        ).expires
        expire_2 = ESIClient.head(
            "/markets/{region_id}/history/", region_id=10000002, type_id=12005
        ).expires
        dt_format = "%a, %d %b %Y %H:%M:%S %Z"
        expected_expires = (
            datetime.strftime(
                min(
                    datetime.strptime(expire_1, dt_format),
                    datetime.strptime(expire_2, dt_format),
                ),
                dt_format,
            )
            + "GMT"
        )
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

    def test_request_raises(self):
        """Test ESI.request(..., raises=True/False/None).

        Currently not available because _RequestChecker could 100% block requests with invalid type_id."""
        # Make a correct request first
        # resp = ESIClient.get(
        #     "/markets/{region_id}/history/", region_id=10000002, type_id=12005
        # )
        # self.assertEqual(resp.error_remain, ESIRequestError._global_error_remain[0])

        # # Test: raises = True
        # error_remain_before = ESIRequestError._global_error_remain[0]
        # with self.assertRaises(ClientResponseError):  # 404
        #     ESIClient.get(
        #         "/markets/{region_id}/history/",
        #         region_id=10000002,
        #         type_id=60078,
        #         raises=True,
        #     )
        # error_remain_after = ESIRequestError._global_error_remain[0]
        # self.assertEqual(error_remain_before - error_remain_after, 1)

        # with self.assertRaises(ClientResponseError):  # 404
        #     ESIClient.get(  # with async_loop
        #         "/markets/{region_id}/history/",
        #         async_loop=["type_id"],
        #         region_id=10000002,
        #         type_id=[60078],
        #         raises=True,
        #     )

        # # Test: raises = False
        # resp = ESIClient.get(
        #     "/markets/{region_id}/history/",
        #     region_id=10000002,
        #     type_id=60078,
        #     raises=False,
        # )
        # self.assertIsNone(resp)

        # resp = ESIClient.get(
        #     "/markets/{region_id}/history/",
        #     async_loop=["type_id"],
        #     region_id=10000002,
        #     type_id=[60078, 12005],
        #     raises=False,
        # )
        # self.assertEqual(len(resp), 1)

        # resp = ESIClient.head(
        #     "/markets/{region_id}/history/",
        #     region_id=10000002,
        #     type_id=60078,
        #     raises=False,
        # )
        # self.assertIsNone(resp)

        # # Test: raises = None
        # ESIRequestError._global_error_remain[0] = 7
        # resp = ESIClient.get(
        #     "/markets/{region_id}/history/",
        #     region_id=10000002,
        #     type_id=60078,
        #     raises=None,
        # )
        # self.assertIsNone(resp)
        # self.assertEqual(ESIRequestError._global_error_remain[0], 6)

        # with self.assertRaises(ClientResponseError):  # 404
        #     ESIClient.get(
        #         "/markets/{region_id}/history/",
        #         region_id=10000002,
        #         type_id=60078,
        #         raises=None,
        #     )
        # self.assertEqual(ESIRequestError._global_error_remain[0], 5)

        # # Test: default value
        # ESIClient.get(
        #     "/markets/{region_id}/history/", region_id=10000002, type_id=12005
        # )  # correct request

        # if ESIRequestError._global_error_remain[0] > 7:
        #     error_before = ESIRequestError._global_error_remain[0]
        #     resp = ESIClient.get(
        #         "/markets/{region_id}/history/",
        #         async_loop=["type_id"],
        #         region_id=10000002,
        #         type_id=[60078, 12005, 63715],
        #     )
        #     error_after = ESIRequestError._global_error_remain[0]
        #     self.assertEqual(len(resp), 1)
        #     self.assertEqual(error_before - error_after, 2)

        # ESIRequestError._global_error_remain[0] = 5
        # with self.assertRaises(ClientResponseError):  # 404
        #     ESIClient.get(
        #         "/markets/{region_id}/history/",
        #         async_loop=["type_id"],
        #         region_id=10000002,
        #         type_id=[63715, 1],
        #     )
        # self.assertEqual(ESIRequestError._global_error_remain[0], 4)

        # with self.assertRaises(ClientResponseError):  # 404
        #     ESIClient.head(
        #         "/markets/{region_id}/history/",
        #         region_id=10000002,
        #         type_id=63715,
        #     )
        return


class TestRequestChecker(unittest.TestCase):
    checker = _RequestChecker()
    checker_cache = SqliteCache(CacheDB, "checker_cache")

    def test_check_type_id(self):
        """Tests _RequestChecker._check_request_type_id()."""
        type_id = 12005
        res = request_from_ESI(
            self.checker._check_request_type_id, type_id, cache=self.checker_cache
        )
        self.assertTrue(res)

        type_id = 12007  # blocked: not a type_id
        res = request_from_ESI(
            self.checker._check_request_type_id, type_id, cache=self.checker_cache
        )
        self.assertFalse(res)

        type_id = 63715  # blocked: ESI endpoint
        res = request_from_ESI(
            self.checker._check_request_type_id, type_id, cache=self.checker_cache
        )
        self.assertFalse(res)


class TestSSO(unittest.TestCase):
    def test_pc_copy(self):
        # Testing check_call and other cmd are not necessary.
        # Only to make sure we can copy/paste correctly.
        msg = "ESI_TEST"
        self.assertIsNone(to_clipboard(msg))
        self.assertEqual(msg, read_clipboard())
