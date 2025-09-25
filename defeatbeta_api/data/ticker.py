import logging
from collections import defaultdict
from decimal import Decimal
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

from defeatbeta_api.client.duckdb_client import get_duckdb_client
from defeatbeta_api.client.duckdb_conf import Configuration
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.data.balance_sheet import BalanceSheet
from defeatbeta_api.data.finance_item import FinanceItem
from defeatbeta_api.data.finance_value import FinanceValue
from defeatbeta_api.data.income_statement import IncomeStatement
from defeatbeta_api.data.news import News
from defeatbeta_api.data.print_visitor import PrintVisitor
from defeatbeta_api.data.statement import Statement
from defeatbeta_api.data.stock_statement import StockStatement
from defeatbeta_api.data.transcripts import Transcripts
from defeatbeta_api.utils.case_insensitive_dict import CaseInsensitiveDict
from defeatbeta_api.utils.const import stock_profile, stock_earning_calendar, stock_historical_eps, stock_officers, \
    stock_split_events, \
    stock_dividend_events, stock_revenue_estimates, stock_earning_estimates, stock_summary, stock_tailing_eps, \
    stock_prices, stock_statement, income_statement, balance_sheet, cash_flow, quarterly, annual, \
    stock_earning_call_transcripts, stock_news, stock_revenue_breakdown, stock_shares_outstanding, exchange_rate
from defeatbeta_api.utils.util import load_finance_template, parse_all_title_keys, income_statement_template_type, \
    balance_sheet_template_type, cash_flow_template_type, load_financial_currency


class Ticker:
    def __init__(self, ticker, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.ticker = ticker.upper()
        self.http_proxy = http_proxy
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()
        self.log_level = log_level

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

    def quarterly_income_statement(self) -> Statement:
        return self._statement(income_statement, quarterly)

    def annual_income_statement(self) -> Statement:
        return self._statement(income_statement, annual)

    def quarterly_balance_sheet(self) -> Statement:
        return self._statement(balance_sheet, quarterly)

    def annual_balance_sheet(self) -> Statement:
        return self._statement(balance_sheet, annual)

    def quarterly_cash_flow(self) -> Statement:
        return self._statement(cash_flow, quarterly)

    def annual_cash_flow(self) -> Statement:
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

        result_df = price_df.copy()
        result_df = result_df.rename(columns={'report_date': 'price_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('price_report_date'),
            eps_df.sort_values('report_date'),
            left_on='price_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['ttm_pe'] = round(result_df['close'] / result_df['tailing_eps'], 2)

        result_df = result_df[[
            'price_report_date',
            'report_date',
            'close',
            'tailing_eps',
            'ttm_pe'
        ]]

        result_df = result_df.rename(columns={
            'price_report_date': 'report_date',
            'close': 'close_price',
            'tailing_eps': 'ttm_eps',
            'report_date': 'eps_report_date'
        })

        return result_df

    def quarterly_gross_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('gross', 'quarterly', 'gross_profit', 'gross_margin')

    def annual_gross_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('gross', 'annual', 'gross_profit', 'gross_margin')

    def quarterly_operating_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('operating', 'quarterly', 'operating_income', 'operating_margin')

    def annual_operating_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('operating', 'annual', 'operating_income', 'operating_margin')

    def quarterly_net_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('net', 'quarterly', 'net_income_common_stockholders', 'net_margin')

    def annual_net_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('net', 'annual', 'net_income_common_stockholders', 'net_margin')

    def quarterly_ebitda_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('ebitda', 'quarterly', 'ebitda', 'ebitda_margin')

    def annual_ebitda_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('ebitda', 'annual', 'ebitda', 'ebitda_margin')

    def quarterly_fcf_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('fcf', 'quarterly', 'free_cash_flow', 'fcf_margin')

    def annual_fcf_margin(self) -> pd.DataFrame:
        return self._generate_margin_sql('fcf', 'annual', 'free_cash_flow', 'fcf_margin')

    def earning_call_transcripts(self) -> Transcripts:
        return Transcripts(self.ticker, self._query_data(stock_earning_call_transcripts), self.log_level)

    def news(self) -> News:
        url = self.huggingface_client.get_url_path(stock_news)
        sql = f"SELECT * FROM '{url}' WHERE ARRAY_CONTAINS(related_symbols, '{self.ticker}') ORDER BY report_date ASC"
        return News(self.duckdb_client.query(sql))

    def revenue_by_segment(self) -> pd.DataFrame:
        return self._revenue_by_breakdown('segment')

    def revenue_by_geography(self) -> pd.DataFrame:
        return self._revenue_by_breakdown('geography')

    def revenue_by_product(self) -> pd.DataFrame:
        return self._revenue_by_breakdown('product')

    def quarterly_revenue_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='total_revenue', period_type='quarterly', finance_type='income_statement')

    def annual_revenue_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='total_revenue', period_type='annual', finance_type='income_statement')

    def quarterly_operating_income_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='operating_income', period_type='quarterly', finance_type='income_statement')

    def annual_operating_income_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='operating_income', period_type='annual', finance_type='income_statement')

    def quarterly_net_income_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='net_income_common_stockholders', period_type='quarterly', finance_type='income_statement')

    def annual_net_income_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='net_income_common_stockholders', period_type='annual', finance_type='income_statement')

    def quarterly_fcf_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='free_cash_flow', period_type='quarterly', finance_type='cash_flow')

    def annual_fcf_yoy_growth(self) -> pd.DataFrame:
        return self._calculate_yoy_growth(item_name='free_cash_flow', period_type='annual', finance_type='cash_flow')

    def quarterly_eps_yoy_growth(self) -> pd.DataFrame:
        return self._quarterly_eps_yoy_growth('eps', 'eps', 'prev_year_eps')

    def quarterly_ttm_eps_yoy_growth(self) -> pd.DataFrame:
        return self._quarterly_eps_yoy_growth('tailing_eps', 'ttm_eps', 'prev_year_ttm_eps')

    def market_capitalization(self) -> pd.DataFrame:
        price_url = self.huggingface_client.get_url_path(stock_prices)
        price_sql = f"SELECT * FROM '{price_url}' WHERE symbol = '{self.ticker}'"
        price_df = self.duckdb_client.query(price_sql)

        shares_url = self.huggingface_client.get_url_path(stock_shares_outstanding)
        shares_sql = f"SELECT * FROM '{shares_url}' WHERE symbol = '{self.ticker}'"
        shares_df = self.duckdb_client.query(shares_sql)

        price_df['report_date'] = pd.to_datetime(price_df['report_date'])
        shares_df['report_date'] = pd.to_datetime(shares_df['report_date'])

        result_df = price_df.copy()
        result_df = result_df.rename(columns={'report_date': 'price_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('price_report_date'),
            shares_df.sort_values('report_date'),
            left_on='price_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['market_cap'] = round(result_df['close'] * result_df['shares_outstanding'], 2)

        result_df = result_df[[
            'price_report_date',
            'report_date',
            'close',
            'shares_outstanding',
            'market_cap'
        ]]

        result_df = result_df.rename(columns={
            'price_report_date': 'report_date',
            'close': 'close_price',
            'report_date': 'shares_report_date',
            'market_cap': 'market_capitalization'
        })

        return result_df

    def ps_ratio(self) -> pd.DataFrame:
        market_cap_df = self.market_capitalization()
        ttm_revenue_df = self.ttm_revenue()

        market_cap_df['report_date'] = pd.to_datetime(market_cap_df['report_date'])
        ttm_revenue_df['report_date'] = pd.to_datetime(ttm_revenue_df['report_date'])

        result_df = market_cap_df.copy()
        result_df = result_df.rename(columns={'report_date': 'market_cap_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('market_cap_report_date'),
            ttm_revenue_df.sort_values('report_date'),
            left_on='market_cap_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df = result_df[result_df['report_date'].notna()]

        result_df['ps_ratio'] = round(result_df['market_capitalization'] / result_df['ttm_total_revenue_usd'], 2)

        result_df = result_df[[
            'market_cap_report_date',
            'market_capitalization',
            'report_date',
            'ttm_total_revenue',
            'exchange_to_usd_rate',
            'ttm_total_revenue_usd',
            'ps_ratio'
        ]]

        result_df = result_df.rename(columns={
            'market_cap_report_date': 'report_date',
            'report_date': 'fiscal_quarter',
            'ttm_total_revenue': 'ttm_revenue',
            'exchange_to_usd_rate': 'exchange_rate',
            'ttm_total_revenue_usd': 'ttm_revenue_usd'
        })

        return result_df

    def pb_ratio(self) -> pd.DataFrame:
        market_cap_df = self.market_capitalization()
        bve_df = self._quarterly_book_value_of_equity()

        market_cap_df['report_date'] = pd.to_datetime(market_cap_df['report_date'])
        bve_df['report_date'] = pd.to_datetime(bve_df['report_date'])

        result_df = market_cap_df.copy()
        result_df = result_df.rename(columns={'report_date': 'market_cap_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('market_cap_report_date'),
            bve_df.sort_values('report_date'),
            left_on='market_cap_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df = result_df[result_df['report_date'].notna()]

        result_df['pb_ratio'] = round(result_df['market_capitalization'] / result_df['book_value_of_equity_usd'], 2)

        result_df = result_df[[
            'market_cap_report_date',
            'market_capitalization',
            'report_date',
            'book_value_of_equity',
            'exchange_to_usd_rate',
            'book_value_of_equity_usd',
            'pb_ratio'
        ]]

        result_df = result_df.rename(columns={
            'market_cap_report_date': 'report_date',
            'report_date': 'fiscal_quarter',
            'ttm_total_revenue': 'book_value_of_equity',
            'exchange_to_usd_rate': 'exchange_rate',
            'ttm_total_revenue_usd': 'book_value_of_equity_usd'
        })

        return result_df

    def peg_ratio(self) -> pd.DataFrame:
        ttm_pe_df = self.ttm_pe()
        revenue_yoy_df = self.quarterly_revenue_yoy_growth()
        eps_yoy_df = self.quarterly_eps_yoy_growth()

        ttm_pe_df['report_date'] = pd.to_datetime(ttm_pe_df['report_date']).astype('datetime64[ns]')
        revenue_yoy_df['report_date'] = pd.to_datetime(revenue_yoy_df['report_date']).astype('datetime64[ns]')
        eps_yoy_df['report_date'] = pd.to_datetime(eps_yoy_df['report_date']).astype('datetime64[ns]')

        result_df = ttm_pe_df.copy()
        result_df = result_df.rename(columns={'report_date': 'ttm_pe_report_date'})
        result_df = result_df[result_df['eps_report_date'].notna()]

        result_df = pd.merge_asof(
            result_df,
            eps_yoy_df,
            left_on='eps_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['peg_ratio_by_eps'] = np.where(
            (result_df['ttm_pe'] < 0) | (result_df['yoy_growth'] < 0),
            -np.abs(result_df['ttm_pe'] / (result_df['yoy_growth'] * 100)),
            np.abs(result_df['ttm_pe'] / (result_df['yoy_growth'] * 100))
        ).round(2)

        result_df = result_df[[
            'ttm_pe_report_date',
            'close_price',
            'report_date',
            'ttm_eps',
            'ttm_pe',
            'yoy_growth',
            'peg_ratio_by_eps'
        ]]

        result_df = result_df.rename(columns={
            'ttm_pe_report_date': 'report_date',
            'report_date': 'fiscal_quarter',
            'yoy_growth': 'eps_yoy_growth'
        })

        result_df = pd.merge_asof(
            result_df,
            revenue_yoy_df,
            left_on='fiscal_quarter',
            right_on='report_date',
            direction='backward'
        )

        result_df['peg_ratio_by_revenue'] = np.where(
            (result_df['ttm_pe'] < 0) | (result_df['yoy_growth'] < 0),
            -np.abs(result_df['ttm_pe'] / (result_df['yoy_growth'] * 100)),
            np.abs(result_df['ttm_pe'] / (result_df['yoy_growth'] * 100))
        ).round(2)

        result_df = result_df[[
            'report_date_x',
            'close_price',
            'fiscal_quarter',
            'ttm_eps',
            'ttm_pe',
            'eps_yoy_growth',
            'yoy_growth',
            'peg_ratio_by_revenue',
            'peg_ratio_by_eps'
        ]]

        result_df = result_df.rename(columns={
            'report_date_x': 'report_date',
            'yoy_growth': 'revenue_yoy_growth'
        })

        result_df = result_df[result_df['ttm_pe'].notna()]
        return result_df

    def _quarterly_book_value_of_equity(self) -> pd.DataFrame:
        stockholders_equity_url = self.huggingface_client.get_url_path(stock_statement)
        stockholders_equity_sql = f"""
            SELECT symbol, report_date, item_value as book_value_of_equity 
            FROM 
                '{stockholders_equity_url}' 
            WHERE 
                symbol = '{self.ticker}' 
                AND item_name = 'stockholders_equity' 
                AND period_type = 'quarterly'
                AND item_value IS NOT NULL
                AND report_date != 'TTM'
        """
        stockholders_equity_df = self.duckdb_client.query(stockholders_equity_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'
        currency_symbol = currency + '=X'
        currency_url = self.huggingface_client.get_url_path(exchange_rate)
        currency_sql = f"""
            SELECT * FROM '{currency_url}' WHERE symbol = '{currency_symbol}'
        """
        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                stockholders_equity_df['report_date'])
            currency_df['symbol'] = currency_symbol
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.duckdb_client.query(currency_sql)

        stockholders_equity_df['report_date'] = pd.to_datetime(stockholders_equity_df['report_date'])
        currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

        result_df = stockholders_equity_df.copy()
        result_df = result_df.rename(columns={'report_date': 'book_value_of_equity_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('book_value_of_equity_report_date'),
            currency_df.sort_values('report_date'),
            left_on='book_value_of_equity_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['book_value_of_equity_usd'] = round(result_df['book_value_of_equity'] / result_df['close'], 2)

        result_df = result_df[[
            'book_value_of_equity_report_date',
            'book_value_of_equity',
            'report_date',
            'close',
            'book_value_of_equity_usd'
        ]]

        result_df = result_df.rename(columns={
            'book_value_of_equity_report_date': 'report_date',
            'report_date': 'exchange_report_date',
            'close': 'exchange_to_usd_rate'
        })

        return result_df

    def ttm_revenue(self) -> pd.DataFrame:
        ttm_revenue_url = self.huggingface_client.get_url_path(stock_statement)
        ttm_revenue_sql = f"""
            WITH quarterly_data AS (
                SELECT 
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type,
                    YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
                FROM 
                    '{ttm_revenue_url}'  
                WHERE 
                    symbol = '{self.ticker}' 
                    AND item_name = 'total_revenue' 
                    AND period_type = 'quarterly'
                    AND item_value IS NOT NULL
                    AND report_date != 'TTM'
            ),
            quarterly_data_rn AS (
                SELECT
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type,
                    continuous_id,
                    ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
                FROM
                    quarterly_data
            ),
            grouped_data AS (
                SELECT
                    *,
                    continuous_id - rn_asc AS group_id
                FROM
                    quarterly_data_rn
            ),
            base_data_window AS (
                SELECT
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type
                FROM
                    grouped_data t1
                    where t1.group_id = (
                        SELECT
                            group_id
                        FROM
                            grouped_data
                        ORDER BY
                            continuous_id DESC
                            LIMIT 1
                    )
                ORDER BY
                    continuous_id ASC
            ),
            sliding_window AS (
                SELECT
                report_date,
                ttm_total_revenue,
                TO_JSON(MAP(window_report_dates, window_item_values)) AS report_date_2_revenue
                FROM (
                    SELECT
                        symbol,
                        report_date,
                        item_name,
                        item_value,
                        finance_type,
                        period_type,
                        SUM(item_value) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS ttm_total_revenue,
                        COUNT(*) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS quarter_count,
                        ARRAY_AGG(report_date) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS window_report_dates,
                        ARRAY_AGG(item_value) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS window_item_values
                    FROM base_data_window
                ) t
                WHERE quarter_count = 4
            )
            SELECT 
                * from sliding_window
        """
        ttm_revenue_df = self.duckdb_client.query(ttm_revenue_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'
        currency_symbol = currency + '=X'
        currency_url = self.huggingface_client.get_url_path(exchange_rate)
        currency_sql = f"""
            SELECT * FROM '{currency_url}' WHERE symbol = '{currency_symbol}'
        """
        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                ttm_revenue_df['report_date'])
            currency_df['symbol'] = currency_symbol
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.duckdb_client.query(currency_sql)

        ttm_revenue_df['report_date'] = pd.to_datetime(ttm_revenue_df['report_date'])
        currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

        result_df = ttm_revenue_df.copy()
        result_df = result_df.rename(columns={'report_date': 'ttm_revenue_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('ttm_revenue_report_date'),
            currency_df.sort_values('report_date'),
            left_on='ttm_revenue_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['ttm_total_revenue_usd'] = round(result_df['ttm_total_revenue'] / result_df['close'], 2)

        result_df = result_df[[
            'ttm_revenue_report_date',
            'ttm_total_revenue',
            'report_date_2_revenue',
            'report_date',
            'close',
            'ttm_total_revenue_usd'
        ]]

        result_df = result_df.rename(columns={
            'ttm_revenue_report_date': 'report_date',
            'report_date': 'exchange_report_date',
            'close': 'exchange_to_usd_rate'
        })

        return result_df

    def ttm_net_income_common_stockholders(self) -> pd.DataFrame:
        ttm_net_income_url = self.huggingface_client.get_url_path(stock_statement)
        ttm_net_income_sql = f"""
            WITH quarterly_data AS (
                SELECT 
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type,
                    YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
                FROM 
                    '{ttm_net_income_url}'  
                WHERE 
                    symbol = '{self.ticker}' 
                    AND item_name = 'net_income_common_stockholders' 
                    AND period_type = 'quarterly'
                    AND item_value IS NOT NULL
                    AND report_date != 'TTM'
            ),
            quarterly_data_rn AS (
                SELECT
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type,
                    continuous_id,
                    ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
                FROM
                    quarterly_data
            ),
            grouped_data AS (
                SELECT
                    *,
                    continuous_id - rn_asc AS group_id
                FROM
                    quarterly_data_rn
            ),
            base_data_window AS (
                SELECT
                    symbol, 
                    report_date, 
                    item_name, 
                    item_value, 
                    finance_type, 
                    period_type
                FROM
                    grouped_data t1
                    where t1.group_id = (
                        SELECT
                            group_id
                        FROM
                            grouped_data
                        ORDER BY
                            continuous_id DESC
                            LIMIT 1
                    )
                ORDER BY
                    continuous_id ASC
            ),
            sliding_window AS (
                SELECT
                report_date,
                ttm_net_income,
                TO_JSON(MAP(window_report_dates, window_item_values)) AS report_date_2_net_income,
                FROM (
                    SELECT
                        symbol,
                        report_date,
                        item_name,
                        item_value,
                        finance_type,
                        period_type,
                        SUM(item_value) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS ttm_net_income,
                        COUNT(*) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS quarter_count,
                        ARRAY_AGG(report_date) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS window_report_dates,
                        ARRAY_AGG(item_value) OVER (
                            PARTITION BY symbol
                            ORDER BY CAST(report_date AS DATE)
                            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
                        ) AS window_item_values
                    FROM base_data_window
                ) t
                WHERE quarter_count = 4
            )
            SELECT 
                * from sliding_window
        """
        ttm_revenue_df = self.duckdb_client.query(ttm_net_income_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'
        currency_symbol = currency + '=X'
        currency_url = self.huggingface_client.get_url_path(exchange_rate)
        currency_sql = f"""
            SELECT * FROM '{currency_url}' WHERE symbol = '{currency_symbol}'
        """
        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                ttm_revenue_df['report_date'])
            currency_df['symbol'] = currency_symbol
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.duckdb_client.query(currency_sql)

        ttm_revenue_df['report_date'] = pd.to_datetime(ttm_revenue_df['report_date'])
        currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

        result_df = ttm_revenue_df.copy()
        result_df = result_df.rename(columns={'report_date': 'ttm_net_income_report_date'})

        result_df = pd.merge_asof(
            result_df.sort_values('ttm_net_income_report_date'),
            currency_df.sort_values('report_date'),
            left_on='ttm_net_income_report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['ttm_net_income_usd'] = round(result_df['ttm_net_income'] / result_df['close'], 2)

        result_df = result_df[[
            'ttm_net_income_report_date',
            'ttm_net_income',
            'report_date_2_net_income',
            'report_date',
            'close',
            'ttm_net_income_usd'
        ]]

        result_df = result_df.rename(columns={
            'ttm_net_income_report_date': 'report_date',
            'report_date': 'exchange_report_date',
            'close': 'exchange_to_usd_rate'
        })

        return result_df

    def roe(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = f"""
                WITH roe_table AS (
                            SELECT
                                symbol,
                                report_date,
                                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                                MAX(CASE WHEN item_name = 'stockholders_equity' THEN item_value END) AS stockholders_equity
                            FROM
                                '{url}'
                            WHERE
                                symbol = '{self.ticker}'
                                AND item_name IN ('net_income_common_stockholders', 'stockholders_equity')
                                AND report_date != 'TTM'
                                AND period_type = 'quarterly'
                                AND finance_type in ('income_statement', 'balance_sheet')
                            GROUP BY symbol, report_date
                ),
                
                base_data AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        stockholders_equity,
                        YEAR(report_date::DATE) AS report_year,
                        QUARTER(report_date::DATE) AS report_quarter,
                        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
                    FROM
                        roe_table
                    WHERE
                        net_income_common_stockholders IS NOT NULL AND stockholders_equity IS NOT NULL
                ),
                
                base_data_rn AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        stockholders_equity,
                        report_year,
                        report_quarter,
                        continuous_id,
                        ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
                    FROM
                        base_data
                ),
                
                grouped_data AS (
                    SELECT
                        *,
                        continuous_id - rn_asc AS group_id
                    FROM
                        base_data_rn
                ),
                
                base_data_window AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        stockholders_equity,
                        ROW_NUMBER() OVER (ORDER BY report_date ASC) AS rn
                    FROM
                        grouped_data t1
                        JOIN (
                            SELECT
                                group_id
                            FROM
                                grouped_data
                            ORDER BY
                                continuous_id DESC
                                LIMIT 1
                        ) t2
                    ON t1.group_id = t2.group_id
                    ORDER BY
                        continuous_id ASC
                ),
                
                equity_with_lag AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        stockholders_equity as ending_stockholders_equity,
                        LAG(stockholders_equity, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_stockholders_equity
                    FROM base_data_window
                ),
                
                equity_avg AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        ending_stockholders_equity,
                        beginning_stockholders_equity,
                        (beginning_stockholders_equity + ending_stockholders_equity) / 2.0 AS avg_equity
                    FROM equity_with_lag
                    WHERE beginning_stockholders_equity IS NOT NULL
                )
                
                select symbol,
                        report_date,
                        net_income_common_stockholders,
                        beginning_stockholders_equity,
                        ending_stockholders_equity,
                        avg_equity,
                        round(net_income_common_stockholders / avg_equity, 4) AS roe
                    from equity_avg order by report_date;
        """
        result_df = self.duckdb_client.query(sql)
        result_df = result_df[[
            'report_date',
            'net_income_common_stockholders',
            'beginning_stockholders_equity',
            'ending_stockholders_equity',
            'avg_equity',
            'roe'
        ]]
        return result_df

    def roa(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = f"""
                WITH roe_table AS (
                            SELECT
                                symbol,
                                report_date,
                                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                                MAX(CASE WHEN item_name = 'total_assets' THEN item_value END) AS total_assets
                            FROM
                                '{url}'
                            WHERE
                                symbol = '{self.ticker}'
                                AND item_name IN ('net_income_common_stockholders', 'total_assets')
                                AND report_date != 'TTM'
                                AND period_type = 'quarterly'
                                AND finance_type in ('income_statement', 'balance_sheet')
                            GROUP BY symbol, report_date
                ),
                
                base_data AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        total_assets,
                        YEAR(report_date::DATE) AS report_year,
                        QUARTER(report_date::DATE) AS report_quarter,
                        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
                    FROM
                        roe_table
                    WHERE
                        net_income_common_stockholders IS NOT NULL AND total_assets IS NOT NULL
                ),
                
                base_data_rn AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        total_assets,
                        report_year,
                        report_quarter,
                        continuous_id,
                        ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
                    FROM
                        base_data
                ),
                
                grouped_data AS (
                    SELECT
                        *,
                        continuous_id - rn_asc AS group_id
                    FROM
                        base_data_rn
                ),
                
                base_data_window AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        total_assets,
                        ROW_NUMBER() OVER (ORDER BY report_date ASC) AS rn
                    FROM
                        grouped_data t1
                        JOIN (
                            SELECT
                                group_id
                            FROM
                                grouped_data
                            ORDER BY
                                continuous_id DESC
                                LIMIT 1
                        ) t2
                    ON t1.group_id = t2.group_id
                    ORDER BY
                        continuous_id ASC
                ),
                
                assets_with_lag AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        total_assets as ending_total_assets,
                        LAG(total_assets, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_total_assets
                    FROM base_data_window
                ),
                
                asserts_avg AS (
                    SELECT
                        symbol,
                        report_date,
                        net_income_common_stockholders,
                        ending_total_assets,
                        beginning_total_assets,
                        (beginning_total_assets + ending_total_assets) / 2.0 AS avg_assets
                    FROM assets_with_lag
                    WHERE beginning_total_assets IS NOT NULL
                )
                
                select symbol,
                        report_date,
                        net_income_common_stockholders,
                        beginning_total_assets,
                        ending_total_assets,
                        avg_assets,
                        round(net_income_common_stockholders / avg_assets, 4) AS roa
                    from asserts_avg order by report_date;
            """
        result_df = self.duckdb_client.query(sql)
        result_df = result_df[[
            'report_date',
            'net_income_common_stockholders',
            'beginning_total_assets',
            'ending_total_assets',
            'avg_assets',
            'roa'
        ]]
        return result_df

    def roic(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = f"""
                WITH roic_table AS (
                 SELECT
                     symbol,
                     report_date,
                     MAX(CASE WHEN item_name = 'ebit' THEN item_value END) AS ebit,
                     MAX(CASE WHEN item_name = 'tax_rate_for_calcs' THEN item_value END) AS tax_rate_for_calcs,
                     MAX(CASE WHEN item_name = 'invested_capital' THEN item_value END) AS invested_capital
                 FROM
                     '{url}'
                 WHERE
                     symbol = '{self.ticker}'
                     AND item_name IN ('ebit', 'tax_rate_for_calcs', 'net_income_common_stockholders', 'invested_capital')
                     AND report_date != 'TTM'
                     AND period_type = 'quarterly'
                     AND finance_type in ('income_statement', 'balance_sheet')
                 GROUP BY symbol, report_date
                ),

                base_data AS (
                  SELECT
                      symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      ebit * (1 - tax_rate_for_calcs) as nopat,
                      invested_capital,
                      YEAR(report_date::DATE) AS report_year,
                      QUARTER(report_date::DATE) AS report_quarter,
                      YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
                  FROM
                      roic_table
                ),

                base_data_rn AS (
                  SELECT
                      symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      nopat,
                      invested_capital,
                      report_year,
                      report_quarter,
                      continuous_id,
                      ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
                  FROM
                      base_data
                ),

                grouped_data AS (
                  SELECT
                      *,
                      continuous_id - rn_asc AS group_id
                  FROM
                      base_data_rn
                ),

                base_data_window AS (
                  SELECT
                      symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      nopat,
                      invested_capital,
                      ROW_NUMBER() OVER (ORDER BY report_date ASC) AS rn
                  FROM
                      grouped_data t1
                      JOIN (
                          SELECT
                              group_id
                          FROM
                              grouped_data
                          ORDER BY
                              continuous_id DESC
                              LIMIT 1
                      ) t2
                  ON t1.group_id = t2.group_id
                  ORDER BY
                      continuous_id ASC
                ),

                invested_capital_with_lag AS (
                  SELECT
                      symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      nopat,
                      invested_capital as ending_invested_capital,
                      LAG(invested_capital, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_invested_capital
                  FROM base_data_window
                ),

                invested_capital_avg AS (
                  SELECT
                      symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      nopat,
                      ending_invested_capital,
                      beginning_invested_capital,
                      (beginning_invested_capital + ending_invested_capital) / 2.0 AS avg_invested_capital
                  FROM invested_capital_with_lag
                  WHERE beginning_invested_capital IS NOT NULL
                )


                select symbol,
                      report_date,
                      ebit,
                      tax_rate_for_calcs,
                      nopat,
                      beginning_invested_capital,
                      ending_invested_capital,
                      avg_invested_capital,
                      round(nopat / avg_invested_capital, 4) AS roic
                  from invested_capital_avg order by report_date; 
            """
        result_df = self.duckdb_client.query(sql)
        result_df = result_df[[
            'report_date',
            'ebit',
            'tax_rate_for_calcs',
            'nopat',
            'beginning_invested_capital',
            'ending_invested_capital',
            'avg_invested_capital',
            'roic'
        ]]
        return result_df

    def equity_multiplier(self) -> pd.DataFrame:
        roe = self.roe()
        roa = self.roa()

        roe['report_date'] = pd.to_datetime(roe['report_date'])
        roa['report_date'] = pd.to_datetime(roa['report_date'])

        result_df = pd.merge_asof(
            roe.sort_values('report_date'),
            roa.sort_values('report_date'),
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['equity_multiplier'] = round(result_df['roe'] / result_df['roa'], 2)

        result_df = result_df[[
            'report_date',
            'roe',
            'roa',
            'equity_multiplier'
        ]]
        return result_df

    def asset_turnover(self) -> pd.DataFrame:
        roa = self.roa()
        quarterly_net_margin = self.quarterly_net_margin()

        roa['report_date'] = pd.to_datetime(roa['report_date'])
        quarterly_net_margin['report_date'] = pd.to_datetime(quarterly_net_margin['report_date'])

        result_df = pd.merge_asof(
            roa.sort_values('report_date'),
            quarterly_net_margin.sort_values('report_date'),
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['asset_turnover'] = round(result_df['roa'] / result_df['net_margin'], 2)

        result_df = result_df[[
            'report_date',
            'roa',
            'net_margin',
            'asset_turnover'
        ]]

        return result_df

    def _quarterly_eps_yoy_growth(self, eps_column: str, current_alias: str, prev_alias: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_tailing_eps)
        sql = f"""
            WITH eps_data AS (
                SELECT 
                    symbol,
                    CAST(report_date AS DATE) AS report_date,
                    {eps_column}
                FROM '{url}'
                WHERE symbol = '{self.ticker}'
            ),
            yoy AS (
                SELECT 
                    e1.symbol,
                    e1.report_date,
                    e1.{eps_column} AS {current_alias},
                    e2.{eps_column} AS {prev_alias}
                FROM eps_data e1
                LEFT JOIN eps_data e2
                  ON e1.symbol = e2.symbol
                 AND strftime(e2.report_date, '%m-%d') = strftime(e1.report_date, '%m-%d')
                 AND date_diff('year', e2.report_date, e1.report_date) = 1
            )
            SELECT 
                symbol,
                report_date,
                {current_alias},
                {prev_alias},
                CASE 
                    WHEN {prev_alias} IS NOT NULL AND {prev_alias} != 0 
                        THEN ROUND(({current_alias} - {prev_alias}) / ABS({prev_alias}), 4)
                    WHEN {prev_alias} IS NOT NULL AND {prev_alias} = 0 AND {current_alias} > 0
                        THEN 1.00
                    WHEN {prev_alias} IS NOT NULL AND {prev_alias} = 0 AND {current_alias} < 0
                        THEN -1.00
                    ELSE NULL
                END AS yoy_growth
            FROM yoy
            ORDER BY report_date;
        """
        return self.duckdb_client.query(sql)

    def _calculate_yoy_growth(self, item_name: str, period_type: str, finance_type: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        metric_name = item_name.replace('total_', '')  # For naming consistency in output
        lag_period = 4 if period_type == 'quarterly' else 1
        ttm_filter = "AND report_date != 'TTM'" if period_type == 'quarterly' else ''

        sql = f"""
            WITH metric_data AS (
                SELECT 
                    symbol,
                    CAST(report_date AS DATE) AS report_date,
                    item_value as {metric_name}
                FROM '{url}' 
                WHERE symbol='{self.ticker}' 
                    AND finance_type = '{finance_type}' 
                    AND item_name='{item_name}' 
                    AND period_type='{period_type}'
                    {ttm_filter}
            ),
            yoy AS (
                SELECT 
                    e1.symbol,
                    e1.report_date,
                    e1.{metric_name} AS {metric_name},
                    e2.{metric_name} AS prev_year_{metric_name}
                FROM metric_data e1
                LEFT JOIN metric_data e2
                  ON e1.symbol = e2.symbol
                 AND strftime(e2.report_date, '%m-%d') = strftime(e1.report_date, '%m-%d')
                 AND date_diff('year', e2.report_date, e1.report_date) = 1
            )
            SELECT 
                symbol,
                report_date,
                {metric_name},
                prev_year_{metric_name},
                CASE 
                    WHEN prev_year_{metric_name} IS NOT NULL AND prev_year_{metric_name} != 0 
                    THEN ROUND(({metric_name} - prev_year_{metric_name}) / ABS(prev_year_{metric_name}), 4)
                    ELSE NULL
                END as yoy_growth
            FROM yoy
            WHERE {metric_name} IS NOT NULL
            ORDER BY report_date;
        """
        return self.duckdb_client.query(sql)

    def _revenue_by_breakdown(self, breakdown_type: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_revenue_breakdown)
        sql = f"SELECT * FROM '{url}' WHERE symbol = '{self.ticker}' AND breakdown_type = '{breakdown_type}' ORDER BY report_date ASC"
        data = self.duckdb_client.query(sql)
        df_wide = data.pivot(index=['report_date'], columns='item_name', values='item_value').reset_index()
        df_wide.columns.name = None
        df_wide = df_wide.fillna(0)
        return df_wide

    def _generate_margin_sql(self, margin_type: str, period_type: str, numerator_item: str,
                             margin_column: str) -> pd.DataFrame:
        ttm_filter = "AND report_date != 'TTM'" if period_type == 'quarterly' else ""
        finance_type_filter = \
            "AND finance_type = 'income_statement'" if margin_type in ['gross', 'operating', 'net', 'ebitda'] \
            else "AND finance_type in ('income_statement', 'cash_flow')" if margin_type == 'fcf' \
            else ""
        sql = f"""
            SELECT symbol,
                   report_date,
                   {numerator_item},
                   total_revenue,
                   round({numerator_item}/total_revenue, 4) as {margin_column}
            FROM (
                SELECT
                     symbol,
                     report_date,
                     MAX(CASE WHEN t1.item_name = '{numerator_item}' THEN t1.item_value END) AS {numerator_item},
                     MAX(CASE WHEN t1.item_name = 'total_revenue' THEN t1.item_value END) AS total_revenue
                  FROM '{self.huggingface_client.get_url_path('stock_statement')}' t1
                  WHERE symbol = '{self.ticker}'
                    {finance_type_filter}
                    {ttm_filter}
                    AND item_name IN ('{numerator_item}', 'total_revenue')
                    AND period_type = '{period_type}'
                  GROUP BY symbol, report_date
            ) t 
            ORDER BY report_date ASC
        """
        return self.duckdb_client.query(sql)

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