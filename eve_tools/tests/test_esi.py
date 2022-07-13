import unittest
from datetime import datetime

from eve_tools.ESI import ESIClient
from eve_tools.ESI.metadata import ESIMetadata, ESIRequest
from eve_tools.ESI.utils import _SessionRecord


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
