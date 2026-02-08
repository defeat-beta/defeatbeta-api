import shutil
from pathlib import Path
from .util import create_ticker


def get_stock_dcf_analysis(symbol: str):
    """
    Generate a comprehensive Discounted Cash Flow (DCF) valuation Excel spreadsheet for a given stock.

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
                f"📁 File Location:\n"
                f"   • Path: {downloads_path}\n"
                f"   • Filename: {new_filename}\n"
                f"   • Folder: Downloads\n\n"
                f"📊 The Excel file contains complete DCF valuation analysis including:\n"
                f"   • WACC and discount rate calculations\n"
                f"   • Historical growth rates (Revenue, FCF, EBITDA, Net Income)\n"
                f"   • 10-year cash flow projections\n"
                f"   • Fair value estimate and current price comparison\n"
                f"   • Investment recommendation (Buy/Hold/Sell)\n"
                f"   • All formulas are editable for sensitivity analysis\n\n"
                f"🎯 Please inform the user:\n"
                f"   \"I've generated a DCF valuation analysis for {symbol} and saved it to your Downloads folder.\n"
                f"   The file is named '{new_filename}'.\n"
                f"   You can open it in Excel to view the complete analysis with all calculations and assumptions.\""
            )
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
