from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass
class Param:
    """Hold a Param for an API

    Attributes:
        name: A str for the name of the param. E.g. "character_id"
        _in: A str for the occurance of the param. One of ["path", "query", "header"]
        required: A bool for requirement.
        dtype: A str for data type of the param.
        default: Default value for the Param.
    """

    name: str  # characther_id
    _in: str  # "path" / "query" / "header" / "body"
    required: bool
    dtype: type  # "string" / "integer" / "array" / "boolean" / "" (schema)
    default: Optional[Any] = None


@dataclass
class ESIParams:
    """A list like datastructure of Param(s).

    Attributes:
        params: A list of Param instance.
    """

    # list of ESI pre-defined meta parameters, initialized at the start
    # Param.name: #/parameters/{actual_name}
    params: List[Param]

    def append(self, param: Param) -> None:
        """Append a Param similar to list append.
        No value checking. Used for testing.
        """
        self.params.append(param)

    def __getitem__(self, name: str) -> Param:
        """Returns a reference of Param with name.
        If no Param with name found, return None
        """
        for p in self.params:
            if p.name == name:
                return p

        return None

    def __iter__(self):
        yield from self.params
