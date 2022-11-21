import re
from pandas import DataFrame
from typing import TYPE_CHECKING

from eve_tools.data import ESIDBManager
from eve_tools.log import getLogger
from eve_tools.data.utils import InsertBuffer

if TYPE_CHECKING:
    from eve_tools.ESI.response import ESIResponse

logger = getLogger(__name__)


class ESIDBHandler(ESIDBManager):

    def __init__(self, db_name: str = ..., parent_dir: str = None, schema_name: str = None):
        self.enabled = True
        if db_name is Ellipsis:
            db_name = "esi"
        self.db_name = db_name
        super().__init__(db_name, parent_dir, schema_name)
        self.buffer = InsertBuffer(self.conn, cap=200)

    def __call__(self, key: str, resp: "ESIResponse") -> "ESIResponse":
        func_name = self.__format_key(key)
        db_func = getattr(self, func_name, None)
        if db_func is None or not self.enabled:
            return resp

        return db_func(resp)

    def markets_region_id_history(self, resp: "ESIResponse") -> "ESIResponse":
        table = "market_history"

        if resp.formatted is False:
            return resp

        # Checks resp if data has been correctly formatted,
        # rules specific for this function
        if resp.data is None or not isinstance(resp.data, DataFrame) or len(resp.data) == 0:
            return resp

        columns = self.columns.get(table)
        if columns is None:
            return resp

        df_columns = resp.data.columns
        if not set(columns).issubset(set(df_columns)):
            return resp

        # resp.data is clean for db insert
        # Write to insert buffer, which would handle insert later
        # df = resp.data[columns]
        # for line in df.values:
        #     self.buffer.insert(tuple(line), table)

        resp.stored = True
        return resp

    @staticmethod
    def __format_key(key: str) -> str:
        return "_".join(re.split("\W+", key.strip("/")))

    @staticmethod
    def __log(msg: str, resp: "ESIResponse") -> None:
        logger.warning(
            "%s: key = %s, kwd = %s", msg, resp.request_info.request_key, str(resp.request_info.kwd)
        )
