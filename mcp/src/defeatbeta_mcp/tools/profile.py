from .util import create_ticker


def get_stock_profile(symbol: str):
    """
        Retrieve the basic company profile information for a given stock symbol.

        Args:
            symbol (str): The stock ticker symbol, e.g., "TSLA" or "tsla" (will be automatically converted to uppercase).

        Returns:
            dict: A dictionary containing the company's basic profile information. Common keys include:
                - symbol: Stock ticker symbol
                - address: Company headquarters address
                - city: City where the company is headquartered
                - country: Country of headquarters
                - phone: Company phone number
                - zip: Postal/ZIP code
                - industry: Industry classification
                - sector: Sector classification
                - long_business_summary: Detailed business description/summary
                - full_time_employees: Number of full-time employees
                - web_site: Official company website URL
                - report_date: Date of the data report or last update

        Example (for TSLA):
            {
                'symbol': 'TSLA',
                'address': '1 Tesla Road',
                'city': 'Austin',
                'country': 'United States',
                'phone': '512 516 8177',
                'zip': '78725',
                'industry': 'Auto Manufacturers',
                'sector': 'Consumer Cyclical',
                'long_business_summary': 'Tesla, Inc. designs, develops, manufactures, l...',
                'full_time_employees': 125665,
                'web_site': 'https://www.tesla.com',
                'report_date': '2025-04-12'
            }

        Notes:
            - The underlying data is returned as a single-row pandas DataFrame from the ticker details.
            - The function converts the first row to a dictionary for easier handling.
            - If no data is available (empty DataFrame), an empty dictionary is returned.
    """
    symbol = symbol.upper()
    ticker = create_ticker(symbol)
    df = ticker.info()
    # Convert the first row of the DataFrame to dict; return empty dict if no data
    profile = df.iloc[0].to_dict() if not df.empty else {}

    return profile