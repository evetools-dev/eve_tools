import os
import sqlite3
import yaml

from eve_tools.config import DATA_DIR

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


class ESIDBManager:
    """Manage sqlite3 database for ESI api.

    Currently ESIDB is used to cache market api requests, which usually needs hundreds of ESI API calls.
    ESIDB is also useful to store time sensitive data, such as market data, which could be used for analysis.
    """

    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = sqlite3.connect(os.path.join(DATA_DIR, db_name + ".db"))
        self.cursor = self.conn.cursor()

        self.__init_tables()
        self.__init_columns()

    def __del__(self):
        self.cursor.close()
        self.conn.close()

    def clear_table(self, table_name: str):
        self.cursor.execute(f"DELETE FROM {table_name};")
        self.conn.commit()

    def drop_table(self, table_name: str):
        self.cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        self.conn.commit()

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
        with open(os.path.join(DATA_DIR, "dbconfig.yaml")) as f:
            dbconfig = yaml.full_load(f)
        self._dbconfig = dbconfig.get(self.db_name)
        self.tables = self._dbconfig.get("tables")
        for table in self.tables:
            table_config = self._dbconfig.get(table)
            schema = table_config.get("schema")
            self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({schema});")
