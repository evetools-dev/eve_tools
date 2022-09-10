import re
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from eve_tools.ESI.esi import ESIResponse


class ESIFormatter:

    def __call__(self, key: str, resp: "ESIResponse") -> "ESIResponse":
        format_func_name = self.__format_key(key)
        formatter = getattr(self, format_func_name, None)

        if formatter is None:
            return resp
        
        return formatter(resp)

    def markets_region_id_history(self, resp: "ESIResponse") -> "ESIResponse":
        return resp

    @staticmethod
    def __format_key(key: str):
        return "_".join(re.split("\W+", key.strip("/")))