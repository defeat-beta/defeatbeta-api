import logging
import unittest

from defeatbeta_api.data.treasure import Treasure


class TestTreasure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.treasure = Treasure(http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

    def test_daily_treasure_yield(self):
        result = self.treasure.daily_treasure_yield()
        print(result)
