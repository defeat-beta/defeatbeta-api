import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import xlwings as xw
from .util import create_ticker


def _read_excel_data(file_path: str) -> Dict[str, Any]:
    """
    Read Excel file content using xlwings and extract all DCF analysis sections.

    Args:
        file_path: Path to the Excel file

    Returns:
        Dictionary containing all extracted data from 5 sections
    """
    # Open workbook in read-only mode (no Excel app window)
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(file_path, read_only=True, update_links=False)
        ws = wb.sheets[0]

        # ========== Section 1: Discount Rate Estimates ==========
        discount_rate_estimates = {
            "report_date": ws.range("B1").value.split("(")[-1].rstrip(")") if "(" in str(ws.range("B1").value) else None,
            "market_cap": ws.range("C2").value,
            "beta_5y": ws.range("C3").value,
            "total_debt": ws.range("C4").value,
            "interest_expense": ws.range("C5").value,
            "pretax_income": ws.range("C6").value,
            "tax_provision": ws.range("C7").value,
            "risk_free_rate": ws.range("C8").value,
            "expected_market_return": ws.range("C9").value,
            "weight_of_debt": ws.range("E2").value,
            "weight_of_equity": ws.range("E3").value,
            "cost_of_debt": ws.range("E4").value,
            "cost_of_equity": ws.range("E5").value,
            "tax_rate": ws.range("E6").value,
            "wacc": ws.range("E9").value
        }

        # ========== Section 2: Growth Estimates ==========
        # Revenue growth (3 years)
        revenue_data = []
        for i in range(3, 6):  # rows 3-5
            revenue_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        revenue_cagr = ws.range("H6").value

        # FCF growth (3 years)
        fcf_data = []
        for i in range(8, 11):  # rows 8-10
            fcf_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        fcf_cagr = ws.range("H11").value

        # EBITDA growth (3 years)
        ebitda_data = []
        for i in range(13, 16):  # rows 13-15
            ebitda_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        ebitda_cagr = ws.range("H16").value

        # Net Income growth (3 years)
        net_income_data = []
        for i in range(18, 21):  # rows 18-20
            net_income_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        net_income_cagr = ws.range("H21").value

        growth_estimates = {
            "revenue": {
                "historical": revenue_data,
                "cagr_3y": revenue_cagr
            },
            "fcf": {
                "historical": fcf_data,
                "cagr_3y": fcf_cagr
            },
            "ebitda": {
                "historical": ebitda_data,
                "cagr_3y": ebitda_cagr
            },
            "net_income": {
                "historical": net_income_data,
                "cagr_3y": net_income_cagr
            }
        }

        # ========== Section 3: DCF Template ==========
        # Get TTM label to extract date range
        ttm_revenue_label = ws.range("B23").value

        # Extract projection years from row 26
        projection_years = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            year_value = ws.range(f"{col}26").value
            if year_value:
                projection_years.append(str(year_value))

        # Extract FCF projections
        fcf_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            fcf_value = ws.range(f"{col}27").value
            if fcf_value is not None:
                fcf_projections.append(fcf_value)

        # Extract Revenue projections
        revenue_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            rev_value = ws.range(f"{col}28").value
            if rev_value is not None:
                revenue_projections.append(rev_value)

        # Extract FCF Margin projections
        fcf_margin_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            margin_value = ws.range(f"{col}29").value
            if margin_value is not None:
                fcf_margin_projections.append(margin_value)

        # Extract Terminal Value and Present Value
        terminal_values = []
        for col in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            tv_value = ws.range(f"{col}30").value
            if tv_value is not None:
                terminal_values.append(tv_value)

        present_values = []
        for col in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            pv_value = ws.range(f"{col}31").value
            if pv_value is not None:
                present_values.append(pv_value)

        dcf_template = {
            "decay_factor": ws.range("C17").value,
            "future_growth_rate_1_5y": ws.range("C18").value,
            "future_growth_rate_6_10y": ws.range("C19").value,
            "future_growth_rate_terminal": ws.range("C20").value,
            "discount_rate": ws.range("C21").value,
            "ttm_revenue": ws.range("C23").value,
            "ttm_revenue_label": ttm_revenue_label,
            "future_revenue_growth_1_5y": ws.range("C24").value,
            "future_revenue_growth_6_10y": ws.range("C25").value,
            "projections": {
                "years": projection_years,
                "fcf": fcf_projections,
                "revenue": revenue_projections,
                "fcf_margin": fcf_margin_projections,
                "terminal_value": terminal_values,
                "present_value": present_values
            },
            "total_value": ws.range("M32").value
        }

        # ========== Section 4: DCF Value ==========
        dcf_value = {
            "report_date": ws.range("B36").value.split("(")[-1].rstrip(")") if "(" in str(ws.range("B36").value) else None,
            "enterprise_value": ws.range("C37").value,
            "cash_and_st_investments": ws.range("C38").value,
            "total_debt": ws.range("C39").value,
            "equity_value": ws.range("C40").value,
            "outstanding_shares": ws.range("C41").value,
            "fair_price": ws.range("C42").value,
            "current_price": ws.range("C43").value,
            "margin_of_safety": ws.range("C44").value
        }

        # ========== Section 5: Buy/Sell Recommendation ==========
        # Read the merged cells for display
        fair_price_display = ws.range("F37").value  # Fair price value
        current_price_display = ws.range("F40").value  # Current price value
        buy_sell_signal = ws.range("F43").value  # Buy/Sell signal

        buy_sell = {
            "fair_price": fair_price_display,
            "current_price": current_price_display,
            "recommendation": buy_sell_signal,
            "upside_potential": ((fair_price_display / current_price_display) - 1) if (fair_price_display and current_price_display and current_price_display != 0) else None
        }

        return {
            "discount_rate_estimates": discount_rate_estimates,
            "growth_estimates": growth_estimates,
            "dcf_template": dcf_template,
            "dcf_value": dcf_value,
            "buy_sell": buy_sell
        }

    finally:
        wb.close()
        app.quit()


def get_stock_dcf_analysis(symbol: str):
    """
    Generate a comprehensive Discounted Cash Flow (DCF) valuation analysis for a given stock.

    This function generates an Excel DCF model and extracts all calculated values into a structured
    format. The analysis includes discount rate calculations, growth estimates, 10-year projections,
    and fair value assessment with buy/sell recommendation.

    Args:
        symbol (str):
            Stock ticker symbol (case-insensitive).
            Examples: "AAPL", "TSLA", "MSFT", "GOOGL"

    Returns:
        dict: Comprehensive DCF analysis containing:
            - symbol (str): Normalized ticker symbol (uppercase)
            - file_path (str): Absolute path to Excel file in Downloads folder
            - file_name (str): Filename (e.g., "AAPL_DCF_Analysis.xlsx")
            - discount_rate_estimates (dict): WACC calculation components
            - growth_estimates (dict): Historical growth rates for Revenue, FCF, EBITDA, Net Income
            - dcf_template (dict): Growth assumptions and 10-year cash flow projections
            - dcf_value (dict): Enterprise value, equity value, fair price calculations
            - buy_sell (dict): Investment recommendation and upside potential

    Error Response:
        dict: {
            "symbol": str,
            "error": str  # Error message if generation fails
        }

    Example Success Response:
        {
            "symbol": "AAPL",
            "file_path": "/Users/username/Downloads/AAPL_DCF_Analysis.xlsx",
            "file_name": "AAPL_DCF_Analysis.xlsx",
            "discount_rate_estimates": {...},
            "growth_estimates": {...},
            "dcf_template": {...},
            "dcf_value": {...},
            "buy_sell": {
                "fair_price": 175.50,
                "current_price": 150.00,
                "recommendation": "BUY",
                "upside_potential": 0.17
            }
        }
    """

    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    try:
        # Generate DCF Excel file
        result = ticker.dcf()

        if not result or "file_path" not in result:
            return {
                "symbol": symbol,
                "error": (
                    f"Failed to generate DCF analysis for {symbol}. "
                    "The ticker may not have sufficient financial data, or the symbol may be invalid."
                )
            }

        original_path = result["file_path"]

        # Create descriptive filename
        new_filename = f"{symbol}_DCF_Analysis.xlsx"

        # Copy to Downloads folder
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(exist_ok=True)
        downloads_path = downloads_dir / new_filename

        # Copy file (overwrite if exists)
        shutil.copy2(original_path, downloads_path)

        # Read and extract all data from Excel file
        excel_data = _read_excel_data(str(downloads_path))

        # Return comprehensive analysis data
        return {
            "symbol": symbol,
            "file_path": str(downloads_path),
            "file_name": new_filename,
            **excel_data
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
