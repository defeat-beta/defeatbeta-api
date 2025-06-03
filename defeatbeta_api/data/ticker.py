import logging
from collections import defaultdict
from decimal import Decimal
from typing import Optional, List, Dict

import pandas as pd
import numpy as np

from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data import statement
from defeatbeta_api.data.balance_sheet import BalanceSheet
from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_value import FinanceValue
from defeatbeta_api.data.income_statement import IncomeStatement
from defeatbeta_api.data.print_visitor import PrintVisitor
from defeatbeta_api.data.statement import Statement
from defeatbeta_api.data.stock_statement import StockStatement
from defeatbeta_api.data.transcripts import Transcripts
from defeatbeta_api.utils.case_insensitive_dict import CaseInsensitiveDict
from defeatbeta_api.utils.const import stock_profile, stock_earning_calendar, stock_historical_eps, stock_officers, \
    stock_split_events, \
    stock_dividend_events, stock_revenue_estimates, stock_earning_estimates, stock_summary, stock_tailing_eps, \
    stock_prices, stock_statement, income_statement, balance_sheet, cash_flow, quarterly, annual, \
    stock_earning_call_transcripts
from defeatbeta_api.utils.util import load_finance_template, parse_all_title_keys, income_statement_template_type, \
    balance_sheet_template_type, cash_flow_template_type


class Ticker:
    def __init__(self, ticker, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.ticker = ticker.upper()
        self.http_proxy = http_proxy
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()

    def info(self) -> pd.DataFrame:
        return self._query_data(stock_profile)

    def officers(self) -> pd.DataFrame:
        return self._query_data(stock_officers)

    def calendar(self) -> pd.DataFrame:
        return self._query_data(stock_earning_calendar)

    def earnings(self) -> pd.DataFrame:
        return self._query_data(stock_historical_eps)

    def splits(self) -> pd.DataFrame:
        return self._query_data(stock_split_events)

    def dividends(self) -> pd.DataFrame:
        return self._query_data(stock_dividend_events)

    def revenue_forecast(self) -> pd.DataFrame:
        return self._query_data(stock_revenue_estimates)

    def earnings_forecast(self) -> pd.DataFrame:
        return self._query_data(stock_earning_estimates)

    def summary(self) -> pd.DataFrame:
        return self._query_data(stock_summary)

    def ttm_eps(self) -> pd.DataFrame:
        return self._query_data(stock_tailing_eps)

    def price(self) -> pd.DataFrame:
        return self._query_data(stock_prices)

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

    def ttm_pe(self) -> pd.DataFrame:
        price_url = self.huggingface_client.get_url_path(stock_prices)
        price_sql = f"SELECT * FROM '{price_url}' WHERE symbol = '{self.ticker}'"
        price_df = self.duckdb_client.query(price_sql)
        eps_url = self.huggingface_client.get_url_path(stock_tailing_eps)
        eps_sql = f"SELECT * FROM '{eps_url}' WHERE symbol = '{self.ticker}'"
        eps_df = self.duckdb_client.query(eps_sql)

        price_df['report_date'] = pd.to_datetime(price_df['report_date'])
        eps_df['report_date'] = pd.to_datetime(eps_df['report_date'])
        latest_trade_date = price_df['report_date'].max()
        latest_price_data = price_df[price_df['report_date'] == latest_trade_date].iloc[0]
        pe_data = pd.merge_asof(
            eps_df.sort_values('report_date'),
            price_df.sort_values('report_date'),
            left_on='report_date',
            right_on='report_date',
            direction='forward'
        )
        pe_data['ttm_pe'] = round(pe_data['close'] / pe_data['tailing_eps'], 2)
        pe_data = pe_data[pe_data['ttm_pe'].notna() & np.isfinite(pe_data['ttm_pe'])]
        pe_data = pe_data.sort_values('report_date', ascending=False)
        latest_eps = pe_data.iloc[0]['tailing_eps']
        current_pe = round(latest_price_data['close'] / latest_eps, 2)
        result_data = {
            'report_date': [],
            'ttm_pe': [],
            'price': [],
            'ttm_eps': []
        }

        result_data['report_date'].append(latest_price_data['report_date'].strftime('%Y-%m-%d'))
        result_data['ttm_pe'].append(current_pe)
        result_data['price'].append(latest_price_data['close'])
        result_data['ttm_eps'].append(latest_eps)
        for row in pe_data.itertuples():
            result_data['report_date'].append(row.report_date.strftime('%Y-%m-%d'))
            result_data['ttm_pe'].append(row.ttm_pe)
            result_data['price'].append(row.close)
            result_data['ttm_eps'].append(row.tailing_eps)

        return pd.DataFrame(result_data)

    def quarterly_gross_margin(self) -> pd.DataFrame:
        quarterly_gross_margin_sql = f"""
            SELECT symbol,
                   report_date,
                   gross_profit,
                   total_revenue,
                   round(gross_profit/total_revenue, 2) as gross_margin
            from (
                SELECT
                     symbol,
                     report_date,
                     MAX(CASE WHEN t1.item_name = 'gross_profit' THEN t1.item_value END)                   AS gross_profit,
                     MAX(CASE WHEN t1.item_name = 'total_revenue' THEN t1.item_value END)     AS total_revenue
                  FROM '{self.huggingface_client.get_url_path(stock_statement)}'  t1
                  WHERE symbol = '{self.ticker}'
                    AND report_date != 'TTM'
                    AND item_name IN ('gross_profit', 'total_revenue')
                    AND period_type = 'quarterly'
                  GROUP BY symbol, report_date) t ORDER BY report_date ASC
            """
        return self.duckdb_client.query(quarterly_gross_margin_sql)

    def earning_call_transcripts(self) -> Transcripts:
        return Transcripts(self._query_data(stock_earning_call_transcripts))

    def _query_data(self, table_name: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(table_name)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}'"
        return self.duckdb_client.query(sql)

    def _statement(self, finance_type: str, period_type: str) -> Statement:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}' and finance_type = '{finance_type}' and period_type = '{period_type}'"
        df = self.duckdb_client.query(sql)
        stock_statements = self._dataframe_to_stock_statements(df=df)
        if finance_type == income_statement:
            template_type = income_statement_template_type(df)
            template = load_finance_template(income_statement, template_type)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = IncomeStatement(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor()
            stmt.accept(printer)
            return printer.get_statement()
        elif finance_type == balance_sheet:
            template_type = balance_sheet_template_type(df)
            template = load_finance_template(balance_sheet, template_type)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = BalanceSheet(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor()
            stmt.accept(printer)
            return printer.get_statement()
        elif finance_type == cash_flow:
            template_type = cash_flow_template_type(df)
            template = load_finance_template(cash_flow, template_type)
            finance_values_map = self._get_finance_values_map(statements=stock_statements, finance_template=template)
            stmt = BalanceSheet(finance_template=template, income_finance_values=finance_values_map)
            printer = PrintVisitor()
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