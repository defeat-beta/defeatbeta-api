from decimal import Decimal
from dataclasses import dataclass
from typing import Optional


@dataclass
class FinanceValue:
    finance_key: str
    report_date: str
    report_value: Optional[Decimal]
    period_type: str

    def get_period_type(self):
        return self.period_type

    def get_report_date(self):
        return self.report_date

    def get_report_value(self):
        return self.report_value
