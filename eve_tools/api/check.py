from eve_tools.ESI import ESIClient


def check_type_id(type_id: int) -> bool:
    """Checks if a type_id is valid.

    A type_id is "valid" if other apis requring type_id field do not give 404 errors.

    Checks using /universe/types/{type_id}/ endpoint, which returns information of type_id.
    There are lots of fields in response, and only uses "published" field as valid flag.
    "published" field is present in all responses from this endpoint.

    Args:
        type_id: A int that specifies the type_id to check.

    Returns:
        A bool that shows if type_id is valid.
    """
    resp = ESIClient.get("/universe/types/{type_id}/", type_id=type_id)
    valid = resp.data.get("published")
    return valid


async def _check_type_id_async(type_id: int) -> bool:
    """Coroutine version of check_type_id(). See check_type_id()."""
    resp = await ESIClient.request("get", "/universe/types/{type_id}/", type_id=type_id)
    valid = resp.data.get("published")
    return valid
