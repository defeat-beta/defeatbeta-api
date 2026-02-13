from typing import Dict, Any, Optional, List
import xlwings as xw
from .util import create_ticker


def _read_excel_data(file_path: str) -> Dict[str, Any]:
    """
    Read Excel file content using xlwings and extract all DCF analysis sections.

    The Excel file will remain open after reading, allowing users to view and edit it directly.

    Args:
        file_path: Path to the Excel file

    Returns:
        Dictionary containing all extracted data from 5 sections
    """
    # Open workbook with visible Excel window
    app = xw.App(visible=True, add_book=False)
    wb = app.books.open(file_path, read_only=True, update_links=False)

    try:
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
        for i in range(9, 12):  # rows 9-11
            fcf_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        fcf_cagr = ws.range("H12").value

        # EBITDA growth (3 years)
        ebitda_data = []
        for i in range(15, 18):  # rows 15-17
            ebitda_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        ebitda_cagr = ws.range("H18").value

        # Net Income growth (3 years)
        net_income_data = []
        for i in range(21, 24):  # rows 21-23
            net_income_data.append({
                "date": ws.range(f"G{i}").value,
                "value": ws.range(f"H{i}").value,
                "yoy_growth": ws.range(f"I{i}").value
            })
        net_income_cagr = ws.range("H24").value

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
        # Extract projection years from row 26
        projection_years = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            year_value = ws.range(f"{col}26").value
            if year_value:
                projection_years.append(str(year_value))

        # Extract FCF projections (row 27)
        fcf_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            fcf_value = ws.range(f"{col}27").value
            if fcf_value is not None:
                fcf_projections.append(fcf_value)

        # Extract Terminal Value (row 28, only column M has value)
        terminal_value = ws.range("M28").value

        # Extract Total Value projections (row 29)
        total_value_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            total_val = ws.range(f"{col}29").value
            if total_val is not None:
                total_value_projections.append(total_val)

        # Extract FCF Margin projections (row 30)
        fcf_margin_projections = []
        for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
            margin_value = ws.range(f"{col}30").value
            if margin_value is not None:
                fcf_margin_projections.append(margin_value)

        # Extract Historical FCF Margin data (rows 32-33, dynamically)
        # Check if historical data exists by looking for "Year (Historical)" label
        historical_fcf_margin = {}
        year_historical_label = ws.range("B32").value

        if year_historical_label and "Historical" in str(year_historical_label):
            # Read historical years and FCF margins
            col_index = 0
            for col in ['C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M']:
                year_value = ws.range(f"{col}32").value
                margin_value = ws.range(f"{col}33").value

                # Stop when we hit empty cells
                if year_value is None or year_value == "":
                    break

                # Store as key-value pair: year -> margin
                historical_fcf_margin[str(year_value)] = margin_value
                col_index += 1

        # Read growth rate values and their components
        future_growth_1_5y = ws.range("C18").value
        future_growth_6_10y = ws.range("C19").value
        future_growth_terminal = ws.range("C20").value

        revenue_cagr_val = ws.range("H6").value
        fcf_cagr_val = ws.range("H12").value
        ebitda_cagr_val = ws.range("H18").value
        ni_cagr_val = ws.range("H24").value
        decay_factor_val = ws.range("C17").value
        risk_free_rate_val = ws.range("C8").value

        dcf_template = {
            "decay_factor": decay_factor_val,
            "future_growth_rate_1_5y": future_growth_1_5y,
            "future_growth_rate_1_5y_explanation": {
                "formula": "Revenue_CAGR × 0.4 + FCF_CAGR × 0.3 + EBITDA_CAGR × 0.2 + NI_CAGR × 0.1",
                "description": "Weighted average of historical 3-year CAGRs",
                "components": {
                    "revenue_cagr": {"value": revenue_cagr_val, "weight": 0.4, "rationale": "Primary growth driver"},
                    "fcf_cagr": {"value": fcf_cagr_val, "weight": 0.3, "rationale": "Cash generation sustainability"},
                    "ebitda_cagr": {"value": ebitda_cagr_val, "weight": 0.2, "rationale": "Operational efficiency"},
                    "net_income_cagr": {"value": ni_cagr_val, "weight": 0.1, "rationale": "Profitability trend"}
                }
            },
            "future_growth_rate_6_10y": future_growth_6_10y,
            "future_growth_rate_6_10y_explanation": {
                "formula": "MAX(Growth_1_5Y × Decay_Factor ^ 5, Risk_Free_Rate)",
                "description": "Decayed growth rate with risk-free rate floor",
                "components": {
                    "base_growth": future_growth_1_5y,
                    "decay_factor": decay_factor_val,
                    "years_decayed": 5,
                    "decayed_growth": future_growth_1_5y * (decay_factor_val ** 5) if decay_factor_val else None,
                    "risk_free_rate_floor": risk_free_rate_val
                },
                "rationale": "Growth naturally slows over time. Floor at risk-free rate ensures minimum growth matches economic baseline"
            },
            "future_growth_rate_terminal": future_growth_terminal,
            "future_growth_rate_terminal_explanation": {
                "formula": "Risk_Free_Rate (10Y Treasury)",
                "description": "Perpetual growth rate set to risk-free rate",
                "components": {
                    "risk_free_rate": risk_free_rate_val
                },
                "rationale": "Conservative assumption: mature companies cannot grow faster than the economy indefinitely. 10Y Treasury rate represents long-term economic growth expectation"
            },
            "discount_rate": ws.range("C21").value,
            "ttm_revenue": ws.range("C22").value,
            "ttm_revenue_label": ws.range("B22").value,
            "future_revenue_growth_1_5y": ws.range("C23").value,
            "future_revenue_growth_6_10y": ws.range("C24").value,
            "projections": {
                "years": projection_years,
                "fcf": fcf_projections,
                "terminal_value": terminal_value,
                "total_value": total_value_projections,
                "fcf_margin": fcf_margin_projections
            },
            "historical_fcf_margin": historical_fcf_margin
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
            - file_path (str): Absolute path to generated Excel file
            - discount_rate_estimates (dict): WACC calculation components
            - growth_estimates (dict): Historical growth rates for Revenue, FCF, EBITDA, Net Income
            - dcf_template (dict): Growth assumptions, 10-year cash flow projections, and historical FCF margin
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
            "file_path": "/tmp/defeatbeta/dcf/AAPL.xlsx",
            "discount_rate_estimates": {...},
            "growth_estimates": {...},
            "dcf_template": {
                "future_growth_rate_1_5y": 0.0842,
                "future_growth_rate_1_5y_explanation": {
                    "formula": "Revenue_CAGR × 0.4 + FCF_CAGR × 0.3 + EBITDA_CAGR × 0.2 + NI_CAGR × 0.1",
                    "description": "Weighted average of historical 3-year CAGRs",
                    "components": {...}
                },
                "future_growth_rate_6_10y": 0.0422,
                "future_growth_rate_6_10y_explanation": {
                    "formula": "MAX(Growth_1_5Y × Decay_Factor ^ 5, Risk_Free_Rate)",
                    "description": "Decayed growth rate with risk-free rate floor",
                    "components": {...}
                },
                "future_growth_rate_terminal": 0.0422,
                "future_growth_rate_terminal_explanation": {
                    "formula": "Risk_Free_Rate (10Y Treasury)",
                    "description": "Perpetual growth rate set to risk-free rate",
                    "rationale": "Conservative assumption: mature companies cannot grow faster than the economy indefinitely"
                },
                "projections": {...},
                "historical_fcf_margin": {...}
            },
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

        file_path = result["file_path"]

        # Read and extract all data from Excel file
        excel_data = _read_excel_data(file_path)

        # Return comprehensive analysis data
        return {
            "symbol": symbol,
            "file_path": file_path,
            **excel_data
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
