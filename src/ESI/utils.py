import copy
import logging
from aiohttp import ClientResponseError
from functools import wraps
from typing import Coroutine, Optional


class ESIRequestError:
    """A decorator that handles errors in ESI requests.

    Currently, this decorator only retries ESI requests upon error. 
    In the future, different errors will be detected and handled differently.
    For example, a 400 error (bad request) should not be repeated, while a 502 (bad gateway) could be repeated.
    It should be assumed that this decorator does not change behavior of async_request() method.

    Attributes:
        attempts: Number of attempts, default 3.
        raises: Raises ClientResponseError or not. Default True, raising errors when no attempts left.
            If set to False, a None is returned.
    """

    def __init__(
        self,
        attempts: Optional[int] = 3,
        raises: Optional[bool] = True,
    ):
        self.attempts = attempts
        self.raises = raises

    def wrapper_retry(self, func: Coroutine):
        @wraps(func)
        async def wrapped_retry(_caller_self, *args, **kwd):
            """Retry ESI request upon error.
            
            ESI's async_request has signature (self, ESIRequest, method), so a _caller_self arg is added."""
            _args = copy.deepcopy(args)
            _kwd = copy.deepcopy(kwd)

            attempts = self.attempts

            success = False
            ret = None
            while not success and attempts > 0:
                try:
                    ret = await func(_caller_self, *_args, **_kwd)
                    success = True
                except ClientResponseError as exc:
                    logging.warning("%s | attempts left: %s", exc, self.attempts)
                    attempts -= 1
                    if attempts == 0 and self.raises:
                        raise
            return ret

        return wrapped_retry

    def __call__(self, func):

        return self.wrapper_retry(func)
