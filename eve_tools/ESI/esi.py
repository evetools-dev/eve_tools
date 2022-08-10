import asyncio
import aiohttp
import copy
import logging
import os
import pandas as pd
from dataclasses import dataclass
from tqdm.asyncio import tqdm_asyncio
from typing import Iterable, Optional, Union, List


from .token import ESITokens, Token
from .metadata import ESIMetadata, ESIRequest
from .application import ESIApplications, Application
from .utils import (
    ESIRequestError,
    _SessionRecord,
    _session_recorder,
    cache_check_request,
)
from eve_tools.config import SDE_DIR


logger = logging.getLogger(__name__)


@dataclass
class ESIResponse:
    """Response returned by ESI.request() family.

    User should never create ESIResponse but gets it from ESI.request() calls.

    Attributes: (referencing aiohttp doc)
        status: int
            HTTP status code of response.
        method: str
            Request's method.
        headers: dict
            A case insensitive dictionary with HTTP headers of response.
        request_info: ESIRequest
            A copy for request info with url, params, headers used in request.
        data: dict | List | int
            A json serialized response body, a dictionary or a list or an int.
        expires: str | None
            A RFC7231 formatted datetime string, if any.
        error_remain: int
            Errors the user can make in the time window.
        error_reset: int
            Time window left, in seconds. After this many seconds, error_remain will be refreshed to 100.
    """

    status: int
    method: str
    headers: dict
    request_info: ESIRequest
    data: Optional[Union[dict, List, int]]
    expires: Optional[str] = None
    error_remain: Optional[int] = 100
    error_reset: Optional[int] = 60

    def __len__(self):
        return len(self.data)


class ESI(object):
    """ESI request client for API requests.

    Simplifies ESI API requests and oauth process.
    """

    metaurl = "https://esi.evetech.net/latest"
    default_callback = "https://localhost/callback/"

    def __init__(self):

        self.apps = ESIApplications()
        self._metadata = ESIMetadata()

        ### Async request
        # Can't put this ClientSession instance to be a global variable.
        # If ClientSession is global, its __del__ will run before ESI.__del__,
        # and ClientSession.__del__ logs some messages, causing things like "Module open not found".
        # If put within ESI, ESI.__del__ will be run first, which closes session connections,
        # avoiding errors from aiohttp.
        self._async_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False), raise_for_status=True
        )  # default maximum 100 connections  # aiohttp advices not to create session per request

        self._event_loop = asyncio.get_event_loop()

        ### Exit flag
        self._app_changed = False

        ### Session record
        self._record_session = True  # default recording
        self._record: _SessionRecord = _SessionRecord()
        
        ### Request checker
        self._request_checker = _RequestChecker()


    @_session_recorder(fields="timer")
    def get(
        self,
        key: str,
        async_loop: Optional[List] = None,
        **kwd,
    ) -> Union[dict, List[dict]]:
        """Requests GET an ESI API.

        Simplifies coroutine execution and send asynchronous GET request to ESI server.
        The usage is similar to requests.get, with simplified async speed up.
        When async_loop argument is empty, this method is sending one request and waiting its result.
        When async_loop is given, this method will loop through arguments in async_loop and run these tasks asynchronously,
        effectively executing multiple requests in parallel.
        Parameters are enforced similar to the "Try it out" function on the ESI website.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            key: str
                A string identifying the API endpoint, in the format "/characters/{character_id}/industry/jobs/".
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            async_loop: List | None
                A list of arguments that this method would loop through in order and execute asynchronously.
                If async_loop is not given, this method would perform similar to a requests.get method.
                If async_loop is given, this method requires corresponding kwd arguments exist and are iterable.
            kwd.raises: bool | None
                Raises ClientResponseError or not. One of [None, True, False].
                If async_loop not given, default True. If given, default None.
                None: raises when "x-esi-error-limit-remain" <= 5, return None when > 5.
                True: always raises when no attempts left (1 attempt on code 400, 404, 420).
                False: never raises, return None on error when no attempts left.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.
            kwd.generate_token: bool
                A bool that specifies in case token doesn't exist, whether to go through token generation or raise errors.
                Default generating tokens.
            kwd.checks: bool
                Whether to use _RequestChecker to incorrect requests.


        Returns:
            A dictionary or a list of dictionary, depends on async_loop argument.

        Note:
            If request needs character_id field and is an authenticated endpoint, character_id field is optional,
            because authentication result contains the character_id of the authenticated character.


        Example:
        >>> from eve_tools import ESIClient   # ESIClient is an instance instantiated upon import
        >>> data = ESIClient.get("/markets/structures/{structure_id}/", structure_id=1035466617946)     # Single synchronous request
        >>> # Asynchronously request 100 pages (1000 orders per page) of buy orders of The Forge (region of Jita)
        >>> data = ESIClient.get("/markets/{region_id}/orders/", async_loop=["page"], region_id=1000002, page=range(1, 101), order_type="buy")
        """
        if kwd.get("raises", "not given") == "not given":
            # uses default raises
            if async_loop:
                raises = None
            else:
                raises = True
        else:
            raises = kwd.pop("raises")

        if not async_loop:
            return self._event_loop.run_until_complete(
                self.request("get", key, raises=raises, **kwd)
            )

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
                tasks.append(
                    asyncio.ensure_future(
                        self.request("get", key, raises=raises, **kwd)
                    )
                )
                return
            async_loop_cpy = async_loop[:]
            curr = async_loop_cpy.pop(0)
            kwd_cpy = kwd.copy()
            if curr not in kwd:
                raise ValueError(
                    f'Element "{curr}" in async_loop argument is not given as **kwd argument.'
                )
            if not isinstance(kwd[curr], Iterable):
                raise ValueError(f"Keyword argument {curr} should be iterable.")
            for value in kwd[curr]:
                kwd_cpy[curr] = value
                recursive_looper(async_loop_cpy, kwd_cpy)

        recursive_looper(list(async_loop), kwd)

        # self._event_loop.run_until_complete(tqdm_asyncio.gather(*tasks))
        self._event_loop.run_until_complete(tqdm_asyncio.gather(*tasks))

        ret = []
        for task in tasks:
            # each task.result() is a ESIResponse instance or None
            result = task.result()
            if result is not None:
                ret.append(result)
        return ret

    @_session_recorder(fields="timer")
    def head(self, key: str, **kwd) -> dict:
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
                Raises ClientResponseError or not. One of [None, True, False]. Default True.
                None: raises when "x-esi-error-limit-remain" <= 5, return None when > 5.
                True: always raises when no attempts left (1 attempt on code 400, 404, 420).
                False: never raises, return None on error when no attempts left.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.
            kwd.generate_token: bool
                A bool that specifies in case token doesn't exist, whether to go through token generation or raise errors.
                Default generating tokens
            kwd.checks: bool
                Whether to use _RequestChecker to incorrect requests.

        Returns:
            A dictionary containing headers from ESI request.
            None, if request is blocked or has error.

        Example:
        >>> from eve_tools import ESIClient       # ESIClient is an instance instantiated upon import
        >>> headers = ESIClient.head("/markets/structures/{structure_id}/", structure_id=sid, page=1)
        >>> x_pages = int(headers["X-Pages"])   # X-Pages tells total # of pages for "page" parameter
        """
        raises = kwd.pop("raises", True)
        return self._event_loop.run_until_complete(
            self.request("head", key, raises=raises, **kwd)
        )

    async def request(self, method: str, key: str, **kwd) -> Union[dict, None]:
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
                Raises ClientResponseError or not. One of [None, True, False].
                None: raises when "x-esi-error-limit-remain" <= 5, return None when > 5.
                True: always raises when no attempts left (1 attempt on code 400, 404, 420).
                False: never raises, return None on error when no attempts left.
            kwd.checks: bool
                Whether to use _RequestChecker to incorrect requests.
            kwd: Keywords necessary for sending the request, such as headers, params, and other ESI required inputs.

        Returns:
            An instance of ESIResponse containing response of the request.
            None, if request is blocked, or an error occurs and kwd.raises set to False or None.

        Raises:
            NotImplementedError: Request type POST/DELETE/PUT is not supported.

        See also:
            ESI.get(): sends asynchronous request GET to an API.
        """
        self._check_key(key)

        api_request = self._metadata[key]
        if api_request.request_type not in ["get", "head"]:
            raise NotImplementedError(
                f"Request type {api_request.request_type} is not supported."
            )

        api_request.kwd = copy.deepcopy(kwd)

        self._check_method(api_request, method)

        params = kwd.get("params", {})
        api_request.params.update(params)

        headers = kwd.get("headers", {})
        generate_token = kwd.get("generate_token", True)
        # if has security and has no Authorization field, get auth token.
        if api_request.security and not headers.get("Authorization"):
            app = self.apps.search_scope(" ".join(api_request.security))
            with ESITokens(app) as tokens:
                cname = kwd.pop("cname", "any")
                if generate_token and not tokens.exist(cname):
                    logger.debug("Generate token for request: %s %s", method, key)
                    token = tokens.generate()
                else:
                    token = tokens[cname]
                api_request.token = token
                headers.update(self._get_auth_headers(token))

        api_request.headers.update(headers)

        raises = kwd.pop("raises", None)
        checks = kwd.pop("checks", True)

        self._parse_request_keywords(api_request, kwd)

        # Using asyncio.run() is problematic because it creates a new event loop (or maybe other advanced/mysterious reasons?).
        # For my application (web request), aiohttp kind of like non-blocking accept in C,
        # where I need to use epoll (or select) to interrupt the blocking accept and do something else (like servering a client).
        # Something cool and slightly difficult to understand: https://stackoverflow.com/questions/49005651/how-does-asyncio-actually-work
        # self.async_request = ESIRequestError(raises=raises)(self.async_request)
        res = await ESIRequestError(raises=raises)(self.async_request)(
            api_request, method, checks=checks
        )

        return res

    @_session_recorder(exclude="timer")
    async def async_request(
        self, api_request: ESIRequest, method: str, checks: bool = True
    ) -> Union[dict, None]:
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
            None, if request is blocked or a 400/404 error occurs.
        """
        # Check (predict) if api_request sent will cause ESI error.
        # This reduces 400, 404, and 403 errors.
        if checks and not await self._request_checker(api_request):
            return None

        # no encoding: "4-HWF" stays what it is
        if method == "get":
            async with self._async_session.get(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as req:
                data = await req.json()
                resp = ESIResponse(
                    status=req.status,
                    method=req.method,
                    headers=dict(req.headers),
                    request_info=api_request,
                    data=data,
                    expires=req.headers.get("Expires"),
                    error_remain=int(req.headers.get("x-esi-error-limit-remain")),
                    error_reset=int(req.headers.get("x-esi-error-limit-reset")),
                )

        elif method == "head":
            async with self._async_session.head(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as req:
                resp = ESIResponse(
                    status=req.status,
                    method=req.method,
                    headers=dict(req.headers),
                    request_info=api_request,
                    data=None,
                    expires=req.headers.get("Expires"),
                    error_remain=int(req.headers.get("x-esi-error-limit-remain")),
                    error_reset=int(req.headers.get("x-esi-error-limit-reset")),
                )

        return resp

    def add_app_generate_token(
        self, clientId: str, scope: str, callbackURL: Optional[str] = None
    ) -> None:
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
            self._app_changed = True
            self.apps.save()

        with ESITokens(new_app) as token:
            token.generate()

    def _get_auth_headers(self, token: Token) -> dict:
        # Read from local token file and append to request headers.
        access_token = token.access_token
        auth_headers = {"Authorization": "Bearer {}".format(access_token)}
        return auth_headers

    def _check_key(self, key: str) -> None:
        if key not in self._metadata.paths:
            raise ValueError(f"{key} is not a valid request key.")

    def _check_method(self, api_request: ESIRequest, method: str) -> None:
        """Checks if method is supported by the ESIRequest.
        Assume only one request_type (one of "get", "post", etc.) for api_request.
        """
        req_method = api_request.request_type
        if req_method == method:
            return

        if method == "head" and req_method == "get":
            return

        raise ValueError(
            f"Request method {method} is not supported by {api_request.request_key} request."
        )

    def _parse_request_keywords(self, api_request: ESIRequest, keywords: dict) -> None:
        """Parses and checks user provided parameters.

        Checks fields in keywords if necessary parameters are given.
        Fills in ESIRequest with parameters parsed from keywords.

        Args:
            api_request: ESIRequest
                A struct holding request info for an API request.
                Necessary info (url, params, headers) is filled in according to metadata and some facts.
            keywords: dict
                Kwd argument provided by user, containing headers, params, and other necessary fields for the API.
                Missing keywords (such as character_id) raises errors.

        Facts:
            _in: path
                1. Param.required = True
                2. Appears as {Param.name} in url: https://.../characters/{character_id}/orders/
                3. Pass in with kwd argument, not params, headers, or data
                4. Param.default is None
            _in: query
                1. Pass in with either kwd or params, not headers or data
                2. Appears as ?query=value in url: https://.../?datasource=tranquility
            _in: header
                1. Request token has been updated to headers before calling this function
                2. ESI marks "token" param as optional
        """

        path_params = {}  # params for request url.format()
        query_params = {}  # params for url/?{key1}={value1}?{key2}={value2}...
        headers = keywords.pop("headers", {})

        cid = 0
        if api_request.token is not None:
            cid = api_request.token.character_id

        for api_param_ in api_request.parameters:
            if api_param_._in == "path":
                key = api_param_.name
                value = self._parse_request_keywords_in_path(
                    keywords, key, api_param_.dtype, cid
                )
                path_params.update({key: value})
                # dict unpacking later
            elif api_param_._in == "query":
                default = api_param_.default
                key = api_param_.name
                value = self._parse_request_keywords_in_query(
                    keywords, key, api_param_.required, api_param_.dtype
                )
                if value is not None:
                    query_params.update({key: value})  # update if value is given
                elif default is not None:
                    query_params.update({key: default})  # else update if default is set
            elif api_param_._in == "header":  # not "headers"
                # usually not reached
                key = api_param_.name
                value = self._parse_request_keywords_in_header(
                    headers, key, api_param_.required, api_param_.dtype
                )
                if value is not None:
                    headers.update({key: value})

        url = api_request.request_key
        url = url.format(**path_params)
        api_request.params.update(query_params)
        api_request.headers.update(headers)
        api_request.url = self.metaurl + url  # urljoin is difficult to deal with...

    @staticmethod
    def _parse_request_keywords_in_path(
        where: dict, key: str, dtype: str, cid: int = 0
    ) -> str:
        # dtype is not checked yet. Checking it needs to parse "schema" field and integerate into "dtype",
        # and needs to find a way to fit user input to the dtype field.
        # No need to check Param.required because Param._in == "path" => Param.required == True
        if key == "character_id" and cid > 0 and "character_id" not in where:
            # Prioritizes user input character_id
            return cid
        value = where.pop(key, None)
        if value is None:
            raise KeyError(f'Missing key "{key}" in keywords.')
        return value

    @staticmethod
    def _parse_request_keywords_in_query(
        where: dict, key: str, required: bool, dtype: str
    ) -> str:
        value = where.pop(key, None)
        params = where.get("params")
        value2 = None
        if params:
            value2 = params.get(key)

        if value and value2:
            raise KeyError(f'Duplicate key "{key}" in both keywords and params.')

        if value is None and value2 is None and required:
            raise KeyError(f'Missing key "{key}" in keywords.')

        if value is not None:
            return value
        elif value2 is not None:
            return value2
        else:
            return None

    @staticmethod
    def _parse_request_keywords_in_header(
        where: dict, key: str, required: bool, dtype: str
    ) -> str:
        value = where.pop(key, None)
        if not required:
            return value
        if value is None:
            raise KeyError(f'Missing key "{key}" in keywords.')
        return value

    def __del__(self):
        """Close ClientSession of the ESI instance."""
        if self._async_session is None:
            return

        if not self._async_session.closed:
            if self._async_session._connector_owner:
                self._async_session._connector._close()  # silence deprecation warning
            self._async_session._connector = None

        if not self._event_loop.is_closed():
            self._event_loop.run_until_complete(asyncio.sleep(0))
            self._event_loop.close()

    def _start_record(self):
        """Starts recording useful response info."""
        self._record_session = True

    def _stop_record(self):
        """Stops recording ESIResponse."""
        self._record_session = False

    def _clear_record(self, field: Optional[str] = None):
        """Clears record of the instance."""
        self._record.clear(field)


class _RequestChecker:
    """Checks a request for validity.

    Checks various parameters to avoid 400 and 404 errors from ESI.
    The expectation is to completely eliminate 400 and 404 errors in stable state.
    All checkers only check according to some rules, having no feedback loop from ESIResponse.
    """

    # Reading a .csv.bz2 is costly. Takes 15MB memory and a long time (~0.x second)
    invTypes = pd.read_csv(os.path.join(SDE_DIR, "invTypes.csv.bz2"))

    requests = 0  # just for fun

    async def __call__(self, api_request: ESIRequest) -> bool:
        valid = await self._check_request(api_request)
        if valid:
            w = "PASSED"
        else:
            w = "BLOCKED"
        logger.info(
            '%s - endpoint "%s" with kwd %s',
            w,
            api_request.request_key,
            api_request.kwd,
        )
        return valid

    @cache_check_request
    async def _check_request(self, api_request: ESIRequest) -> bool:
        """Checks if an ESIRequest is valid.

        Checks parameters of an ESIRequest, and predicts if the request is valid.
        Currently, the ESI._check_* family only checks parameters following some rules.
        This means there is no feedback loop from responses.
        """
        valid = True
        # Check type_id if exists
        if "type_id" in api_request.params:
            type_id = api_request.params.get("type_id")
            valid = await self._check_request_type_id(type_id)

        return valid

    @cache_check_request
    async def _check_request_type_id(self, type_id: int) -> bool:
        """Checks if a type_id is valid.

        Uses type_id from api_requests.params["type_id"].
        First checks using SDE, then checks using ESI endpoint if SDE passed.
        This method is independent from api/check and api/search.
        """
        if type_id not in self.invTypes["typeID"].values:
            return False

        invType = self.invTypes.loc[self.invTypes["typeID"] == type_id]
        published = bool(int(invType["published"]))
        if not published:
            return False

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False), raise_for_status=True
        ) as session:
            async with session.get(
                f"https://esi.evetech.net/latest/universe/types/{type_id}/?datasource=tranquility&language=en",
            ) as resp:
                data: dict = await resp.json()
                published = data.get("published")
                self.requests += 1
                if not published:
                    return False

        return True
