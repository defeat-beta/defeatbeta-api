import pandas as pd

from defeatbeta_api.data.ticker import Ticker
from .util import get_currency

def get_stock_quarterly_revenue_yoy_growth(symbol: str):
    """
    Retrieve historical quarterly Year-over-Year (YoY) revenue growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                 # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                      # Revenue growth is measured on a quarterly basis
            "periods": list[str],                            # List of fiscal period end dates
            "rows_returned": int,                            # Number of periods returned
            "data": list[dict],                              # List of records with:
                - period (str):                              # Fiscal period end date
                - revenue (decimal | None):                  # Revenue for the current quarter
                - prev_year_revenue (decimal | None):        # Revenue from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):               # Year-over-Year revenue growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_revenue_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "revenue": row.get("revenue"),
            "prev_year_revenue": row.get("prev_year_revenue"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_revenue_yoy_growth(symbol: str):
    """
    Retrieve historical annual Year-over-Year (YoY) revenue growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                 # Reporting currency (e.g., "USD")
            "period_type": "annual",                         # Revenue growth is measured on a annual basis
            "periods": list[str],                            # List of fiscal period end dates
            "rows_returned": int,                            # Number of periods returned
            "data": list[dict],                              # List of records with:
                - period (str):                              # Fiscal period end date
                - revenue (decimal | None):                  # Revenue for the current quarter
                - prev_year_revenue (decimal | None):        # Revenue from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):               # Year-over-Year revenue growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_revenue_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "revenue": row.get("revenue"),
            "prev_year_revenue": row.get("prev_year_revenue"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_quarterly_operating_income_yoy_growth(symbol: str):
    """
    Retrieve historical quarterly Year-over-Year (YoY) operating income growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                    # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                         # Operating income growth is measured on a quarterly basis
            "periods": list[str],                               # List of fiscal period end dates
            "rows_returned": int,                               # Number of periods returned
            "data": list[dict],                                 # List of records with:
                - period (str):                                 # Fiscal period end date
                - operating_income (decimal | None):            # Operating income for the current quarter
                - prev_year_operating_income (decimal | None):  # Operating income from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):                  # Year-over-Year Operating income growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_operating_income_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "operating_income": row.get("operating_income"),
            "prev_year_operating_income": row.get("prev_year_operating_income"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_operating_income_yoy_growth(symbol: str):
    """
    Retrieve historical annual Year-over-Year (YoY) operating income growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                    # Reporting currency (e.g., "USD")
            "period_type": "annual",                            # Operating income growth is measured on a annual basis
            "periods": list[str],                               # List of fiscal period end dates
            "rows_returned": int,                               # Number of periods returned
            "data": list[dict],                                 # List of records with:
                - period (str):                                 # Fiscal period end date
                - operating_income (decimal | None):            # Operating income for the current quarter
                - prev_year_operating_income (decimal | None):  # Operating income from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):                  # Year-over-Year Operating income growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_operating_income_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "operating_income": row.get("operating_income"),
            "prev_year_operating_income": row.get("prev_year_operating_income"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_quarterly_ebitda_yoy_growth(symbol: str):
    """
    Retrieve historical quarterly Year-over-Year (YoY) EBITDA growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                          # Reporting currency (e.g., "USD")
            "period_type": "quarterly",               # EBITDA growth is measured on a quarterly basis
            "periods": list[str],                     # List of fiscal period end dates
            "rows_returned": int,                     # Number of periods returned
            "data": list[dict],                       # List of records with:
                - period (str):                       # Fiscal period end date
                - ebitda (decimal | None):            # EBITDA for the current quarter
                - prev_year_ebitda (decimal | None):  # EBITDA from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):        # Year-over-Year EBITDA growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_ebitda_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "ebitda": row.get("ebitda"),
            "prev_year_ebitda": row.get("prev_year_ebitda"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_ebitda_yoy_growth(symbol: str):
    """
    Retrieve historical annual Year-over-Year (YoY) EBITDA growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                          # Reporting currency (e.g., "USD")
            "period_type": "annual",                  # EBITDA growth is measured on a annual basis
            "periods": list[str],                     # List of fiscal period end dates
            "rows_returned": int,                     # Number of periods returned
            "data": list[dict],                       # List of records with:
                - period (str):                       # Fiscal period end date
                - ebitda (decimal | None):            # EBITDA for the current quarter
                - prev_year_ebitda (decimal | None):  # EBITDA from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):        # Year-over-Year EBITDA growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_ebitda_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "ebitda": row.get("ebitda"),
            "prev_year_ebitda": row.get("prev_year_ebitda"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_quarterly_net_income_yoy_growth(symbol: str):
    """
    Retrieve historical quarterly Year-over-Year (YoY) Net Income growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                                    # Reporting currency (e.g., "USD")
            "period_type": "quarterly",                                         # Net Income growth is measured on a quarterly basis
            "periods": list[str],                                               # List of fiscal period end dates
            "rows_returned": int,                                               # Number of periods returned
            "data": list[dict],                                                 # List of records with:
                - period (str):                                                 # Fiscal period end date
                - net_income_common_stockholders (decimal | None):              # Net Income for the current quarter
                - prev_year_net_income_common_stockholders (decimal | None):    # Net Income from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):                                  # Year-over-Year Net Income growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_net_income_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "prev_year_net_income_common_stockholders": row.get("prev_year_net_income_common_stockholders"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_net_income_yoy_growth(symbol: str):
    """
    Retrieve historical annual Year-over-Year (YoY) Net Income growth data
    for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "currency": str,                                                    # Reporting currency (e.g., "USD")
            "period_type": "annual",                                            # Net Income growth is measured on a annual basis
            "periods": list[str],                                               # List of fiscal period end dates
            "rows_returned": int,                                               # Number of periods returned
            "data": list[dict],                                                 # List of records with:
                - period (str):                                                 # Fiscal period end date
                - net_income_common_stockholders (decimal | None):              # Net Income for the current quarter
                - prev_year_net_income_common_stockholders (decimal | None):    # Net Income from the same fiscal quarter in the prior year
                - yoy_growth (decimal | None):                                  # Year-over-Year Net Income growth rate
        }
    """

    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_net_income_yoy_growth()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "prev_year_net_income_common_stockholders": row.get("prev_year_net_income_common_stockholders"),
            "yoy_growth": row.get("yoy_growth")
        })

    return {
        "symbol": symbol,
        "currency": get_currency(symbol),
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }