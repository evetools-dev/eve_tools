import asyncio
import aiohttp
from tqdm.asyncio import tqdm_asyncio
from typing import Iterable, Optional, Union, List

from .checker import ESIRequestChecker
from .dbHandler import ESIDBHandler
from .formatter import ESIFormatter
from .parser import ESIRequestParser
from .token import ESITokens
from .metadata import ESIRequest
from .application import ESIApplications, Application
from .response import ESIResponse
from .utils import (
    ESIRequestError,
    _SessionRecord,
    _session_recorder,
)
from eve_tools.log import getLogger


logger = getLogger(__name__)


class ESI(object):
    """ESI request client for API requests.

    Contains ESI.request family for sending requests to ESI and deals with ESI OAuth process.

    Note:
        ESI class is singleton by design.
    """

    default_callback = "https://localhost/callback/"

    def __init__(self):

        self.apps = ESIApplications()

        ### Async request
        # Can't put this ClientSession instance to be a global variable.
        # If ClientSession is global, its __del__ will run before ESI.__del__,
        # and ClientSession.__del__ logs some messages, causing things like "Module open not found".
        # If put within ESI, ESI.__del__ will be run first, which closes session connections,
        # avoiding errors from aiohttp.

        # default maximum 100 connections
        # aiohttp advices not to create session per request
        # even not setting raise_for_status=True, ESI class still raises conditionally.
        self.__async_session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
        self.__event_loop = asyncio.get_event_loop()

        ### Formatter
        self.__formatter = ESIFormatter()

        ### Session record
        self._record_session = True  # default recording
        self._record: _SessionRecord = _SessionRecord()

        ### Request checker
        self.__request_checker = ESIRequestChecker()
        self.__raises = None  # user defined raise flag

        ### Request parser
        self.__parser = ESIRequestParser(self.apps)

        ### Request DB handler
        self.__db = ESIDBHandler()

        logger.info("ESI instance initiated")

    def __new__(cls):
        """Singleton design."""
        if not hasattr(cls, "__instance"):
            cls.__instance = super(ESI, cls).__new__(cls)
        else:
            logger.debug("ESI instance copy used")
        return cls.__instance

    def __del__(self):
        """Close ClientSession of the ESI instance."""
        if self.__async_session is None:
            return

        if not self.__async_session.closed:
            if self.__async_session._connector_owner:
                self.__async_session._connector._close()  # silence deprecation warning
            self.__async_session._connector = None

        if not self.__event_loop.is_closed():
            self.__event_loop.run_until_complete(asyncio.sleep(0))
            self.__event_loop.close()

    def setChecker(self, chkr: ESIRequestChecker):
        """Sets an ESIRequestChecker instance for ESIClient."""
        self.__request_checker = chkr

    @property
    def checker(self) -> ESIRequestChecker:
        return self.__request_checker

    def setFormatter(self, fmt: ESIFormatter):
        self._formatter = fmt

    @property
    def formatter(self):
        return self.__formatter

    @property
    def parser(self) -> ESIRequestParser:
        return self.__parser

    @_session_recorder(fields="timer")
    def get(
        self,
        key: str,
        async_loop: Optional[List] = None,
        **kwd,
    ) -> Union[ESIResponse, List[ESIResponse], None]:
        """Requests GET an ESI API.

        Simplifies coroutine execution and send asynchronous GET request to ESI server.
        The usage is similar to requests.get, with simplified async speed up.
        When async_loop argument is empty, this method is sending one request through aiohttp and waiting its result.
        When async_loop is given, this method will loop through arguments in async_loop and run these tasks asynchronously,
        effectively executing multiple requests in parallel.

        Parameters are enforced similar to the "Try it out" function on the ESI website.
        Some invalid parameters, such as region_id = 12345, are blocked locally and thus return None,
        while some are not detected and thus might raise or return None depending on kwd ``raises``.
        By default, raises for singular blocked request and not raise for blocked request within async loop.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            key: str
                A string identifying the API endpoint, in the format ``/characters/{character_id}/industry/jobs/``.
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            async_loop: List | None
                A list of arguments that this method would loop through in order and execute asynchronously.
                If async_loop is not given, this method would perform similar to a requests.get method.
                If async_loop is given, this method requires corresponding kwd arguments exist and are iterable.
            kwd.raises: bool | None
                Raises errors or not on invalid/failed requests. One of [None, True, False].
                If async_loop not given, default True. If given, default None.
                * True: always raises on errors (some errors allow multiple attempts).
                * False: promise never raises, return None on error. Use with caution.
                * None: same as True when response headers "x-esi-error-limit-remain" <= 5. Otherwise, not raise on status error (status > 400), raise on some other errors (TimeoutError, ServerDisconnectedError). Promise return an ESIResponse (or list of ESIResponse) when no error.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.
            kwd.checks: bool
                Whether to use ``ESIRequestChecker`` to block incorrect requests, default ``True``.
            kwd.formats: bool
                Whether to use ``ESIFormatter`` to format ``ESIResponse``, default ``False``.
            kwd.stores: bool
                Whether to use ``ESIDBHandler`` to store ``ESIResponse`` to database, default ``False``.
                If set to ``True``, ``formats`` keyword automatically sets to True.

        Returns:
            An ESIResponse instance or a list of ESIResponse instances, depends on async_loop argument.
            Or None, if ``async_loop = None`` and an error occurs and keyword ``raises = False``.

        Note:
            If request needs ``character_id`` field and is an authenticated endpoint, ``character_id`` field is optional,
            because authentication result contains the character_id of the authenticated character.

        Example:
        >>> from eve_tools import ESIClient   # ESIClient is an instance instantiated upon import
        >>> data = ESIClient.get("/markets/structures/{structure_id}/", structure_id=1035466617946)     # Single synchronous request
        >>> # Asynchronously request 100 pages (1000 orders per page) of buy orders of The Forge (region of Jita)
        >>> data = ESIClient.get("/markets/{region_id}/orders/", async_loop=["page"], region_id=1000002, page=range(1, 101), order_type="buy")
        """
        if kwd.get("raises", ...) is Ellipsis:
            # uses default raises
            if async_loop:
                raises = None
            else:
                raises = True
        else:
            raises = kwd.pop("raises")

        if not async_loop:
            logger.info("REQUEST GET - %s w/k %s", key, str(kwd))
            ret = self.__event_loop.run_until_complete(self.request("get", key, raises=raises, **kwd))
            return ret

        if async_loop is not None and not isinstance(async_loop, Iterable):
            raise ValueError("async_loop should be iterable.")

        # Not sure which is better
        # creating coroutines, gathering them, then run_until_complete the coro with gather, or
        # using ensure_future to create lots of futures, and run_until_complete all futures
        tasks = []

        def recursive_looper(async_loop: List, kwd: dict):
            """A recursive helper that unfold a list into a nested loop.

            Example:
            >>> kwd["loop1"] = [0, 1, 2]
            >>> kwd["loop2"] = ["a", "b", "c"]
            >>> kwd["loop3"] = [111, 222, 333]
            >>> async_loop = ["loop1", "loop2", "loop3"]
            With this set up, this function is equivalent to
            >>> for i in loop1:
            >>>     for j in loop2:
            >>>         for k in loop3:
            >>>             do something
            """
            if not async_loop:
                tasks.append(asyncio.ensure_future(self.request("get", key, raises=raises, **kwd)))
                return
            async_loop_cpy = async_loop[:]
            curr = async_loop_cpy.pop(0)
            kwd_cpy = kwd.copy()
            if curr not in kwd:
                raise ValueError(f'Element "{curr}" in async_loop argument is not given as **kwd argument.')
            if not isinstance(kwd[curr], Iterable):
                raise ValueError(f"Keyword argument {curr} should be iterable.")
            for value in kwd[curr]:
                kwd_cpy[curr] = value
                recursive_looper(async_loop_cpy, kwd_cpy)

        recursive_looper(list(async_loop), kwd)

        logger.info(f"REQUEST GET - {key} on {str(async_loop)}: {len(tasks)} tasks w/ keyword {str(kwd)}")

        # self.__event_loop.run_until_complete(tqdm_asyncio.gather(*tasks))
        self.__event_loop.run_until_complete(tqdm_asyncio.gather(*tasks))

        ret = []
        for task in tasks:
            # each task.result() is a ESIResponse instance or None
            result = task.result()
            if result is not None:
                ret.append(result)
        return ret

    @_session_recorder(fields="timer")
    def head(self, key: str, **kwd) -> ESIResponse:
        """Request HEAD an ESI API.

        Checks input parameters and send a synchronous HEAD request to ESI server.
        The usage is similar to ESIClient.get method, with same parameters and async_loop set to None.
        Parameters are enforced similar to the "Try it out" function on the ESI website.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            key: str
                A string identifying the API endpoint, in the format "/characters/{character_id}/industry/jobs/".
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            kwd.raises: bool | None
                Raises errors or not on invalid/failed requests. One of [None, True, False]. Default True.
                * True: always raises on errors (some errors allow multiple attempts).
                * False: promise never raises, return None on error. Use with caution.
                * None: same as True when response headers "x-esi-error-limit-remain" <= 5. Otherwise, not raise on status error (status > 400), raise on some other errors (TimeoutError, ServerDisconnectedError). Promise return an ESIResponse when no error.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.
            kwd.checks: bool
                Whether to use _RequestChecker to block incorrect requests, default True.

        Returns:
            A dictionary containing headers from ESI request.
            Or None, if an error occurs and keyword ``raises = False``.

        Example:
        >>> from eve_tools import ESIClient       # ESIClient is an instance instantiated upon import
        >>> headers = ESIClient.head("/markets/structures/{structure_id}/", structure_id=sid, page=1)
        >>> x_pages = int(headers["X-Pages"])   # X-Pages tells total # of pages for "page" parameter
        """
        raises = kwd.pop("raises", True)
        logger.info("REQUEST HEAD - %s w/k %s", key, str(kwd))
        ret = self.__event_loop.run_until_complete(self.request("head", key, raises=raises, **kwd))
        return ret

    async def request(self, method: str, key: str, **kwd) -> Union[ESIResponse, None]:
        """Sends one request to an ESI API.

        Checks input parameters and send one asynchronous request to ESI server.
        Request method is checked against the key to see if the API supports the given method.
        Parameters are enforced similar to the "Try it out" function on the ESI website,
        EXCEPT for character_id in authenticated endpoint.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            method: str
                A string for HTTP request method, e.g. "get", "head"
            key: str
                A string identifying the API endpoint, in the format "/characters/{character_id}/industry/jobs/".
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            kwd.raises: bool | None
                Raises errors or not on invalid/failed requests. One of [None, True, False]. Default None.
                * True: always raises on errors (some errors allow multiple attempts).
                * False: promise never raises, return None on error. Use with caution.
                * None: same as True when response headers "x-esi-error-limit-remain" <= 5. Otherwise, not raise on status error (status > 400), raise on some other errors (TimeoutError, ServerDisconnectedError). Promise return an ESIResponse (or list of ESIResponse) when no error.
            kwd.checks: bool
                Whether to use ``ESIRequestChecker`` to block incorrect requests, default ``True``.
            kwd.formats: bool
                Whether to use ``ESIFormatter`` to format ``ESIResponse``, default ``False``.
            kwd.stores: bool
                Whether to use ``ESIDBHandler`` to store ``ESIResponse`` to database, default ``False``.
                If set to ``True``, ``formats`` keyword automatically sets to True.
            kwd: Keywords necessary for sending the request, such as ``headers``, ``params``, and other ESI required inputs.

        Returns:
            An instance of ESIResponse containing response of the request.
            Or None, if an error occurs and keyword ``raises`` set to False.

        Raises:
            NotImplementedError: Request type POST/DELETE/PUT is not supported.

        See also:
            ESI.get(): sends asynchronous request GET to an API.
        """

        self.__raises = kwd.pop("raises", None)
        checks = self.__request_checker.enabled and kwd.pop("checks", True)
        stores = self.__db.enabled and kwd.pop("stores", False)
        formats = self.__formatter.enabled and stores or kwd.pop("formats", False)

        # Parser: parse user input
        api_request = await self.__parser(key, method, **kwd)

        # Checker: (predict) if api_request sent will cause ESI error.
        # This reduces 400, 404, and 403 errors.
        __raise_flag = self.__raises
        if checks:
            valid = await self.__request_checker(api_request, __raise_flag)
            if not valid:  # blocked
                if self.__raises is None:
                    # promised to return an ESIResponse
                    return ESIResponse(-1, api_request.request_type, {}, api_request, data=None)
                else:
                    return None

        # Using asyncio.run() is problematic because it creates a new event loop (or maybe other advanced/mysterious reasons?).
        # For my application (web request), aiohttp kind of like non-blocking accept in C,
        # where I need to use epoll (or select) to interrupt the blocking accept and do something else (like servering a client).
        # Something cool and slightly difficult to understand: https://stackoverflow.com/questions/49005651/how-does-asyncio-actually-work
        # self.async_request = ESIRequestError(raises=raises)(self.async_request)
        res: ESIResponse = await ESIRequestError(raises=self.__raises)(self.async_request)(
            api_request, method, checks=checks
        )

        # Parser: etag cache
        if res is not None:
            etag = res.headers.get("Etag")
            if res.status == 304:  # Uses etag cache
                res.data = self.__parser._get_etag_payload(api_request.rid)
            elif res.status == 200:
                self.__parser._set_etag(api_request.rid, etag, res.data)

        self.__raises = None  # back to default

        # Formatter: format response
        if formats:
            res = self.__formatter(key, res)

        if stores:
            res = self.__db(key, res)
        return res

    @_session_recorder(exclude="timer")
    async def async_request(
        self, api_request: ESIRequest, method: str, checks: bool = True
    ) -> Union[ESIResponse, None]:
        """Asynchronous requests to ESI API.

        Uses aiohttp to asynchronously request GET to ESI API.
        ClientSession is created once for each instance and shared by multiple async_request call of the instance.
        Default having maximum 100 open connections (100 async_request pending).

        Args:
            api_request: ESIRequest
                A fully initialized ESIRequest with url, params, headers field filled in, given to aiohttp.ClientSession.get.
            method: str
                A str for HTTP request method.
            checks: bool
                Whether to use _RequestChecker to incorrect requests.

        Returns:
            An instance of ESIResponse containing response of the request. Memory allocation assumed not to be a problem.
            Or None, if an error occurs and ESI.request family sets keyword ``raises = False``.
        """
        # no encoding: "4-HWF" stays what it is
        if method == "get":
            async with self.__async_session.get(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as resp:
                api_request.url = str(resp.url)  # URL class implements str
                data = None
                if resp.status == 200:
                    data = await resp.json()
                elif resp.status != 304:
                    logger.warning(
                        "Response status %d: key = %s, kwd = %s",
                        resp.status,
                        api_request.request_key,
                        str(api_request.kwd),
                    )
                # If resp not OK, some headers fields might be empty.
                # Default values for these fields might be dangerous as they might be unexpected.
                ret = ESIResponse(
                    status=resp.status,
                    method=resp.method,
                    headers=dict(resp.headers),
                    request_info=api_request,
                    data=data,
                    expires=resp.headers.get("Expires"),
                    reason=resp.reason,
                    error_remain=int(resp.headers.get("x-esi-error-limit-remain", 100)),
                    error_reset=int(resp.headers.get("x-esi-error-limit-reset", 60)),
                )

        elif method == "head":
            async with self.__async_session.head(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as resp:
                api_request.url = str(resp.url)
                ret = ESIResponse(
                    status=resp.status,
                    method=resp.method,
                    headers=dict(resp.headers),
                    request_info=api_request,
                    data=None,
                    expires=resp.headers.get("Expires"),
                    reason=resp.reason,
                    error_remain=int(resp.headers.get("x-esi-error-limit-remain")),
                    error_reset=int(resp.headers.get("x-esi-error-limit-reset")),
                )

        return ret

    def add_app_generate_token(self, clientId: str, scope: str, callbackURL: Optional[str] = None) -> None:
        """Adds a new Application to the client and generate a token for it.

        Creates a new Application with given parameters, which should be obtained from applications in:
        https://developers.eveonline.com/applications/

        If clientId exists in any current applications, new app is not allocated nor added.
        Invalid parameters are not checked and may lead to undefined behavior.
        New Application is stored to "application.json" instantly.
        New Token is stored instantly.

        Args:
            clientId: str
                A str acting as a unique key for an Application, created and retrieved from ESI developer site:
                https://developers.eveonline.com/

            scope: str
                A comma seperated str, usually copied from ESI developer site,
                in the format "esi...v1 esi...v1 esi...v1"
            callbackURL: str
                A str of URL that the authentication will redirect to.
                Default and recommend using: https://localhost/callback/
        """
        if not callbackURL:
            callbackURL = self.default_callback

        update_flag = True
        for app in self.apps.apps:  # ESIApplications does not implement __iter__ method
            if app.clientId == clientId:
                new_app = app
                update_flag = False

        if update_flag:
            new_app = Application(clientId, scope, callbackURL)
            self.apps.append(new_app)
            self.apps.save()

        with ESITokens(new_app) as token:
            token.generate()

    def _start_record(self):
        """Starts recording useful response info."""
        self._record_session = True

    def _stop_record(self):
        """Stops recording ESIResponse."""
        self._record_session = False

    def _clear_record(self, field: Optional[str] = None):
        """Clears record of the instance."""
        self._record.clear(field)
        logger.debug("ESI SessionRecord cleared")
