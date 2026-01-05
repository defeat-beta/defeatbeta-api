import pandas as pd

from defeatbeta_api.data.ticker import Ticker


def get_stock_quarterly_asset_turnover(symbol: str):
    """
        Retrieve historical Assert Turnover data for a given stock symbol.

        In DuPont Analysis, the Assert Turnover can be derived from ROA and Net Margin:
        Assert Turnover = ROA / Net Margin

        Args:
            symbol (str):
                Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

        Returns:
            dict: {
                "symbol": str,
                "period_type": "quarterly",           # Equity Multiplier is reported on a quarterly basis
                "periods": list[str],                 # List of fiscal period end dates
                "rows_returned": int,                 # Number of periods returned
                "data": list[dict],                   # List of records with:
                    - period (str):                   # Fiscal period end date
                    - roa (decimal):                  # Return on Assets (ROA)
                    - net_margin (decimal):           # Net Income Margin
                    - asset_turnover (decimal):       # Asset Turnover
            }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.asset_turnover()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "roa": row.get("roa"),
            "net_margin": row.get("net_margin"),
            "asset_turnover": row.get("asset_turnover")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_industry_quarterly_asset_turnover(symbol: str):
    """
        Retrieve historical industry-level Assert Turnover data
        for the industry to which a given stock symbol belongs.

        In DuPont Analysis, the Assert Turnover can be derived from ROA and Net Margin:
        Industry Assert Turnover = Industry ROA / Industry Net Margin

        Args:
            symbol (str):
                Stock ticker symbol, e.g., "TSLA", "AAPL" (case-insensitive).

        Returns:
            dict: {
                "symbol": str,
                "period_type": "quarterly",               # Equity Multiplier is reported on a quarterly basis
                "periods": list[str],                     # List of fiscal period end dates
                "rows_returned": int,                     # Number of periods returned
                "data": list[dict],                       # List of records with:
                    - period (str):                       # Fiscal period end date
                    - industry(str)                       # Industry name
                    - industry_roa (decimal):             # Return on Assets (ROA)
                    - industry_net_margin (decimal):      # Net Income Margin
                    - industry_asset_turnover (decimal):  # Asset Turnover
            }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.industry_asset_turnover()
    df['report_date'] = (
        pd.to_datetime(df['report_date'], errors='coerce')
        .dt.strftime('%Y-%m-%d')
    )

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "industry": row.get("industry"),
            "industry_roa": row.get("industry_roa"),
            "industry_net_margin": row.get("industry_net_margin"),
            "industry_asset_turnover": row.get("industry_asset_turnover")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }