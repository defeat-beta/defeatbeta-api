import unittest

from utils.util import load_finance_template
from utils.const import income_statement


class TestUtil(unittest.TestCase):

    def test_load_finance_template(self):
        template = load_finance_template(income_statement)
        print(template)
        self.assertIsNotNone(template)