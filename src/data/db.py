import os
import sqlite3

from matplotlib.pyplot import table

orders_columns = ["order_id", "type_id", "is_buy_order", "price", "duration", "volume_remain", "volume_total", "min_volume", "range", "location_id", "system_id", "region_id", "issued", "retrieve_time"]

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
        conn.executemany(d, data_iter)