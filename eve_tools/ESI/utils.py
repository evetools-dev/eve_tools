import copy
import time
from aiohttp.client_exceptions import ServerDisconnectedError
from asyncio.exceptions import TimeoutError
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate
from functools import wraps
from inspect import iscoroutinefunction
from typing import Callable, Coroutine, List, Optional, Union, TYPE_CHECKING

from eve_tools.data import make_cache_key
from eve_tools.exceptions import ESIResponseError
from eve_tools.log import getLogger

if TYPE_CHECKING:
    from eve_tools.ESI import ESIRequestChecker

logger = getLogger(__name__)

BAD_REQUEST = 400
NOT_FOUND = 404
ERROR_LIMITED = 420
STATUS_RAISE = (BAD_REQUEST, NOT_FOUND, ERROR_LIMITED, )

ERROR_CATCHED = (
    TimeoutError,
    ServerDisconnectedError,
)  # ESIResponseError not raise in _session_recorder


class ESIRequestError:
    """A decorator that handles errors in ESI requests.

    This decorator retries ESI requests conditionally on error.
    Some response status codes, such as 400, 404, 420, etc., that are not ESI's error, are not repeated.
    ESI response headers has an x-error-limit field, which triggers an ERROR_LIMITED error when reaching 0.

    Attributes:
        attempts: Number of attempts, default 3.
        raises: Raises errors or not. Default None, not raising errors when no attempts left.
            If set to False, a None is returned. See ESI.get for more details.
    """

    _global_error_remain = [100]

    def __init__(
        self,
        attempts: Optional[int] = 3,
        raises: Optional[bool] = None,
    ):
        self.attempts = attempts
        self.raises = raises

    def wrapper_retry(self, func: Coroutine):
        # This func is ESI.async_request wrapped by _session_recorder()
        @wraps(func)
        async def wrapped_retry(_esi_self, *args, **kwd):
            """Retry ESI request upon error.

            ESI's async_request has signature (self, ESIRequest, method), so a _esi_self arg is added."""

            # Can't use something like _caller_self = _args.pop(0),
            # because deepcopy can't copy ESI.self.
            _args = copy.deepcopy(args)
            _kwd = copy.deepcopy(kwd)

            attempts = self.attempts

            success = False
            ret = None
            error = None
            while not success and attempts > 0:
                try:
                    ret = await func(_esi_self, *_args, **_kwd)  # ESIResponse instance
                    success = ret is not None and ret.status < 400
                    if ret is None:
                        attempts = 0  # ret = None when request is blocked
                    else:
                        self._global_error_remain[0] = ret.error_remain
                        ret.raise_for_status()
                except ESIResponseError as exc:
                    attempts -= 1
                    resp_code = exc.status
                    if resp_code in STATUS_RAISE:
                        attempts = 0
                        self.__log_error(exc, attempts)
                    else:
                        self.__log_warning(exc, attempts)

                    self._global_error_remain[0] -= 1
                    error = exc
                except TimeoutError as exc:  # asyncio.exceptions.TimeoutError has empty exc
                    attempts = 0
                    logger.error("FAILED: asyncio.exceptions.TimeoutError")
                    error = exc
                    if self.raises is None:
                        raise
                except ServerDisconnectedError as exc:
                    attempts -= 1
                    error = exc
                    if attempts == 0 and self.raises is None:
                        self.__log_error(exc, attempts)
                        raise
                    else:
                        self.__log_warning(exc, attempts)

                # raise or return None | ESIResponse
                if attempts == 0:
                    if self.raises is True:
                        raise error from None
                    if self.raises is False:
                        return None
                    if self.raises is None:
                        # Why 5?
                        # If set to 0, ESI will always give 420 error, not being informative.
                        if self._global_error_remain[0] <= 5:
                            raise
                        else:
                            return ret
            return ret

        return wrapped_retry

    def __call__(self, func):

        return self.wrapper_retry(func)

    @staticmethod
    def __log_warning(exc, attempts: int):
        logger.warning("FAILED: %s | attempts left: %s", exc, attempts)

    @staticmethod
    def __log_error(exc, attempts: int):
        logger.error("FAILED: %s | attempts left: %s", exc, attempts)


@dataclass
class _SessionRecord:
    """Stores useful info from ESI.request family.

    Attributes:
        requests: Optional[int]
            Number of requests made. Increments each time ESI.async_request is called.
        timer: Optional[float]
            Time used for a request. Only functional for synchronous requests, such as ESI.get().
        expires: Optional[str]
            API cache uses this to know how long the response expires.
        requests_failed: Optional[int]
            Number of failed requests made. Increments when ClientResponseError is raised.
        requests_succeed: Optional[int]
            Number of successful requests made. Increments when ClientResponseError not raised.
        requests_blocked: Optional[int]
            Number of blocked requests made. Increments when ESI._check_request() blocks a request.
    """

    requests: Optional[int] = 0
    timer: Optional[float] = 0.0
    expires: Optional[str] = None
    requests_failed: Optional[int] = 0
    requests_succeed: Optional[int] = 0
    requests_blocked: Optional[int] = 0

    def clear(self, field: Optional[str] = None):
        if field is None:
            self.expires = None
            self.requests = 0
            self.timer = 0.0
            self.requests_failed = 0
            self.requests_succeed = 0
            self.requests_blocked = 0
        elif field == "expires":
            self.expires = None
        elif field == "requests":
            self.requests = 0
            self.requests_failed = 0
            self.requests_succeed = 0
            self.requests_blocked = 0
        elif field == "timer":
            self.timer = 0.0

    def __bool__(self) -> bool:
        """True if class is not cleared."""
        return self.expires is not None or self.requests > 0 or self.timer > 0.0

    def __eq__(self, __other: object) -> bool:
        if isinstance(__other, _SessionRecord):
            return (
                self.expires == __other.expires
                and self.requests == __other.requests
                and self.timer == __other.timer
                and self.requests_failed == __other.requests_failed
                and self.requests_succeed == __other.requests_succeed
                and self.requests_blocked == __other.requests_blocked
            )

        raise NotImplemented


def _session_recorder(
    func: Union[Coroutine, Callable] = None,
    fields: Optional[Union[str, List]] = None,
    exclude: Optional[Union[str, List]] = None,
):
    """Records useful info from ESIResponse.

    Decorates ESI.request family to record useful stats along making requests.
    """

    def _session_recorder_wrapper(func: Union[Coroutine, Callable]):
        # func is ESI.async_request or ESI.get/head
        @wraps(func)
        async def _session_recorder_wrapped_async(_self, *args, **kwd):
            # Used when a coroutine function is decorated.
            if not _self._record_session:
                return await func(_self, *args, **kwd)

            resp = None
            time_start = time.monotonic_ns()
            try:
                resp = await func(_self, *args, **kwd)  # _self: ESI
                # Currently this async version is only used by ESI.async_request,
                # which returns an ESIResponse if request sent,
                # or returns a None if request blocked.
                if resp is not None:
                    resp.raise_for_status()
            except ERROR_CATCHED:
                time_finish = time.monotonic_ns()
                _session_record_fill(_self, resp, time_start, time_finish, failed=True)
                raise  # ESIRequestError catches this
            except ESIResponseError:
                time_finish = time.monotonic_ns()
                _session_record_fill(_self, resp, time_start, time_finish, failed=True)
            else:
                time_finish = time.monotonic_ns()
                blocked = resp is None or resp.request_info.blocked
                _session_record_fill(_self, resp, time_start, time_finish, failed=False, blocked=blocked)

            return resp

        @wraps(func)
        def _session_recorder_wrapped_normal(_self, *args, **kwd):
            # Used when a normal callable function is decorated.
            if not _self._record_session:
                return func(_self, *args, **kwd)

            resp = None
            time_start = time.monotonic_ns()
            try:
                resp = func(_self, *args, **kwd)  # _self: ESI
            except ERROR_CATCHED:
                time_finish = time.monotonic_ns()
                _session_record_fill(_self, resp, time_start, time_finish, failed=True)
                raise  # ESIRequestError catches this
            else:
                time_finish = time.monotonic_ns()
                _session_record_fill(_self, resp, time_start, time_finish, failed=False)

            return resp

        def _session_record_fill(_self, resp, t_s, t_f, failed: bool, blocked: bool = False):
            """Fills out useful info of from the response.
            Defines rules to fill out a _SessionRecord instance."""
            nonlocal fields, exclude
            if isinstance(fields, str):
                fields = [fields]
            if isinstance(exclude, str):
                exclude = [exclude]
            if fields is not None and exclude is not None:
                for field in fields:
                    if field in exclude:
                        raise ValueError(f"{field} should not exist in both fields and exclude.")

            record: _SessionRecord = _self._record

            # Update requests
            if (fields is None or "requests" in fields) and (exclude is None or "requests" not in exclude):
                record.requests += 1

                # Update requests_blocked
                if resp is None and not failed or blocked:
                    record.requests_blocked += 1

                # Update requests_failed
                if failed:
                    record.requests_failed += 1

                # Update requests_succeed
                if resp is not None and not failed and not blocked:
                    record.requests_succeed += 1

            # Update timer
            if (fields is None or "timer" in fields) and (exclude is None or "timer" not in exclude):
                record.timer = round(record.timer + (t_f - t_s) / 1e9, 3)

            # Update expires: keep the earliest expire
            if (fields is None or "expires" in fields) and (exclude is None or "expires" not in exclude):
                if resp is not None and resp.expires:
                    if record.expires is None:
                        record.expires = resp.expires
                    else:
                        expires_dt = datetime(*parsedate(resp.expires)[:6])
                        record_dt = datetime(*parsedate(record.expires)[:6])
                        if expires_dt < record_dt:
                            record.expires = resp.expires

            return

        if iscoroutinefunction(func):
            return _session_recorder_wrapped_async
        else:
            return _session_recorder_wrapped_normal

    if func is None:
        return _session_recorder_wrapper

    if iscoroutinefunction(func) or callable(func):
        return _session_recorder_wrapper(func)

    raise NotImplementedError


def cache_check_request(func: Coroutine):
    # func has signature: async def _check_*(self, *) -> boolh
    @wraps(func)
    async def cache_check_request_wrapped(_self: "ESIRequestChecker", *args, **kwd):
        # Caches _RequestChecker methods
        key = make_cache_key(func, *args, **kwd)
        value = _self.cache.get(key)
        if value is not None:  # cache hit
            return value

        ret = await func(_self, *args, **kwd)  # exec

        expires = 24 * 3600 * 30  # one month
        _self.cache.set(key, ret, expires)
        return ret

    return cache_check_request_wrapped
