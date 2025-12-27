from defeatbeta_api import HuggingFaceClient


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
    client = HuggingFaceClient()
    data_update_time = client.get_data_update_time()
    return {
        "latest_data_date": data_update_time,
        "note": "This is the latest DATA UPDATE DATE of the defeatbeta dataset. "
                "All historical price data available through this API is current "
                "up to this date. Use this date as the base for any relative time "
                "queries (e.g., 'recent 10 days' refers to the 10 trading days ending "
                "on or before this date)."
    }