import asyncio
import json
import unittest

from mcp import Client
from mcp.types import CallToolResult, TextContent

from defeatbeta_mcp.server import mcp


class ServerV2IntegrationTests(unittest.IsolatedAsyncioTestCase):
    def parse_json_result(self, result: CallToolResult) -> dict:
        self.assertFalse(result.is_error)
        self.assertEqual(1, len(result.content))
        self.assertIsInstance(result.content[0], TextContent)
        return json.loads(result.content[0].text)

    async def test_representative_data_tools_return_results(self):
        async with Client(mcp) as client:
            metadata, price, news = await asyncio.gather(
                client.call_tool("get_latest_data_update_date"),
                client.call_tool(
                    "get_stock_price",
                    {
                        "symbol": "AAPL",
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-10",
                    },
                ),
                client.call_tool(
                    "get_stock_news",
                    {
                        "symbol": "AAPL",
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-29",
                        "max_rows": 1,
                    },
                ),
            )

        metadata_payload = self.parse_json_result(metadata)
        price_payload = self.parse_json_result(price)
        news_payload = self.parse_json_result(news)

        self.assertIn("latest_data_date", metadata_payload)
        self.assertEqual("AAPL", price_payload["symbol"])
        self.assertGreater(price_payload["rows_returned"], 0)
        self.assertEqual("AAPL", news_payload["symbol"])
        self.assertLessEqual(news_payload["rows_returned"], 1)

    async def test_parallel_price_calls_share_duckdb_safely(self):
        async with Client(mcp) as client:
            aapl, msft = await asyncio.gather(
                client.call_tool(
                    "get_stock_price",
                    {
                        "symbol": "AAPL",
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-10",
                    },
                ),
                client.call_tool(
                    "get_stock_price",
                    {
                        "symbol": "MSFT",
                        "start_date": "2026-07-01",
                        "end_date": "2026-07-10",
                    },
                ),
            )

        aapl_payload = self.parse_json_result(aapl)
        msft_payload = self.parse_json_result(msft)

        self.assertEqual("AAPL", aapl_payload["symbol"])
        self.assertEqual("MSFT", msft_payload["symbol"])
        self.assertGreater(aapl_payload["rows_returned"], 0)
        self.assertGreater(msft_payload["rows_returned"], 0)

    async def test_invalid_date_is_a_tool_result_not_a_protocol_error(self):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_stock_price",
                {"symbol": "AAPL", "start_date": "not-a-date"},
            )

        payload = self.parse_json_result(result)
        self.assertIn("Invalid start_date format", payload["error"])


if __name__ == "__main__":
    unittest.main()
