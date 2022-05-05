from ..ESI import ESIClient

def search_id(search: str, category: str) -> int:
    """Searches for the id of an entity in EVE that matches search word.

    Searches for character_id, region_id, corporation_id, etc., provided with correct search word.
    Only allow search that returns one results. Default to strict=true. Use precise search word.

    This method does not require any scope.
    
    Args:
        search: A string to search for.
        category: A string chosen from "alliance", "character", "constellation", "corporation", "inventory_type", "region", "solar_system", "station".
            Incorrect category is rejected.
    
    Returns:
        An int, the id of the search entity within the given category. 
        Assume no overflow.

    Raises:
        ValueError: Use search_structure_id to search for structure id with a given name.
        ValueError: Invalid category given. Choose ONE from accepted categories.
        ValueError: No record of search word in category. Raised when search returns empty result.
        Warning: Raised when return value from ESI has more than one entry.
    """
    accepted_categories = ["alliance", "character", "constellation", "corporation", "inventory_type", "region", "solar_system", "station"]
    if category == "structure":
        raise ValueError("Use search_structure_id to search for structure id with a given name.")
    if category not in accepted_categories:
        raise ValueError(f"Invalid category given. Choose ONE from {accepted_categories}.")

    resp = ESIClient.get("/search/", search=search, categories=category, strict="true")
    ret = resp.get(category)

    if not ret:
        raise ValueError(f"No record of {search} in {category}.")
    
    if len(ret) > 1:
        # TODO: change to "use search_ids" upon completion.
        raise Warning(f"Search should only return one result instead of {len(ret)}. Use precise search word and set strict=True to avoid this warning.")
    return ret[0]

def search_structure_id(search: str, cname: str) -> int:
    """Searches for structure id given a structure. 

    EVE ESI requires docking permission for structure_id search. 

    This method requires 1 scope: esi-search.search_structures.v1

    Args:
        search: str
            The structure name to search for. It needs to be a precise name of the structure.
            For example, for 4-H citadel, search should be "4-HWWF - WinterCo. Central Station".
        cname: str
            The character that has docking access to the structure.
            Internally, a Token with cname (if generated before) will be used for the request.
        
    Returns:
        An int, the structure_id of the given structure, if any.
        Assume no overflow.

    Raises:
        ValueError: No record of structure {search}. Either {cname} does not have docking access, or the search is not precise.
    """
    resp = ESIClient.get("/search/", search=cname, categories="character", strict="true")
    cid = resp.get("character")
    if not cid:
        raise ValueError(f"Invalid character name given: {cname}")
    cid = cid[0]

    resp = ESIClient.get("/characters/{character_id}/search/", categories="structure", character_id=cid, search=search, strict="true", cname=cname)
    ret = resp.get("structure")

    if not ret:
        raise ValueError(f"No record of structure \"{search}\". Either {cname} does not have docking access, or the search is not precise.")
    return ret[0]