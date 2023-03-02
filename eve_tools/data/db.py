import os
import sqlite3
import time
import yaml
from dataclasses import dataclass

from eve_tools.config import DATA_DIR
from eve_tools.log import getLogger

logger = getLogger(__name__)

orders_columns = [
    "order_id",
    "type_id",
    "is_buy_order",
    "price",
    "duration",
    "volume_remain",
    "volume_total",
    "min_volume",
    "range",
    "location_id",
    "system_id",
    "region_id",
    "issued",
    "retrieve_time",
]
history_columns = [
    "type_id",
    "region_id",
    "date",
    "average",
    "highest",
    "lowest",
    "order_count",
    "volume",
]


@dataclass(repr=False)
class CMDInfo:
    """Stores statistics for a database keyword, such as SELECT, DELETE, etc."""

    _cmd: str
    _cnt: int = 0
    _t: float = 0.0  # unit: nanosecond

    def __repr__(self) -> str:
        return f"(calls={self._cnt}, time={self._t / 1e9:.7f})"  # 7f because windows time has max 1e-07 resolution


@dataclass(init=False)
class _ESIDBStats:
    """Stores statistics for a database instance."""

    def __init__(self, db_name: str) -> None:
        self.db_name = db_name
        self.calls: int = 0

    def increment(self, cmd: str, _t: float):
        """Increments statistics of the database instance.

        Args:
            cmd: str
                A SQL keyword, such as SELECT or INSERT.
            _t: float
                Time spent for this db command. Unit in nanosecond.
        """
        self.calls += 1

        # If SQL query involves transaction, stored procedure, etc., they probably start with "BEGIN".
        # This is beyond the scope of this class design. You might see something like BEGIN=(calls=1, time=xxx).
        info: CMDInfo = getattr(
            self, cmd, CMDInfo(cmd)
        )  # cmd_info = self.SELECT || CMDInfo("SELECT")
        info._cnt += 1
        info._t += _t
        if not hasattr(self, cmd):
            setattr(self, cmd, info)

    def __repr__(self) -> str:
        nodef_f_vals = ((f, getattr(self, f)) for f in self.__dict__)

        nodef_f_repr = ", ".join(f"{name}={value}" for name, value in nodef_f_vals)
        return f"{self.__class__.__name__}({nodef_f_repr})"


class ESIDBManager:
    """Manage sqlite3 database for ESI api.

    Currently ESIDB is used to cache market api requests, which usually needs hundreds of ESI API calls.
    ESIDB is also useful to store time sensitive data, such as market data, which could be used for analysis.

    Attributes:
        db_name: str
            Name of the database. If db_name is abc, the db file is named as "abc.db".
        parent_dir: str
            Location of the database file. Default under eve_tools/data/.
        schema_name: str
            Uses which schema predefined in schema.yaml. Default using schema with name db_name.
    """

    def __init__(self, db_name, parent_dir: str = None, schema_name: str = None):
        self.db_name = db_name
        if parent_dir is None:
            parent_dir = DATA_DIR
        self.schema_name = schema_name
        if schema_name is None:
            self.schema_name = db_name

        self.db_path = os.path.join(parent_dir, db_name + ".db")
        self.conn = sqlite3.connect(self.db_path)  # can't use isolation_level=None
        self._cursor = self.conn.cursor()

        self.__init_tables()
        self.__init_columns()
        self.__init_stats()
        logger.info(
            "DB initiated with schema %s: %s @ %s",
            self.schema_name,
            db_name,
            parent_dir,
        )

    def __del__(self):
        self._cursor.close()
        self.conn.close()

    @property
    def stats(self) -> _ESIDBStats:
        return self._stats

    def execute(self, __sql: str, __parameters=...) -> sqlite3.Cursor:
        """Wraps cursor.execute with custom add-ons.
        Usage is the same (or should be the same) as cursor.execute() method of sqlite3.Cursor class."""
        cmd = __sql.split()[0]
        _s = time.perf_counter_ns()  # perf_counter has 1e-07 resolution in win32, lowest in time methods
        if __parameters is Ellipsis:
            cursor = self._cursor.execute(__sql)
        else:
            cursor = self._cursor.execute(__sql, __parameters)
        _t = time.perf_counter_ns() - _s
        self._stats.increment(cmd, _t)
        return cursor

    def commit(self) -> None:
        """Same as connection.commit() from sqlite3.Connection class."""
        self.conn.commit()

    def clear_table(self, table_name: str):
        """Clears a table using DELETE FROM table"""
        self._cursor.execute(f"DELETE FROM {table_name};")
        self.conn.commit()
        logger.debug("Clear table %s-%s successful", self.db_name, table_name)

    def drop_table(self, table_name: str):
        """Drops a table using DROP TABLE table"""
        self._cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        self.conn.commit()
        logger.debug("Drop table %s-%s successful", self.db_name, table_name)

    def clear_db(self):
        """Clears tables of db by calling clear_table() on every table."""
        for table in self.tables:
            self.clear_table(table)
        logger.debug("Clear DB %s successful", self.db_name)

    @staticmethod
    def orders_insert_update(table, conn, keys, data_iter):
        """df.to_sql append method

        Conflict on primary key constraint happens when
        1. Order is unchanged
        2. Order is changed (e.g. volume_remain decreased)

        Therefore the append needs to UPDATE the order on conflict when 2 happens and ignore when 1 happens.
        For simplicity, also update when 1 happens.

        A trigger before insert could be useful, but not necessary in current context.
        """
        d = "REPLACE INTO orders({}) VALUES({});".format(
            ", ".join(orders_columns), ",".join("?" * len(orders_columns))
        )
        conn.executemany(
            d, data_iter
        )  # No need to commit since pandas uses context manager on conn

    @staticmethod
    def history_insert_ignore(table, conn, keys, data_iter):
        """df.to_sql append method

        On conflict (primary key), ignore entry. History entries never change, so ignore conflicting entries.
        """
        d = "INSERT OR IGNORE INTO market_history({}) VALUES({});".format(
            ", ".join(history_columns), ",".join("?" * len(history_columns))
        )
        conn.executemany(d, data_iter)

    def __init_columns(self):
        ret = {}
        for table in self.tables:
            cur = self.conn.execute(f"SELECT * FROM {table}")
            names = list(map(lambda x: x[0], cur.description))
            ret[table] = names
        self.columns = ret

    def __init_tables(self):
        with open(os.path.join(DATA_DIR, "schema.yml")) as f:
            dbconfig = yaml.full_load(f)
        self._dbconfig = dbconfig.get(self.schema_name)
        self.tables = self._dbconfig.get("tables")
        for table in self.tables:
            table_config = self._dbconfig.get(table)
            schema = table_config.get("schema")
            self._cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({schema});")

    def __init_stats(self):
        self._stats: _ESIDBStats = _ESIDBStats(self.db_name)
