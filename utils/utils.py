"""
Shared logging utilities, lifecycle helpers, and simple data classes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict

COLOR_CODES = {
  "g": "\033[32m",   # green
  "d": "\033[90m",   # dark grey
  "w": "\033[97m",   # white
  "b": "\033[94m",   # blue
  "p": "\033[95m",   # purple / magenta
  "y": "\033[33m",   # yellow
  "r": "\033[31m",   # red
}

LIFECYCLE_STAGES = {
  "query": ("User prompt received", "w", "[prompt]"),
  "analysis": ("Model analysis & tool selection", "b", "[model]"),
  "mcp": ("MCP client dispatch", "y", "[mcp-client]"),
  "prepare": ("Model drafting response", "b", "[model]"),
  "final": ("Final result", "g", "[result]"),
}


def log_color(
  message: str,
  color: str = "w",
  prefix: str = "[agent]",
  *,
  emit: bool = True,
  use_stderr: bool = False,
) -> str:
  """
  Wrap a message in an ANSI colour code and optionally print it.
  """
  colour_code = COLOR_CODES.get(color, COLOR_CODES["w"])
  suffix = "\033[0m"
  formatted = f"{colour_code}{prefix} {message}{suffix}"
  if emit:
    stream = sys.stderr if use_stderr else sys.stdout
    print(formatted, file=stream, flush=True)
  return formatted


def log_lifecycle_event(stage: str, detail: str) -> None:
  """
  Emit a colour-coded lifecycle event for the client flows.
  """
  label, color, prefix = LIFECYCLE_STAGES.get(stage, ("Event", "w", "[agent]"))
  log_color(f"{label}: {detail}", color, prefix=prefix)


@dataclass
class ToolCall:
  """
  Normalised representation of a tool invocation determined by the router.
  """

  name: str
  arguments: Dict[str, str]
  source: str = "unknown"


def render_result(tool_call: ToolCall, result: Dict[str, object]) -> str:
  """
  Convert a tool response into a human-readable message.
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


__all__ = [
  "COLOR_CODES",
  "LIFECYCLE_STAGES",
  "ToolCall",
  "log_color",
  "log_lifecycle_event",
  "render_result",
]
