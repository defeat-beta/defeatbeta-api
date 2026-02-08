from .util import create_ticker


def get_stock_dcf_analysis(symbol: str):
    """
    Generate a comprehensive Discounted Cash Flow (DCF) valuation Excel spreadsheet for a given stock.

    The DCF method estimates a company's intrinsic value by projecting future free cash flows
    and discounting them back to present value using the Weighted Average Cost of Capital (WACC).
    This tool generates a professional Excel file with all calculations, growth assumptions,
    discount rates, and fair value estimates.

    Args:
        symbol (str):
            Stock ticker symbol, e.g., "AAPL", "TSLA", "QCOM" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,              # Stock ticker symbol
            "file_path": str,           # Absolute path to the generated Excel file
            "description": str,         # Brief description of the analysis
            "note": str                 # Important instructions for the AI
        }

    What's in the Excel file:
        - Discount Rate Estimates (WACC, Cost of Equity, Cost of Debt)
        - Growth Estimates (Historical 3-year CAGR for Revenue, FCF, EBITDA, Net Income)
        - DCF Template (10-year cash flow projections with present value calculations)
        - DCF Valuation (Enterprise Value, Fair Price, Current Price, Margin of Safety)
        - Investment Recommendation (Buy/Sell based on fair value vs current price)

    Important:
        The Excel file is fully editable. Users can adjust growth assumptions, discount rates,
        and other parameters to perform sensitivity analysis. All formulas will automatically recalculate.

    Example:
        >>> get_stock_dcf_analysis("AAPL")
        {
            "symbol": "AAPL",
            "file_path": "/tmp/defeatbeta/AAPL.xlsx",
            "description": "DCF Valuation Analysis for AAPL",
            "note": "DCF Excel file generated successfully. To view the complete analysis, ..."
        }
    """

    symbol = symbol.upper()
    ticker = create_ticker(symbol)

    try:
        result = ticker.dcf()

        if not result or "file_path" not in result:
            return {
                "symbol": symbol,
                "error": "Failed to generate DCF analysis. The ticker may not have sufficient financial data."
            }

        return {
            "symbol": symbol,
            "file_path": result["file_path"],
            "description": result.get("description", f"DCF Valuation Analysis for {symbol}"),
            "note": (
                f"DCF Excel file generated successfully at: {result['file_path']}\n\n"
                "To view the complete DCF analysis with all details:\n"
                "1. Use the Read tool to read the Excel file at the path above\n"
                "2. The Excel contains 5 sections: Discount Rate Estimates, Growth Estimates, "
                "DCF Template (10-year projections), DCF Value (Fair Price), and Investment Recommendation\n"
                "3. Read the file to extract fair value, current price, buy/sell recommendation, "
                "WACC, growth rates, and other valuation metrics\n\n"
                "The Excel file is fully editable for sensitivity analysis."
            )
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
