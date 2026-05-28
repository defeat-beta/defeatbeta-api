import importlib.util
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_SRC = REPO_ROOT / "mcp" / "src"
TOOLS_SRC = MCP_SRC / "defeatbeta_mcp" / "tools"

_STUBBED_MODULE_NAMES = [
    "defeatbeta_api",
    "defeatbeta_api.data",
    "defeatbeta_api.data.ticker",
    "defeatbeta_api.data.company_meta",
    "defeatbeta_mcp",
    "defeatbeta_mcp.tools",
    "defeatbeta_mcp.tools.util",
    "defeatbeta_mcp.tools.breakdown",
]
_SAVED_MODULES = {
    name: sys.modules.get(name)
    for name in _STUBBED_MODULE_NAMES
}

sys.modules["defeatbeta_api"] = types.ModuleType("defeatbeta_api")
sys.modules["defeatbeta_api.data"] = types.ModuleType("defeatbeta_api.data")
sys.modules["defeatbeta_api.data.ticker"] = types.ModuleType("defeatbeta_api.data.ticker")
sys.modules["defeatbeta_api.data.ticker"].Ticker = object
sys.modules["defeatbeta_api.data.company_meta"] = types.ModuleType("defeatbeta_api.data.company_meta")
sys.modules["defeatbeta_api.data.company_meta"].CompanyMeta = object

package = types.ModuleType("defeatbeta_mcp")
package.__path__ = [str(MCP_SRC / "defeatbeta_mcp")]
tools_package = types.ModuleType("defeatbeta_mcp.tools")
tools_package.__path__ = [str(TOOLS_SRC)]
sys.modules["defeatbeta_mcp"] = package
sys.modules["defeatbeta_mcp.tools"] = tools_package

util_spec = importlib.util.spec_from_file_location(
    "defeatbeta_mcp.tools.util",
    TOOLS_SRC / "util.py",
)
util_module = importlib.util.module_from_spec(util_spec)
sys.modules["defeatbeta_mcp.tools.util"] = util_module
util_spec.loader.exec_module(util_module)

breakdown_spec = importlib.util.spec_from_file_location(
    "defeatbeta_mcp.tools.breakdown",
    TOOLS_SRC / "breakdown.py",
)
breakdown_module = importlib.util.module_from_spec(breakdown_spec)
sys.modules["defeatbeta_mcp.tools.breakdown"] = breakdown_module
breakdown_spec.loader.exec_module(breakdown_module)

for module_name, saved_module in _SAVED_MODULES.items():
    if saved_module is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = saved_module

get_revenue_breakdown = breakdown_module.get_revenue_breakdown


class FakeTicker:
    def __init__(self):
        self.called = []

    def quarterly_revenue_by_breakdown(self):
        self.called.append("quarterly")
        return pd.DataFrame([
            {
                "symbol": "AMD",
                "breakdown": "revenue-by-segment",
                "breakdown_name": "Revenue by Segment",
                "period_type": "quarterly",
                "report_date": "2025-03-29",
                "series_name": "Data Center",
                "value": 3708000000,
                "value_type": "CURRENCY",
                "currency": "USD",
            },
            {
                "symbol": "AMD",
                "breakdown": "revenue-by-segment",
                "breakdown_name": "Revenue by Segment",
                "period_type": "quarterly",
                "report_date": "2025-03-29",
                "series_name": "Gaming",
                "value": pd.NA,
                "value_type": "CURRENCY",
                "currency": "USD",
            },
        ])

    def trailing_revenue_by_breakdown(self):
        self.called.append("trailing")
        return pd.DataFrame([
            {
                "symbol": "AMD",
                "breakdown": "customer-count",
                "breakdown_name": pd.NA,
                "period_type": "trailing",
                "report_date": "2025-03-29",
                "series_name": "Enterprise",
                "value": 42,
                "value_type": "NUMBER",
                "currency": pd.NA,
            }
        ])


class TestMcpBreakdown(unittest.TestCase):
    def test_quarterly_revenue_breakdown_shape(self):
        fake_ticker = FakeTicker()

        with patch.object(breakdown_module, "create_ticker", return_value=fake_ticker):
            result = get_revenue_breakdown("amd", "quarterly")

        self.assertEqual(fake_ticker.called, ["quarterly"])
        self.assertEqual(result["symbol"], "AMD")
        self.assertEqual(result["period_type"], "quarterly")
        self.assertEqual(result["rows_returned"], 2)
        self.assertEqual(result["breakdowns"], [
            {
                "breakdown": "revenue-by-segment",
                "breakdown_name": "Revenue by Segment",
                "value_type": "CURRENCY",
                "currency": "USD",
            }
        ])
        self.assertEqual(result["data"][1]["value"], None)

    def test_trailing_revenue_breakdown_handles_missing_metadata(self):
        fake_ticker = FakeTicker()

        with patch.object(breakdown_module, "create_ticker", return_value=fake_ticker):
            result = get_revenue_breakdown("amd", "trailing")

        self.assertEqual(fake_ticker.called, ["trailing"])
        self.assertEqual(result["period_type"], "trailing")
        self.assertEqual(result["breakdowns"], [
            {
                "breakdown": "customer-count",
                "breakdown_name": None,
                "value_type": "NUMBER",
                "currency": None,
            }
        ])
        self.assertEqual(result["data"], [
            {
                "breakdown": "customer-count",
                "report_date": "2025-03-29",
                "series_name": "Enterprise",
                "value": 42,
            }
        ])

    def test_invalid_period_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_revenue_breakdown("AMD", "annual")


if __name__ == "__main__":
    unittest.main()
