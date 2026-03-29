import logging
import unittest

from defeatbeta_api.data.company_meta import CompanyMeta
from test.test_ticker import TestTicker

meta = CompanyMeta(http_proxy="http://127.0.0.1:8118", log_level=logging.DEBUG)

for _symbol in meta.get_all_tickers():
    _cls_name = f"TestTicker_{_symbol.replace('.', '_').replace('-', '_')}"
    globals()[_cls_name] = type(_cls_name, (TestTicker,), {"SYMBOL": _symbol})

if __name__ == "__main__":
    unittest.main()
