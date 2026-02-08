import shutil
from pathlib import Path
from .util import create_ticker


def get_stock_dcf_analysis(symbol: str):
    """
    Generate a comprehensive Discounted Cash Flow (DCF) valuation Excel spreadsheet for a given stock.

    The DCF method estimates a company's intrinsic value by projecting future free cash flows
    and discounting them back to present value using the Weighted Average Cost of Capital (WACC).

    This tool generates a professional Excel file containing:
    - Discount Rate Estimates: WACC, Cost of Equity, Cost of Debt with detailed calculations
    - Growth Estimates: 3-year historical CAGR for Revenue, FCF, EBITDA, and Net Income
    - DCF Template: 10-year cash flow projections with discount factors and present values
    - DCF Valuation: Enterprise Value, Equity Value, Fair Price per share
    - Investment Recommendation: Buy/Hold/Sell decision based on fair value vs current price
    - Supporting Data: All assumptions, formulas, and intermediate calculations

    The Excel file is fully interactive and editable. Users can modify growth assumptions,
    discount rates, terminal growth rates, and other parameters to perform sensitivity analysis.
    All formulas will automatically recalculate based on changes.

    Args:
        symbol (str):
            Stock ticker symbol (case-insensitive).
            Examples: "AAPL", "TSLA", "MSFT", "GOOGL"

    Returns:
        dict: {
            "symbol": str,                  # Normalized ticker symbol (uppercase)
            "file_path": str,               # Absolute path to Excel file in Downloads folder
            "file_name": str,               # Filename only (e.g., "AAPL_DCF_Analysis.xlsx")
            "downloads_location": str,      # User-friendly location description
            "description": str,             # Brief description of the analysis
            "note": str                     # Detailed instructions for AI on how to present the file
        }

    Error Response:
        dict: {
            "symbol": str,
            "error": str                    # Error message if generation fails
        }

    Example Success Response:
        {
            "symbol": "AAPL",
            "file_path": "/Users/username/Downloads/AAPL_DCF_Analysis.xlsx",
            "file_name": "AAPL_DCF_Analysis.xlsx",
            "downloads_location": "Downloads folder",
            "description": "DCF Valuation Analysis for AAPL",
            "note": "Instructions for presenting the file to user..."
        }

    Use Cases:
        - Investment analysis and stock valuation
        - Due diligence for M&A transactions
        - Portfolio management and stock screening
        - Sensitivity analysis with different assumptions
        - Educational purposes to understand DCF methodology

    Technical Details:
        - File Format: Excel (.xlsx) with formulas
        - Calculation Method: Discounted Cash Flow (DCF) with WACC
        - Projection Period: 10 years plus terminal value
        - Currency: Automatically uses company's reporting currency
        - Data Source: Historical financials from defeatbeta-api

    Note:
        This tool does NOT parse or return the Excel content. It generates the file
        and instructs the AI to inform the user where to find it. The user must
        open the Excel file directly to view the complete DCF analysis.
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

        return {
            "symbol": symbol,
            "file_path": str(downloads_path),
            "file_name": new_filename,
            "downloads_location": "Downloads folder",
            "description": f"DCF Valuation Analysis for {symbol}",
            "note": (
                f"✅ DCF Excel file successfully generated for {symbol}!\n\n"
                f"📊 File Details:\n"
                f"   • Filename: {new_filename}\n"
                f"   • Location: {downloads_path}\n"
                f"   • Format: Excel (.xlsx) with formulas\n\n"
                f"📋 Excel Content Overview:\n"
                f"   1. Discount Rate Section:\n"
                f"      - WACC (Weighted Average Cost of Capital)\n"
                f"      - Cost of Equity (calculated using CAPM)\n"
                f"      - Cost of Debt (after-tax)\n"
                f"      - Beta, Risk-Free Rate, Market Risk Premium\n\n"
                f"   2. Growth Estimates Section:\n"
                f"      - Revenue CAGR (3-year historical)\n"
                f"      - Free Cash Flow CAGR (3-year historical)\n"
                f"      - EBITDA CAGR (3-year historical)\n"
                f"      - Net Income CAGR (3-year historical)\n"
                f"      - Year-over-year growth details\n\n"
                f"   3. DCF Template Section:\n"
                f"      - Base Year (TTM) Free Cash Flow\n"
                f"      - 10-year cash flow projections\n"
                f"      - Discount factors for each year\n"
                f"      - Present value calculations\n"
                f"      - Terminal value estimation\n"
                f"      - Total Enterprise Value\n\n"
                f"   4. DCF Valuation Section:\n"
                f"      - Enterprise Value (EV)\n"
                f"      - Plus: Cash and Cash Equivalents\n"
                f"      - Minus: Total Debt\n"
                f"      - Equals: Equity Value\n"
                f"      - Fair Price per Share\n"
                f"      - Current Market Price\n"
                f"      - Margin of Safety (%)\n\n"
                f"   5. Investment Recommendation:\n"
                f"      - Buy/Hold/Sell decision\n"
                f"      - Based on fair value vs. current price comparison\n\n"
                f"🎯 IMPORTANT - Instructions for AI:\n\n"
                f"   Please inform the user with the following message:\n\n"
                f"   \"✅ DCF Analysis Complete!\n\n"
                f"   📁 I've saved the DCF valuation Excel file to your Downloads folder:\n"
                f"      • Filename: {new_filename}\n"
                f"      • Full path: {downloads_path}\n\n"
                f"   📊 To view the complete analysis:\n"
                f"      1. Open your Downloads folder\n"
                f"      2. Double-click on '{new_filename}' to open it in Excel\n\n"
                f"   The Excel file contains:\n"
                f"      • Complete DCF calculations with all formulas\n"
                f"      • WACC and discount rate breakdown\n"
                f"      • 10-year cash flow projections\n"
                f"      • Fair value estimate and investment recommendation\n"
                f"      • All assumptions are editable for sensitivity analysis\n\n"
                f"   💡 Tip: You can modify the growth rate assumptions in the Excel file,\n"
                f"   and all calculations will automatically update.\"\n\n"
                f"⚠️  DO NOT attempt to read or parse the Excel file programmatically.\n"
                f"    Simply present the above message to the user and let them open the file."
            )
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
