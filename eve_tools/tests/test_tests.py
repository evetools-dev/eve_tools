import os
import unittest
import yaml

from .utils import TestConfig
from eve_tools.log import getLogger

logger = getLogger("test_tests")


class TestUtils(unittest.TestCase):
    local_file_name = "testconfig.yml"
    config_path = os.path.join(TestConfig.TESTDIR, local_file_name)

    def setUp(self) -> None:
        logger.debug("TEST running: %s", self.id())

    def test_config(self):
        """Test TestConfig"""
        config = TestConfig(self.local_file_name)
        self.assertEqual(config._fname, self.local_file_name)

        # Test: __save_config
        _c = TestConfig("testsaveconfig.yml")
        _c._TestConfig__save_config()  # deliberate accessing private method __save_config
        _c_path = os.path.join(TestConfig.TESTDIR, "testsaveconfig.yml")
        self.assertTrue(os.path.exists(_c_path) and os.stat(_c_path).st_size > 0)
        os.remove(_c_path)

        # Test: config.set
        structure_name = "test structure - 123"
        cname = "test character"
        config.set(structure_name, cname)
        self.assertEqual(config.structure_name, structure_name)
        self.assertEqual(config.cname, cname)
        self.assertTrue(
            os.path.exists(self.config_path) and os.stat(self.config_path).st_size > 0
        )

        with open(self.config_path) as f:
            config_content = yaml.full_load(f)  # same load method as TestConfig
        self.assertEqual(config_content, config.config)  # dict == equality works

        # Test: __check_config
        with self.assertRaises(ValueError):
            config.set(123, cname)
        with self.assertRaises(ValueError):
            config.set(structure_name, 123)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.path.exists(cls.config_path):
            os.remove(cls.config_path)
            logger.debug("TEST Test configuration removed: %s", cls.config_path)
