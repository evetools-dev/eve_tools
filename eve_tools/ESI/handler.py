import re
from pandas import DataFrame
from typing import TYPE_CHECKING

from eve_tools.data.esidb import ESIDB
from eve_tools.log import getLogger

if TYPE_CHECKING:
    from eve_tools.ESI.response import ESIResponse


class ESIDBHandler:
    def __init__(self, db_name: str = ..., parent_dir: str = None, schema_name: str = None):
        self.enabled = True
        if db_name is Ellipsis:
            db_name = "esi"
        self.__db_name = db_name
        self.__db = ESIDB(db_name, parent_dir, schema_name)

        self.logger = getLogger(__name__)

    def __call__(self, key: str, resp: "ESIResponse") -> "ESIResponse":
        func_name = self.__format_key(key)
        db_func = getattr(self, func_name, None)
        if db_func is None or not self.enabled:
            return resp

        return db_func(resp)

    def markets_region_id_history(self, resp: "ESIResponse") -> "ESIResponse":
        table = "market_history"  # insert data to this table

        # Only insert formatted response to db
        if resp.formatted is False:
            return resp

        df = resp.data

        # Checks resp if data has been correctly formatted,
        # rules specific for this function
        if df is None or not isinstance(df, DataFrame) or len(df) == 0:
            return resp

        columns = self.__db.columns.get(table)
        if columns is None:
            return resp

        df_columns = df.columns
        if not set(columns).issubset(set(df_columns)):
            # Check columns matching or not
            return resp

        # resp.data is clean for db insert
        # Write to db
        df = df[columns]
        self.__db.insert(df, table)

        resp.stored = True
        return resp

    @staticmethod
    def __format_key(key: str) -> str:
        return "_".join(re.split("\W+", key.strip("/")))

    def __log(self, msg: str, resp: "ESIResponse") -> None:
        self.logger.warning(
            "%s: key = %s, kwd = %s", msg, resp.request_info.request_key, str(resp.request_info.kwd)
        )
