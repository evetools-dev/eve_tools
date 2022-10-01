import copy
from ctypes import Union
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from .token import ESITokens
from .metadata import ESIRequest, ESIMetadata
from eve_tools.log import getLogger
from eve_tools.data import SqliteCache, CacheDB

if TYPE_CHECKING:
    from eve_tools.ESI.application import ESIApplications
    from eve_tools.data.db import ESIDBManager

logger = getLogger(__name__)


@dataclass
class ETagEntry:
    """Struct for storing etag and etag's payload."""

    etag: str
    payload: Optional[Any]


class ESIRequestParser:
    """Parses user input parameters to a formalized ``ESIRequest`` instance."""

    def __init__(self, apps: "ESIApplications", cache: "ESIDBManager" = ...) -> None:
        self.metadata = ESIMetadata()
        self.apps = apps
        self.metaurl = "https://esi.evetech.net/latest"

        if cache is Ellipsis:
            self.etag_cache = SqliteCache(CacheDB, table="etag_cache")
        else:
            self.etag_cache = cache

        self.user_agent = "python-eve_tools/ESIClient"

    async def __call__(self, key: str, method: str, **kwd) -> ESIRequest:
        """Parses user input ``key``, ``method``, and keywords to a ``ESIRequest``.

        This method first consults with ``ESIMetadata`` to retrieve metadata information of a request endpoint.
        Then fills users input parameters to ``headers`` and ``params``.

        Args:
            key: str
                ESI request key, in "/.../.../" format, retrieved from ESI website.
            method: str
                One of ``get``, ``head``. ``post`` and other methods are not supported.

        Returns:
            An ``ESIRequest`` instance, with all relevent fields filled in.
        """

        api_request = self.metadata[key]  # metadata of endpoint
        self.__check_method(api_request, method)

        api_request.kwd = copy.deepcopy(kwd)

        params = kwd.get("params", {})
        api_request.params.update(params)

        # Update request headers
        self.__generate_req_headers(api_request, kwd)

        # Parse user input keyword
        self.__parse_request_keywords(api_request, kwd)

        return api_request

    def __check_method(self, api_request: ESIRequest, method: str) -> None:
        """Checks if request method is supported by ESI.

        Args:
            api_request: ESIRequest
                Request info for a request. Retrieved from ``ESIMetadata.__getitem__``.
            method: str
                User input request method.
        """
        if api_request.request_type not in ["get", "head"]:
            raise NotImplementedError(f"Request type {api_request.request_type} is not supported.")

        req_method = api_request.request_type
        if req_method == method:
            return

        if method == "head" and req_method == "get":
            return

        logger.error("Invalid request method: %s for %s", method, api_request.request_key)
        raise NotImplementedError(
            f"Request method {method} is not supported by {api_request.request_key} request."
        )

    def __generate_req_headers(self, api_request: ESIRequest, kwd: dict) -> dict:
        """Generates request headers from metadata.

        Most ESI request needs no user-input headers, but some request headers are useful,
        such as ``If-None-Match`` and ``User-Agent``.
        This method defines default value of these useful HTTP request headers field.
        """
        headers: dict = {}

        # Add oauth to headers
        if api_request.security and "Authorization" not in headers:  # some method does not need oauth
            app = self.apps.search_scope(" ".join(api_request.security))  # find matching application
            with ESITokens(app) as tokens:
                cname = kwd.pop("cname", "any")  # "any" for matching any token
                token = tokens.generate() if not tokens.exist(cname) else tokens[cname]
                api_request.token = token
                access_token = token.access_token
                headers["Authorization"] = "Bearer {}".format(access_token)

        # Add If-None-Match to headers
        # Comply with HTTP Etag headers, see https://developers.eveonline.com/blog/article/esi-etag-best-practices.
        if "If-None-Match" not in headers:
            headers["If-None-Match"] = self._get_etag(api_request.rid)

        # Add User-Agent to headers
        # Provides better bookkeeping for ESI servers.
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.user_agent

        api_request.headers.update(headers)

    def _get_etag(self, request_id: tuple) -> str:
        """Gets etag value for a request with ``request_id``.

        If no matching etag, returns empty string."""
        etag: ETagEntry = self.etag_cache.get(request_id)
        return etag.etag if etag is not None and etag.etag is not None else ""

    def _get_etag_payload(self, request_id: tuple) -> str:
        """Gets response content for request with ``request_id``.

        Use this method when ESI returns ``status: 304``."""
        etag: ETagEntry = self.etag_cache.get(request_id)
        return etag.payload if etag is not None else None

    def _set_etag(self, request_id: tuple, etag: str, payload: Any) -> None:
        """Sets cache entry with key: ``request_id``, value: ``ETagEntry(etag, payload)``."""
        value = ETagEntry(etag, payload)
        # An expires param is given for safety.
        # If for example response content has updated, this ``set`` would update etag for a request.
        # If for example a request is rare, this request's etag would be deleted after 7 days (reasonably long time).
        self.etag_cache.set(request_id, value, 24 * 3600 * 7)

    def __parse_request_keywords(self, api_request: ESIRequest, keywords: dict) -> None:
        """Parses user input parameters according to endpoints metadata.

        Checks fields in ``keywords`` if necessary parameters are given.
        If given, fills in ``api_request`` with fields from keywords.
        If not, either raises errors if field is ``required``, or fill in default value if defined by ESI metadata.

        Args:
            api_request: ESIRequest
                Request info for a request. Retrieved from ``ESIMetadata.__getitem__``.
                Necessary info (url, params, headers) should be filled in by ``ESIMetadata``.
            keywords: dict
                Keywords provided by user, containing ``headers``, ``params``, and other necessary fields defined by ESI,
                such as ``character_id``, ``type_id``, etc.
                If ESI metadata marks fields as ``required``, missing these fields in ``keywords`` raises errors.

        Facts:
            _in: path
                1. Always marked as ``required``
                2. Appears as ``Param.name`` in url: https://.../characters/{character_id}/orders/
                3. Pass in with kwd argument, not params, headers, or data
                4. No default value defined by ESI
            _in: query
                1. Pass in with either ``kwd or ``params``, not ``headers``
                2. Appears as ``?query=value`` in url: https://.../?datasource=tranquility
            _in: header
                1. Request token has been updated to headers before calling this function
                2. ESI marks ``token`` field as optional

        Note:
            ``dtype`` field in ESI metadata is not checked nor enforced.
        """

        path_params = {}  # params for request url.format()
        query_params = {}  # params for url/?{key1}={value1}?{key2}={value2}...
        headers = keywords.pop("headers", {})

        cid = 0
        if api_request.token is not None:
            # Update to tackle ESI's authenticated search endpoint, see https://github.com/esi/esi-issues/issues/1323.
            cid = api_request.token.character_id

        for api_param_ in api_request.parameters:
            # Each param has a "in" field defined by metadata.
            if api_param_._in == "path":
                key = api_param_.name
                value = self.__parse_request_keywords_in_path(keywords, key, api_param_.dtype, cid)
                path_params.update({key: value})  # dict unpacking later

            elif api_param_._in == "query":
                default = api_param_.default
                key = api_param_.name
                value = self.__parse_request_keywords_in_query(
                    keywords,
                    key,
                    api_param_.required,
                    api_param_.default,
                    api_param_.dtype,
                )
                if value is not None:
                    query_params.update({key: value})  # update if value is given
                elif default is not None:
                    query_params.update({key: default})  # else update if default is set

            elif api_param_._in == "header":  # not "headers"
                key = api_param_.name
                value = self.__parse_request_keywords_in_header(
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
    def __parse_request_keywords_in_path(where: dict, key: str, dtype: str, cid: int = 0) -> str:
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
    def __parse_request_keywords_in_query(
        where: dict, key: str, required: bool, default, dtype: str
    ) -> str:
        value = where.pop(key, None)
        params = where.get("params")
        value2 = None
        if params:
            value2 = params.get(key)

        if value and value2:
            raise KeyError(f'Duplicate key "{key}" in both keywords and params.')

        if value is None and value2 is None and required and default is None:
            raise KeyError(f'Missing key "{key}" in keywords.')

        if value is None and value2 is None:
            return default
        if value is not None:
            return value
        if value2 is not None:
            return value2

    @staticmethod
    def __parse_request_keywords_in_header(where: dict, key: str, required: bool, dtype: str) -> str:
        value = where.pop(key, None)
        if not required:
            return value
        if value is None:
            raise KeyError(f'Missing key "{key}" in keywords.')
        return value
