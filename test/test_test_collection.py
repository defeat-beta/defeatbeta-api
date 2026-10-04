"""Keep optional network suites safe to import during test discovery."""

import runpy
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from defeatbeta_api.data.company_meta import CompanyMeta


class TestTestCollection(unittest.TestCase):
    def test_all_ticker_module_does_not_initialize_a_client_on_import(self):
        module = Path(__file__).with_name("test_all_tickers.py")
        with patch.object(
            CompanyMeta,
            "__init__",
            side_effect=AssertionError("Test collection must not create a client"),
        ):
            runpy.run_path(str(module))

    def test_excel_integration_is_opt_in(self):
        module = Path(__file__).with_name("test_ticker.py")
        with patch.dict(os.environ, {"DEFEATBETA_RUN_EXCEL_TESTS": ""}):
            namespace = runpy.run_path(str(module))
        self.assertTrue(namespace["TestTicker"].test_dcf.__unittest_skip__)

    def test_siliconflow_integration_is_opt_in(self):
        module = Path(__file__).with_name("test_ai_transcripts.py")
        with patch.dict(os.environ, {"DEFEATBETA_RUN_AI_TESTS": ""}):
            namespace = runpy.run_path(str(module))
        self.assertTrue(namespace["TestAITranscripts"].__unittest_skip__)
        with patch.dict(os.environ, {"DEFEATBETA_RUN_AI_TESTS": "1"}):
            namespace = runpy.run_path(str(module))
        self.assertFalse(getattr(namespace["TestAITranscripts"], "__unittest_skip__", False))

    def test_report_module_does_not_initialize_a_client_on_import(self):
        module = Path(__file__).with_name("test_report.py")
        with patch("defeatbeta_api.data.ticker.Ticker", side_effect=AssertionError(
            "Test collection must not create a client"
        )):
            runpy.run_path(str(module))

    def test_parallel_ticker_sample_is_bounded_and_deterministic(self):
        from test.test_ticker_multithreaded import select_symbols

        candidates = ["ZZZ", "AAA", "BABA", "MMM", "AAA", "BBB"]
        self.assertEqual(
            select_symbols("BABA", candidates, limit=4),
            ["BABA", "AAA", "BBB", "MMM"],
        )


if __name__ == "__main__":
    unittest.main()
