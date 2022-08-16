import os
import unittest
import yaml

from .utils import TestConfig


class TestUtils(unittest.TestCase):
    local_file_name = "testconfig.yml"
    config_path = os.path.join(TestConfig.TESTDIR, local_file_name)

    def test_config(self):
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

    def tearDown(self) -> None:
        if os.path.exists(self.config_path):
            os.remove(self.config_path)
