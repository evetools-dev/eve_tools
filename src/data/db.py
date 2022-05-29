import os
import sqlite3
from typing import List

orders_columns = ['order_id', 'type_id', 'is_buy_order', 'price', 'duration', 'volume_remain', 'volume_total', 'min_volume', 'range', 'location_id', 'system_id', 'region_id', 'issued', 'retrieve_time']
history_columns = ['type_id', 'region_id', 'date', 'average', 'highest', 'lowest', 'order_count', 'volume']


class ESIDBManager:
    """Manage sqlite3 database for ESI api.

    Currently ESIDB is used to cache market api requests, which usually needs hundreds of ESI API calls.
    ESIDB is also useful to store time sensitive data, such as market data, which could be used for analysis.
    """
    def __init__(self):
        self.conn = sqlite3.connect(os.path.realpath(os.path.join(os.path.dirname(__file__), "esi.db")))
        self.cursor = self.conn.cursor()
    
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
                            order_id INTEGER PRIMARY KEY,
                            type_id INTEGER NOT NULL,
                            is_buy_order INTEGER,
                            price REAL NOT NULL,
                            duration INTEGER,
                            volume_remain INTEGER,
                            volume_total INTEGER,
                            min_volume INTEGER, 
                            range TEXT,
                            location_id INTEGER,
                            system_id INTEGER,
                            region_id INTEGER,
                            issued TEXT,
                            retrieve_time REAL DEFAULT 0
                            );''')
        
        # Foreign key constaint on type_id, region_id, and other *_id(s) should be added.
        # But it is only useful after seperate tables for types, regions, etc. are created.
        # It also requires some initialization on DB that needs to call ESIClient.
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS market_history (
                            type_id INTEGER,
                            region_id INTEGER,
                            date REAL,
                            average REAL,
                            highest REAL,
                            lowest REAL,
                            order_count INTEGER,
                            volume INTEGER DEFAULT 0,
                            PRIMARY KEY(type_id, region_id, date)
                            );''')

        self.columns = self._init_columns()
        
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
        d = "REPLACE INTO orders({}) VALUES({});".format(', '.join(orders_columns), ','.join('?'*len(orders_columns)))
        conn.executemany(d, data_iter)      # No need to commit since pandas uses context manager on conn

    @staticmethod
    def history_insert_ignore(table, conn, keys, data_iter):
        """df.to_sql append method

        On conflict (primary key), ignore entry. History entries never change, so ignore conflicting entries.
        """
        d = "INSERT OR IGNORE INTO market_history({}) VALUES({});".format(', '.join(history_columns), ','.join('?'*len(history_columns)))
        conn.executemany(d, data_iter)

    def _init_columns(self):
        ret = {}
        for table in self._table_names():
            cur = self.conn.execute(f"SELECT * FROM {table}")
            names = list(map(lambda x: x[0], cur.description))
            ret[table] = names
        return ret
    
    def _table_names(self) -> List[str]:
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return list(map(lambda x: x[0], self.cursor.fetchall()))