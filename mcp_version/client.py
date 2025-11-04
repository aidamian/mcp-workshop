"""
Interactive client that talks to the MCP SDK-powered server.

The conversational flow mirrors the raw implementation but uses the official
``modelcontextprotocol`` client runtime for transport and tool invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from raw_version.client import DeepseekRouter, ToolCall, log_color, render_result

try:  # pragma: no cover - optional dependency for this variant
  from mcp.client.session import Session
  from mcp.transport.stdio import StdioClientTransport
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError(
    "Install the 'modelcontextprotocol' package to use the MCP client variant."
  ) from exc


class MCPStockClient:
  """Manage an MCP stdio session against the stock tool server."""

  def __init__(self, server_path: Path, debug: bool = False) -> None:
    self.server_path = server_path
    self.debug = debug
    self._transport: Optional[StdioClientTransport] = None
    self._session: Optional[Session] = None

  async def __aenter__(self) -> "MCPStockClient":
    await self.start()
    return self

  async def __aexit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    await self.shutdown()

  async def start(self) -> None:
    """Launch the MCP server subprocess and handshake a session."""
    if self._session is not None:
      return

    command = [sys.executable, "-u", str(self.server_path)]
    if self.debug:
      log_color(f"[MCP Client] Starting server: {command}", "d", prefix="[debug]")

    self._transport = await StdioClientTransport.create(command)
    self._session = Session("stock-workshop", self._transport)
    await self._session.initialize()

  async def shutdown(self) -> None:
    """Terminate the MCP session and the underlying subprocess."""
    if self._session is not None:
      await self._session.close()
      self._session = None

    if self._transport is not None:
      await self._transport.close()
      self._transport = None

  async def invoke(self, tool_call: ToolCall) -> Dict[str, Any]:
    """Execute a tool call over the MCP session."""
    if self._session is None:
      raise RuntimeError("MCP session is not initialised.")

    if self.debug:
      log_color(
        f"[MCP Client] Invoking {tool_call.name} with {tool_call.arguments}",
        "d",
        prefix="[debug]",
      )

    response = await self._session.call_tool(tool_call.name, tool_call.arguments)
    if hasattr(response, "to_dict"):
      return response.to_dict()  # type: ignore[no-any-return]
    if isinstance(response, dict):
      return response
    return {"data": response}


async def interactive_loop(debug: bool = False) -> None:
  """Run the async REPL that communicates with the MCP server."""
  load_dotenv()
  api_key = os.getenv("DEEPSEEK_KEY")
  router = DeepseekRouter(api_key=api_key, debug=debug)
  server_path = Path(__file__).with_name("server.py")

  if api_key:
    log_color("Deepseek routing is enabled.", "w")
  else:
    log_color("Deepseek API key not found. Falling back to keyword routing.", "w")

  if debug:
    log_color("Debug mode enabled; verbose MCP logs will be displayed.", "d", prefix="[debug]")

  log_color("Type 'exit' or 'quit' to leave the session.", "w")

  async with MCPStockClient(server_path=server_path, debug=debug) as client:
    while True:
      try:
        prompt_text = log_color("What is your query? → ", "w", emit=False)
        loop = asyncio.get_running_loop()
        user_input = await loop.run_in_executor(None, input, prompt_text)
      except (EOFError, KeyboardInterrupt):
        log_color("\nGoodbye.", "w")
        break

      if debug:
        log_color(f"[MCP Client] User input: {user_input}", "d", prefix="[debug]")

      if user_input.strip().lower() in {"exit", "quit"}:
        log_color("Goodbye.", "w")
        break

      try:
        tool_call = router.route(user_input)
        if debug:
          log_color(f"[MCP Client] Routed tool call: {tool_call}", "d", prefix="[debug]")
      except ValueError as exc:
        log_color(f"⚠️  {exc}", "w")
        continue

      try:
        response = await client.invoke(tool_call)
        message = render_result(tool_call, response)
        log_color(message, "g", prefix="[model]")
      except Exception as exc:  # pylint: disable=broad-except
        log_color(f"⚠️  {exc}", "w")


def main() -> None:
  """CLI entry point for the MCP-enabled client."""
  parser = argparse.ArgumentParser(description="Interact with the MCP-enabled stock client.")
  parser.add_argument(
    "--debug",
    action="store_true",
    help="Enable verbose debug logging for routing and MCP transport.",
  )
  args = parser.parse_args()
  asyncio.run(interactive_loop(debug=args.debug))


if __name__ == "__main__":
  main()
