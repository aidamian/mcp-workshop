"""
MCP SDK-based server exposing the stock tools.

This variant uses the ``modelcontextprotocol`` package so that any MCP-capable
client can connect via stdio. The raw :mod:`raw_version.server` module is reused
for data fetching logic to avoid code duplication.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from raw_version.server import StockDataProvider

try:  # pragma: no cover - the import is exercised at runtime
  from mcp.server import Server
  from mcp.server.stdio import stdio_server
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError(
    "Install the 'modelcontextprotocol' package to run the MCP server variant."
  ) from exc

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "stocks_data.csv"

provider = StockDataProvider(csv_path=CSV_PATH)
server = Server("stocks-mcp")


@server.tool()
async def get_stock_price(symbol: str) -> Dict[str, str]:
  """Lookup a ticker and return the structured price payload."""
  price = provider.get_stock_price(symbol)
  return price.as_dict()


@server.tool()
async def compare_stocks(symbol_one: str, symbol_two: str) -> Dict[str, Dict[str, str]]:
  """Compare two tickers and return the summary payload."""
  return provider.compare_stocks(symbol_one, symbol_two)


async def main() -> None:
  """Entrypoint compatible with ``python -m mcp_version.server``."""
  await stdio_server(server)


if __name__ == "__main__":
  asyncio.run(main())
