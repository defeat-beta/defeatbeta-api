import logging

from defeatbeta_api.data.ticker import Ticker
import defeatbeta_api.reports.tearsheet as tearsheet

ticker = Ticker("LI", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)

tearsheet.html(ticker, output='/tmp/test.html')