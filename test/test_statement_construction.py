"""Keep bulk statement construction identical to the former row-by-row code."""

from decimal import Decimal
import random
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from defeatbeta_api.data.company_meta import CompanyMeta
from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_value import FinanceValue
from defeatbeta_api.data.print_visitor import PrintVisitor
from defeatbeta_api.data.stock_statement import StockStatement
from defeatbeta_api.data.ticker import Ticker


def legacy_frame(headers, rows):
    """The former visitor appended each row to the DataFrame with .loc."""
    frame = pd.DataFrame(columns=headers)
    for row in rows:
        frame.loc[len(frame)] = row
    return frame


def legacy_statements(df):
    statements = []
    for _, row in df.iterrows():
        item_value = Decimal(str(row['item_value'])) if not pd.isna(row['item_value']) else None
        statements.append(StockStatement(
            symbol=str(row['symbol']), report_date=str(row['report_date']),
            item_name=str(row['item_name']), item_value=item_value,
            finance_type=str(row['finance_type']), period_type=str(row['period_type'])))
    return statements


def visit(rows, headers):
    visitor = PrintVisitor()
    visitor.finance_item_describe = {}
    visitor.visit_title(headers)
    for title, values in rows:
        item = FinanceItem(title, title, [], False, None, None)
        values = [None if value is None else FinanceValue(title, header, value, "3M")
                  for value, header in zip(values, headers[1:])]
        visitor.visit_row(None, item, values, 0, False)
    return visitor


class TestStatementConstruction(unittest.TestCase):
    headers = ["Breakdown", "TTM", "2024-12-31", "2023-12-31"]

    def assert_matches_legacy(self, rows):
        visitor = visit(rows, self.headers)
        expected = legacy_frame(self.headers, [
            [title] + ["*" if value is None else value for value in values] for title, values in rows])
        statement = visitor.get_statement()
        assert_frame_equal(statement.data, expected, check_exact=True, check_index_type=True)
        return statement

    def test_mixed_missing_and_empty_statements_match_row_appends(self):
        cases = {
            "numbers_first": [("Revenue", [Decimal("1200"), None, Decimal("-5")]),
                              ("Cost", [None, None, None])],
            "missing_first": [("Revenue", [None, None, None]),
                              ("Cost", [Decimal("2.5"), None, Decimal("3000000")])],
            "all_missing": [("Revenue", [None, None, None]), ("Cost", [None, None, None])],
            "single": [("Revenue", [Decimal("1"), Decimal("2"), Decimal("3")])],
            "empty": [],
        }
        for name, rows in cases.items():
            with self.subTest(name=name):
                self.assert_matches_legacy(rows)

    def test_random_statements_match_row_appends(self):
        generator = random.Random(209)
        for _ in range(200):
            rows = [(f"Item {index}",
                     [None if generator.random() < 0.4 else Decimal(generator.randint(-10**7, 10**7)) / 100
                      for _ in self.headers[1:]])
                    for index in range(generator.randint(0, 8))]
            self.assert_matches_legacy(rows)

    def test_printed_table_and_row_metadata_are_unchanged(self):
        statement = self.assert_matches_legacy([("Revenue", [Decimal("1200000"), None, Decimal("12")])])
        self.assertIn("1,200", statement.table)
        self.assertIn("| Revenue", statement.table)
        self.assertEqual(statement.row_meta, [{"indent": 0, "is_section": False}])

    def test_stock_statements_match_row_iteration(self):
        frame = pd.DataFrame({
            "symbol": pd.Series(["AAPL", "AAPL", "AAPL"], dtype="str"),
            "report_date": pd.Series(["TTM", "2024-09-30", "2023-09-30"], dtype="str"),
            "item_name": pd.Series(["revenue", "net_income", "eps"], dtype="str"),
            "item_value": [391035000000.0, np.nan, 6.08],
            "finance_type": pd.Series(["income_statement"] * 3, dtype="str"),
            "period_type": pd.Series(["annual"] * 3, dtype="str"),
        })
        for name, df in {"strings": frame,
                         "datetime": frame.iloc[1:].assign(report_date=lambda f: pd.to_datetime(f.report_date)),
                         "empty": frame.iloc[0:0]}.items():
            with self.subTest(name=name):
                self.assertEqual([vars(s) for s in Ticker._dataframe_to_stock_statements(df)],
                                 [vars(s) for s in legacy_statements(df)])

    def test_currency_map_keeps_missing_values(self):
        for dtype in ("str", object):
            with self.subTest(dtype=dtype):
                meta = CompanyMeta.__new__(CompanyMeta)
                frame = pd.DataFrame({"symbol": pd.Series(["A", "B"], dtype=dtype),
                                      "financial_currency": pd.Series(["USD", None], dtype=dtype)})
                meta._get_all_companies = lambda frame=frame: frame
                expected = dict(zip(frame["symbol"], frame["financial_currency"]))
                actual = meta.get_financial_currency_map()
                self.assertEqual(list(actual), list(expected))
                self.assertEqual(actual["A"], "USD")
                self.assertIs(type(actual["B"]), type(expected["B"]))
                self.assertTrue(pd.isna(actual["B"]))


if __name__ == "__main__":
    unittest.main()
