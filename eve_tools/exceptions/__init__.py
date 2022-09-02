from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from eve_tools.ESI.esi import ESIRequest


class InvalidRequestError(Exception):
    """Incorrect request parameters being blocked."""

    def __init__(self, reson: str, value):
        self.reason = reson
        self.value = value
        self.msg = "Request blocked: invalid request parameter {reason}: {value}"

    def __str__(self):
        return self.msg.format(reason=self.reason, value=self.value)


class ESIResponseError(Exception):
    """Connection error during reading response, catch from aiohttp.ClientResponseError.

    request_info: instance of ESIRequest
    """
    def __init__(self, status: int, request_info: "ESIRequest", message: str):
        self.status = status
        self.request_info = request_info
        self.message = message

    def __str__(self) -> str:
        return "{}, message={!r}, url={!r}".format(
            self.status,
            self.message,
            self.request_info.real_url,
        )
