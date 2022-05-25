import pandas as pd
import time
from typing import Union, Optional

from src.ESI import ESIClient
from src.api import search_structure_id, search_id, search_station_region_id
from src.data import ESIDB, orders_columns
from .utils import _update_or_not, _select_from_orders


def get_structure_market(structure_name_or_id: Union[str, int], cname: Optional[str] = None, **kwd) -> pd.DataFrame:
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
        cname: str | None
            A string for the character name, used by the search_structure_id to search for structure_id of a given structure name.
            This character should have docking (market) access to the structure. See search_structure_id().
            If a structure name is given, cname is required. If a structure id is given, cname is optional.
        kwd.page: int
            An integer that specifies which page to retrieve from ESI. Defaul retrieving all orders from ESI.
            Page number is purely random and speficying a page number is only useful in testing.
        kwd.update_threshold: int
            An integer that specifies the minimum interval between two updates. Unit in seconds.
            Default 1200 (20 minutes). User can set this to -1 if forcing update.
        kwd.system_id: int
            A int for the system_id in which the structure is located.
            system_id can be retrieved by search_structure_system_id() method, which requires additonal esi-universe.read_structures.v1 scope.
        kwd.region_id: int
            A int for the region_id in which the structure is located.
            region_id can be retrieved by search_system_region_id() method, provided with the region_id of the structure.
            
    Returns:
        A pd.DataFrame that contains active orders given by ESI. Some simple sorting is added to give better readability.

    Raises:
        TypeError: Argument structure_name_or_id should be str or int, not {type(structure_name_or_id)}.
        ValueError: Require parameter "cname" for authentication when structure name is given instead of structure id.

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
        raise TypeError(f"Argument structure_name_or_id should be str or int, not {type(structure_name_or_id)}.")
    
    if not sid and not cname:   # if s_id not given, cname is required for search_structure_id api
        raise ValueError(f"Require parameter \"cname\" for authentication when structure name is given instead of structure id.")
    else:
        sid = search_structure_id(structure_name_or_id, cname)

    # Using cache db or get from ESI
    update_threshold = kwd.get("update_threshold", 1200)
    update_flag, retrieve_time = _update_or_not(update_threshold, location_id=sid)
    if not update_flag:
        df = _select_from_orders(location_id=sid, retrieve_time=retrieve_time)
        return df
    
    # Getting from ESI
    page = kwd.get("page", -1)
    if page == -1:
        headers = ESIClient.head("/markets/structures/{structure_id}/", structure_id=sid, page=1)
        x_pages = int(headers["X-Pages"])   # get X-Pages headers, which tells how many pages of data
        pages = range(1, x_pages+1)
    else:
        pages = [page]

    all_orders = ESIClient.get("/markets/structures/{structure_id}/", async_loop=["page"], structure_id=sid, page=pages)
    
    # Formmating output and append to db
    df = pd.DataFrame(all_orders)

    df["retrieve_time"] = int(time.time())      # save some digits
    df["region_id"] = kwd.get("region_id", 0)   # default 0
    df["system_id"] = kwd.get("system_id", 0)   # default 0, use search_structure_system_id() to find system_id

    df.sort_values(["type_id", "is_buy_order", "price"], axis=0, ascending=[True, True, True], inplace=True)
    df = df[orders_columns]     # reorder columns

    df.to_sql("orders", ESIDB.conn, if_exists="append", index=False, method=ESIDB.orders_insert_update)
    return df

def get_region_market(region_name_or_id: Union[str, int], order_type: str = "all", type_id: Optional[int] = None, **kwd) -> pd.DataFrame:
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
            A string for the optional order_type parameter. Default to "all".
            One of ["all", "sell", "buy"].
        type_id: int | None
            An integer that specifies the type_id to retrieve from ESI.
            If type_id is given, only returns market orders of that specific type.
        kwd.page: int
            An integer that specifies which page to retrieve from ESI. Defaul retrieving all orders from ESI (~300 pages).
            Page number is purely random and speficying a page number is only useful in testing.
        kwd.update_threshold: int
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
        raise TypeError(f"Argument region_name_or_id should be str or int, not {type(region_name_or_id)}.")

    if order_type not in ["sell", "buy", "all"]:
        raise ValueError(f"Argument \"order_type\" accepts one of [\"sell\", \"buy\", \"all\"], not {order_type}.")

    page = kwd.get("page", -1)
    update_threshold = kwd.get("update_threshold", 1200)

    # Using cache db or get from ESI
    update_flag, retrieve_time = _update_or_not(update_threshold, region_id=rid)
    if not update_flag:
        print("Using cache data")
        df = _select_from_orders(order_type, type_id, region_id=rid, retrieve_time=retrieve_time)
        return df

    # Getting from ESI
    if page == -1:
        headers = ESIClient.head("/markets/{region_id}/orders/", region_id=rid, order_type=order_type, type_id=type_id, page=1)
        x_pages = int(headers["X-Pages"])   # get X-Pages headers, which tells how many pages of data
        pages = range(1, x_pages+1)
    else:
        pages = [page]

    all_orders = ESIClient.get("/markets/{region_id}/orders/", async_loop=["page"], region_id=rid, order_type=order_type, type_id=type_id, page=pages)

    # Formmating output and append to db
    df = pd.DataFrame(all_orders)

    df["retrieve_time"] = int(time.time())  # save some digits
    df["region_id"] = rid

    df.sort_values(["type_id", "is_buy_order", "price"], axis=0, ascending=[True, True, True], inplace=True)
    df = df[orders_columns]     # reorder columns 

    df.to_sql("orders", ESIDB.conn, if_exists="append", index=False, method=ESIDB.orders_insert_update)
    return df

def get_station_market(station_name_or_id: Union[str, int], order_type: str = "all", type_id: Optional[int] = None, **kwd) -> pd.DataFrame:
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
        kwd.update_threshold: int
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
        raise TypeError(f"Argument station_name_or_id should be str or int, not {type(station_name_or_id)}.")
    
    if order_type not in ["sell", "buy", "all"]:
        raise ValueError(f"Argument \"order_type\" accepts one of [\"sell\", \"buy\", \"all\"], not {order_type}.")

    # Get the region that the station is in
    region_id = search_station_region_id(station_id)
    
    update_threshold = kwd.get("update_threshold", 1200)
    no_update_flag, retrieve_time = _update_or_not(update_threshold, region_id=region_id, location_id=station_id)
    if not no_update_flag:
        get_region_market(region_id, order_type, type_id, update_threshold=update_threshold)
    
    # Uses sqlite to filter instead of DataFrame.
    df = _select_from_orders(order_type, type_id, region_id=region_id, location_id=station_id, retrieve_time=retrieve_time)
    return df

def get_jita_market(order_type: str = "all", type_id: Optional[int] = None) -> pd.DataFrame:
    """Retrieves market orders of Jita trade hub.

    A shortcut to the get_station_market() method. See get_station_market() for documentation.
    """
    return get_station_market("Jita IV - Moon 4 - Caldari Navy Assembly Plant", order_type, type_id)