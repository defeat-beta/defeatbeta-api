from dataclasses import dataclass
from typing import Dict, List

from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_statement import FinanceStatement
from defeatbeta_api.data.finance_value import FinanceValue
from defeatbeta_api.utils.case_insensitive_dict import CaseInsensitiveDict
from defeatbeta_api.utils.util import parse_all_key_titles


@dataclass
class IncomeStatement(FinanceStatement):
    def __init__(self,
                 finance_template: Dict[str, 'FinanceItem'],
                 income_finance_values: Dict[str, List['FinanceValue']]):
        super().__init__()

        self.finance_item_key_titles = CaseInsensitiveDict()
        parse_all_key_titles(list(finance_template.values()), self.finance_item_key_titles)
        self.finance_template: Dict[str, 'FinanceItem'] = dict(finance_template)
        self.finance_values: Dict[str, List['FinanceValue']] = {}
        self.date: List[str] = []

        for key, values in income_finance_values.items():
            title = self.finance_item_key_titles.get(key.lower())
            if title:
                self.finance_values[title] = values

        report_dates = set()
        for values in income_finance_values.values():
            for value in values:
                if not value:
                    continue
                period = value.get_period_type()
                report_dates.add("TTM" if period == "TTM" else value.get_report_date())

        sorted_dates = []
        if "TTM" in report_dates:
            sorted_dates.append("TTM")
            report_dates.remove("TTM")

        sorted_dates.extend(sorted(report_dates, reverse=True))
        self.date = sorted_dates

    def get_date(self) -> List[str]:
        return self.date

    def get_finance_template(self) -> Dict[str, 'FinanceItem']:
        return self.finance_template

    def get_finance_values(self) -> Dict[str, List['FinanceValue']]:
        return self.finance_values
