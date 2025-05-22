from typing import List, Optional
from dataclasses import dataclass


@dataclass
class FinanceItem:
    key: str
    title: str
    children: List['FinanceItem']
    spec: Optional[str]
    ref: Optional[str]
    industry: Optional[str]

    def children_is_empty(self) -> bool:
        return not self.children

    def get_title(self):
        return self.title

    def get_children(self):
        return self.children

    def get_spec(self):
        return self.spec

    def get_key(self):
        return self.key
