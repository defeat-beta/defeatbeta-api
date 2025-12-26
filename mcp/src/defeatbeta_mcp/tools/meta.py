from defeatbeta_api import __version__
from datetime import datetime, timezone

from defeatbeta_api import data_update_time

def get_latest_data_update_date():
    """
    MCP Tool: Get the latest data update date.

    This tool defines the current reference date of the MCP data universe.
    All company, financial, and market data provided by this MCP server
    is guaranteed to be complete and consistent up to this date.

    This is NOT the real-world current date and NOT a real-time timestamp.

    LLMs should treat this date as "today" when reasoning about:
    - Recent stock prices
    - Latest earnings and financial statements
    - Most recent earnings calls
    - Company news and events
    - Relative time expressions such as "last 10 days", "past month",
      "year-to-date", or "latest quarter"

    Returns:
        dict: A dictionary containing:
            - latest_data_date (str): Data reference date in YYYY-MM-DD format
            - timezone (str): Timezone of the data reference date
            - semantics (str): Explanation of how this date should be used
    """
    return {
        "latest_data_date": data_update_time,
        "timezone": "UTC",
        "semantics": (
            "This date represents the current reference point of the MCP data universe. "
            "All financial, company, and market data is complete up to and including this date. "
            "Use this date as 'today' for all data-driven reasoning."
        )
    }


def get_current_datetime():
    """
    MCP Tool: Get the current real-world datetime.

    This tool provides the ground-truth current date and time from the server.
    It is intended for temporal comparison and reasoning, NOT as a replacement
    for the MCP data reference date.

    Returns:
        dict: A dictionary containing:
            - datetime (str): ISO-8601 formatted datetime (UTC)
            - date (str): Current date in YYYY-MM-DD format
            - timestamp (int): Unix timestamp (seconds)
            - timezone (str): Timezone
            - day_of_week (str): Day of the week
    """
    now = datetime.now(timezone.utc)

    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": int(now.timestamp()),
        "timezone": "UTC",
        "day_of_week": now.strftime("%A"),
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