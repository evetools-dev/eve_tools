from dataclasses import dataclass
from typing import Optional, Union, List, TYPE_CHECKING

from eve_tools.exceptions import ESIResponseError

if TYPE_CHECKING:
    from pandas import DataFrame
    from .metadata import ESIRequest


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
        reason: str | None
            Reason-Phrase from aiohttp.ClientResponse.
        error_remain: int
            Errors the user can make in the time window.
        error_reset: int
            Time window left, in seconds. After this many seconds, error_remain will be refreshed to 100.

    Note:
        ESI class uses status=-1 to mark an error internally. (well this is abnormal but a useful shortcut...)
    """

    status: int
    method: str
    headers: dict
    request_info: "ESIRequest"
    data: Optional[Union[dict, List, int, "DataFrame"]]
    expires: Optional[str] = None
    reason: Optional[str] = None
    error_remain: Optional[int] = 100
    error_reset: Optional[int] = 60

    formatted: Optional[bool] = False  # whether resp goes through ESIFormatter
    stored: Optional[bool] = False  # whether resp goes through ESIDBHandler

    def __len__(self):
        if self.data is None:
            return 0
        return len(self.data)

    def __repr__(self) -> str:
        return f"<Response [{self.status}]>"

    def raise_for_status(self):
        # Please note that this raise_for_status() is only intended for printing out useful exception message.
        # This method does not recreate aiohttp.ClientResponse's raise_for_status().
        if self.status >= 400:
            raise ESIResponseError(self.status, self.request_info, self.reason)

    @property
    def ok(self) -> bool:
        """Returns ``True`` if ``status`` is ``200`` or ``304``, ``False`` if not.

        This is **not** a check for ``200 OK``.
        """
        return self.status == 200 or self.status == 304
