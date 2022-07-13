from functools import wraps
import logging
import pandas as pd
import time
from typing import Callable, Optional, Tuple

from eve_tools.data import ESIDB, api_cache, make_cache_key
from eve_tools.data.db import ESIDBManager
from eve_tools.ESI import ESIClient

logger = logging.getLogger(__name__)


def _update_or_not(
    threshold: int, table: str, max_column: str, **kwd
) -> Tuple[bool, float]:
    """Determines whether to use db or retrieve from ESI.

    Checks rules to determines whether to retrieve market data from ESI or use cached data in esi.db.
    Rules are predetermined to fit market data api.
    Set threshold=-1 to bypass all rule checking and force market api to retrieve from ESI.
    Set max_value_check=False or fresh_entry_check=False to bypass specific rules.

    Args:
        threshold: int
            The threshold above which the update will not be enabled.
            If max(max_columns) < threshold, this function will return True and enable request from ESI.
        table: str
            The table that will be checked.
        max_column: str
            The column that will be selected from using SELECT MAX(max_column).
        kwd.max_value_check: bool
            A flag that tells whether to check if max value of a column is greater than the given threshold.
        kwd.fresh_entry_check: bool
            A flag that tells whether to check fresh entry count. Default True.
        kwd.min_fresh_entry: int
            A int that specifies the minimum number of entries with max_column = max(max_column).
            If fresh_entry_check=True, this argument is required.
        kwd:
            A list arguments that helps finding correct retrieve_time from db.
            E.g. region_id=1000002, location_id=6000012.

    Returns:
        A tuple[bool, float]. tuple[0] is a bool that flags update or not.
        tuple[1] is most recent retrieve_time of entries following arguments in kwd.

    Example:
    >>> # The Forge region, with 20 minutes interval, at least 1000 fresh entry with max(retrieve_time)
    >>> update_flag, retrieve_time = _update_or_not(1200, "orders", "retrieve_time", min_fresh_entry=1000, region_id=10000002)
    >>> # The Forge region, with 20 minutes interval, do not check fresh entries
    >>> update_flag, retrieve_time = _update_or_not(1200, "orders", "retrieve_time", fresh_entry_check=False, region_id=10000002)
    >>> # Force update
    >>> update_flag, retrieve_time = _update_or_not(-1, "orders", "retrieve_time")
    This call finds all orders with kwd arguments and check the most recent retrieve_time entry.
    """
    if threshold < 0:
        return True, 0

    fresh_entry_check = kwd.pop("fresh_entry_check", True)
    max_value_check = kwd.pop("max_value_check", True)
    fresh_entry_flag = False
    max_value_flag = False
    min_fresh_entry = kwd.pop("min_fresh_entry", 0)

    if fresh_entry_check and not min_fresh_entry:
        raise ValueError(
            'Keyword argument "min_fresh_entry" is required when fresh_entry_check=True (which is by default).'
        )

    where_clause = " AND ".join(
        [f"{k}={v}" for k, v in kwd.items()]
    )  # region_id=12345, location_id=123 -> "region_id=12345 AND location_id=123"
    if kwd:  # if there's any left in kwd
        select_max_value: float = ESIDB.cursor.execute(
            f"SELECT MAX({max_column}) FROM {table} WHERE {where_clause}"
        ).fetchone()[0]
    else:
        select_max_value: float = ESIDB.cursor.execute(
            f"SELECT MAX({max_column}) FROM {table}"
        ).fetchone()[0]

    # If select_max_value not null and below the threshold
    max_value_flag = max_value_check and (
        not select_max_value or select_max_value < threshold
    )

    # After running this function with a given page, fresh_entry_cnt would be 1000, but the MAX(retrieve_time) will be updated.
    # To avoid this, check there are sufficient entries (more than 1 page) in database.
    if fresh_entry_check and select_max_value:
        if kwd:
            fresh_entry_cnt = ESIDB.cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {max_column}={select_max_value} AND {where_clause}"
            ).fetchone()[0]
        else:
            fresh_entry_cnt = ESIDB.cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {max_column}={select_max_value}"
            ).fetchone()[0]
        fresh_entry_flag = fresh_entry_cnt < min_fresh_entry

    return (max_value_flag or fresh_entry_flag), select_max_value


def _select_from_orders(
    order_type: str = "all", type_id: Optional[int] = None, **kwd
) -> pd.DataFrame:
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
        is_buy_order_filter = -1  # is_buy_order != -1 -> is_buy_order == 0 or 1
    elif order_type == "buy":
        is_buy_order_filter = 0  # is_buy_order != 0 -> is_buy_order == 1
    else:
        is_buy_order_filter = 1  # is_buy_order != 1 -> is_buy_order == 0

    where_clause = " AND ".join([f"{k}={v}" for k, v in kwd.items() if v is not None])

    if type_id:
        rows = ESIDB.cursor.execute(
            f"SELECT * FROM orders WHERE type_id={type_id} AND is_buy_order!={is_buy_order_filter} AND {where_clause} \
                                    ORDER BY type_id, is_buy_order, price"
        )
    else:
        rows = ESIDB.cursor.execute(
            f"SELECT * FROM orders WHERE is_buy_order!={is_buy_order_filter} AND {where_clause} \
                                    ORDER BY type_id, is_buy_order, price"
        )
    df = pd.DataFrame(rows, columns=ESIDB.columns["orders"])
    return df


def reduce_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce a market history DataFrame to volume data.
    Calculates 30 days volume and 7 days volume and put them in a one-line DataFrame.
    """
    target = ["volume_seven_days", "volume_thirty_days"]
    thirty_days = 31 * 24 * 3600  # 31 days because market history is delayed by one day
    df = df[df.date > time.time() - thirty_days]
    volume_seven_days = round(df.volume.sum() / 30, 2)

    seven_days = 8 * 24 * 3600
    df = df[df.date > time.time() - seven_days]
    volume_thirty_days = round(df.volume.sum() / 7, 2)

    row = [volume_seven_days, volume_thirty_days]
    return pd.DataFrame([row], columns=target)


def cache(
    func: Optional[Callable] = None,
    expires: Optional[int] = None,
    cache_instance: Optional[ESIDBManager] = None,
):
    """A decorator that handles api caching.

    Handles caching on api level. User should expect a functional caching functionality.
    It is designed to hide caching operation from users.
    Future designs may use an ESIAPI decorator class to wrap up cache and leave space for other functionality.

    Args:
        func: Callable
            An ESI API that needs to be cached for result.
        expires: int
            User of this decorator can set a custom expire time.
            Some api could be updated in a longer interval than what's specified in the expired headers.
        cache_instance: ESIDBManager
            A cache instance to which cache entries are stored and retrieved.
            If not given, use default api_cache instance.

    Note:
        Priority on arg ``expires`` (from high to low):
            1. API user specified: get_market_history(..., expires=24*3600)
            2. cache user specified: @cache(expires=24*3600)
            3. expires headers from ESI: resp.headers["Expires"]

    """

    def wrapper_api_cache(func: Callable):
        @wraps(func)
        def wrapped_api_cache(*args, **kwd):
            nonlocal expires, cache_instance  # avoid unboundLocalError

            if cache_instance is None:
                cache_instance = api_cache

            key = make_cache_key(func, *args, **kwd)
            value = cache_instance.get(key)
            if value is not None:  # cache hit
                return value

            # record_session for recording "Expires" entry in ESI response headers
            ESIClient._clear_record(field="expires")
            ret = func(*args, **kwd)  # exec

            # Priority: kwd["expires"] > cache(expires) > ESIResponse.expires
            expires = kwd.get("expires", expires)
            if expires is None:
                expires = ESIClient._record.expires

            # expires could be a datetime formatted string, or seconds in integer.
            cache_instance.set(key, ret, expires)
            return ret

        return wrapped_api_cache

    if func is None:
        return wrapper_api_cache

    if callable(func):
        return wrapper_api_cache(func)

    raise NotImplementedError
