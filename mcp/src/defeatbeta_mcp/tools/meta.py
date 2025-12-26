from defeatbeta_api import __version__

from defeatbeta_api import data_update_time

def get_latest_data_update_date():
    """
    Get the latest data update date.

    Returns:
        dict: A dictionary containing:
            - latest_data_date (str): Data reference date in YYYY-MM-DD format
            - timezone (str): Timezone of the data reference date
    """
    return {
        "latest_data_date": data_update_time,
        "timezone": "UTC"
    }


def get_current_datetime():
    """
    MCP Tool: Get the current real-world datetime.

    Returns:
        dict: A dictionary containing:
            - datetime (str): ISO-8601 formatted datetime (UTC)
            - date (str): Current date in YYYY-MM-DD format
            - timestamp (int): Unix timestamp (seconds)
            - timezone (str): Timezone
            - day_of_week (str): Day of the week
    """
    now = data_update_time

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