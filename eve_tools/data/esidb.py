"""Handles db operations for esi.db."""
import atexit

from .db import ESIDBManager
from .utils import InsertBuffer


class ESIDB(ESIDBManager):
    def __init__(self, db_name: str, parent_dir: str = None, schema_name: str = None):
        super().__init__(db_name, parent_dir, schema_name)
        self.buffer = InsertBuffer(self)
        atexit.register(self.buffer.flush)

    def insert(self, data, table: str):
        pass
