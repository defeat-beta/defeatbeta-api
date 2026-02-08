import os
import shutil
from pathlib import Path
from .util import create_ticker


def get_stock_dcf_analysis(symbol: str):
    """
    Generate a comprehensive Discounted Cash Flow (DCF) valuation Excel spreadsheet for a given stock.

    Args:
        symbol (str): Stock ticker symbol, e.g., "AAPL", "TSLA", "QCOM" (case-insensitive).

    Returns:
        dict: {
            "symbol": str,
            "file_path": str,           # Path in Downloads folder
            "original_path": str,       # Original path in /tmp
            "file_name": str,
            "description": str,
            "note": str
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
                "error": "Failed to generate DCF analysis. The ticker may not have sufficient financial data."
            }

        original_path = result["file_path"]
        new_filename = f"{symbol}_DCF_Analysis.xlsx"

        # Try to copy to Downloads folder
        downloads_path = None
        try:
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(exist_ok=True)
            downloads_path = downloads_dir / new_filename
            shutil.copy2(original_path, downloads_path)
        except Exception as e:
            pass  # If copy fails, we'll just use original path

        # Determine which path to return
        final_path = str(downloads_path) if downloads_path else original_path

        return {
            "symbol": symbol,
            "file_path": final_path,
            "original_path": original_path,
            "file_name": new_filename,
            "description": result.get("description", f"DCF Valuation Analysis for {symbol}"),
            "note": (
                f"✅ DCF Excel file generated successfully!\n\n"
                f"📁 Primary location: {final_path}\n"
                f"📁 Original location: {original_path}\n"
                f"📊 Filename: {new_filename}\n\n"
                f"🎯 INSTRUCTIONS FOR AI:\n"
                f"  1. Inform the user that the DCF file has been generated\n"
                f"  2. Tell them the file location: {final_path}\n"
                f"  3. DO NOT try to read or parse the Excel file\n"
                f"  4. Just let the user know they can open it directly\n\n"
                f"📋 The Excel file contains complete DCF analysis including:\n"
                f"  • WACC and discount rate calculations\n"
                f"  • Historical growth rates (Revenue, FCF, EBITDA, Net Income)\n"
                f"  • 10-year cash flow projections\n"
                f"  • Fair value calculation and buy/sell recommendation"
            )
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": f"Error generating DCF analysis: {str(e)}"
        }
