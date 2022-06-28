import os
import yaml

from eve_tools import search_id, search_structure_id


class TestInit:
    """Init testing with necessary global config info."""

    TESTDIR = os.path.realpath(os.path.dirname(__file__))

    with open(os.path.join(TESTDIR, "testconfig.yaml")) as f:
        global_config = yaml.full_load(f).get("test_config")

    cname = global_config.get("cname")
    structure_name = global_config.get("structure_name")

    cid = search_id(cname, "character")
    sid = search_structure_id(structure_name, cname)
