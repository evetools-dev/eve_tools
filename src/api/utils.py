import time
import pandas as pd
from typing import Optional, Tuple

from src.data import ESIDB, orders_columns


def _update_or_not(threshold: int, **kwd) -> Tuple[bool, float]:
    """Determines whether to use db or retrieve from ESI.

    Checks rules to determines whether to retrieve market data from ESI or use cached data in esi.db.
    Rules are predetermined to fit market data api. Default forcing update interval > 20 minutes.
    Set threshold=-1 to bypass all rule checking and force market api to retrieve from ESI.

    Args:
        threshold: int
            The minimum interval between two consecutive updates. Unit is in seconds. Default 1200 seconds.
            Forces update when threshold is below 0.
        kwd:
            A list arguments that helps finding correct retrieve_time from db. 
            E.g. region_id=1000002, location_id=6000012.
    
    Returns:
        A tuple[bool, float]. tuple[0] is a bool that flags update or not. 
        tuple[1] is most recent retrieve_time of entries following arguments in kwd.

    Example:
    >>> update_flag, retrieve_time = _update_or_not(1200, region_id=10000002)   # The Forge region, with 20 minutes interval
    >>> update_flag, retrieve_time = _update_or_not(-1, location_id=6000012)    # Jita trade hub, force update
    This call finds all orders with kwd arguments and check the most recent retrieve_time entry.
    """
    if threshold < 0:
        return True, 0
    
    curr_time = time.time()
    where_clause = ' AND '.join([f"{k}={v}" for k, v in kwd.items()])     # region_id=12345, location_id=123 -> "region_id=12345 AND location_id=123"
    retrieve_time: float = ESIDB.cursor.execute(f"SELECT MAX(retrieve_time) FROM orders WHERE {where_clause}").fetchone()[0]
    if not retrieve_time:
        retrieve_time = 0

    # After running this functino with a given page, fresh_entry_cnt would be 1000, but the MAX(retrieve_time) will be updated.
    # To avoid this, check there are sufficient entries (more than 1 page) in database.
    fresh_entry_cnt = 0
    if retrieve_time:
        fresh_entry_cnt = ESIDB.cursor.execute(f"SELECT COUNT(*) FROM orders WHERE retrieve_time={retrieve_time} AND {where_clause}").fetchone()[0]
    # Check update threshold and fresh_entry count
    return (curr_time-retrieve_time > threshold or fresh_entry_cnt <= 1000), retrieve_time


def _select_from_orders(order_type: str = "all", type_id: Optional[int] = None, **kwd) -> pd.DataFrame:
    """Execute SQL SELECT FROM with arguments specific on market orders.

    Filter out market orders with given conditions. All orders should have order_type and type_id field.
    Optional fields, such as region_id, location_id, etc., are accepted in kwd.

    Args:
        order_type: str
            A string for the optional order_type parameter. Default to "all".
            One of ["all", "sell", "buy"].
        type_id: int | None
            An integer that specifies the type_id to retrieve from ESI.
            If type_id is given, only returns market orders of that specific type.
        kwd:
            Additonal conditions to filter out useful data entries.
    
    Returns:
        A pd.DataFrame that contains useful data entries following given conditions.
    """
    if order_type == "all":
        is_buy_order_filter = -1    # is_buy_order != -1 -> is_buy_order == 0 or 1
    elif order_type == "buy":
        is_buy_order_filter = 0     # is_buy_order != 0 -> is_buy_order == 1
    else:
        is_buy_order_filter = 1     # is_buy_order != 1 -> is_buy_order == 0

    where_clause = ' AND '.join([f"{k}={v}" for k, v in kwd.items()])

    if type_id:
        rows = ESIDB.cursor.execute(f"SELECT * FROM orders WHERE type_id={type_id} AND is_buy_order!={is_buy_order_filter} AND {where_clause} \
                                    ORDER BY type_id, is_buy_order, price")
    else:
        rows = ESIDB.cursor.execute(f"SELECT * FROM orders WHERE is_buy_order!={is_buy_order_filter} AND {where_clause} \
                                    ORDER BY type_id, is_buy_order, price")
    df = pd.DataFrame(rows)
    df.columns = orders_columns
    return df