import aiohttp
import os
import pandas as pd

from .metadata import ESIRequest
from .utils import cache_check_request
from eve_tools.config import SDE_DIR
from eve_tools.data import SqliteCache, CacheDB
from eve_tools.exceptions import InvalidRequestError
from eve_tools.log import getLogger


logger = getLogger(__name__)


class _NonOverridable(type):
    """Prevents subclass overriding some methods."""

    __final__ = ["__call__", "__check_request"]  # methods not overridable

    def __new__(cls, __name: str, __bases, __namespace):
        if __bases:
            for finals in cls.__final__:
                if finals in __namespace:
                    raise SyntaxError(f"Overriding {finals} is not allowed")
        return type.__new__(cls, __name, __bases, __namespace)


class ESIRequestChecker(metaclass=_NonOverridable):
    """Checks a request for validity.

    Checks various parameters to avoid errors from ESI.
    The expectation is to completely eliminate 400 and 404 errors in stable state.
    All checkers only check according to some rules, having no feedback loop from ``ESIResponse``.

    User could override individual check methods to customize checking rules.
    ``__call__`` and ``__check_request`` methods are not allowed to override.

    Attributes:
        cache: SqliteCache
            A cache instance to store the check result. If not given, default ``checker_cache`` under ``eve_tools/data/cache.db``.

    Note:
        Individual check methods should be async functions, and should be decorated by ``cache_check_request`` from ``eve_tools.ESI``.
    """

    def __init__(self, cache: SqliteCache = ...) -> None:
        self.raise_flag = False
        self.requests = 0  # just for fun

        if cache is Ellipsis:
            self.cache = SqliteCache(CacheDB, "checker_cache")
        else:
            self.cache = cache

        # Reading a .csv.bz2 is costly. Takes 15MB memory and a long time (~0.x second)
        self.invTypes = pd.read_csv(os.path.join(SDE_DIR, "invTypes.csv.bz2"))

    async def __call__(self, api_request: ESIRequest, raise_flag: bool = False) -> bool:
        self.raise_flag = raise_flag
        return await self.__check_request(api_request)

    async def __check_request(self, api_request: ESIRequest) -> bool:
        """Checks if an ESIRequest is valid.

        Checks parameters of an ESIRequest, and predicts if the request is valid.
        Currently, the ESI._check_* family only checks parameters following some rules.
        This means there is no feedback loop from responses.

        Raises:
            InvalidRequestError: raised when request is blocked and ESI.request family sets keyword ``raises = True``.

        Note:
            This method is not cached, but individual checks are cached for one month.
        """
        valid = True
        error = None
        # Check type_id in query
        if valid and "type_id" in api_request.kwd:
            type_id = api_request.kwd.get("type_id")
            type_id_param = api_request.parameters["type_id"]

            # Decide check or not
            if type_id_param:  # if "type_id" not in parameters -> should be ignored
                if type_id is None and not api_request.parameters["type_id"].required:
                    # sometimes type_id = None is valid, so no check
                    valid = True
                else:  # check
                    valid = await self.check_type_id(type_id)
            if not valid:
                error = InvalidRequestError("type_id", type_id)

        # other tests: if valid and "xxx" in api_request.params:
        if not valid:
            self.__log(api_request)
            api_request.blocked = True
            if self.raise_flag is True and error is not None:
                raise error from None

        return valid

    @cache_check_request
    async def check_type_id(self, type_id: int) -> bool:
        """Checks if a type_id is valid.

        Uses type_id from api_request.kwd.
        First checks using SDE, then checks using ESI endpoint if SDE passed.
        This method is independent from api/check and api/search.

        Note:
            This method is cached for one month.
        """
        valid = type_id in self.invTypes["typeID"].values

        if valid is True:
            invType = self.invTypes.loc[self.invTypes["typeID"] == type_id]
            valid = bool(int(invType["published"]))

        if valid is True:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False), raise_for_status=True
            ) as session:
                async with session.get(
                    f"https://esi.evetech.net/latest/universe/types/{type_id}/?datasource=tranquility&language=en",
                ) as resp:
                    data: dict = await resp.json()
                    self.requests += 1
                    valid = data.get("published")

        return valid

    def __log(self, api_request: ESIRequest):
        logger.warning(
            'BLOCKED - endpoint_"%s": %s',
            api_request.request_key,
            api_request.kwd,
        )
