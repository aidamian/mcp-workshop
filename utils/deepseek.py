"""
Deepseek routing helpers shared across client variants.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional

import requests

from utils.utils import ToolCall, log_color

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
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


class DeepseekRouter:
  """
  Determine which tool to invoke based on a natural language query.

  When a Deepseek API key is available the router requests a structured JSON
  response. Failures fall back to a deterministic heuristic so the user can
  continue without external connectivity.
  """

  def __init__(self, api_key: Optional[str], model: str = DEFAULT_MODEL, debug: bool = True) -> None:
    self.api_key = api_key
    self.model = model
    self.debug = debug

  def route(self, prompt: str) -> ToolCall:
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
      raise ValueError("Query cannot be empty.")

    self._log_debug(f"[Router] Received prompt: {cleaned_prompt}")

    if not self.api_key:
      self._log_debug("[Router] No Deepseek key detected; using heuristic classifier.")
      return self._fallback_route(cleaned_prompt, source_label="heuristic_no_key")

    try:
      return self._deepseek_route(cleaned_prompt)
    except Exception as exc:  # pylint: disable=broad-except
      self._log_debug(f"[Router] Deepseek routing failed ({exc}); reverting to heuristics.")
      return self._fallback_route(cleaned_prompt, source_label="heuristic_fallback")

  def _deepseek_route(self, prompt: str) -> ToolCall:
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

    tool_call = ToolCall(tool_name, {key: str(value) for key, value in arguments.items()}, source="deepseek")
    self._log_debug(f"[Deepseek] Routed to: {tool_call.name} with args {tool_call.arguments}")
    return tool_call

  def _fallback_route(self, prompt: str, source_label: str = "heuristic") -> ToolCall:
    lower_prompt = prompt.lower()
    symbols = self._extract_symbols(prompt)
    self._log_debug(f"[Router] Heuristic symbols detected: {symbols}")

    if "compare" in lower_prompt or "vs" in lower_prompt or "versus" in lower_prompt:
      if len(symbols) < 2:
        raise ValueError("Could not determine two symbols to compare.")
      symbol_one, symbol_two = symbols[:2]
      return ToolCall(
        "compare_stocks",
        {"symbol_one": symbol_one, "symbol_two": symbol_two},
        source=source_label,
      )

    if not symbols:
      raise ValueError("Could not determine a stock symbol from the query.")

    return ToolCall("get_stock_price", {"symbol": symbols[0]}, source=source_label)

  def _extract_symbols(self, prompt: str) -> list[str]:
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
    if self.debug:
      log_color(message, "d", prefix="[debug]")


__all__ = [
  "DEEPSEEK_API_URL",
  "DEFAULT_MODEL",
  "KNOWN_TICKERS",
  "NAME_TO_TICKER",
  "DeepseekRouter",
]
