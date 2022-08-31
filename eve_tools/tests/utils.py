import os
import socket
import yaml
from asyncio import get_event_loop
from inspect import iscoroutinefunction
from typing import Callable, Coroutine, Union, Optional

from eve_tools import api_cache
from eve_tools.data.cache import make_cache_key
from eve_tools.log import getLogger

logger = getLogger(__name__)


class TestConfig:
    """Configures variables for unittest.

    Some functionalities of this package require certain in-game privileges.
    So users need to specify their characters, among other in-game names or ids,
    to mimic the actual workflow of this package.
    This configuration is necessary when running the test for the first time,
    and stored to local file `testconfig.yml`.

    Example usage:
    >>> import unittest
    >>> from eve_tools.tests import *
    >>> test_config.set(structure_name="a player's structure", cname="a character with docking access to the structure")
    >>> unittest.main()
    ............... (tests start running)
    """

    TESTDIR = os.path.realpath(os.path.dirname(__file__))

    def __init__(self, local_file_name: str = ...):
        if local_file_name is Ellipsis:
            local_file_name = "config.yml"
        self._fname = local_file_name
        self._path = os.path.join(self.TESTDIR, self._fname)
        self.config = {}
        if os.path.exists(self._path) and os.stat(self._path).st_size > 0:
            with open(self._path) as f:
                self.config = yaml.full_load(f)

        if self.config is None:
            self.config = {}

    def __call__(self):
        """Gets tests configuration."""
        return self.config

    @property
    def structure_name(self) -> str:
        return self.config.get("structure_name")

    @property
    def cname(self) -> str:
        return self.config.get("cname")

    @structure_name.setter
    def structure_name(self, _s: str):
        self.config["structure_name"] = _s

    @cname.setter
    def cname(self, _c: str):
        self.config["cname"] = _c

    @property
    def configured(self) -> bool:
        return self.structure_name is not None and self.cname is not None

    def set(self, structure_name: Optional[str] = None, cname: Optional[str] = None):
        """Sets configuration for testing.

        Sets variables needed for running unittest,
        and instantly writes to local `config.yml` file.
        Configuration does not check if the character has docking access to structure or not.

        Args:
            structure_name: str
                A structure that fits the following condition:
                    1. Has a valid market (has buy/sell orders)
                    2. Your character has docking and market access to the structure
                Structure name should be in precise string with no abbreviation:
                "4-HWWF - WinterCo. Central Station" instead of "4-H Keepstar".
            cname: str
                A character that has docking and market access to the structure you entered.
        """
        _d = {}
        if structure_name is not None:
            self.structure_name = structure_name
            _d["structure_name"] = structure_name
        if cname is not None:
            self.cname = cname
            _d["cname"] = cname
        logger.info("Test configuration set: %s", str(_d))
        self.__check_config()
        self.__save_config()

    def update(self, **d):
        """Updates test configuration both locally and for the instance."""
        self.config.update(d)
        logger.info("Test configuration updated: %s", str(d))
        self.__check_config()
        self.__save_config()

    def __save_config(self):
        with open(self._path, "w") as _f:
            yaml.dump(self.config, _f)
            logger.info("Test configuration saved to %s", self._path)

    def __check_config(self):
        """Some simple checks for config variables.
        Does not check for the content of variables (e.g. not checking if "random name" is a valid character name).
        """
        if not isinstance(self.structure_name, str):
            raise ValueError(
                f"Incorrect type given for param 'structure_name': expect str, got {type(self.structure_name)}"
            )
        if not isinstance(self.cname, str):
            raise ValueError(
                f"Incorrect type given for param 'cname': expect str, got {type(self.cname)}"
            )


test_config = TestConfig()  # user is expected to use test_config instance


class TestInit:
    """Init testing with necessary global config info."""

    TESTDIR = os.path.realpath(os.path.dirname(__file__))

    config = test_config


def request_from_ESI(esi_func: Union[Callable, Coroutine], *args, **kwd):
    """Enforce a function not to use cache.

    Args:
        esi_func: Callable | Coroutine
            An ESI API defined under eve_tools.api, or a coroutine from other eve_tools modules.
        kwd.cache: BaseCache
            Cache used to check esi_func.
    """
    cache = kwd.pop("cache", api_cache)
    key = make_cache_key(esi_func, *args, **kwd)
    cache.evict(key)
    if iscoroutinefunction(esi_func):
        loop = get_event_loop()
        resp = loop.run_until_complete(esi_func(*args, **kwd))
    elif callable(esi_func):
        resp = esi_func(*args, **kwd)
    else:
        raise NotImplemented
    return resp


def internet_on() -> bool:
    """Has internet connection or not.

    Uses Google's public DNS server with port 53/tcp to check connectivity.
    With a good internet connection, this method takes milliseconds to complete.
    If internet is not connected, some tests will be skipped.

    Retrieved from: https://stackoverflow.com/a/33117579/18191767
    """
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except socket.error as ex:
        logger.warning(ex)  # tests should run regardless of connectivity
        return False
