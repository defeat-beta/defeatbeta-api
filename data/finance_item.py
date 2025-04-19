from typing import List, Optional
from dataclasses import dataclass

@dataclass
class FinanceItem:
    key: str
    title: str
    children: List['FinanceItem']
    spec: str
    ref: str
    industry: Optional[str]

    def children_is_empty(self) -> bool:
        return not self.children

    def is_bank(self) -> bool:
        return self.industry and self.industry.lower() == "bank"

    def is_insurance(self) -> bool:
        return self.industry and self.industry.lower() == "insurance"