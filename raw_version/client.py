"""
Interactive CLI that delegates stock queries to the MCP-style tool server.

The router relies on Deepseek for natural language interpretation when an API
key is present. If the key is missing or the API call fails, a deterministic
keyword-based classifier is used instead so that the workshop remains usable in
offline settings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import requests
from dotenv import load_dotenv


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
COLOR_CODES = {
  "g": "\033[32m",   # green
  "d": "\033[90m",   # dark grey
  "w": "\033[97m",   # white
  "b": "\033[94m",   # blue
  "y": "\033[33m",   # yellow
  "r": "\033[31m",   # red
}
KNOWN_TICKERS = {
  "AAPL",
  "MSFT",
  "GOOGL",
  "TSLA",
  "AMZN",
  "NVDA",
  "META",
  "IBM",
  "ORCL",
  "NFLX",
}
NAME_TO_TICKER = {
  "APPLE": "AAPL",
  "MICROSOFT": "MSFT",
  "TESLA": "TSLA",
  "AMAZON": "AMZN",
  "GOOGLE": "GOOGL",
  "ALPHABET": "GOOGL",
  "META": "META",
  "FACEBOOK": "META",
  "NVIDIA": "NVDA",
  "IBM": "IBM",
  "ORACLE": "ORCL",
  "NETFLIX": "NFLX",
}


def log_color(
  message: str,
  color: str = "w",
  prefix: str = "[agent]",
  *,
  emit: bool = True,
) -> str:
  """
  Wrap a message in an ANSI colour code and optionally print it.

  Parameters
  ----------
  message : str
      Text to render in colour.
  color : str
      Logical colour identifier using single-letter keys (for example ``"g"`` for
      green, ``"d"`` for dark grey).
  prefix : str, optional
      Tag prepended to the message (defaults to ``"[agent]"``).
  emit : bool, optional
      When ``True`` (default) the coloured message is printed with ``flush=True``.

  Returns
  -------
  str
      Message wrapped in the appropriate ANSI escape code.
  """
  colour_code = COLOR_CODES.get(color, COLOR_CODES["w"])
  suffix = "\033[0m"
  formatted = f"{colour_code}{prefix} {message}{suffix}"
  if emit:
    print(formatted, flush=True)
  return formatted


@dataclass
class ToolCall:
  """
  Normalised representation of a tool invocation determined by the router.

  Attributes
  ----------
  name : str
      Name of the tool to invoke.
  arguments : Dict[str, str]
      Dictionary of serialised arguments relevant to the tool.
  """

  name: str
  arguments: Dict[str, str]


class DeepseekRouter:
  """
  Determine which tool to invoke based on a natural language query.

  When a Deepseek API key is available the router requests a structured JSON
  response. Failures fall back to a deterministic heuristic so the user can
  continue without external connectivity.
  """

  def __init__(self, api_key: Optional[str], model: str = DEFAULT_MODEL, debug: bool = False) -> None:
    """
    Create a router instance.

    Parameters
    ----------
    api_key : Optional[str]
        Deepseek API key. When ``None``, the router will only use heuristics.
    model : str, optional
        Deepseek model identifier requested when the key is available.
    debug : bool, optional
        When ``True`` the router emits verbose debug logs.
    """
    self.api_key = api_key
    self.model = model
    self.debug = debug

  def route(self, prompt: str) -> ToolCall:
    """
    Classify the user's prompt into a concrete tool call.

    Parameters
    ----------
    prompt : str
        Raw natural language query from the user.

    Returns
    -------
    ToolCall
        Routed tool name and argument mapping.

    Raises
    ------
    ValueError
        Raised when the prompt is empty or cannot be mapped to a familiar tool.
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
      raise ValueError("Query cannot be empty.")

    self._log_debug(f"[Router] Received prompt: {cleaned_prompt}")

    if not self.api_key:
      self._log_debug("[Router] No Deepseek key detected; using heuristic classifier.")
      return self._fallback_route(cleaned_prompt)

    try:
      return self._deepseek_route(cleaned_prompt)
    except Exception as exc:
      self._log_debug(f"[Router] Deepseek routing failed ({exc}); reverting to heuristics.")
      return self._fallback_route(cleaned_prompt)

  def _deepseek_route(self, prompt: str) -> ToolCall:
    """
    Ask Deepseek to translate a prompt into a tool call.

    Parameters
    ----------
    prompt : str
        Natural-language user request.

    Returns
    -------
    ToolCall
        Routed tool call obtained from the Deepseek API.

    Raises
    ------
    ValueError
        Raised when the API response is malformed or lacks actionable content.
    requests.HTTPError
        Propagated if Deepseek responds with an HTTP error status.
    """
    headers = {
      "Authorization": f"Bearer {self.api_key}",
      "Content-Type": "application/json",
    }
    payload = {
      "model": self.model,
      "response_format": {"type": "json_object"},
      "messages": [
        {
          "role": "system",
          "content": (
            "You are a routing assistant for a stock data toolset. "
            "Map the user's prompt to either 'get_stock_price' or "
            "'compare_stocks'. Always return JSON with keys "
            "tool (string) and arguments (object). For get_stock_price "
            "provide symbol. For compare_stocks provide symbol_one and "
            "symbol_two. Symbols must be uppercase tickers."
          ),
        },
        {"role": "user", "content": prompt},
      ],
    }
    self._log_debug(f"[Deepseek] Request payload: {json.dumps(payload, ensure_ascii=False)}")

    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    self._log_debug(f"[Deepseek] Raw response: {json.dumps(data, ensure_ascii=False)}")

    choices = data.get("choices") or []
    if not choices:
      raise ValueError("Deepseek did not return any choices.")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
      content = "".join(
        chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        for chunk in content
      )
    try:
      parsed = json.loads(content)
    except json.JSONDecodeError as exc:
      raise ValueError("Deepseek response was not valid JSON.") from exc

    tool_name = parsed.get("tool")
    arguments = parsed.get("arguments")
    if tool_name not in {"get_stock_price", "compare_stocks"} or not isinstance(arguments, dict):
      raise ValueError("Deepseek response did not include a valid tool call.")

    self._log_debug(f"[Deepseek] Routed to: {tool_name} with args {arguments}")
    return ToolCall(tool_name, {key: str(value) for key, value in arguments.items()})

  def _fallback_route(self, prompt: str) -> ToolCall:
    """
    Use a heuristic classifier when Deepseek is unavailable.

    Parameters
    ----------
    prompt : str
        User's request in natural language.

    Returns
    -------
    ToolCall
        Routed tool call derived from keyword matching.

    Raises
    ------
    ValueError
        Raised when the heuristic cannot infer the appropriate symbols.
    """
    lower_prompt = prompt.lower()
    symbols = self._extract_symbols(prompt)
    self._log_debug(f"[Router] Heuristic symbols detected: {symbols}")

    if "compare" in lower_prompt or "vs" in lower_prompt or "versus" in lower_prompt:
      if len(symbols) < 2:
        raise ValueError("Could not determine two symbols to compare.")
      symbol_one, symbol_two = symbols[:2]
      return ToolCall("compare_stocks", {"symbol_one": symbol_one, "symbol_two": symbol_two})

    if not symbols:
      raise ValueError("Could not determine a stock symbol from the query.")

    return ToolCall("get_stock_price", {"symbol": symbols[0]})

  def _extract_symbols(self, prompt: str) -> list[str]:
    """
    Identify probable ticker symbols mentioned in a prompt.

    Parameters
    ----------
    prompt : str
        Raw user query.

    Returns
    -------
    list[str]
        Candidate ticker symbols in the order they appear.
    """
    uppercase_tokens = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    candidates = [token for token in uppercase_tokens if token in KNOWN_TICKERS]
    if candidates:
      return candidates

    name_hits = []
    upper_prompt = prompt.upper()
    for name, ticker in NAME_TO_TICKER.items():
      if re.search(rf"\b{re.escape(name)}\b", upper_prompt):
        name_hits.append(ticker)
    if name_hits:
      seen = set()
      ordered = []
      for ticker in name_hits:
        if ticker not in seen:
          seen.add(ticker)
          ordered.append(ticker)
      return ordered

    dollar_tokens = re.findall(r"\$([A-Za-z]{1,5})", prompt)
    return [token.upper() for token in dollar_tokens if token.isalpha()]

  def _log_debug(self, message: str) -> None:
    """
    Emit a debug message when debugging is enabled.

    Parameters
    ----------
    message : str
        Text to send to stdout.
    """
    if self.debug:
      log_color(message, "d", prefix="[debug]")


class StockToolClient:
  """
  Manage the lifecycle of the stock tool server and act as a thin RPC client.
  """

  def __init__(self, server_path: Path, router: DeepseekRouter, debug: bool = False) -> None:
    """
    Create a new client.

    Parameters
    ----------
    server_path : Path
        Filesystem path pointing to the raw stdio server module.
    router : DeepseekRouter
        Router used to translate user prompts into tool calls.
    debug : bool, optional
        When ``True`` the client logs subprocess lifecycle events.
    """
    self.server_path = server_path
    self.router = router
    self.debug = debug
    self.process: Optional[subprocess.Popen[str]] = None

  def __enter__(self) -> "StockToolClient":
    """
    Start the server process when entering a context manager.

    Returns
    -------
    StockToolClient
        Self-reference enabling ``with`` statements.
    """
    self.start()
    return self

  def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    """
    Shut down the server process when leaving a context manager.

    Parameters
    ----------
    exc_type : Optional[type]
        Exception type raised in the managed block.
    exc : Optional[BaseException]
        Exception instance raised in the managed block.
    traceback : Optional[TracebackType]
        Traceback associated with ``exc``.
    """
    self.shutdown()

  def start(self) -> None:
    """
    Launch the tool server as a subprocess if it is not already running.

    Raises
    ------
    RuntimeError
        Raised when the server handshake fails.
    """
    if self.process is not None:
      return

    command = [sys.executable, "-u", str(self.server_path)]
    self._log_debug(f"[Client] Starting server with command: {command}")
    self.process = subprocess.Popen(
      command,
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      stderr=sys.stderr,
      text=True,
    )

    if self.process.stdout is None:
      raise RuntimeError("Server stdout pipe is not available.")

    ready_line = self.process.stdout.readline().strip()
    self._log_debug(f"[Client] Handshake line: {ready_line}")
    try:
      ready_payload = json.loads(ready_line)
    except json.JSONDecodeError as exc:
      raise RuntimeError(f"Failed to start server. Output: {ready_line}") from exc

    if ready_payload.get("type") != "ready":
      raise RuntimeError(f"Unexpected server handshake: {ready_payload}")

  def shutdown(self) -> None:
    """
    Terminate the tool server subprocess if it is running.
    """
    if self.process is None:
      return

    if self.process.stdin is not None:
      shutdown_payload = {"type": "shutdown", "id": str(uuid.uuid4())}
      self._log_debug(f"[Client] Sending shutdown payload: {shutdown_payload}")
      self.process.stdin.write(json.dumps(shutdown_payload) + "\n")
      self.process.stdin.flush()
      self.process.stdin.close()

    try:
      self.process.wait(timeout=2)
    except subprocess.TimeoutExpired:
      self._log_debug("[Client] Shutdown timed out; killing process.")
      self.process.kill()
    finally:
      if self.process.stdout is not None and not self.process.stdout.closed:
        self.process.stdout.close()
      if self.process.stderr not in (None, sys.stderr):
        self.process.stderr.close()
      self.process = None

  def invoke(self, tool_call: ToolCall) -> Dict[str, object]:
    """
    Send a tool invocation to the server and await the response.

    Parameters
    ----------
    tool_call : ToolCall
        Routed tool request produced by :class:`DeepseekRouter`.

    Returns
    -------
    Dict[str, object]
        Result payload returned by the tool server.

    Raises
    ------
    RuntimeError
        Raised when the server is not running or responds with an error.
    """
    if self.process is None or self.process.stdin is None or self.process.stdout is None:
      raise RuntimeError("Server process is not running.")

    request_id = str(uuid.uuid4())
    payload = {
      "type": "invoke",
      "id": request_id,
      "tool": tool_call.name,
      "arguments": tool_call.arguments,
    }
    self._log_debug(f"[Client] Sending request: {payload}")

    self.process.stdin.write(json.dumps(payload) + "\n")
    self.process.stdin.flush()

    response_line = self.process.stdout.readline().strip()
    self._log_debug(f"[Client] Raw response line: {response_line}")
    if not response_line:
      raise RuntimeError("Server returned an empty response.")

    response_payload = json.loads(response_line)
    if response_payload.get("id") != request_id:
      raise RuntimeError("Server response did not match the request id.")

    if "error" in response_payload and response_payload["error"] is not None:
      raise RuntimeError(str(response_payload["error"]))

    return response_payload.get("result", {})

  def _log_debug(self, message: str) -> None:
    """
    Emit a debug message when debugging is enabled.

    Parameters
    ----------
    message : str
        Text to send to stdout.
    """
    if self.debug:
      log_color(message, "d", prefix="[debug]")


def render_result(tool_call: ToolCall, result: Dict[str, object]) -> str:
  """
  Convert a tool response into a human-readable message.

  Parameters
  ----------
  tool_call : ToolCall
      Invoked tool metadata.
  result : Dict[str, object]
      Payload returned by the server.

  Returns
  -------
  str
      User-facing message reflecting the tool output.
  """
  if tool_call.name == "get_stock_price":
    data = result.get("data") or {}
    symbol = data.get("symbol", "UNKNOWN")
    price = data.get("price", "?")
    source = data.get("source", "unknown")
    return f"The current price of {symbol} is ${price} ({source})."

  if tool_call.name == "compare_stocks":
    data = result.get("data") or {}
    summary = data.get("summary", "Comparison data unavailable.")
    return summary

  return "Received an unexpected tool response."


def interactive_loop(debug: bool = False) -> None:
  """
  Run the interactive REPL loop that powers the workshop client.

  Parameters
  ----------
  debug : bool, optional
      When ``True`` verbose routing and transport logs are printed.
  """
  load_dotenv()
  api_key = os.getenv("DEEPSEEK_KEY")
  router = DeepseekRouter(api_key=api_key, debug=debug)
  server_path = Path(__file__).with_name("server.py")

  if api_key:
    log_color("Deepseek routing is enabled.", "w")
  else:
    log_color("Deepseek API key not found. Falling back to keyword routing.", "w")

  if debug:
    log_color("Debug mode enabled; verbose logs will be displayed.", "d", prefix="[debug]")

  log_color("Type 'exit' or 'quit' to leave the session.", "w")

  try:
    with StockToolClient(server_path=server_path, router=router, debug=debug) as client:
      while True:
        try:
          prompt_text = log_color("What is your query? → ", "w", emit=False)
          user_input = input(prompt_text).strip()
        except EOFError:
          log_color("\nGoodbye.", "w")
          break
        if debug:
          log_color(f"[Client] User input: {user_input}", "d", prefix="[debug]")

        if user_input.lower() in {"exit", "quit"}:
          log_color("Goodbye.", "w")
          break

        try:
          tool_call = router.route(user_input)
          if debug:
            log_color(f"[Client] Routed tool call: {tool_call}", "d", prefix="[debug]")
        except ValueError as exc:
          log_color(f"⚠️  {exc}", "w")
          continue

        try:
          response = client.invoke(tool_call)
          if debug:
            log_color(f"[Client] Tool response payload: {response}", "d", prefix="[debug]")
          message = render_result(tool_call, response)
          log_color(message, "g", prefix="[model]")
        except Exception as exc:  # pylint: disable=broad-except
          log_color(f"⚠️  {exc}", "w")
  finally:
    pass


def main() -> None:
  """
  Entrypoint used by ``python mcp_client.py``.
  """
  parser = argparse.ArgumentParser(description="Interact with the Deepseek MCP workshop client.")
  parser.add_argument(
    "--debug",
    action="store_true",
    help="Enable verbose debug logging for routing and tool calls.",
  )
  args = parser.parse_args()
  interactive_loop(debug=args.debug)


if __name__ == "__main__":
  main()
