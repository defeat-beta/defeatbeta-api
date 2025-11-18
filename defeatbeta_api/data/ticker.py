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
from defeatbeta_api.data.sql.sql_loader import load_sql
from defeatbeta_api.data.statement import Statement
from defeatbeta_api.data.stock_statement import StockStatement
from defeatbeta_api.data.transcripts import Transcripts
from defeatbeta_api.data.treasure import Treasure
from defeatbeta_api.utils.case_insensitive_dict import CaseInsensitiveDict
from defeatbeta_api.utils.const import stock_profile, stock_earning_calendar, stock_historical_eps, stock_officers, \
    stock_split_events, \
    stock_dividend_events, stock_revenue_estimates, stock_earning_estimates, stock_summary, stock_tailing_eps, \
    stock_prices, stock_statement, income_statement, balance_sheet, cash_flow, quarterly, annual, \
    stock_earning_call_transcripts, stock_news, stock_revenue_breakdown, stock_shares_outstanding, exchange_rate
from defeatbeta_api.utils.util import load_finance_template, parse_all_title_keys, income_statement_template_type, \
    balance_sheet_template_type, cash_flow_template_type, load_financial_currency, sp500_cagr_returns_rolling


class Ticker:
    def __init__(self, ticker, http_proxy: Optional[str] = None, log_level: Optional[str] = logging.INFO, config: Optional[Configuration] = None):
        self.ticker = ticker.upper()
        self.http_proxy = http_proxy
        self.config = config
        self.duckdb_client = get_duckdb_client(http_proxy=self.http_proxy, log_level=log_level, config=config)
        self.huggingface_client = HuggingFaceClient()
        self.log_level = log_level
        self.treasure = Treasure(
            http_proxy=self.http_proxy,
            log_level=self.log_level,
            config=config
        )

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

    def currency(self, symbol: str) -> pd.DataFrame:
        return self._query_data2(exchange_rate, symbol)

    def shares(self) -> pd.DataFrame:
        return self._query_data(stock_shares_outstanding)

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
        price_df = self.price()

        eps_df = self.ttm_eps()

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
        return self._generate_margin('gross', 'quarterly', 'gross_profit', 'gross_margin')

    def annual_gross_margin(self) -> pd.DataFrame:
        return self._generate_margin('gross', 'annual', 'gross_profit', 'gross_margin')

    def quarterly_operating_margin(self) -> pd.DataFrame:
        return self._generate_margin('operating', 'quarterly', 'operating_income', 'operating_margin')

    def annual_operating_margin(self) -> pd.DataFrame:
        return self._generate_margin('operating', 'annual', 'operating_income', 'operating_margin')

    def quarterly_net_margin(self) -> pd.DataFrame:
        return self._generate_margin('net', 'quarterly', 'net_income_common_stockholders', 'net_margin')

    def annual_net_margin(self) -> pd.DataFrame:
        return self._generate_margin('net', 'annual', 'net_income_common_stockholders', 'net_margin')

    def quarterly_ebitda_margin(self) -> pd.DataFrame:
        return self._generate_margin('ebitda', 'quarterly', 'ebitda', 'ebitda_margin')

    def annual_ebitda_margin(self) -> pd.DataFrame:
        return self._generate_margin('ebitda', 'annual', 'ebitda', 'ebitda_margin')

    def quarterly_fcf_margin(self) -> pd.DataFrame:
        return self._generate_margin('fcf', 'quarterly', 'free_cash_flow', 'fcf_margin')

    def annual_fcf_margin(self) -> pd.DataFrame:
        return self._generate_margin('fcf', 'annual', 'free_cash_flow', 'fcf_margin')

    def earning_call_transcripts(self) -> Transcripts:
        return Transcripts(self.ticker, self._query_data(stock_earning_call_transcripts), self.log_level)

    def news(self) -> News:
        url = self.huggingface_client.get_url_path(stock_news)
        sql = load_sql("select_news_by_symbol", ticker = self.ticker, url = url)
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
        price_df = self.price()

        shares_df = self.shares()

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
        stockholders_equity_sql = load_sql("select_quarterly_book_value_of_equity_by_symbol",
                                           ticker = self.ticker,
                                           stockholders_equity_url = stockholders_equity_url)
        stockholders_equity_df = self.duckdb_client.query(stockholders_equity_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'

        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                stockholders_equity_df['report_date'])
            currency_df['symbol'] = currency + '=X'
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.currency(currency + '=X')

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
        ttm_revenue_sql = load_sql("select_ttm_revenue_by_symbol",
                                   ticker = self.ticker,
                                   ttm_revenue_url = ttm_revenue_url)
        ttm_revenue_df = self.duckdb_client.query(ttm_revenue_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'
        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                ttm_revenue_df['report_date'])
            currency_df['symbol'] = currency + '=X'
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.currency(symbol = currency + '=X')

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
        ttm_net_income_sql = load_sql("select_ttm_net_income_common_stockholders_by_symbol",
                                      ticker=self.ticker,
                                      ttm_net_income_url=ttm_net_income_url)
        ttm_net_income_df = self.duckdb_client.query(ttm_net_income_sql)

        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'

        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                ttm_net_income_df['report_date'])
            currency_df['symbol'] = currency + '=X'
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.currency(symbol = currency + '=X')

        ttm_net_income_df['report_date'] = pd.to_datetime(ttm_net_income_df['report_date'])
        currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

        result_df = ttm_net_income_df.copy()
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
        sql = load_sql("select_roe_by_symbol", ticker = self.ticker, url = url)
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
        sql = load_sql("select_roa_by_symbol", ticker = self.ticker, url = url)
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
        sql = load_sql("select_roic_by_symbol", ticker = self.ticker, url = url)
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
            roe,
            roa,
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
            roa,
            quarterly_net_margin,
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

    def wacc(self) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = load_sql("select_wacc_by_symbol", ticker = self.ticker, url = url)
        wacc_df = self.duckdb_client.query(sql)
        currency = load_financial_currency().get(self.ticker)
        if currency is None:
            currency = 'USD'

        if currency == 'USD':
            currency_df = pd.DataFrame()
            currency_df['report_date'] = pd.to_datetime(
                wacc_df['report_date'])
            currency_df['symbol'] = currency + '=X'
            currency_df['open'] = 1.0
            currency_df['close'] = 1.0
            currency_df['high'] = 1.0
            currency_df['low'] = 1.0
        else:
            currency_df = self.currency(symbol = currency + '=X')

        currency_df = currency_df[[
            'report_date',
            'close'
        ]]
        currency_df = currency_df.rename(columns={
            'close': 'exchange_rate',
        })

        wacc_df['report_date'] = pd.to_datetime(wacc_df['report_date'])
        currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

        wacc_df = pd.merge_asof(
            wacc_df,
            currency_df,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )
        wacc_df['total_debt_usd'] = round(wacc_df['total_debt'] / wacc_df['exchange_rate'], 0)
        wacc_df['interest_expense_usd'] = round(wacc_df['interest_expense'] / wacc_df['exchange_rate'], 0)
        wacc_df['pretax_income_usd'] = round(wacc_df['pretax_income'] / wacc_df['exchange_rate'], 0)
        wacc_df['tax_provision_usd'] = round(wacc_df['tax_provision'] / wacc_df['exchange_rate'], 0)

        market_cap_df = self.market_capitalization()

        market_cap_df['report_date'] = pd.to_datetime(market_cap_df['report_date'])

        result_df1 = pd.merge_asof(
            wacc_df,
            market_cap_df,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        max_date = wacc_df['report_date'].max()

        market_cap_after = market_cap_df.loc[
            (market_cap_df['report_date'] >= pd.Timestamp.today() - pd.DateOffset(years=5)) &
            (market_cap_df['report_date'] >= max_date)
        ]

        result_df2 = pd.merge_asof(
            market_cap_after,
            wacc_df,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )
        result_df = pd.concat([result_df1, result_df2], ignore_index=True).drop_duplicates().sort_values('report_date').reset_index(drop=True)

        result_df = result_df[[
            'symbol',
            'report_date',
            'market_capitalization',
            'exchange_rate',
            'total_debt',
            'total_debt_usd',
            'interest_expense',
            'interest_expense_usd',
            'pretax_income',
            'pretax_income_usd',
            'tax_provision',
            'tax_provision_usd',
            'tax_rate_for_calcs'
        ]]
        ten_year_returns = sp500_cagr_returns_rolling(10)
        ten_year_returns['end_date'] = pd.to_datetime(ten_year_returns['end_date'])

        result_df = pd.merge_asof(
            result_df,
            ten_year_returns,
            left_on='report_date',
            right_on='end_date',
            direction='backward'
        )

        result_df = result_df[[
            'symbol',
            'report_date',
            'market_capitalization',
            'exchange_rate',
            'total_debt',
            'total_debt_usd',
            'interest_expense',
            'interest_expense_usd',
            'pretax_income',
            'pretax_income_usd',
            'tax_provision',
            'tax_provision_usd',
            'tax_rate_for_calcs',
            'end_year',
            'cagr_returns_10_years'
        ]]

        result_df = result_df.rename(columns={
            'cagr_returns_10_years': 'sp500_10y_cagr',
            'end_year': 'sp500_cagr_end'
        })

        treasure = self.treasure.daily_treasure_yield()
        treasure['report_date'] = pd.to_datetime(treasure['report_date'])

        result_df = pd.merge_asof(
            result_df,
            treasure,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df = result_df[[
            'symbol',
            'report_date',
            'market_capitalization',
            'exchange_rate',
            'total_debt',
            'total_debt_usd',
            'interest_expense',
            'interest_expense_usd',
            'pretax_income',
            'pretax_income_usd',
            'tax_provision',
            'tax_provision_usd',
            'tax_rate_for_calcs',
            'sp500_cagr_end',
            'sp500_10y_cagr',
            'bc10_year'
        ]]

        result_df = result_df.rename(columns={
            'bc10_year': 'treasure_10y_yield',
        })

        summary = self.summary()
        result_df['beta_5y'] = summary.at[0, "beta"]

        result_df['tax_rate_for_calcs'] = np.where(
            result_df['tax_rate_for_calcs'].notna(),
            result_df['tax_rate_for_calcs'],
            result_df['tax_provision_usd'] / result_df['pretax_income_usd']
        )

        result_df['weight_of_debt'] = round(result_df['total_debt_usd'] / (result_df['total_debt_usd'] + result_df['market_capitalization']), 4)
        result_df['weight_of_equity'] = round(result_df['market_capitalization'] / (result_df['total_debt_usd'] + result_df['market_capitalization']), 4)
        result_df['cost_of_debt'] = round(result_df['interest_expense_usd'] / result_df['total_debt_usd'], 4)
        result_df['cost_of_equity'] = round(result_df['treasure_10y_yield'] + result_df['beta_5y'] * (result_df['sp500_10y_cagr'] - result_df['treasure_10y_yield']), 4)
        result_df['wacc'] = round(
            result_df['weight_of_debt'] * result_df['cost_of_debt'] * (1 - result_df['tax_rate_for_calcs']) +
            result_df['weight_of_equity'] * result_df['cost_of_equity'],
            4
        )
        return result_df

    def industry_ttm_pe(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url = url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        market_cap_table_sql = load_sql("select_market_cap_by_industry",
                                        stock_prices = self.huggingface_client.get_url_path(stock_prices),
                                        stock_shares_outstanding = self.huggingface_client.get_url_path(stock_shares_outstanding),
                                        symbols = ", ".join(f"'{s}'" for s in symbols))

        total_market_cap = self.duckdb_client.query(market_cap_table_sql)

        market_cap_cols = [col for col in total_market_cap.columns if col != 'report_date']

        total_market_cap['total_market_cap'] = total_market_cap[market_cap_cols].sum(axis=1, skipna=True)
        total_market_cap['industry'] = industry
        total_market_cap = total_market_cap[['report_date', 'industry', 'total_market_cap']]
        total_market_cap['report_date'] = pd.to_datetime(total_market_cap['report_date'])

        ttm_net_income_sql = load_sql("select_ttm_net_income_by_industry",
                                      stock_statement = self.huggingface_client.get_url_path(stock_statement),
                                      symbols = ", ".join(f"'{s}'" for s in symbols))
        ttm_net_income = self.duckdb_client.query(ttm_net_income_sql)
        ttm_net_income_df = ttm_net_income.copy()
        currency_dict = load_financial_currency()
        ttm_net_income_df['report_date'] = pd.to_datetime(ttm_net_income_df['report_date'])
        for symbol in ttm_net_income_df.columns:
            if symbol == 'report_date':
                continue
            currency = currency_dict.get(symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': ttm_net_income_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                ttm_net_income_df[['report_date', symbol]].rename(columns={symbol: 'ttm_net_income'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            ttm_net_income_df[f'{symbol}_usd'] = (merged_df['ttm_net_income'] / merged_df['close']).round(2)

        cols_to_keep = ['report_date'] + [c for c in ttm_net_income_df.columns if c.endswith('_usd')]
        ttm_net_income_usd_df = ttm_net_income_df[cols_to_keep]
        ttm_net_income_usd_df = ttm_net_income_usd_df.ffill()

        ttm_net_income_usd_cols = [col for col in ttm_net_income_usd_df.columns if col != 'report_date']
        ttm_net_income_usd_df['total_ttm_net_income'] = ttm_net_income_usd_df[ttm_net_income_usd_cols].sum(axis=1, skipna=True)
        ttm_net_income_usd_df = ttm_net_income_usd_df[['report_date', 'total_ttm_net_income']]
        ttm_net_income_usd_df['report_date'] = pd.to_datetime(ttm_net_income_usd_df['report_date'])
        df = pd.merge_asof(
                total_market_cap,
                ttm_net_income_usd_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )

        df['industry_pe'] = (df['total_market_cap'] / df['total_ttm_net_income']).replace([np.inf, -np.inf], np.nan).round(2)
        return df

    def industry_ps_ratio(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        market_cap_table_sql = load_sql("select_market_cap_by_industry",
                                        stock_prices=self.huggingface_client.get_url_path(stock_prices),
                                        stock_shares_outstanding=self.huggingface_client.get_url_path(
                                            stock_shares_outstanding),
                                        symbols=", ".join(f"'{s}'" for s in symbols))

        total_market_cap = self.duckdb_client.query(market_cap_table_sql)

        market_cap_cols = [col for col in total_market_cap.columns if col != 'report_date']

        total_market_cap['total_market_cap'] = total_market_cap[market_cap_cols].sum(axis=1, skipna=True)
        total_market_cap['industry'] = industry
        total_market_cap = total_market_cap[['report_date', 'industry', 'total_market_cap']]
        total_market_cap['report_date'] = pd.to_datetime(total_market_cap['report_date'])

        ttm_revenue_sql = load_sql("select_ttm_revenue_by_industry",
                                      stock_statement = self.huggingface_client.get_url_path(stock_statement),
                                      symbols = ", ".join(f"'{s}'" for s in symbols))
        ttm_revenue = self.duckdb_client.query(ttm_revenue_sql)
        ttm_revenue_df = ttm_revenue.copy()
        currency_dict = load_financial_currency()
        ttm_revenue_df['report_date'] = pd.to_datetime(ttm_revenue_df['report_date'])
        new_cols = {}
        for symbol in ttm_revenue_df.columns:
            if symbol == 'report_date':
                continue
            currency = currency_dict.get(symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': ttm_revenue_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                ttm_revenue_df[['report_date', symbol]].rename(columns={symbol: 'ttm_revenue'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_usd'] = (merged_df['ttm_revenue'] / merged_df['close']).round(2)

        ttm_revenue_df = pd.concat([ttm_revenue_df, pd.DataFrame(new_cols)], axis=1)

        cols_to_keep = ['report_date'] + [c for c in ttm_revenue_df.columns if c.endswith('_usd')]
        ttm_revenue_df = ttm_revenue_df[cols_to_keep]
        ttm_revenue_df = ttm_revenue_df.ffill()

        ttm_revenue_df_cols = [col for col in ttm_revenue_df.columns if col != 'report_date']
        ttm_revenue_df['total_ttm_revenue'] = ttm_revenue_df[ttm_revenue_df_cols].sum(axis=1, skipna=True)
        ttm_revenue_df = ttm_revenue_df[['report_date', 'total_ttm_revenue']].copy()
        ttm_revenue_df['report_date'] = pd.to_datetime(ttm_revenue_df['report_date'])
        df = pd.merge_asof(
                total_market_cap,
                ttm_revenue_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )

        df['industry_ps_ratio'] = (df['total_market_cap'] / df['total_ttm_revenue']).replace([np.inf, -np.inf], np.nan).round(2)
        return df

    def industry_pb_ratio(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        market_cap_table_sql = load_sql("select_market_cap_by_industry",
                                        stock_prices=self.huggingface_client.get_url_path(stock_prices),
                                        stock_shares_outstanding=self.huggingface_client.get_url_path(
                                            stock_shares_outstanding),
                                        symbols=", ".join(f"'{s}'" for s in symbols))

        total_market_cap = self.duckdb_client.query(market_cap_table_sql)

        market_cap_cols = [col for col in total_market_cap.columns if col != 'report_date']

        total_market_cap['total_market_cap'] = total_market_cap[market_cap_cols].sum(axis=1, skipna=True)
        total_market_cap['industry'] = industry
        total_market_cap = total_market_cap[['report_date', 'industry', 'total_market_cap']]
        total_market_cap['report_date'] = pd.to_datetime(total_market_cap['report_date'])

        bve_sql = load_sql("select_quarterly_book_value_of_equity_by_industry",
                                      stock_statement = self.huggingface_client.get_url_path(stock_statement),
                                      symbols = ", ".join(f"'{s}'" for s in symbols))
        bve = self.duckdb_client.query(bve_sql)
        bve_df = bve.copy()
        currency_dict = load_financial_currency()
        bve_df['report_date'] = pd.to_datetime(bve_df['report_date'])
        new_cols = {}
        for symbol in bve_df.columns:
            if symbol == 'report_date':
                continue
            currency = currency_dict.get(symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': bve_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                bve_df[['report_date', symbol]].rename(columns={symbol: 'bve'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_usd'] = (merged_df['bve'] / merged_df['close']).round(2)

        bve_df = pd.concat([bve_df, pd.DataFrame(new_cols)], axis=1)

        cols_to_keep = ['report_date'] + [c for c in bve_df.columns if c.endswith('_usd')]
        bve_df = bve_df[cols_to_keep]
        bve_df = bve_df.ffill()

        bve_df_cols = [col for col in bve_df.columns if col != 'report_date']
        bve_df['total_bve'] = bve_df[bve_df_cols].sum(axis=1, skipna=True)
        bve_df = bve_df[['report_date', 'total_bve']].copy()
        bve_df['report_date'] = pd.to_datetime(bve_df['report_date'])
        df = pd.merge_asof(
                total_market_cap,
                bve_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )

        df['industry_pb_ratio'] = (df['total_market_cap'] / df['total_bve']).replace([np.inf, -np.inf], np.nan).round(2)
        return df

    def industry_roe(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        roe_table_sql = load_sql("select_roe_by_industry",
                                        stock_statement=self.huggingface_client.get_url_path(stock_statement),
                                        symbols=", ".join(f"'{s}'" for s in symbols))
        roe_table = self.duckdb_client.query(roe_table_sql)

        net_income_common_stockholders_df = (roe_table[['report_date'] + [
            col for col in roe_table.columns
            if col.endswith('_net_income_common_stockholders')
        ]]).ffill()
        currency_dict = load_financial_currency()
        net_income_common_stockholders_df['report_date'] = pd.to_datetime(net_income_common_stockholders_df['report_date'])
        new_cols = {}
        for symbol in net_income_common_stockholders_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_net_income_common_stockholders")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': net_income_common_stockholders_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                net_income_common_stockholders_df[['report_date', symbol]].rename(columns={symbol: 'net_income_common_stockholders'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_net_income_common_stockholders_usd'] = (merged_df['net_income_common_stockholders'] / merged_df['close']).round(2)

        net_income_common_stockholders_df = pd.concat([net_income_common_stockholders_df['report_date'] , pd.DataFrame(new_cols)], axis=1)
        net_income_common_stockholders_df['total_net_income_common_stockholders'] = net_income_common_stockholders_df[[col for col in net_income_common_stockholders_df.columns if col != 'report_date']].sum(axis=1, skipna=True)
        net_income_common_stockholders_df = net_income_common_stockholders_df[['report_date', 'total_net_income_common_stockholders']]

        avg_equity_df = (roe_table[['report_date'] + [
            col for col in roe_table.columns
            if col.endswith('_avg_equity')
        ]]).ffill()
        avg_equity_df['report_date'] = pd.to_datetime(
            avg_equity_df['report_date'])
        new_cols = {}
        for symbol in avg_equity_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_avg_equity")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': avg_equity_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                avg_equity_df[['report_date', symbol]].rename(
                    columns={symbol: 'avg_equity'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_avg_equity_usd'] = (
                        merged_df['avg_equity'] / merged_df['close']).round(2)

        avg_equity_df = pd.concat(
            [avg_equity_df['report_date'], pd.DataFrame(new_cols)], axis=1)
        avg_equity_df['total_avg_equity'] = avg_equity_df[
            [col for col in avg_equity_df.columns if col != 'report_date']].sum(axis=1, skipna=True)
        avg_equity_df = avg_equity_df[
            ['report_date', 'total_avg_equity']]

        df = (
            net_income_common_stockholders_df
            .merge(avg_equity_df, on='report_date', how='outer')
            .sort_values('report_date')
            .reset_index(drop=True)
        )
        df['industry_roe'] = np.where(
            (df['total_net_income_common_stockholders'] < 0) | (df['total_avg_equity'] < 0),
            -np.abs(df['total_net_income_common_stockholders'] / df['total_avg_equity']),
            df['total_net_income_common_stockholders'] / df['total_avg_equity']
        ).round(4)
        df.insert(1, "industry", industry)
        return df

    def industry_roa(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        roa_table_sql = load_sql("select_roa_by_industry",
                                        stock_statement=self.huggingface_client.get_url_path(stock_statement),
                                        symbols=", ".join(f"'{s}'" for s in symbols))
        roa_table = self.duckdb_client.query(roa_table_sql)

        net_income_common_stockholders_df = (roa_table[['report_date'] + [
            col for col in roa_table.columns
            if col.endswith('_net_income_common_stockholders')
        ]]).ffill()
        currency_dict = load_financial_currency()
        net_income_common_stockholders_df['report_date'] = pd.to_datetime(net_income_common_stockholders_df['report_date'])
        new_cols = {}
        for symbol in net_income_common_stockholders_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_net_income_common_stockholders")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': net_income_common_stockholders_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                net_income_common_stockholders_df[['report_date', symbol]].rename(columns={symbol: 'net_income_common_stockholders'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_net_income_common_stockholders_usd'] = (merged_df['net_income_common_stockholders'] / merged_df['close']).round(2)

        net_income_common_stockholders_df = pd.concat([net_income_common_stockholders_df['report_date'] , pd.DataFrame(new_cols)], axis=1)
        net_income_common_stockholders_df['total_net_income_common_stockholders'] = net_income_common_stockholders_df[[col for col in net_income_common_stockholders_df.columns if col != 'report_date']].sum(axis=1, skipna=True)
        net_income_common_stockholders_df = net_income_common_stockholders_df[['report_date', 'total_net_income_common_stockholders']]

        avg_asserts_df = (roa_table[['report_date'] + [
            col for col in roa_table.columns
            if col.endswith('_avg_asserts')
        ]]).ffill()
        avg_asserts_df['report_date'] = pd.to_datetime(
            avg_asserts_df['report_date'])
        new_cols = {}
        for symbol in avg_asserts_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_avg_asserts")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': avg_asserts_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                avg_asserts_df[['report_date', symbol]].rename(
                    columns={symbol: 'avg_asserts'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_avg_asserts_usd'] = (
                        merged_df['avg_asserts'] / merged_df['close']).round(2)

        avg_asserts_df = pd.concat(
            [avg_asserts_df['report_date'], pd.DataFrame(new_cols)], axis=1)
        avg_asserts_df['total_avg_asserts'] = avg_asserts_df[
            [col for col in avg_asserts_df.columns if col != 'report_date']].sum(axis=1, skipna=True)
        avg_asserts_df = avg_asserts_df[
            ['report_date', 'total_avg_asserts']]

        df = (
            net_income_common_stockholders_df
            .merge(avg_asserts_df, on='report_date', how='outer')
            .sort_values('report_date')
            .reset_index(drop=True)
        )
        df['industry_roa'] = np.where(
            (df['total_net_income_common_stockholders'] < 0) | (df['total_avg_asserts'] < 0),
            -np.abs(df['total_net_income_common_stockholders'] / df['total_avg_asserts']),
            df['total_net_income_common_stockholders'] / df['total_avg_asserts']
        ).round(4)
        df.insert(1, "industry", industry)
        return df

    def industry_equity_multiplier(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]
        roe = self.industry_roe()
        roa = self.industry_roa()

        roe['report_date'] = pd.to_datetime(roe['report_date'])
        roa['report_date'] = pd.to_datetime(roa['report_date'])

        result_df = pd.merge_asof(
            roe,
            roa,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['industry_equity_multiplier'] = round(result_df['industry_roe'] / result_df['industry_roa'], 2)

        result_df = result_df[[
            'report_date',
            'industry_roe',
            'industry_roa',
            'industry_equity_multiplier'
        ]]
        result_df.insert(1, "industry", industry)
        return result_df

    def industry_quarterly_net_margin(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]

        if not industry or pd.isna(industry):
            raise ValueError(f"Unknown industry for this ticker: {self.ticker}")

        url = self.huggingface_client.get_url_path(stock_profile)
        sql = load_sql("select_tickers_by_industry", url=url, industry=industry)
        symbols = self.duckdb_client.query(sql)['symbol']
        symbols = symbols[symbols != self.ticker]
        symbols = pd.concat([pd.Series([self.ticker]), symbols], ignore_index=True)

        net_income_and_revenue_table_sql = load_sql("select_net_income_and_revenue_by_industry",
                                 stock_statement=self.huggingface_client.get_url_path(stock_statement),
                                 symbols=", ".join(f"'{s}'" for s in symbols))
        net_income_and_revenue_table = self.duckdb_client.query(net_income_and_revenue_table_sql)

        currency_dict = load_financial_currency()
        net_income_df = (net_income_and_revenue_table[['report_date'] + [
            col for col in net_income_and_revenue_table.columns
            if col.endswith('_net_income_common_stockholders')
        ]]).ffill()
        net_income_df['report_date'] = pd.to_datetime(
            net_income_df['report_date'])
        new_cols = {}
        for symbol in net_income_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_net_income_common_stockholders")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': net_income_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                net_income_df[['report_date', symbol]].rename(
                    columns={symbol: 'net_income_common_stockholders'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_net_income_usd'] = (
                    merged_df['net_income_common_stockholders'] / merged_df['close']).round(2)

        net_income_df = pd.concat(
            [net_income_df['report_date'], pd.DataFrame(new_cols)], axis=1)
        net_income_df['total_net_income'] = net_income_df[
            [col for col in net_income_df.columns if col != 'report_date']].sum(axis=1, skipna=True)

        net_income_df = net_income_df[
            ['report_date', 'total_net_income']]

        revenue_df = (net_income_and_revenue_table[['report_date'] + [
            col for col in net_income_and_revenue_table.columns
            if col.endswith('_revenue')
        ]]).ffill()
        revenue_df['report_date'] = pd.to_datetime(
            revenue_df['report_date'])
        new_cols = {}
        for symbol in revenue_df.columns:
            if symbol == 'report_date':
                continue
            currency_symbol = symbol.removesuffix("_revenue")
            currency = currency_dict.get(currency_symbol, 'USD')
            if currency == 'USD':
                currency_df = pd.DataFrame({
                    'report_date': revenue_df['report_date'],
                    'close': 1.0
                })
            else:
                currency_df = self.currency(symbol=currency + '=X')
                currency_df['report_date'] = pd.to_datetime(currency_df['report_date'])

            merged_df = pd.merge_asof(
                revenue_df[['report_date', symbol]].rename(
                    columns={symbol: 'revenue'}),
                currency_df,
                left_on='report_date',
                right_on='report_date',
                direction='backward'
            )
            new_cols[f'{symbol}_revenue_usd'] = (
                    merged_df['revenue'] / merged_df['close']).round(2)

        revenue_df = pd.concat(
            [revenue_df['report_date'], pd.DataFrame(new_cols)], axis=1)
        revenue_df['total_revenue'] = revenue_df[
            [col for col in revenue_df.columns if col != 'report_date']].sum(axis=1, skipna=True)
        revenue_df = revenue_df[
            ['report_date', 'total_revenue']]

        df = (
            net_income_df
            .merge(revenue_df, on='report_date', how='outer')
            .sort_values('report_date')
            .reset_index(drop=True)
        )
        df['industry_net_margin'] = np.where(
            (df['total_net_income'] < 0) | (df['total_revenue'] < 0),
            -np.abs(df['total_net_income'] / df['total_revenue']),
            df['total_net_income'] / df['total_revenue']
        ).round(4)
        df.insert(1, "industry", industry)
        return df

    def industry_asset_turnover(self) -> pd.DataFrame:
        info = self.info()
        industry = info['industry']
        if isinstance(industry, pd.Series):
            industry = industry.iloc[0]
        roa = self.industry_roa()
        quarterly_net_margin = self.industry_quarterly_net_margin()

        roa['report_date'] = pd.to_datetime(roa['report_date'])
        quarterly_net_margin['report_date'] = pd.to_datetime(quarterly_net_margin['report_date'])

        result_df = pd.merge_asof(
            roa,
            quarterly_net_margin,
            left_on='report_date',
            right_on='report_date',
            direction='backward'
        )

        result_df['industry_asset_turnover'] = round(result_df['industry_roa'] / result_df['industry_net_margin'], 2)

        result_df = result_df[[
            'report_date',
            'industry_roa',
            'industry_net_margin',
            'industry_asset_turnover'
        ]]
        result_df.insert(1, "industry", industry)

        return result_df

    def _quarterly_eps_yoy_growth(self, eps_column: str, current_alias: str, prev_alias: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_tailing_eps)
        sql = load_sql("select_quarterly_eps_yoy_growth_by_symbol",
                       ticker = self.ticker,
                       url = url,
                       eps_column = eps_column,
                       current_alias = current_alias,
                       prev_alias = prev_alias)
        return self.duckdb_client.query(sql)

    def _calculate_yoy_growth(self, item_name: str, period_type: str, finance_type: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_statement)
        metric_name = item_name.replace('total_', '')  # For naming consistency in output
        ttm_filter = "AND report_date != 'TTM'" if period_type == 'quarterly' else ''

        sql = load_sql("select_metric_calculate_yoy_growth_by_symbol",
                       ticker = self.ticker,
                       url = url,
                       metric_name = metric_name,
                       item_name = item_name,
                       period_type = period_type,
                       finance_type = finance_type,
                       ttm_filter = ttm_filter)
        return self.duckdb_client.query(sql)

    def _revenue_by_breakdown(self, breakdown_type: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(stock_revenue_breakdown)
        sql = load_sql(
            "select_revenue_breakdown_by_symbol",
            ticker = self.ticker,
            url = url,
            breakdown_type = breakdown_type)
        data = self.duckdb_client.query(sql)
        df_wide = data.pivot(index=['report_date'], columns='item_name', values='item_value').reset_index()
        df_wide.columns.name = None
        df_wide = df_wide.fillna(0)
        return df_wide

    def _generate_margin(self, margin_type: str, period_type: str, numerator_item: str,
                         margin_column: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path('stock_statement')
        ttm_filter = "AND report_date != 'TTM'" if period_type == 'quarterly' else ""
        finance_type_filter = \
            "AND finance_type = 'income_statement'" if margin_type in ['gross', 'operating', 'net', 'ebitda'] \
            else "AND finance_type in ('income_statement', 'cash_flow')" if margin_type == 'fcf' \
            else ""
        sql = load_sql("select_margin_for_symbol",
                       ticker = self.ticker,
                       url = url,
                       numerator_item = numerator_item,
                       margin_column = margin_column,
                       period_type = period_type,
                       ttm_filter = ttm_filter,
                       finance_type_filter = finance_type_filter)
        return self.duckdb_client.query(sql)

    def _query_data(self, table_name: str) -> pd.DataFrame:
        return self._query_data2(table_name, self.ticker)

    def _query_data2(self, table_name: str, ticker: str) -> pd.DataFrame:
        url = self.huggingface_client.get_url_path(table_name)
        sql = load_sql(
            "select_all_by_symbol",
                        ticker = ticker,
                        url = url)
        return self.duckdb_client.query(sql)

    def _statement(self, finance_type: str, period_type: str) -> Statement:
        url = self.huggingface_client.get_url_path(stock_statement)
        sql = load_sql("select_statement_by_symbol",
                       url=url,
                       ticker=self.ticker,
                       finance_type=finance_type,
                       period_type=period_type)
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