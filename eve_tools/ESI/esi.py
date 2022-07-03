import asyncio
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate
import logging
import aiohttp
from typing import Coroutine, Optional, Union, List

from .token import ESITokens
from .metadata import ESIMetadata, ESIRequest
from .application import ESIApplications, Application
from .utils import ESIRequestError

# Assume python int has sufficient precision
# Assume each path is either GET or POST, not both

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
        data: dict | List | int
            A json serialized response body, a dictionary or a list or an int.
        expires: str | None
            A RFC7231 formatted datetime string, if any.
    """

    status: int
    method: str
    headers: dict
    data: Optional[Union[dict, List, int]]
    expires: Optional[str] = None


class ESI(object):
    """ESI request client for API requests.

    Simplifies ESI API requests and oauth process.
    """

    metaurl = "https://esi.evetech.net/latest"
    default_callback = "https://localhost/callback/"

    def __init__(self, **kwd):

        self.apps = ESIApplications()
        self._metadata = ESIMetadata()

        ### Async request
        self._async_session = None  # aiohttp advices not to create session per request
        self._event_loop = asyncio.get_event_loop()

        ### Exit flag
        self._app_changed = False

        ### API session
        self._api_session = False
        self._api_session_record = None

    def get(
        self,
        key: str,
        generate_token: Optional[bool] = True,
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
            generate_token: bool
                A bool that specifies in case token doesn't exist, whether to go through token generation or raise errors.
                Default generating tokens.
            async_loop: List | None
                A list of arguments that this method would loop through in order and execute asynchronously.
                If async_loop is not given, this method would perform similar to a requests.get method.
                If async_loop is given, this method requires corresponding kwd arguments exist and are iterable.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.

        Returns:
            A dictionary or a list of dictionary, depends on async_loop argument.

        Example:
        >>> from src.ESI import ESIClient   # ESIClient is an instance instantiated upon import
        >>> data = ESIClient.get("/markets/structures/{structure_id}/", structure_id=1035466617946)     # Single synchronous request
        >>> # Asynchronously request 100 pages (1000 orders per page) of buy orders of The Forge (region of Jita)
        >>> data = ESIClient.get("/markets/{region_id}/orders/", async_loop=["page"], region_id=1000002, page=range(1, 101), order_type="buy")
        """
        if not async_loop:
            return self._event_loop.run_until_complete(
                self.request("get", key, generate_token, **kwd)
            )

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
                        self.request("get", key, generate_token, **kwd)
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
            for value in kwd[curr]:
                kwd_cpy[curr] = value
                recursive_looper(async_loop_cpy, kwd_cpy)

        recursive_looper(async_loop, kwd)

        self._event_loop.run_until_complete(asyncio.wait(tasks))

        ret = []
        for task in tasks:
            # each task.result() is a ESIResponse instance
            ret.append(task.result())  # well, let's forget about memory

        return ret

    def head(self, key: str, generate_token: Optional[bool] = True, **kwd) -> dict:
        """Request HEAD an ESI API.

        Checks input parameters and send a synchronous HEAD request to ESI server.
        The usage is similar to ESIClient.get method, with same parameters and async_loop set to None.
        Parameters are enforced similar to the "Try it out" function on the ESI website.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            key: str
                A string identifying the API endpoint, in the format "/characters/{character_id}/industry/jobs/".
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            generate_token: bool
                A bool that specifies in case token doesn't exist, whether to go through token generation or raise errors.
                Default generating tokens.
            kwd.params: dict
                A dictionary containing parameters for the request.
                Required params indicated by ESI are enforced. Optional params are filled in with default values.
            kwd.headers: dict
                A dictionary containing headers for the request. Request Token is not necessary in this headers.
                If headers["Authorization"] field is provided, skips all Token operations.
                EVE ESI does not require headers info, but supplying with User-Agent, etc., is recommended.
            kwd.cname: str
                A string of character name. Token with cname would be used for the request.

        Returns:
            A dictionary containing headers from ESI request.

        Example:
        >>> from src.ESI import ESIClient       # ESIClient is an instance instantiated upon import
        >>> headers = ESIClient.head("/markets/structures/{structure_id}/", structure_id=sid, page=1)
        >>> x_pages = int(headers["X-Pages"])   # X-Pages tells total # of pages for "page" parameter
        """
        return self._event_loop.run_until_complete(
            self.request("head", key, generate_token, **kwd)
        )

    async def request(
        self, method: str, key: str, generate_token: Optional[bool] = True, **kwd
    ) -> dict:
        """Sends one request to an ESI API.

        Checks input parameters and send one asynchronous request to ESI server.
        Request method is checked against the key to see if the API supports the given method.
        Parameters are enforced similar to the "Try it out" function on the ESI website.
        Some APIs require authorization. Use add_app_generate_token() method to ease through ESI oauth process.

        Args:
            method: str
                A string for HTTP request method, e.g. "get", "head"
            key: str
                A string identifying the API endpoint, in the format "/characters/{character_id}/industry/jobs/".
                Keys should be copy-pasted from ESI website. Invalid keys are rejected.
            generate_token: bool
                A bool that specifies in case token doesn't exist, whether to go through token generation or raise errors.
                Default generating tokens if not exists.
            kwd: Keywords necessary for sending the request, such as headers, params, and other ESI required inputs.

        Returns:
            An instance of ESIResponse containing response of the request.

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

        self._check_method(api_request, method)

        params = kwd.get("params", {})
        api_request.params.update(params)

        headers = kwd.get("headers", {})
        # if has security and has no Authorization field, get auth token.
        if api_request.security and not headers.get("Authorization"):
            app = self.apps.search_scope(" ".join(api_request.security))
            with ESITokens(app) as tokens:
                cname = kwd.pop("cname", "any")
                if generate_token and not tokens.exist(cname):
                    logger.debug("Generate token for request: %s %s", method, key)
                    tokens.generate()
                headers.update(self._get_auth_headers(tokens, cname))

        api_request.headers.update(headers)

        self._parse_request_keywords(api_request, kwd)

        # Using asyncio.run() is problematic because it creates a new event loop (or maybe other advanced/mysterious reasons?).
        # For my application (web request), aiohttp kind of like non-blocking accept in C,
        # where I need to use epoll (or select) to interrupt the blocking accept and do something else (like servering a client).
        # Something cool and slightly difficult to understand: https://stackoverflow.com/questions/49005651/how-does-asyncio-actually-work
        res = await self.async_request(api_request, method)

        return res

    def _api_session_recorder(_coro: Coroutine):
        """Records useful info from ESIResponse that can be fed to other objects."""

        async def _api_session_recorder_wrapped(_self, *args, **kwd):
            resp: ESIResponse = await _coro(
                _self, *args, **kwd
            )  # this _self should be an instance of ESI

            if not _self._api_session:
                return resp

            expires = resp.expires

            if not _self._api_session_record:
                _self._api_session_record = expires

            # Use the earliest expire
            if expires:
                expires_dt = datetime(*parsedate(expires)[:6])
                record_dt = datetime(*parsedate(_self._api_session_record)[:6])
                if expires_dt < record_dt:
                    _self._api_session_record = expires
            return resp

        return _api_session_recorder_wrapped

    @ESIRequestError(attempts=3)
    @_api_session_recorder
    async def async_request(self, api_request: ESIRequest, method: str) -> dict:
        """Asynchronous requests to ESI API.

        Uses aiohttp to asynchronously request GET to ESI API.
        ClientSession is created once for each instance and shared by multiple async_request call of the instance.
        Default having maximum 100 open connections (100 async_request pending).

        Args:
            api_request: ESIRequest
                A fully initialized ESIRequest with url, params, headers field filled in, given to aiohttp.ClientSession.get.
            method: str
                A str for HTTP request method.

        Returns:
            An instance of ESIResponse containing response of the request. Memory allocation assumed not to be a problem.
        """
        if not self._async_session:
            self._async_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False), raise_for_status=True
            )  # default maximum 100 connections

        # no encoding: "4-HWF" stays what it is
        if method == "get":
            async with self._async_session.get(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as req:
                data = await req.json()
                resp = ESIResponse(
                    req.status,
                    req.method,
                    dict(req.headers),
                    data,
                    req.headers.get("Expires"),
                )

        elif method == "head":
            async with self._async_session.head(
                api_request.url, params=api_request.params, headers=api_request.headers
            ) as req:
                resp = ESIResponse(
                    req.status,
                    req.method,
                    dict(req.headers),
                    None,
                    req.headers.get("Expires"),
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

    def _get_auth_headers(
        self, tokens: ESITokens, cname: Optional[str] = "any"
    ) -> dict:
        # Read from local token file and append to request headers.
        access_token = tokens[cname].access_token
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

    def _parse_request_keywords(self, api_request: ESIRequest, keywords: dict):
        """Parses and checks user provided parameters.

        Checks fields in keywords if necessary parameters are given.
        Fills in ESIRequest with parameters parsed from keywords.

        Args:
            api_request: ESIRequest
                A struct holding request info for an API request.
                Necessary info (url, params, headers) is filled in according to metadata and some facts.
            keywords: dict
                A dictionary provided by user, containing headers, params, and other necessary fields for the API.
                Missing keywords (such as character_id) raises errors.

        Facts:
            _in: path
                1. Param.required = True
                2. Appears as {Param.name} in url
                3. Pass in with kwd argument, not params, headers, or data
                4. Param.default is None
            _in: query
                1. Pass in with either kwd or params, not headers or data
            _in: header
                1. Request token has been updated to headers before calling this function
                2. ESI marks "token" param as optional
        """

        path_params = {}  # params for request url.format()
        query_params = {}  # params for url/?{key1}={value1}?{key2}={value2}...
        headers = keywords.pop("headers", {})

        for api_param_ in api_request.parameters:
            if api_param_._in == "path":
                key = api_param_.name
                value = self._parse_request_keywords_in_path(
                    keywords, key, api_param_.dtype
                )
                path_params.update({key: value})
                # dict unpacking later
            elif api_param_._in == "query":
                default = api_param_.default
                key = api_param_.name
                value = self._parse_request_keywords_in_query(
                    keywords, key, api_param_.required, api_param_.dtype
                )
                if value:
                    query_params.update({key: value})  # update if value is given
                elif default:
                    query_params.update({key: default})  # else update if default is set
            elif api_param_._in == "header":  # not "headers"
                # usually not reached
                key = api_param_.name
                value = self._parse_request_keywords_in_header(
                    headers, key, api_param_.required, api_param_.dtype
                )
                if value:
                    headers.update({key: value})

        url = api_request.request_key
        url = url.format(**path_params)
        api_request.params.update(query_params)
        api_request.headers.update(headers)
        api_request.url = self.metaurl + url  # urljoin is difficult to deal with...

    @staticmethod
    def _parse_request_keywords_in_path(where: dict, key: str, dtype: str) -> str:
        # dtype is not checked yet. Checking it needs to parse "schema" field and integerate into "dtype",
        # and needs to find a way to fit user input to the dtype field.
        # No need to check Param.required because Param._in == "path" => Param.required == True
        value = where.pop(key, None)
        if not value:
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

        if not value and not value2 and required:
            raise KeyError(f'Missing key "{key}" in keywords.')

        if value:
            return value
        elif value2:
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
        if not value:
            raise KeyError(f'Missing key "{key}" in keywords.')
        return value

    def __del__(self):
        """Close ClientSession of the ESI instance."""
        if not self._async_session:
            return

        if not self._async_session.closed:
            if self._async_session._connector_owner:
                self._async_session._connector.close()
            self._async_session._connector = None

    def _start_api_session(self):
        """Starts recording useful ESIResponse from API calls."""
        self._api_session = True
        self._api_session_record = None

    def _end_api_session(self):
        """Ends recording ESIResponse from API calls."""
        self._api_session = False

    def _clear_api_record(self):
        """Clears _api_session_record entry of the instance."""
        self._api_session_record = None
        self._api_session = False
