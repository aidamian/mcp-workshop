"""
Stock data tool server for the Deepseek-powered MCP workshop.

This module exposes two tools via a lightweight stdio protocol so that the
interactive client can request stock data. The implementation favours a simple
line-delimited JSON contract to stay close to the Model Context Protocol style
while remaining easy to reason about in a standalone workshop environment.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from utils.utils import log_color

try:
  import yfinance as yf
except ModuleNotFoundError:  # pragma: no cover - optional dependency
  yf = None  # type: ignore[assignment]

SERVER_PREFIX = "[mcp-server]"
SERVER_COLOR = "p"


def log_server(message: str) -> None:
  """
  Emit colourised server-side lifecycle logs to stderr.

  Parameters
  ----------
  message : str
      Human-readable status text.
  """
  formatted = log_color(message, SERVER_COLOR, prefix=SERVER_PREFIX, emit=False)
  print(formatted, file=sys.stderr, flush=True)


@dataclass
class StockPrice:
  """
  Canonical representation of a stock price lookup result.

  Attributes
  ----------
  symbol : str
      Upper-case stock ticker symbol.
  price : float
      Price quoted in USD.
  source : str
      Identifier for the data source (for example ``"yfinance"`` or ``"fallback_csv"``).
  """

  symbol: str
  price: float
  source: str

  def as_dict(self) -> Dict[str, str]:
    """
    Convert the stock price to a serialisable dictionary.

    Returns
    -------
    Dict[str, str]
        Dictionary with ``symbol``, ``price`` (formatted to two decimals), and ``source``.
    """
    return {
      "symbol": self.symbol,
      "price": f"{self.price:.2f}",
      "source": self.source,
    }


class StockDataProvider:
  """
  Resolve stock price requests using Yahoo Finance with a CSV fallback.

  The provider first attempts a live lookup using :mod:`yfinance`. If the network
  call fails or produces no price, it falls back to a deterministic CSV dataset
  located in the repository root.
  """

  def __init__(self, csv_path: Path = Path("stocks_data.csv")) -> None:
    """
    Build a provider instance.

    Parameters
    ----------
    csv_path : Path, optional
        Location of the fallback CSV file. Defaults to ``stocks_data.csv`` in the working directory.
    """
    self.csv_path = csv_path
    self._fallback_prices = self._load_csv(csv_path)

  def get_stock_price(self, symbol: str) -> StockPrice:
    """
    Retrieve the current price for a symbol.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol supplied by the client.

    Returns
    -------
    StockPrice
        Structured price data originating from either Yahoo Finance or the fallback CSV.

    Raises
    ------
    ValueError
        Raised when the symbol is empty or when the symbol is unknown after exhausting all sources.
    """
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
      raise ValueError("Symbol must be a non-empty string.")

    live_price = self._fetch_live_price(clean_symbol)
    if live_price is not None:
      log_server(f"Using live price for {clean_symbol} via yfinance.")
      return StockPrice(clean_symbol, live_price, "yfinance")

    fallback_price = self._fallback_prices.get(clean_symbol)
    if fallback_price is None:
      raise ValueError(f"Price not available for symbol {clean_symbol}.")

    log_server(f"Using CSV fallback for {clean_symbol}.")
    return StockPrice(clean_symbol, fallback_price, "fallback_csv")

  def compare_stocks(self, symbol_one: str, symbol_two: str) -> Dict[str, Dict[str, str]]:
    """
    Compare the prices of two symbols and produce a synthesised summary.

    Parameters
    ----------
    symbol_one : str
        Primary ticker symbol.
    symbol_two : str
        Secondary ticker symbol.

    Returns
    -------
    Dict[str, Dict[str, str]]
        Dictionary containing both price payloads and a human readable summary.

    Raises
    ------
    ValueError
        Propagated from :meth:`get_stock_price` if either symbol cannot be resolved.
    """
    price_one = self.get_stock_price(symbol_one)
    price_two = self.get_stock_price(symbol_two)

    if price_one.price > price_two.price:
      summary = (
        f"{price_one.symbol} is trading higher than "
        f"{price_two.symbol} ({price_one.price:.2f} vs {price_two.price:.2f})."
      )
    elif price_one.price < price_two.price:
      summary = (
        f"{price_one.symbol} is trading lower than "
        f"{price_two.symbol} ({price_one.price:.2f} vs {price_two.price:.2f})."
      )
    else:
      summary = (
        f"{price_one.symbol} and {price_two.symbol} have the same "
        f"price at {price_one.price:.2f}."
      )

    return {
      "symbol_one": price_one.as_dict(),
      "symbol_two": price_two.as_dict(),
      "summary": summary,
    }

  def _fetch_live_price(self, symbol: str) -> Optional[float]:
    """
    Attempt to request the most recent price from Yahoo Finance.

    Parameters
    ----------
    symbol : str
        Ticker symbol already validated by :meth:`get_stock_price`.

    Returns
    -------
    Optional[float]
        Floating-point price if a live quote is available; otherwise ``None``.

    Notes
    -----
    Returns ``None`` immediately when :mod:`yfinance` is not installed.
    """
    if yf is None:
      return None
    try:
      ticker = yf.Ticker(symbol)
      fast_info = getattr(ticker, "fast_info", None)
      if fast_info:
        live_price = fast_info.get("last_price") or fast_info.get("lastPrice")
        if live_price:
          return float(live_price)

      history = ticker.history(period="1d", interval="1m")
      if not history.empty:
        return float(history["Close"].iloc[-1])
    except Exception:
      return None
    return None

  def _load_csv(self, path: Path) -> Dict[str, float]:
    """
    Populate the fallback price dictionary.

    Parameters
    ----------
    path : Path
        Target CSV path containing ``symbol,price`` rows.

    Returns
    -------
    Dict[str, float]
        Mapping with upper-case symbols as keys and numeric prices as values.
    """
    if not path.exists():
      return {}

    fallback: Dict[str, float] = {}
    with path.open("r", encoding="utf-8") as csv_file:
      for index, line in enumerate(csv_file):
        if index == 0:
          continue
        parts = [value.strip() for value in line.split(",")]
        if len(parts) < 2:
          continue
        symbol, price_str = parts[0], parts[1]
        try:
          fallback[symbol.upper()] = float(price_str)
        except ValueError:
          continue
    return fallback


class StockToolServer:
  """
  Minimal stdio-based tool server.

  Every request is expected to be a single JSON object on its own line. The
  response mirrors the request ``id`` so the client can correlate the result.
  """

  def __init__(self, provider: StockDataProvider) -> None:
    """
    Store the provider for subsequent tool invocations.

    Parameters
    ----------
    provider : StockDataProvider
        Concrete provider used to fulfil stock price requests.
    """
    self.provider = provider

  def run(self, input_stream: Iterable[str] = sys.stdin) -> None:
    """
    Consume requests from an input stream and publish JSON responses.

    Parameters
    ----------
    input_stream : Iterable[str], optional
        Source of newline-delimited JSON. Defaults to ``sys.stdin``.
    """
    log_server("Starting raw stdio MCP server and sending readiness signal.")
    ready_message = {"type": "ready", "version": "1.0"}
    print(json.dumps(ready_message), flush=True)

    for line in input_stream:
      line = line.strip()
      if not line:
        continue

      try:
        payload = json.loads(line)
      except json.JSONDecodeError:
        log_server("Rejecting payload: invalid JSON.")
        self._emit_error("unknown", "Invalid JSON payload.")
        continue

      message_type = payload.get("type")
      if message_type == "shutdown":
        log_server(f"Shutdown requested by client (id={payload.get('id')}).")
        self._emit_response(payload.get("id", "unknown"), {"status": "shutting_down"})
        break

      if message_type != "invoke":
        log_server(
          f"Unsupported message type '{message_type}' received; id={payload.get('id', 'unknown')}.",
        )
        self._emit_error(payload.get("id", "unknown"), "Unsupported message type.")
        continue

      request_id = payload.get("id")
      tool_name = payload.get("tool")
      arguments = payload.get("arguments") or {}
      log_server(
        f"Executing tool '{tool_name}' for request {request_id} with arguments {arguments}.",
      )

      try:
        result = self._invoke_tool(tool_name, arguments)
        log_server(
          f"Tool '{tool_name}' completed for request {request_id}; result keys={list(result.keys())}.",
        )
        self._emit_response(request_id, result)
      except Exception as exc:  # pylint: disable=broad-except
        log_server(f"Error while executing request {request_id}: {exc}")
        self._emit_error(request_id, str(exc))

  def _invoke_tool(self, tool_name: str, arguments: Dict[str, str]) -> Dict[str, object]:
    """
    Dispatch a tool request to the provider.

    Parameters
    ----------
    tool_name : str
        Name of the requested tool.
    arguments : Dict[str, str]
        Payload containing tool-specific parameters.

    Returns
    -------
    Dict[str, object]
        Result wrapper that will be serialised back to the client.

    Raises
    ------
    ValueError
        Raised when the tool name is unknown.
    """
    if tool_name == "get_stock_price":
      symbol = arguments.get("symbol", "")
      price = self.provider.get_stock_price(symbol)
      return {"data": price.as_dict()}

    if tool_name == "compare_stocks":
      symbol_one = arguments.get("symbol_one", "")
      symbol_two = arguments.get("symbol_two", "")
      comparison = self.provider.compare_stocks(symbol_one, symbol_two)
      return {"data": comparison}

    raise ValueError(f"Unknown tool '{tool_name}'.")

  @staticmethod
  def _emit_response(request_id: Optional[str], result: Dict[str, object]) -> None:
    """
    Write a successful response to stdout.

    Parameters
    ----------
    request_id : Optional[str]
        Identifier echoed from the original request.
    result : Dict[str, object]
        Result payload returned by the invoked tool.
    """
    payload = {"type": "response", "id": request_id, "result": result}
    print(json.dumps(payload), flush=True)

  @staticmethod
  def _emit_error(request_id: Optional[str], message: str) -> None:
    """
    Write an error payload to stdout.

    Parameters
    ----------
    request_id : Optional[str]
        Identifier echoed from the original request.
    message : str
        Human-readable error message.
    """
    payload = {"type": "response", "id": request_id, "error": message}
    print(json.dumps(payload), flush=True)


def main() -> None:
  """
  Entry point that initialises environment variables and starts the server.
  """
  load_dotenv()
  provider = StockDataProvider()
  server = StockToolServer(provider)
  server.run()


if __name__ == "__main__":
  main()
