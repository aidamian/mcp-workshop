from __future__ import annotations

"""
Variant launcher for the MCP workshop client.

Usage:
  python mcp_client.py           # defaults to raw variant
  python mcp_client.py course    # explicit variant (positional)
  python mcp_client.py --variant mcp
"""

import argparse
import importlib
import sys
from typing import Literal, cast

Variant = Literal["raw", "mcp", "course"]


def _load_variant(variant: Variant):
  if variant == "raw":
    return importlib.import_module("raw_version.client")
  if variant == "mcp":
    return importlib.import_module("mcp_version.client")
  if variant == "course":
    return importlib.import_module("course_version.client")
  raise ValueError(f"Unknown variant {variant}")


def main() -> None:
  parser = argparse.ArgumentParser(description="Launch MCP workshop client.")
  parser.add_argument(
    "variant",
    nargs="?",
    choices=["raw", "mcp", "course"],
    help="Client variant to run (default: raw).",
  )
  parser.add_argument(
    "--variant",
    dest="variant_flag",
    choices=["raw", "mcp", "course"],
    default=None,
    help="Client variant to run (default: raw).",
  )
  args, remaining = parser.parse_known_args()
  if args.variant and args.variant_flag and args.variant != args.variant_flag:
    parser.error("Variant provided twice with different values.")

  selected = args.variant_flag or args.variant or "raw"
  module = _load_variant(cast(Variant, selected))
  sys.argv = [sys.argv[0], *remaining]
  module.main()


if __name__ == "__main__":
  main()
