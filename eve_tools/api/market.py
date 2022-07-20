import asyncio
import pandas as pd
import time
from typing import Callable, List, Union, Optional
from datetime import datetime

from eve_tools.ESI import ESIClient
from eve_tools.api import search_structure_id, search_id, search_station_region_id
from eve_tools.api.search import search_system_region_id
from eve_tools.data import ESIDB
from .utils import _update_or_not, _select_from_orders, cache


@cache
def get_structure_market(
    structure_name_or_id: Union[str, int], cname: str = "any", **kwd
) -> pd.DataFrame:
    """Retrieves market orders of a player structure.

    Requests market orders of a player's structure from ESI by sending get request to /markets/structures/{structure_id}/ endpoint.
    Authentication scope esi-markets.structure_markets.v1 is required.
    User needs to have docking (or market) access to the structure to pass the authentication.
    Uses a sqlite db to cache market orders and reduce frequency of ESI requests.

    Args:
        structure_name_or_id: str | int
            A string or an integer for the structure.
            If a string is given, it should be the precise name of the structure.
            If an integer is given, it should be a valid structure_id.
        cname: str
            cname's character_id will be used in searching structure_id.
            If supplied, this character needs to have docking access to structure.
        kwd.page: int
            An integer that specifies which page to retrieve from ESI. Defaul retrieving all orders from ESI.
            Page number is purely random and speficying a page number is only useful in testing.
        kwd.expires: int
            The minimum interval between two updates. Unit in seconds.

    Returns:
        A pd.DataFrame that contains active orders given by ESI. Some simple sorting is added to give better readability.

    Raises:
        TypeError: Argument structure_name_or_id should be str or int, not {type(structure_name_or_id)}.

    Some facts:
        1. ESI updates its orders every 5 minutes.
        2. Around 15 pages per update (in 4-HWWF citadel).
        3. Takes around 1 second to complete an update on all orders.
    """
    sid = True
    if isinstance(structure_name_or_id, str):
        sid = False
    elif isinstance(structure_name_or_id, int):
        sid = structure_name_or_id
    else:
        raise TypeError(
            f"Argument structure_name_or_id should be str or int, not {type(structure_name_or_id)}."
        )

    if not sid:
        sid = search_structure_id(structure_name_or_id, cname=cname)

    resp = ESIClient.head(
        "/markets/structures/{structure_id}/", structure_id=sid, page=1, raises=True
    )
    headers = resp.headers

    update_threshold = kwd.get("expires", 1200)

    update_flag, retrieve_time = _update_or_not(
        time.time() - update_threshold,
        "orders",
        "retrieve_time",
        min_fresh_entry=1000,
        location_id=sid,
    )
    if not update_flag:
        df = _select_from_orders(location_id=sid, retrieve_time=retrieve_time)
        return df

    # Getting from ESI
    page = kwd.get("page", -1)
    if page == -1:
        # get X-Pages headers, which tells how many pages of data
        x_pages = int(headers["X-Pages"])
        pages = range(1, x_pages + 1)
    else:
        pages = [page]

    all_resp = ESIClient.get(
        "/markets/structures/{structure_id}/",
        async_loop=["page"],
        structure_id=sid,
        page=pages,
    )
    all_orders = []
    for respp in all_resp:
        all_orders.extend(respp.data)

    # Formmating output and append to db
    df = pd.DataFrame(all_orders)

    df["retrieve_time"] = int(time.time())  # save some digits
    df["system_id"] = ESIClient.get(
        "/universe/structures/{structure_id}/", structure_id=sid
    ).data.get("solar_system_id")
    df["region_id"] = search_system_region_id(df["system_id"][0])

    df.sort_values(
        ["type_id", "is_buy_order", "price"],
        axis=0,
        ascending=[True, True, True],
        inplace=True,
    )
    df = df[ESIDB.columns["orders"]]  # reorder columns

    df.to_sql(
        "orders",
        ESIDB.conn,
        if_exists="append",
        index=False,
        method=ESIDB.orders_insert_update,
    )
    return df


@cache
def get_region_market(
    region_name_or_id: Union[str, int],
    order_type: str = "all",
    type_id: Optional[int] = None,
    **kwd,
) -> pd.DataFrame:
    """Retrieves market orders of a region.

    Requests market orders from ESI by sending get request to /markets/{region_id}/orders/ endpoint.
    Uses a sqlite db to cache market orders and reduce frequency of ESI requests.
    Output is formatted to a DataFrame and also appended into DB using methods in ESIDB.
    Specific formatting and filtering can be performed on the returned DataFrame to suit a scenario.

    Args:
        region_name_or_id: str | int
            A string or an integer for the region.
            If a string is given, it should be the precise region name, such as "The Forge".
            If an integer is given, it should be a valid region_id.
        order_type: str
            One of ["all", "sell", "buy"]. Default to "all".
        type_id: int | None
            An integer that specifies the type_id to retrieve from ESI.
            If type_id is given, only returns market orders of that specific type.
        kwd.page: int
            An integer that specifies which page to retrieve from ESI. Defaul retrieving all orders from ESI (~300 pages).
            Page number is purely random and speficying a page number is only useful in testing.
        kwd.expires: int
            An integer that specifies the minimum interval between two updates. Unit in seconds.
            Default 1200 (20 minutes). User can set this to -1 if forcing update.

    Returns:
        A pd.DataFrame that contains active orders given by ESI. Some simple sorting is added to give better readability.

    Raises:
        TypeError: Argument region_name_or_id should be str or int, not {type(region_name_or_id)}.
        ValueError: Argument order_type accepts one of ["sell", "buy", "all"], not {order_type}.

    Some facts:
        1. ESI updates its orders every 5 minutes.
        2. Around 300+ pages (requests) per update.
        3. Takes around 1-10 seconds to complete an update on all orders.
    """
    if isinstance(region_name_or_id, str):
        rid = search_id(region_name_or_id, "region")
    elif isinstance(region_name_or_id, int):
        rid = region_name_or_id
    else:
        raise TypeError(
            f"Argument region_name_or_id should be str or int, not {type(region_name_or_id)}."
        )

    if order_type not in ["sell", "buy", "all"]:
        raise ValueError(
            f'Argument "order_type" accepts one of ["sell", "buy", "all"], not {order_type}.'
        )

    page = kwd.get("page", -1)
    update_threshold = kwd.get("expires", 1200)

    resp = ESIClient.head(
        "/markets/{region_id}/orders/",
        region_id=rid,
        order_type=order_type,
        type_id=type_id,
        page=1,
        raises=True,
    )
    headers = resp.headers

    # Using cache db or get from ESI
    update_flag, retrieve_time = _update_or_not(
        time.time() - update_threshold,
        "orders",
        "retrieve_time",
        min_fresh_entry=1000,
        region_id=rid,
    )
    if not update_flag:
        df = _select_from_orders(
            order_type, type_id, region_id=rid, retrieve_time=retrieve_time
        )
        return df

    # Getting from ESI
    if page == -1:
        x_pages = int(
            headers["X-Pages"]
        )  # get X-Pages headers, which tells how many pages of data
        pages = range(1, x_pages + 1)
    else:
        pages = [page]

    all_resp = ESIClient.get(
        "/markets/{region_id}/orders/",
        async_loop=["page"],
        region_id=rid,
        order_type=order_type,
        type_id=type_id,
        page=pages,
    )
    all_orders = []
    for respp in all_resp:
        all_orders.extend(respp.data)

    # Formmating output and append to db
    df = pd.DataFrame(all_orders)

    df["retrieve_time"] = int(time.time())  # save some digits
    df["region_id"] = rid

    df.sort_values(
        ["type_id", "is_buy_order", "price"],
        axis=0,
        ascending=[True, True, True],
        inplace=True,
    )
    df = df[ESIDB.columns["orders"]]  # reorder columns

    df.to_sql(
        "orders",
        ESIDB.conn,
        if_exists="append",
        index=False,
        method=ESIDB.orders_insert_update,
    )

    return df


@cache
def get_station_market(
    station_name_or_id: Union[str, int],
    order_type: str = "all",
    type_id: Optional[int] = None,
    **kwd,
) -> pd.DataFrame:
    """Retrieves market orders of a specific station.

    Requests market orders of a station from ESI or local db by filtering result from get_region_market().
    Specific formatting and filtering can be performed on the returned DataFrame to suit a scenario.

    Args:
        station_name_or_id: str | int
            A string or an integer for the station.
            If a string is given, it should be the precise station name, such as "Jita IV - Moon 4 - Caldari Navy Assembly Plant".
            If an integer is given, it should be a valid region_id.
        order_type: str
            A string for the optional order_type parameter. Default to "all".
            One of ["all", "sell", "buy"].
        type_id: int | None
            An integer that specifies the type_id to retrieve from ESI.
            If type_id is given, only returns market orders of that specific type.
        kwd.expires: int
            An integer that specifies the minimum interval between two updates. Unit in seconds.
            Default 1200 (20 minutes). User can set this to -1 if forcing update.

    Returns:
        A pd.DataFrame that contains active orders given by ESI. Some simple sorting is added to give better readability.

    Raises:
        TypeError: Argument region_name_or_id should be str or int, not {type(region_name_or_id)}.
        ValueError: Argument order_type accepts one of ["sell", "buy", "all"], not {order_type}.
    """
    # Get station_id
    if isinstance(station_name_or_id, int):
        station_id = station_name_or_id
    elif isinstance(station_name_or_id, str):
        station_id = search_id(station_name_or_id, "station")
    else:
        raise TypeError(
            f"Argument station_name_or_id should be str or int, not {type(station_name_or_id)}."
        )

    if order_type not in ["sell", "buy", "all"]:
        raise ValueError(
            f'Argument "order_type" accepts one of ["sell", "buy", "all"], not {order_type}.'
        )

    # Get the region that the station is in
    region_id = search_station_region_id(station_id)

    update_threshold = kwd.get("expires", 1200)
    no_update_flag, retrieve_time = _update_or_not(
        time.time() - update_threshold,
        "orders",
        "retrieve_time",
        min_fresh_entry=1000,
        region_id=region_id,
        location_id=station_id,
    )
    if not no_update_flag:
        get_region_market(
            region_id, order_type, type_id, update_threshold=update_threshold
        )

    # Uses sqlite to filter instead of DataFrame.
    df = _select_from_orders(
        order_type,
        type_id,
        region_id=region_id,
        location_id=station_id,
        retrieve_time=retrieve_time,
    )
    return df


@cache
def get_jita_market(
    order_type: str = "all", type_id: Optional[int] = None
) -> pd.DataFrame:
    """Retrieves market orders of Jita trade hub.

    A shortcut to the get_station_market() method. See get_station_market() for documentation.
    """
    return get_station_market(
        "Jita IV - Moon 4 - Caldari Navy Assembly Plant", order_type, type_id
    )


async def _get_type_history_async(
    rid: int, type_id: int, reduces: Optional[Callable] = None
):
    """Gets market history of a EVE type asynchronously.

    Sends GET request to /markets/{region_id}/history/, which takes one region_id & one type_id
    and returns a list of dictionary, each of which represents market history of a day.
    The response raw text from each request is 60+KB with over one year of market history,
    and usually a region has 1000+ (15000 for Jita) type_ids to request.
    This makes response from ESI difficult to deal with, so a reduce function is provided to
    reduce 60+KB data into one line of useful data, such as market volume.

    Args:
        rid: region_id
        type_id: type_id of an EVE type. type_id is checked for validity to avoid 404 error from ESI.
        reduces: A function to reduce size of response from 60KB (400+ lines) to one line of useful data.

    Returns:
        A pd.DataFrame: usually 400+ lines if reduce function not provided, or other length depending on reduce func.
        None: if the type_id is invalid (no market history), which is determined by the "published" field of the type.

    Note:
        The "date" field has been changed from "2022-05-28" to a epoch timestamp equivalent to 2022-05-28 11:05:00 GMT+0000
        to facilitate easier comparison. Might be changed to the text format when better caching mechanism is added.

    Some facts:
        1. ESI updates history api every 24 hours.
        2. Each type_id has ~65KB data.
        3. Null sec region (e.g. Vale of the Silent) has 1000+ type_id(s) on market -> ~90MB json.
        4. Jita has 15000+ type_ids -> ~900MB json.
        5. Each type_id needs one request, so 1000+ requests for Null sec and 15000+ requests for Jita.
    """
    update_flag, _ = _update_or_not(
        time.time() - 2 * 24 * 3600,
        "market_history",
        "date",
        fresh_entry_check=False,
        region_id=rid,
        type_id=type_id,
    )
    # db is used to reduce ESI requests, but indexing a table with nearly one million rows is slow.
    if not update_flag:  # using db
        rows = ESIDB.cursor.execute(
            f"SELECT * FROM market_history WHERE region_id={rid} AND type_id={type_id}"
        )
        df = pd.DataFrame(rows, columns=ESIDB.columns["market_history"])
        if reduces:
            df = reduces(df)
            df["type_id"] = type_id
            df["region_id"] = rid
        return df

    resp = await ESIClient.request(
        "get",
        "/markets/{region_id}/history/",
        region_id=rid,
        type_id=type_id,
        raises=None,
    )
    if resp is None:
        return None

    resp = resp.data
    if len(resp) == 0:
        return

    df = pd.DataFrame(resp)
    df["type_id"] = type_id
    df["region_id"] = rid
    # ESI updates history on 11:05:00 GMT, 39900 for 11:05 in timestamp, UTC is the same as GMT
    df["date"] = df["date"].apply(
        lambda date: datetime.timestamp(
            datetime.strptime(f"{date} +0000", "%Y-%m-%d %z")
        )
        + 39900
    )
    df = df[ESIDB.columns["market_history"]]

    df.to_sql(
        "market_history",
        ESIDB.conn,
        if_exists="append",
        index=False,
        method=ESIDB.history_insert_ignore,
    )

    if reduces:
        df = reduces(df)
        df["type_id"] = type_id
        df["region_id"] = rid
    return df


@cache
def get_type_history(
    region_name_or_id: Union[str, int], type_id: int, reduces: Optional[Callable] = None
) -> pd.DataFrame:
    """Gets market history of one EVE type.

    Wraps the _get_type_history_async coroutine to simplifies asyncio related operation.
    See _get_type_history_async() for documentation.
    """
    if isinstance(region_name_or_id, str):
        rid = search_id(region_name_or_id, "region")
    elif isinstance(region_name_or_id, int):
        rid = region_name_or_id
    else:
        raise TypeError(
            f"Argument region_name_or_id should be str or int, not {type(region_name_or_id)}."
        )

    loop = asyncio.get_event_loop()
    df = loop.run_until_complete(_get_type_history_async(rid, type_id, reduces))

    return df


@cache
def get_market_history(
    region_name_or_id: Union[str, int],
    type_ids: List[int] = None,
    reduces: Optional[Callable] = None,
) -> pd.DataFrame:
    """Gets all market history of a region.

    Uses _get_type_history_async() to retrieve market history of multiple types.
    This call takes about 5 minutes with The Forge region (15000+ requests).
    It is recommended to pass in specific type_ids to shorten request time.
    Results of each type is concatenated using pd.concat.

    Args:
        region_name_or_id: A int for region id or a string for the region name.
        type_ids: A list of type_id(s). If not given, retrieve history of all market types in region.
        reduces: A function to reduce size of response from 60KB (400+ lines) to one line of useful data.
            Function should have signature reduce_func(df: pd.DataFrame) -> pd.DataFrame.
            A default function is provided to retrieve market volume of a type.

    Returns:
        A pd.DataFrame. Each line represents market data of a type_id.

    See also:
        reduce_volume(): Reduce a market history DataFrame to volume data.
        _get_type_history_async(): Gets market history of a market type asynchronously.
    """
    if isinstance(region_name_or_id, str):
        rid = search_id(region_name_or_id, "region")
    elif isinstance(region_name_or_id, int):
        rid = region_name_or_id
    else:
        raise TypeError(
            f"Argument region_name_or_id should be str or int, not {type(region_name_or_id)}."
        )

    if type_ids is None:
        type_ids = get_region_types(rid)

    resp = ESIClient.get(
        "/markets/{region_id}/history/",
        async_loop=["type_id"],
        region_id=rid,
        type_id=type_ids,
    )

    for i in range(len(resp)):
        respp = resp[i]
        data = respp.data
        if len(data) == 0:
            resp[i] = None
            continue
        df = pd.DataFrame(data)
        type_id = respp.request_info.params.get("type_id")
        df["type_id"] = type_id
        df["region_id"] = rid
        # ESI updates history on 11:05:00 GMT, 39900 for 11:05 in timestamp, UTC is the same as GMT
        df["date"] = df["date"].apply(
            lambda date: datetime.timestamp(
                datetime.strptime(f"{date} +0000", "%Y-%m-%d %z")
            )
            + 39900
        )
        df = df[ESIDB.columns["market_history"]]

        df.to_sql(
            "market_history",
            ESIDB.conn,
            if_exists="append",
            index=False,
            method=ESIDB.history_insert_ignore,
        )

        if reduces:
            df = reduces(df)
            df["type_id"] = type_id
            df["region_id"] = rid
        resp[i] = df

    df = pd.concat(resp, ignore_index=True)
    return df


@cache
def get_region_types(region_name_or_id: Union[str, int], src: str = "esi") -> List[int]:
    """Gets type_ids that have active orders in the region.

    Requests a list of type_ids from /markets/{region_id}/types/, with a given region_id.
    It is worth mentioning that although ESI says this endpoint "returns a list of type IDs that have active orders in the region",
    type_ids returned are not all accurate. Some type_id might be unpublished (event items, items for testing, etc.),
    which will cause 404 error when requesting endpoint with type_id field.
    So it is worth using check_type_id() or _check_type_id_async() to check if the type_id is valid.

    Args:
        region_name_or_id: A str for the region name or an int for the region id.
        src: one of ["esi", "db"].
            If set to "esi", requests type_ids from /markets/{region_id}/types/, which contains invalid type_ids.
            If set to "db", selects type_ids from orders table in db, which should all be valid type_ids.

    Returns:
        A list of integers for type_ids. Result is not sorted and the order has no actual meaning.
    """
    if isinstance(region_name_or_id, str):
        rid = search_id(region_name_or_id, "region")
    elif isinstance(region_name_or_id, int):
        rid = region_name_or_id
    else:
        raise TypeError(
            f"Argument region_name_or_id should be str or int, not {type(region_name_or_id)}."
        )

    headers = ESIClient.head("/markets/{region_id}/types/", region_id=rid).headers

    if src == "esi":
        x_pages = int(headers["X-Pages"])
        pages = range(1, x_pages + 1)

        resp = ESIClient.get(
            "/markets/{region_id}/types/",
            async_loop=["page"],
            region_id=rid,
            page=pages,
        )
        ret = []
        for respp in resp:
            ret.extend(respp.data)
    elif src == "db":
        resp = ESIDB.cursor.execute(
            f"SELECT DISTINCT type_id FROM orders WHERE region_id={rid}"
        )
        ret = list(map(lambda x: x[0], resp.fetchall()))

    return ret


@cache(expires=24 * 3600)
def get_structure_types(
    structure_name_or_id: Union[str, int], cname: str = "any"
) -> List[int]:
    """Gets type_ids with active orders in a structure.

    Searches market orders in esi.db database, which includes current and possibly some historic orders.
    If esi.db does not have any orders recorded, uses get_structure_market to obtain current orders.

    Args:
        structure_name_or_id: str | int
            A string or an integer for the structure.
            If a string is given, it should be the precise name of the structure.
            If an integer is given, it should be a valid structure_id.
        cname: str
            cname's character_id will be used in searching structure_id.
            If supplied, this character needs to have docking access to structure.

    Returns:
        A list of integers for type_ids. Result is not sorted and the order has no actual meaning.
    """
    sid = True
    if isinstance(structure_name_or_id, str):
        sid = False
    elif isinstance(structure_name_or_id, int):
        sid = structure_name_or_id
    else:
        raise TypeError(
            f"Argument structure_name_or_id should be str or int, not {type(structure_name_or_id)}."
        )

    if not sid:
        sid = search_structure_id(structure_name_or_id, cname=cname)

    resp = ESIDB.cursor.execute(
        f"SELECT DISTINCT type_id FROM orders WHERE location_id={sid}"
    ).fetchall()
    if not resp:  # esi.db does not have records of structure market orders
        get_structure_market(sid, cname)
        resp = ESIDB.cursor.execute(
            f"SELECT DISTINCT type_id FROM orders WHERE location_id={sid}"
        ).fetchall()
    ret = list(map(lambda x: x[0], resp))
    return ret
