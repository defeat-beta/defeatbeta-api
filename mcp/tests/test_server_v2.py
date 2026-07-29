import subprocess
import sys
import unittest

from mcp import Client, StdioServerParameters, stdio_client
from mcp.server import MCPServer

from defeatbeta_mcp.server import mcp


class ServerV2Tests(unittest.IsolatedAsyncioTestCase):
    def test_server_import_does_not_write_to_stdout(self):
        completed = subprocess.run(
            [sys.executable, "-c", "import defeatbeta_mcp.server"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual("", completed.stdout)

    async def test_server_negotiates_v2_and_lists_all_tools(self):
        self.assertIsInstance(mcp, MCPServer)

        async with Client(mcp) as client:
            result = await client.list_tools()

            self.assertEqual("2026-07-28", client.protocol_version)

        tool_names = {tool.name for tool in result.tools}
        self.assertEqual(68, len(tool_names))
        for tool in result.tools:
            self.assertEqual("object", tool.input_schema["type"])
        self.assertTrue(
            {
                "get_latest_data_update_date",
                "get_stock_price",
                "get_stock_news",
                "get_stock_quarterly_income_statement",
                "get_stock_dcf_analysis",
            }.issubset(tool_names)
        )

    async def test_stdio_transport_negotiates_and_lists_tools(self):
        transport = stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "defeatbeta_mcp"],
            )
        )

        async with Client(transport) as client:
            result = await client.list_tools()

            self.assertEqual("2026-07-28", client.protocol_version)

        self.assertEqual(68, len(result.tools))


if __name__ == "__main__":
    unittest.main()
