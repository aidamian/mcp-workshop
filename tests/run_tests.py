"""
Automated integration tests for the Deepseek MCP workshop.

The suite uses :mod:`unittest` so it can run in any environment via
``python tests/run_tests.py`` without additional dependencies.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from mcp_client import DeepseekRouter, StockToolClient, ToolCall, render_result
from mcp_server import StockDataProvider


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "mcp_server.py"


class StockDataProviderTest(unittest.TestCase):
  """Validate CSV fallbacks and live-price behaviour."""

  def setUp(self) -> None:
    self.provider = StockDataProvider(REPO_ROOT / "stocks_data.csv")

  def test_get_stock_price_fallback(self) -> None:
    """A known ticker in the CSV should return a fallback price."""
    self.provider._fetch_live_price = lambda symbol: None  # type: ignore[method-assign]
    price = self.provider.get_stock_price("AAPL")
    self.assertEqual(price.symbol, "AAPL")
    self.assertEqual(price.source, "fallback_csv")

  def test_compare_stocks_summary(self) -> None:
    """Comparing two fallback tickers should produce a readable summary."""
    self.provider._fetch_live_price = lambda symbol: None  # type: ignore[method-assign]
    comparison = self.provider.compare_stocks("AAPL", "MSFT")
    self.assertIn("summary", comparison)
    self.assertIn("AAPL", comparison["summary"])
    self.assertIn("MSFT", comparison["summary"])


class DeepseekRouterTest(unittest.TestCase):
  """Exercise heuristic routing when Deepseek is unavailable."""

  def setUp(self) -> None:
    self.router = DeepseekRouter(api_key=None)

  def test_route_single_symbol(self) -> None:
    """A simple price query should map to get_stock_price."""
    tool_call = self.router.route("What is the price of AAPL?")
    self.assertEqual(tool_call.name, "get_stock_price")
    self.assertEqual(tool_call.arguments["symbol"], "AAPL")

  def test_route_company_names(self) -> None:
    """Company names without tickers should still resolve."""
    tool_call = self.router.route("Compare Apple and Microsoft stocks today")
    self.assertEqual(tool_call.name, "compare_stocks")
    self.assertEqual(tool_call.arguments["symbol_one"], "AAPL")
    self.assertEqual(tool_call.arguments["symbol_two"], "MSFT")


class StockToolClientIntegrationTest(unittest.TestCase):
  """Launch the real server process and perform round-trip checks."""

  def setUp(self) -> None:
    load_dotenv()

  def test_get_stock_price_round_trip(self) -> None:
    """Client and server should communicate over stdio for price lookups."""
    router = DeepseekRouter(api_key=None)
    with StockToolClient(server_path=SERVER_PATH, router=router) as client:
      result = client.invoke(ToolCall("get_stock_price", {"symbol": "IBM"}))
    data: Dict[str, str] = result.get("data") or {}
    self.assertEqual(data.get("symbol"), "IBM")
    self.assertIn("source", data)

  def test_render_result_compare(self) -> None:
    """Render helper should convert comparison payloads into strings."""
    payload = {
        "data": {
            "symbol_one": {"symbol": "AAPL", "price": "1.00", "source": "fallback_csv"},
            "symbol_two": {"symbol": "MSFT", "price": "2.00", "source": "fallback_csv"},
            "summary": "AAPL vs MSFT summary",
        }
    }
    message = render_result(ToolCall("compare_stocks", {}), payload)
    self.assertIn("summary", message)


if __name__ == "__main__":
  unittest.main()
