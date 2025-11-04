"""
Compatibility wrapper that exposes the raw MCP client implementation.

The repository now contains two variants of the workshop: a raw stdio client
and an MCP SDK-powered client. This module keeps the original import surface
so existing callers and tests continue to function without modification.
"""

from __future__ import annotations

from raw_version.client import (
    COLOR_CODES,
    DEEPSEEK_API_URL,
    DEFAULT_MODEL,
    KNOWN_TICKERS,
    NAME_TO_TICKER,
    DeepseekRouter,
    StockToolClient,
    ToolCall,
    interactive_loop,
    log_color,
    main as raw_main,
    render_result,
)

__all__ = [
    "COLOR_CODES",
    "DEEPSEEK_API_URL",
    "DEFAULT_MODEL",
    "KNOWN_TICKERS",
    "NAME_TO_TICKER",
    "DeepseekRouter",
    "StockToolClient",
    "ToolCall",
    "interactive_loop",
    "log_color",
    "render_result",
    "main",
]


def main() -> None:
  """Entrypoint alias preserved for backwards compatibility."""
  raw_main()


if __name__ == "__main__":
  main()
