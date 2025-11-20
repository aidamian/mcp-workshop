from __future__ import annotations

from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from raw_version.server import StockDataProvider, log_server

try:  # pragma: no cover - the import is exercised at runtime
  from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError("Install the 'mcp' package to run the MCP server variant.") from exc

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = REPO_ROOT / "stocks_data.csv"

provider = StockDataProvider(csv_path=CSV_PATH)
server = FastMCP("stocks-mcp")


@server.tool()
def get_stock_price(symbol: str) -> Dict[str, Dict[str, str]]:
  """Lookup a ticker and return the structured price payload."""
  price = provider.get_stock_price(symbol)
  log_server(f"Serving MCP get_stock_price for {price.symbol} via {price.source}.")
  return {"data": price.as_dict()}


@server.tool()
def compare_stocks(symbol_one: str, symbol_two: str) -> Dict[str, Dict[str, str]]:
  """Compare two tickers and return the summary payload."""
  comparison = provider.compare_stocks(symbol_one, symbol_two)
  log_server(
    f"Serving MCP compare_stocks for {symbol_one} vs {symbol_two}; summary captured.",
  )
  return {"data": comparison}


def main() -> None:
  """Entrypoint compatible with ``python -m mcp_version.server``."""
  log_server("Starting MCP (fastmcp) server over stdio.")
  server.run_stdio()


if __name__ == "__main__":
  main()
