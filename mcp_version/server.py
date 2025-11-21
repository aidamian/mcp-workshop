from pathlib import Path
import sys
from typing import Dict

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
# Ensure repo root is on sys.path so sibling modules import correctly when executed as a script.
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from raw_version.server import StockDataProvider
from utils.utils import log_color

try:  # pragma: no cover - the import is exercised at runtime
  from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError("Install the 'mcp' package to run the MCP server variant.") from exc

load_dotenv()

CSV_PATH = REPO_ROOT / "stocks_data.csv"

provider = StockDataProvider(csv_path=CSV_PATH)
server = FastMCP("stocks-mcp")

# Emit server logs to stderr to avoid interfering with stdio transport.
def log_server(message: str) -> None:
  log_color(message, "p", prefix="[mcp-server]", use_stderr=True)


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
  server.run(transport="stdio")


if __name__ == "__main__":
  main()
