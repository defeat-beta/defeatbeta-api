"""Optional live report generation smoke test."""

import logging
import os
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("DEFEATBETA_RUN_REPORT_TESTS") == "1",
    "Set DEFEATBETA_RUN_REPORT_TESTS=1 to generate a live report",
)
class TestReport(unittest.TestCase):
    def test_tearsheet_html(self):
        from defeatbeta_api.data.ticker import Ticker
        import defeatbeta_api.reports.tearsheet as tearsheet

        proxy = os.environ.get("DEFEATBETA_TEST_HTTP_PROXY") or None
        ticker = Ticker("ADBE", http_proxy=proxy, log_level=logging.WARNING)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.html"
            tearsheet.html(ticker, output=str(target))
            self.assertTrue(target.is_file())
