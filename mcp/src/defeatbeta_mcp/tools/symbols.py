from .util import create_company_meta


def get_supported_stocks():
    """
    Get all supported stock symbols and their metadata in the defeatbeta dataset.

    This function returns a list of all companies with their metadata including
    symbol, CIK, name, and financial currency. Use this to check if a particular
    symbol is supported before querying other financial data.

    Returns:
        A dictionary containing:
        - total_count: The total number of supported companies
        - companies: A list of company metadata, each containing:
            - idx: Index in the dataset
            - symbol: Stock ticker symbol (e.g., "AAPL")
            - cik: SEC Central Index Key
            - name: Company name
            - financial_currency: Currency used in financial statements
        - note: A description of what this data represents
    """
    company_meta = create_company_meta()
    companies = company_meta.get_all_companies_info()
    companies_sorted = sorted(companies, key=lambda x: x["symbol"])
    return {
        "total_count": len(companies_sorted),
        "companies": companies_sorted,
        "note": "This is the list of all companies with financial data available in the defeatbeta dataset."
    }
