from typing import List, Optional
from decimal import Decimal

import pandas as pd

from data.finance_item import FinanceItem
from data.finance_value import FinanceValue
from data.statement import Statement
from data.statement_visitor import StatementVisitor
from utils.util import load_item_dictionary

class PrintVisitor(StatementVisitor):
    def __init__(self, info : pd.DataFrame):
        self.info = info
        self.finance_item_describe = load_item_dictionary()
        self.table_data = []
        self.headers = []
        self.parent_index = []
        self.data = pd.DataFrame()

    def visit_title(self, fields: List[str]) -> None:
        self.headers = fields
        self.data = pd.DataFrame(columns=fields)

    def visit_row(self,
                  parent_item: Optional[FinanceItem],
                  item: FinanceItem,
                  values: Optional[List[FinanceValue]],
                  layer: int,
                  has_children: bool) -> None:
        if values is None or (parent_item is not None and parent_item not in self.parent_index):
            return

        if (self.info['industry'].iloc[0] is not None and
                self.info['industry'].iloc[0].startswith("Banks")):
            if ((item.get_title() in ["OPERATING_REVENUE", "SPECIAL_INCOME_CHARGES",
                                      "NET_INTEREST_INCOME", "INTEREST_INCOME",
                                      "INTEREST_EXPENSE"]) and not item.is_bank()):
                return
            if (item.is_insurance() and
                    item.get_title() in ["DEFERRED_ASSETS", "DEFERRED_TAX_ASSETS",
                                         "CASH_AND_CASH_EQUIVALENTS"]):
                return

        elif (self.info['industry'].iloc[0] is not None and
              self.info['industry'].iloc[0].startswith("Insurance")):
            if (item.is_bank() and
                    item.get_title() in ["DEFERRED_ASSETS", "DEFERRED_TAX_ASSETS"]):
                return
        else:
            if item.is_bank() or item.is_insurance():
                return

        if item.is_bank() or item.is_insurance():
            if (("CURRENT_ASSETS" in self.parent_index and
                 "TOTAL_NON_CURRENT_ASSETS" in self.parent_index) or
                    ("CURRENT_LIABILITIES" in self.parent_index and
                     "TOTAL_NON_CURRENT_LIABILITIES_NET_MINORITY_INTEREST" in self.parent_index)):
                return

        prefix = " " * layer + ("+" if has_children else "")
        item_desc = self.finance_item_describe.get(item.get_title(), item.get_title())

        row_data = [prefix + item_desc]
        frame = [item_desc]

        for v in values:
            if v is None:
                row_data.append("*")
                frame.append("*")
            else:
                report_value = v.get_report_value()
                if report_value is None:
                    row_data.append("*")
                    frame.append("*")
                else:
                    if report_value == Decimal(int(report_value)):
                        val = int(report_value)
                        if -1000 <= val <= 1000:
                            row_data.append(str(val))
                            frame.append(str(val))
                        else:
                            row_data.append(f"{val // 1000:,}")
                            frame.append(f"{val // 1000:,}")
                    else:
                        row_data.append(str(report_value))
                        frame.append(str(report_value))

        if has_children:
            self.parent_index.append(item)
        self.table_data.append(row_data)
        self.data.loc[len(self.data)] = frame

    def get_statement(self) -> Statement:
        statement = Statement(self.data, self._get_table_string())
        return statement

    def _get_table_string(self) -> str:
        col_widths = [
            max(len(str(cell)) for cell in col)
            for col in zip(*self.table_data, self.headers)
        ]


        separator = "|-" + "-+-".join("-" * w for w in col_widths) + "-|"
        lines = [separator]

        header = "| " + " | ".join(f"{h:^{w}}" for h, w in zip(self.headers, col_widths)) + " |"
        lines.append(header)
        lines.append(separator)

        for row in self.table_data:
            line = "| " + " | ".join(f"{str(cell):<{w}}" for cell, w in zip(row, col_widths)) + " |"
            lines.append(line)

        lines.append(separator)
        return "\n".join(lines)