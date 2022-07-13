import os
from dataclasses import dataclass
import pandas as pd

from .utils import cache
from eve_tools.ESI import ESIClient
from eve_tools.config import SDE_DIR


@cache(expires=24 * 3600 * 30)  # one month
def search_id(search: str, category: str, cname: str = "any") -> int:
    """Searches for the id of an entity in EVE that matches search word.

    Searches for character_id, region_id, corporation_id, etc., provided with correct search word.
    Only allow search that returns one results. Default to strict=true. Use precise search word.

    As of July 12th 2022, ESI deprecated unauthenticated /search/ endpoint.
    All searches now need to use authenticated "/characters/{character_id}/search/" endpoint.
    Note that character_id is not a required param with authenticated endpoint.

    Args:
        search: str
            Precise search word.
        category: str
            One of ["alliance", "character", "constellation", "corporation", "type", "inventory_type", "region", "solar_system", "system", "station"].
            Incorrect category is rejected.
        cname: str
            cname's character_id will be used in searching. Specifies which character's token to use.
            If searching for structure, this character needs to have docking access.

    Returns:
        An int, the id of the search entity within the given category.
        Assume no overflow.

    Raises:
        ValueError: Invalid category given. Choose ONE from accepted categories.
        ValueError: No record of search word in category. Raised when search returns empty result.
        Warning: Raised when return value from ESI has more than one entry.

    Caches:
        cache.db-api_cache: one month

    Scopes:
        esi-search.search_structures.v1

    Example:
        >>> from eve_tools import search_id
        >>> print(search_id("Ishtar", categories="inventory_type"))
        12005
        >>> print(search_id("Jita", categories="system"))
        30000240
    """
    if category == "structure":
        return search_structure_id(search, cname)
    elif category == "region":
        return search_region_id(search)
    elif category == "system" or category == "solar_system":
        return search_system_id(search)
    elif category == "type" or category == "inventory_type":
        return search_type_id(search)

    accepted_categories = [
        "alliance",
        "character",
        "constellation",
        "corporation",
        "inventory_type",
        "region",
        "solar_system",
        "station",
    ]

    if category not in accepted_categories:
        raise ValueError(
            f"Invalid category given. Choose ONE from {accepted_categories}."
        )

    resp = ESIClient.get(
        "/characters/{character_id}/search/",
        categories=category,
        search=search,
        strict="true",
        cname=cname,
    ).data

    ret = resp.get(category)

    if not ret:
        raise ValueError(f"No record of {search} in {category}.")

    if len(ret) > 1:
        # TODO: change to "use search_ids" upon completion.
        raise Warning(
            f"Search should only return one result instead of {len(ret)}. Use precise search word and set strict=True to avoid this warning."
        )
    return ret[0]


@dataclass
class Structure:

    structure_id: int
    system_id: int
    owner_id: int
    name: str

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Structure):
            return self.structure_id == __o.structure_id
        raise NotImplemented


@cache(expires=24 * 3600)  # one day
def search_structure(structure_id: int) -> Structure:
    """Searches for a structure's info.

    Args:
        structure_id: str
            A valid structure_id, e.g. 1035466617946

    Returns:
        A Structure instance with station_id.

    Cache:
        cache.db-api_cache: one day

    Example:
        >>> from eve_tools import search_structure
        >>> structure = search_structure(1035466617946)
        >>> print(structure)
        Structure(structure_id=1035466617946, system_id=30000240, owner_id=98599770, name='4-HWWF - WinterCo. Central Station')
    """
    resp = ESIClient.get(
        "/universe/structures/{structure_id}/", structure_id=structure_id
    ).data
    return Structure(
        structure_id=structure_id,
        system_id=resp["solar_system_id"],
        owner_id=resp["owner_id"],
        name=resp["name"],
    )


def search_structure_system_id(structure_id: int) -> int:
    """Searches system_id given a structure_id.

    Args:
        structure_id: int
            A valid structure_id, e.g. 1035466617946

    Returns:
        A int for system_id.

    Example:
        >>> from eve_tools import search_structure_system_id
        >>> print(search_structure_system_id(1035466617946))
        30000240
    """
    structure = search_structure(structure_id)
    return structure.system_id


def search_structure_region_id(structure_id: int) -> int:
    """Searches region_id given a structure_id.

    Args:
        structure_id: int
            A valid structure_id, e.g. 1035466617946

    Returns:
        A int for region_id.

    Example:
        >>> from eve_tools import search_structure_region_id
        >>> print(search_structure_region_id(1035466617946))
        10000003
    """
    system_id = search_structure_system_id(structure_id)
    region_id = search_system_region_id(system_id)
    return region_id


@cache(expires=24 * 3600 * 30)  # one month
def search_structure_id(structure_name: str, cname: str = "any") -> int:
    """Searches for structure_id given a structure.

    The oauth character should have docking access to the structure, as per ESI requirements.

    Args:
        structure_name: str
            The structure name to search for. It needs to be a precise name of the structure.
            For example, for 4-H citadel, search should be "4-HWWF - WinterCo. Central Station",
            instead of "4-H Citadel" or "4-HWWF WinterCo Central Station".
        cname: str
            cname's character_id will be used in searching. This character needs to have docking access to structure.

    Returns:
        An int, the structure_id of the given structure, if any. A structure_id is in int64.

    Raises:
        ValueError: No record of structure {search}.

    Caches:
        cache.db-api_cache: one month

    Scopes:
        esi-search.search_structures.v1

    Example:
        >>> from eve_tools import search_structure_id
        >>> print(search_structure_id("4-HWWF - WinterCo. Central Station"))
        1035466617946
    """
    resp = ESIClient.get(
        "/characters/{character_id}/search/",
        categories="structure",
        search=structure_name,
        strict="true",
        cname=cname,
    ).data
    ret = resp.get("structure")

    if not ret:
        raise ValueError(f'No record of structure "{structure_name}". ')
    return ret[0]


@dataclass
class Station:

    station_id: int
    system_id: int
    region_id: int
    name: str
    security: float
    stationTypeID: int

    def __init__(self, df: pd.DataFrame):
        self.station_id = int(df["stationID"])
        self.system_id = int(df["solarSystemID"])
        self.region_id = int(df["regionID"])
        self.name = df["stationName"].values[0]
        self.security = float(df["security"])
        self.stationTypeID = int(df["stationTypeID"])

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Station):
            return __o.station_id == self.station_id
        raise NotImplemented


@cache(expires=24 * 3600 * 30)
def search_station(station_id: int) -> Station:
    """Searches for a staton's info.

    Args:
        station_id: int
            A valid station_id, e.g. 60000004

    Returns:
        A Station instance with station_id.

    Raises:
        ValueError: Invalid station_id given: {station_id}

    Cache:
        cache.db-api_cache: one month

    Example:
        >>> from eve_tools import search_station
        >>> station = search_station(60000004)
        >>> print(station)
        Station(station_id=60000004, system_id=30002780, region_id=10000033, name='Muvolailen X - Moon 3 - CBD Corporation Storage', security=0.7080867245, stationTypeID=1531)
    """
    staStations = pd.read_csv(os.path.join(SDE_DIR, "staStations.csv.bz2"))

    stationIDs = staStations["stationID"]
    if station_id not in stationIDs.values:
        raise ValueError(f"Invalid station_id given: {station_id}.")

    station = staStations.loc[stationIDs == station_id]
    return Station(station)


def search_station_region_id(station_id: int) -> int:
    """Searches region_id given a station_id.

    Args:
        station_id: int
            A valid station_id, e.g. 60000004

    Returns:
        A int for region_id.

    Example:
        >>> from eve_tools import search_station_region_id
        >>> print(search_station_region_id(60000004))
        10000033
    """
    station = search_station(station_id)
    return station.region_id


def search_station_system_id(station_id: int) -> int:
    """Searches system_id given a station_id.

    Args:
        station_id: int
            A valid station_id, e.g. 60000004

    Returns:
        A int for system_id.

    Example:
        >>> from eve_tools import search_station_system_id
        >>> print(search_station_system_id(60000004))
        30002780
    """
    station = search_station(station_id)
    return station.system_id


@cache(expires=24 * 3600 * 30)  # one month
def search_region_id(search: str) -> int:
    """Searches region_id given a region name.

    Args:
        search: str
            A valid region name in precise form. "The Forge" instead of "The For".

    Returns:
        A int for region_id.

    Raises:
        ValueError: Invalid region name given: {search}

    Caches:
        cache.db-api_cache: one month

    Example:
        >>> from eve_tools import search_region_id
        >>> print(search_region_id("The Forge"))
        10000002
    """
    mapRegions = pd.read_csv(os.path.join(SDE_DIR, "mapRegions.csv.bz2"))

    region_name = mapRegions["regionName"]
    if search not in region_name.values:
        raise ValueError(f"Invalid region name given: {search}.")

    region = mapRegions.loc[region_name == search]
    return int(region["regionID"])


@dataclass
class SolarSystem:

    system_id: int
    region_id: int
    name: str
    security: float

    def __init__(self, df: pd.DataFrame):
        self.system_id = int(df["solarSystemID"])
        self.region_id = int(df["regionID"])
        self.name = df["solarSystemName"].values[0]
        self.security = float(df["security"])

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, SolarSystem):
            return self.system_id == __o.system_id and self.name == __o.name
        raise NotImplemented


@cache(expires=24 * 3600 * 30)
def search_system(system_id: int) -> SolarSystem:
    """Searches for a system's info.

    Args:
        system_id: int
            A valid system_id, e.g. 30000007

    Returns:
        A SolarSystem instance with system_id.

    Raises:
        ValueError: Invalid system_id given: {system_id}

    Cache:
        cache.db-api_cache: one month

    Example:
        >>> from eve_tools import search_system
        >>> esi_system = search_system(30000007)
        >>> print(esi_system)
        System(system_id=30000007, region_id=10000001, name='Yuzier', security=0.9065555105)
    """
    mapSolarSystems = pd.read_csv(os.path.join(SDE_DIR, "mapSolarSystems.csv.bz2"))

    solarSystemID = mapSolarSystems["solarSystemID"]
    if system_id not in solarSystemID.values:
        raise ValueError(f"Invalid system_id given: {system_id}.")

    solar_system = mapSolarSystems.loc[solarSystemID == system_id]
    return SolarSystem(solar_system)


@cache(expires=24 * 3600 * 30)  # one month
def search_system_id(search: str) -> int:
    """Searches system_id given a system name.

    Args:
        search: str
            A valid system name in precise form, e.g. "Jita"

    Returns:
        A int for system_id.

    Raises:
        ValueError: Invalid system name given: {search}

    Caches:
        cache.db-api_cache: one month

    Example:
        >>> from eve_tools import search_system_id
        >>> print(search_system_id("Jita"))
        30000240
    """
    mapSolarSystems = pd.read_csv(os.path.join(SDE_DIR, "mapSolarSystems.csv.bz2"))

    solarSystemName = mapSolarSystems["solarSystemName"]
    if search not in solarSystemName.values:
        raise ValueError(f"Invalid system name given: {search}.")

    solarSystem = mapSolarSystems.loc[solarSystemName == search]
    return int(solarSystem["solarSystemID"])


def search_system_region_id(system_id: int) -> int:
    """Searches for region_id given a system_id.
    Finds which region_id (Vale of the Silent, etc.) the given system (4-HWWF, etc.) is located.
    """
    """Searches region_id given a system_id.

    Args:
        system_id: int
            A valid system_id, e.g. 30000007

    Returns:
        A int for region_id.

    Example:
        >>> from eve_tools import search_system_region_id
        >>> print(search_system_region_id(30000007))
        10000001
    """
    esi_system: SolarSystem = search_system(system_id)
    return esi_system.region_id


@dataclass
class InvType:

    type_id: int
    type_name: str
    published: bool
    marketGroupID: int

    def __init__(self, df: pd.DataFrame):
        self.type_id = int(df["typeID"])
        self.type_name = df["typeName"].values[0]
        self.published = bool(int(df["published"]))
        self.marketGroupID = int(df["marketGroupID"])

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, InvType):
            return self.type_id == __o.type_id and self.type_name == __o.type_name
        raise NotImplemented


@cache(expires=24 * 3600 * 30)
def search_type(type_id: int) -> InvType:
    """Searches for a type's info.

    Args:
        type_id: int
            A valid type_id, e.g. 12005 (ishtar)

    Returns:
        A InvType instance with type_id.

    Raises:
        ValueError: Invalid type_id given: {type_id}

    Cache:
        cache.db-api_cache: one month

    Example:
        >>> from eve_tools import search_type
        >>> invType = search_type(12005)
        >>> print(invType)
        InvType(type_id=12005, type_name='Ishtar', published=True, marketGroupID=451)
    """
    invTypes = pd.read_csv(os.path.join(SDE_DIR, "invTypes.csv.bz2"))

    typeIDs = invTypes["typeID"]
    if type_id not in typeIDs.values:
        raise ValueError(f"Invalid type_id given: {type_id}.")

    invType = invTypes.loc[typeIDs == type_id]
    return InvType(invType)


@cache(expires=24 * 3600 * 30)
def search_type_id(search: str) -> int:
    """Searches type_id given a type name.

    Args:
        search: str
            A valid type name in precise form, e.g. "Ishtar"

    Returns:
        A int for type_id.

    Raises:
        ValueError: Invalid type name given: {search}

    Caches:
        cache.db-api_cache: one month

    Note:
        Using SDE needs more memory (15MB) but less time than ESI endpoint.
        Considering most modern systems have adequate RAM, time is more sensitive.

    Example:
        >>> from eve_tools import search_type_id
        >>> print(search_type_id("Ishtar"))
        12005
    """
    invTypes = pd.read_csv(os.path.join(SDE_DIR, "invTypes.csv.bz2"))

    typeName = invTypes["typeName"]
    if search not in typeName.values:
        raise ValueError(f"Invalid type name given: {search}.")

    invType = invTypes.loc[typeName == search]
    return int(invType["typeID"])
