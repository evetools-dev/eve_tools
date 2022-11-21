import pandas as pd
import re
from datetime import datetime
from typing import TYPE_CHECKING, Union

from eve_tools.log import getLogger


if TYPE_CHECKING:
    from eve_tools.ESI.response import ESIResponse

logger = getLogger(__name__)


class ESIFormatter:

    def __init__(self) -> None:
        self.enabled = False

    def __call__(self, key: str, resp: "ESIResponse") -> Union["ESIResponse", None]:
        if resp is None:
            return None
        if resp.data is None or not self.enabled:
            return resp
        format_func_name = self.__format_key(key)
        formatter = getattr(self, format_func_name, None)

        if formatter is None:
            return resp

        resp.formatted = True  # True regardless of successful or not
        return formatter(resp)

    def markets_region_id_history(self, resp: "ESIResponse") -> "ESIResponse":
        """Formats response from /markets/{region_id}/history/ endpoint.

        If success, ``resp.data`` field is changed to the formatted output.
        If not success, ``resp.data`` is None.
        """
        if resp.data is None or len(resp) == 0:  # ESIResponse defined __len__
            return resp

        df = pd.DataFrame(resp.data)
        api_request = resp.request_info

        # Get type_id for resp
        type_id = api_request.params.get("type_id")
        if type_id is None:
            resp.data = None
            self.__log("Response data set to None - type_id is None")
            return resp

        region_id = api_request.kwd.get("region_id")
        if region_id is None:
            resp.data = None
            self.__log("Response data set to None - region_id is None")
            return resp

        df["type_id"] = type_id
        df["region_id"] = region_id
        # Convert RFC7231 formatted datetime string to epoch timestamp
        # ESI updates history on 11:05:00 GMT, 39900 for 11:05 in timestamp, UTC is the same as GMT
        df["date"] = df["date"].apply(
            lambda date: datetime.timestamp(datetime.strptime(f"{date} +0000", "%Y-%m-%d %z")) + 39900
        )

        resp.data = df

        return resp

    @staticmethod
    def __format_key(key: str) -> str:
        return "_".join(re.split("\W+", key.strip("/")))

    @staticmethod
    def __log(msg: str, resp: "ESIResponse") -> None:
        logger.warning(
            "%s: key = %s, kwd = %s", msg, resp.request_info.request_key, str(resp.request_info.kwd)
        )
