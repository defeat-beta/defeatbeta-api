import unittest

from defeatbeta_api.utils.util import load_finance_template
from defeatbeta_api.utils.const import income_statement


class TestUtil(unittest.TestCase):

    def test_load_finance_template(self):
        template = load_finance_template(income_statement, "default")
        print(template)
        self.assertIsNotNone(template)
        template = load_finance_template(income_statement, "bank")
        print(template)
        self.assertIsNotNone(template)
        template = load_finance_template(income_statement, "insurance")
        print(template)
        self.assertIsNotNone(template)