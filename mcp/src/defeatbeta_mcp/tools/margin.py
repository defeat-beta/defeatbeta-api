from defeatbeta_api.data.ticker import Ticker


def get_stock_quarterly_gross_margin(symbol: str):
    """
    Retrieve quarterly gross margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "gross_profit": decimal | None,
                    "total_revenue": decimal | None,
                    "gross_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_gross_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "gross_profit": row.get("gross_profit"),
            "total_revenue": row.get("total_revenue"),
            "gross_margin": row.get("gross_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }

def get_stock_annual_gross_margin(symbol: str):
    """
    Retrieve annual gross margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "gross_profit": decimal | None,
                    "total_revenue": decimal | None,
                    "gross_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_gross_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "gross_profit": row.get("gross_profit"),
            "total_revenue": row.get("total_revenue"),
            "gross_margin": row.get("gross_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_quarterly_operating_margin(symbol: str):
    """
    Retrieve quarterly operating margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "operating_income": decimal | None,
                    "total_revenue": decimal | None,
                    "operating_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_operating_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "operating_income": row.get("operating_income"),
            "total_revenue": row.get("total_revenue"),
            "operating_margin": row.get("operating_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_annual_operating_margin(symbol: str):
    """
    Retrieve annual operating margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "operating_income": decimal | None,
                    "total_revenue": decimal | None,
                    "operating_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_operating_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "operating_income": row.get("operating_income"),
            "total_revenue": row.get("total_revenue"),
            "operating_margin": row.get("operating_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_quarterly_net_margin(symbol: str):
    """
    Retrieve quarterly net margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "net_income_common_stockholders": decimal | None,
                    "total_revenue": decimal | None,
                    "net_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_net_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "total_revenue": row.get("total_revenue"),
            "net_margin": row.get("net_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_annual_net_margin(symbol: str):
    """
    Retrieve annual net margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "net_income_common_stockholders": decimal | None,
                    "total_revenue": decimal | None,
                    "net_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_net_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "net_income_common_stockholders": row.get("net_income_common_stockholders"),
            "total_revenue": row.get("total_revenue"),
            "net_margin": row.get("net_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_quarterly_ebitda_margin(symbol: str):
    """
    Retrieve quarterly ebitda margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "ebitda": decimal | None,
                    "total_revenue": decimal | None,
                    "ebitda_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_ebitda_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "ebitda": row.get("ebitda"),
            "total_revenue": row.get("total_revenue"),
            "ebitda_margin": row.get("ebitda_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_annual_ebitda_margin(symbol: str):
    """
    Retrieve annual ebitda margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "ebitda": decimal | None,
                    "total_revenue": decimal | None,
                    "ebitda_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_ebitda_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "ebitda": row.get("ebitda"),
            "total_revenue": row.get("total_revenue"),
            "ebitda_margin": row.get("ebitda_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_quarterly_fcf_margin(symbol: str):
    """
    Retrieve quarterly fcf margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "free_cash_flow": decimal | None,
                    "total_revenue": decimal | None,
                    "fcf_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.quarterly_fcf_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "free_cash_flow": row.get("free_cash_flow"),
            "total_revenue": row.get("total_revenue"),
            "fcf_margin": row.get("fcf_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_stock_annual_fcf_margin(symbol: str):
    """
    Retrieve annual fcf margin data for a given stock symbol.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "period_type": "annual",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "free_cash_flow": decimal | None,
                    "total_revenue": decimal | None,
                    "fcf_margin": decimal | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.annual_fcf_margin()

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "free_cash_flow": row.get("free_cash_flow"),
            "total_revenue": row.get("total_revenue"),
            "fcf_margin": row.get("fcf_margin")
        })

    return {
        "symbol": symbol,
        "period_type": "annual",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }


def get_industry_quarterly_gross_margin(symbol: str):
    """
    Retrieve quarterly gross margin for the industry that the given
    stock symbol belongs to.

    Args:
        symbol (str): Stock ticker symbol (e.g. "TSLA", "AMD", "NVDA").

    Returns:
        dict: {
            "symbol": str,
            "industry": str,
            "period_type": "quarterly",
            "periods": list[str],        # report dates (oldest -> newest)
            "rows_returned": int,
            "data": [
                {
                    "period": str,
                    "total_gross_profit": float | None,
                    "total_revenue": float | None,
                    "industry_gross_margin": float | None
                },
                ...
            ]
        }
    """
    symbol = symbol.upper()
    ticker = Ticker(symbol)

    df = ticker.industry_quarterly_gross_margin()

    industry_name = df["industry"].iloc[0] if "industry" in df.columns else None

    data = []
    for _, row in df.iterrows():
        data.append({
            "period": row.get("report_date"),
            "total_gross_profit": row.get("total_gross_profit"),
            "total_revenue": row.get("total_revenue"),
            "industry_gross_margin": row.get("industry_gross_margin")
        })

    return {
        "symbol": symbol,
        "industry": industry_name,
        "period_type": "quarterly",
        "periods": [d["period"] for d in data],
        "rows_returned": len(data),
        "data": data
    }
