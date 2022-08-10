import asyncio
from inspect import iscoroutinefunction
import os
import yaml
from typing import Callable, Coroutine, Union

from eve_tools import api_cache
from eve_tools.data.cache import make_cache_key


class TestInit:
    """Init testing with necessary global config info."""

    TESTDIR = os.path.realpath(os.path.dirname(__file__))

    with open(os.path.join(TESTDIR, "testconfig.yaml")) as f:
        global_config = yaml.full_load(f).get("test_config")

    cname = global_config.get("cname")
    structure_name = global_config.get("structure_name")


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
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(esi_func(*args, **kwd))
    elif callable(esi_func):
        resp = esi_func(*args, **kwd)
    else:
        raise NotImplemented
    return resp
