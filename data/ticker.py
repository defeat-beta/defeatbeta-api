import logging
from collections import defaultdict
from decimal import Decimal
from typing import Optional, List, Dict

import pandas as pd

from client.duckdb_client import DuckDBClient
from client.duckdb_conf import Configuration
from client.hugging_face_client import HuggingFaceClient
from data import statement
from data.balance_sheet import BalanceSheet
from data.finance_item import FinanceItem
from data.finance_value import FinanceValue
from data.income_statement import IncomeStatement
from data.print_visitor import PrintVisitor
from data.statement import Statement
from data.stock_statement import StockStatement
from utils.case_insensitive_dict import CaseInsensitiveDict
from utils.const import stock_profile, stock_earning_calendar, stock_historical_eps, stock_officers, stock_split_events, \
    stock_dividend_events, stock_revenue_estimates, stock_earning_estimates, stock_summary, stock_tailing_eps, \
    stock_prices, stock_statement, income_statement, balance_sheet, cash_flow, quarterly, annual
from utils.util import load_finance_template, parse_all_title_keys


class Ticker:
    def __init__(self, ticker, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.ticker = ticker.upper()
        self.http_proxy = http_proxy
        self.duckdb_client = DuckDBClient(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()

    def info(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_profile)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def officers(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_officers)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def calendar(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_earning_calendar)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def earnings(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_historical_eps)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def splits(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_split_events)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def dividends(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_dividend_events)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def revenue_forecast(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_revenue_estimates)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def earnings_forecast(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_earning_estimates)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def summary(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_summary)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def ttm_eps(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_tailing_eps)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def price(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_prices)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def quarterly_income_statement(self) -> statement:
        return self._statement(income_statement, quarterly)

    def annual_income_statement(self) -> statement:
        return self._statement(income_statement, annual)

    def quarterly_balance_sheet(self) -> statement:
        return self._statement(balance_sheet, quarterly)

    def annual_balance_sheet(self) -> statement:
        return self._statement(balance_sheet, annual)

    def quarterly_cash_flow(self) -> statement:
        return self._statement(cash_flow, quarterly)

    def annual_cash_flow(self) -> statement:
        return self._statement(cash_flow, annual)

    def _statement(self, finance_type: str, period_type: str) -> Statement:
        info = self.info()
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}' and finance_type = '{finance_type}' and period_type = '{period_type}'"
        df = self.duckdb_client.query(sql)
        stock_statements = self._dataframe_to_stock_statements(df=df)
        if finance_type == income_statement:
            template = load_finance_template(income_statement)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = IncomeStatement(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor(info)
            stmt.accept(printer)
            return printer.get_statement()
        elif finance_type == balance_sheet:
            template = load_finance_template(balance_sheet)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = BalanceSheet(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor(info)
            stmt.accept(printer)
            return printer.get_statement()
        elif finance_type == cash_flow:
            template = load_finance_template(cash_flow)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = BalanceSheet(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor(info)
            stmt.accept(printer)
            return printer.get_statement()
        else:
            raise ValueError(f"unknown finance type: {finance_type}")

    @staticmethod
    def _dataframe_to_stock_statements(df: pd.DataFrame) -> List[StockStatement]:
        statements = []

        for _, row in df.iterrows():
            try:
                item_value = Decimal(str(row['item_value'])) if not pd.isna(row['item_value']) else None
                statement = StockStatement(
                    symbol=str(row['symbol']),
                    report_date=str(row['report_date']),
                    item_name=str(row['item_name']),
                    item_value=item_value,
                    finance_type=str(row['finance_type']),
                    period_type=str(row['period_type'])
                )
                statements.append(statement)
            except Exception as e:
                print(f"Error processing row {row}: {str(e)}")
                continue

        return statements

    @staticmethod
    def _get_finance_values_map(statements: List['StockStatement'],
                                finance_template: Dict[str, 'FinanceItem']) -> Dict[str, List['FinanceValue']]:
        finance_item_title_keys = CaseInsensitiveDict()
        parse_all_title_keys(list(finance_template.values()), finance_item_title_keys)

        finance_values = defaultdict(list)

        for statement in statements:
            period = "TTM" if statement.report_date == "TTM" else (
                "3M" if statement.period_type == "quarterly" else "12M")
            value = FinanceValue(
                finance_key=statement.item_name,
                report_date=statement.report_date,
                report_value=statement.item_value,
                period_type=period
            )
            finance_values[statement.item_name].append(value)

        final_map = CaseInsensitiveDict()

        for title, values in finance_values.items():
            key = finance_item_title_keys.get(title)
            if key is not None:
                final_map[key] = values

        return final_map

    def download_data_performance(self) -> str:
        res = f"-------------- Download Data Performance ---------------"
        res += f"\n"
        res += self.duckdb_client.query(
            "SELECT * FROM cache_httpfs_cache_access_info_query()"
        ).to_string()
        res += f"\n"
        res += f"--------------------------------------------------------"
        return res

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duckdb_client.close()

    def __del__(self):
        self.duckdb_client.close()
