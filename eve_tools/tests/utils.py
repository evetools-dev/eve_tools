from typing import Callable
import os
import yaml

from eve_tools import search_id, search_structure_id
from eve_tools import api_cache
from eve_tools.data.cache import hash_key, make_cache_key


class TestInit:
    """Init testing with necessary global config info."""

    TESTDIR = os.path.realpath(os.path.dirname(__file__))

    with open(os.path.join(TESTDIR, "testconfig.yaml")) as f:
        global_config = yaml.full_load(f).get("test_config")

    cname = global_config.get("cname")
    structure_name = global_config.get("structure_name")

    cid = search_id(cname, "character")
    sid = search_structure_id(structure_name, cname)


def request_from_ESI(esi_api: Callable, *args, **kwd):
    """Enforce request api result from ESI."""
    resp = esi_api(*args, **kwd)
    key = make_cache_key(esi_api, *args, **kwd)
    if api_cache._last_used and api_cache._last_used == hash_key(key):
        # resp returned from cache: evit it
        api_cache.evit(key)
        resp = esi_api(*args, **kwd)  # retrieve from ESI
    return resp
