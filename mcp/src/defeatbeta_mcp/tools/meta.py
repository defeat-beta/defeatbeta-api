from defeatbeta_api import __version__

from defeatbeta_api import data_update_time

def get_latest_data_update_date():
    """
    Get the latest data update date of the defeatbeta dataset.

    This is the most recent date for which historical data is available
    in the defeatbeta dataset (typically the last date when the entire dataset
    was refreshed with new trading data).

    Returns:
        dict: A dictionary containing:
            - latest_data_date (str): Data reference date in YYYY-MM-DD format
            - timezone (str): Timezone of the data reference date
    """
    return {
        "latest_data_date": data_update_time,
        "timezone": "UTC"
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