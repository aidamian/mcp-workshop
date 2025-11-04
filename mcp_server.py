"""
Compatibility wrapper that re-exports the raw stdio server implementation.

The project now ships both the legacy JSON-over-stdio tools and an MCP SDK
variant. Keeping this module as a wrapper preserves the original entry point
and import contract for the raw server.
"""

from __future__ import annotations

from raw_version.server import (
    StockDataProvider,
    StockPrice,
    StockToolServer,
    main as raw_main,
)

__all__ = ["StockDataProvider", "StockPrice", "StockToolServer", "main"]


def main() -> None:
  """Entrypoint alias preserved for backwards compatibility."""
  raw_main()


if __name__ == "__main__":
  main()
