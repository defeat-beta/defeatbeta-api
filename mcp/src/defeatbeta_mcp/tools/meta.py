from defeatbeta_api import data_update_time, __version__
from datetime import datetime, timezone

def get_latest_data_update_date():
    """
        Get the latest data update date of the defeatbeta dataset.

        This is the most recent date for which historical price data is available
        in the defeatbeta dataset (typically the last date when the entire dataset
        was refreshed with new trading data).

        This is NOT the real-time server date, and NOT necessarily today's date.
        All available stock prices are up to and including trading days on or before
        this data date.

        Use this date as the reference point ("today" in data terms) when handling
        relative time queries such as "last 10 days", "past month", "year-to-date", etc.

        Returns:
            A dictionary containing the latest data date in YYYY-MM-DD format.
    """
    return {
        "latest_data_date": data_update_time,
        "note": "This is the latest DATA UPDATE DATE of the defeatbeta dataset. "
                "All historical price data available through this API is current "
                "up to this date. Use this date as the base for any relative time "
                "queries (e.g., 'recent 10 days' refers to the 10 trading days ending "
                "on or before this date)."
    }

def get_current_datetime():
    """
    MCP Tool: Get the current real-world date and time.

    This tool provides the ground-truth current datetime from the server,
    which can be used by LLMs to reason about time-sensitive financial data
    such as earnings dates, market status, or recent events.

    Returns:
        dict: A structured datetime object including date, datetime, timestamp,
              timezone, and day of week.
    """
    now = datetime.now(timezone.utc)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "datetime": now.isoformat(),
        "timestamp": int(now.timestamp()),
        "timezone": "UTC",
        "day_of_week": now.strftime("%A")
    }

def get_defeatbeta_api_version():
    """
        Retrieve version and dataset metadata for the Defeat Beta API.

        Returns: A dictionary containing the version of the Defeat Beta API
    """
    version = __version__
    return {
        "version": version,
        "note": "The API version reflects the installed defeatbeta_api package."
    }