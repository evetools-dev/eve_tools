from eve_tools.ESI import ESIClient
from .utils import cache


@cache
def get_wallet_balance(cname: str) -> float:
    """
    Potential cancellation point in future ESI versions.
    """
    resp = ESIClient.get("/characters/{character_id}/wallet/", cname=cname)
    return resp.data