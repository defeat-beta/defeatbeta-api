from abc import ABC, abstractmethod
from typing import List, Optional

from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_value import FinanceValue


class StatementVisitor(ABC):
    @abstractmethod
    def visit_title(self, fields: List[str]) -> None:
        pass

    @abstractmethod
    def visit_row(self,
                  parent_item: Optional['FinanceItem'],
                  item: 'FinanceItem',
                  values: Optional[List['FinanceValue']],
                  layer: int,
                  has_children: bool) -> None:
        pass
