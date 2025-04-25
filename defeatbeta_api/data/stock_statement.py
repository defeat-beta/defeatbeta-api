from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class StockStatement:
    symbol: str
    report_date: str
    item_name: str
    item_value: Optional[Decimal]
    finance_type: str
    period_type: str
