import unittest

from eve_tools.ESI import ESIClient
from eve_tools.ESI.metadata import ESIMetadata, ESIRequest
# from .utils import request_from_ESI


# metadata = ESIMetadata()


# class TestESIMetadata(unittest.TestCase):
#     def test_load_metadata(self):
#         pass


class TestESI(unittest.TestCase):
    def test_api_session_recorder(self):
        """Tests ESI._start_api_session, ESI._end_api_session, ESI._clear_api_record, ESI._api_session_record"""
        # Test: clear session
        ESIClient._api_session_record = "hello world"
        ESIClient._clear_api_record()
        self.assertIsNone(ESIClient._api_session_record)
        self.assertFalse(ESIClient._api_session)

        # Test: start & end session
        ESIClient._clear_api_record()
        ESIClient._start_api_session()
        resp = ESIClient.head("/search/", categories="inventory_type", search=12005)
        ESIClient._end_api_session()
        self.assertIsNotNone(ESIClient._api_session_record)
        self.assertEqual(ESIClient._api_session_record, resp.expires)

        ESIClient._clear_api_record()
        ESIClient.head("/search/", categories="inventory_type", search=12005)
        self.assertIsNone(ESIClient._api_session_record)

        # Test: api_session_record
        ESIClient._clear_api_record()
        ESIClient._start_api_session()
        expire_1 = ESIClient.head(
            "/search/", categories="inventory_type", search=12005
        ).expires
        expire_2 = ESIClient.head(
            "/markets/{region_id}/history/", region_id=10000002, type_id=12005
        ).expires
        ESIClient._end_api_session()
        expected_expires = min(expire_1, expire_2)  # earliest expires
        self.assertEqual(expected_expires, ESIClient._api_session_record)
