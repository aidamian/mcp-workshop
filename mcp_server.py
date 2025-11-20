from __future__ import annotations

"""
Variant launcher for the MCP workshop server.

Usage:
  python mcp_server.py              # defaults to raw variant
  python mcp_server.py --variant mcp
  python mcp_server.py --variant course
"""

import argparse
import importlib
import sys
from typing import Literal

Variant = Literal["raw", "mcp", "course"]


def _load_variant(variant: Variant):
  if variant == "raw":
    return importlib.import_module("raw_version.server")
  if variant == "mcp":
    return importlib.import_module("mcp_version.server")
  if variant == "course":
    return importlib.import_module("course_version.server")
  raise ValueError(f"Unknown variant {variant}")


def main() -> None:
  parser = argparse.ArgumentParser(description="Launch MCP workshop server.")
  parser.add_argument(
    "--variant",
    choices=["raw", "mcp", "course"],
    default="raw",
    help="Server variant to run (default: raw).",
  )
  args, remaining = parser.parse_known_args()
  module = _load_variant(args.variant)
  sys.argv = [sys.argv[0], *remaining]
  module.main()


if __name__ == "__main__":
  main()
