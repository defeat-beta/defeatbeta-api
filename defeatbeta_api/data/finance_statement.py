from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_value import FinanceValue
from defeatbeta_api.data.statement_visitor import StatementVisitor


def _find_finance_value_by_date(values: List['FinanceValue'],
                                target_date: str) -> Optional['FinanceValue']:
    target_date = target_date.upper()

    if target_date == "TTM":
        return next((v for v in values if v and v.get_period_type() == "TTM"), None)
    else:
        return next(
            (v for v in values
             if v and v.get_period_type() != "TTM" and v.get_report_date() == target_date),
            None
        )

@dataclass
class FinanceStatement(ABC):
    @abstractmethod
    def get_date(self) -> List[str]:
        pass

    @abstractmethod
    def get_finance_template(self) -> Dict[str, 'FinanceItem']:
        pass

    @abstractmethod
    def get_finance_values(self) -> Dict[str, List['FinanceValue']]:
        pass

    def accept(self, visitor: 'StatementVisitor') -> None:
        dates = self.get_date()
        fields = ["Breakdown"] + dates
        visitor.visit_title(fields)
        self._visit_row(visitor, None, list(self.get_finance_template().values()), 0)

    def _visit_row(self, visitor: 'StatementVisitor',
                   parent_item: Optional['FinanceItem'],
                   items: List['FinanceItem'],
                   layer: int) -> None:
        for item in items:
            if self._children_is_empty(item):
                row = self._get_row(item)
                visitor.visit_row(parent_item, item, row, layer, False)
            else:
                row = self._get_row(item)
                visitor.visit_row(parent_item, item, row, layer, True)
                self._visit_row(visitor, item, item.get_children(), layer + 1)

    def _get_row(self, item: 'FinanceItem') -> Optional[List['FinanceValue']]:
        dates = self.get_date()
        title = item.get_title()
        values = self.get_finance_values().get(title)

        if not values:
            return None

        ordered_values = []
        for d in dates:
            found = _find_finance_value_by_date(values, d)
            ordered_values.append(found)
        return ordered_values

    def _children_is_empty(self, item):
        for child in item.get_children():
            row = self._get_row(child)
            if row is not None:
                return False
        return True
