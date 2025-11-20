"""
Automated integration tests for the Deepseek MCP workshop.

Run with an optional variant selector to target the raw, mcp, or course implementation:

```
python tests/run_tests.py raw    # default
python tests/run_tests.py mcp
python tests/run_tests.py course
```
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import Dict, Literal, Tuple, Type

from dotenv import load_dotenv

Variant = Literal["raw", "mcp", "course"]
DEFAULT_VARIANT: Variant = "raw"
REPO_ROOT = Path(__file__).resolve().parents[1]


def determine_variant() -> Variant:
  if len(sys.argv) > 1 and sys.argv[1] in {"raw", "mcp", "course"}:
    variant = sys.argv.pop(1)
  else:
    variant = DEFAULT_VARIANT
  return os.environ.get("TEST_VARIANT", variant)  # type: ignore[return-value]


VARIANT: Variant = determine_variant()


def load_variant_modules(
  variant: Variant,
) -> Tuple[Type[object], Type[object], Type[object], object, Path]:
  """Return router, client, tool call class, render helper, and server path for the selected variant."""
  if variant == "raw":
    from raw_version.client import DeepseekRouter, StockToolClient, ToolCall, render_result  # type: ignore
    server_path = REPO_ROOT / "raw_version" / "server.py"
    return DeepseekRouter, StockToolClient, ToolCall, render_result, server_path

  if variant == "mcp":
    try:
      from mcp_version.client import OpenAIBackedRouter as DeepseekRouter  # type: ignore
      from mcp_version.client import MCPStockClient as StockToolClient  # type: ignore
      from mcp_version.client import ToolCall, render_result  # type: ignore
    except ImportError as exc:
      print("mcp package not available; skipping mcp variant tests.")
      sys.exit(0)
    server_path = REPO_ROOT / "mcp_version" / "server.py"
    return DeepseekRouter, StockToolClient, ToolCall, render_result, server_path

  if variant == "course":
    try:
      from course_version.client import GeminiRouter as DeepseekRouter  # type: ignore
      from course_version.client import CourseMCPClient as StockToolClient  # type: ignore
      from course_version.client import ToolCall, render_result  # type: ignore
    except ImportError as exc:
      print("course variant dependencies not available; skipping.")
      sys.exit(0)
    server_path = REPO_ROOT / "course_version" / "server.py"
    return DeepseekRouter, StockToolClient, ToolCall, render_result, server_path

  raise ValueError(f"Unknown variant {variant}")


DeepseekRouter, StockToolClient, ToolCall, render_result, SERVER_PATH = load_variant_modules(VARIANT)  # type: ignore[misc]


class StockDataProviderTest(unittest.TestCase):
  """Validate CSV fallbacks and live-price behaviour using the shared provider."""

  def setUp(self) -> None:
    from raw_version.server import StockDataProvider  # shared provider
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
  """Exercise heuristic routing when the AI router is unavailable."""

  def setUp(self) -> None:
    load_dotenv()
    self.router = DeepseekRouter(api_key=None)  # type: ignore[call-arg]

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
  """Launch the selected server process and perform round-trip checks."""

  def setUp(self) -> None:
    load_dotenv()

  def _invoke_price(self) -> Dict[str, str]:
    router = DeepseekRouter(api_key=None)  # type: ignore[call-arg]
    if VARIANT == "raw":
      with StockToolClient(server_path=SERVER_PATH, router=router) as client:
        return client.invoke(ToolCall("get_stock_price", {"symbol": "IBM"}))

    async def _invoke_async() -> Dict[str, str]:
      async with StockToolClient(server_path=SERVER_PATH, debug=True) as client:  # type: ignore[arg-type]
        return await client.invoke(ToolCall("get_stock_price", {"symbol": "IBM"}))

    return asyncio.run(_invoke_async())

  def test_get_stock_price_round_trip(self) -> None:
    """Client and server should communicate over stdio for price lookups."""
    result = self._invoke_price()
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
