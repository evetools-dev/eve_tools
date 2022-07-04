import copy
import logging
from aiohttp import ClientResponseError
from functools import wraps
from typing import Coroutine, Optional


BAD_REQUEST = 400
NOT_FOUND = 404
ERROR_LIMITED = 420


class ESIRequestError:
    """A decorator that handles errors in ESI requests.

    This decorator retries ESI request with error code 502 and 503. 
    Other codes, such as 400, 404, 420, etc., that are not ESI's error, are not repeated.
    ESI response headers has an x-error-limit field, which triggers an ERROR_LIMITED error when reaching 0.

    Attributes:
        attempts: Number of attempts, default 3.
        raises: Raises ClientResponseError or not. Default True, raising errors when no attempts left.
            If set to False, a None is returned.
    """

    status_raise = [BAD_REQUEST, NOT_FOUND, ERROR_LIMITED]

    def __init__(
        self,
        attempts: Optional[int] = 3,
        raises: Optional[bool] = True,
    ):
        self.attempts = attempts
        self.raises = raises

    def wrapper_retry(self, func: Coroutine):
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
            while not success and attempts > 0:
                try:
                    ret = await func(_esi_self, *_args, **_kwd)
                    success = True
                except ClientResponseError as exc:
                    attempts -= 1
                    resp_code = exc.status
                    if resp_code in self.status_raise:
                        attempts = 0
                    logging.warning("%s | attempts left: %s", exc, attempts)

                    if self.raises and attempts == 0:
                        raise
            return ret

        return wrapped_retry

    def __call__(self, func):

        return self.wrapper_retry(func)
