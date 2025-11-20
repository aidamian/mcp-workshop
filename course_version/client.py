"""
Course variant of the MCP client that uses the official MCP package plus Google
Gemini for tool routing. Logging follows the raw_version colour lifecycle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai

from raw_version.client import DeepseekRouter, ToolCall, log_color, log_lifecycle_event, render_result

try:  # pragma: no cover - optional dependency for this variant
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError("Install the 'mcp' package to use the course MCP client.") from exc


class GeminiRouter:
  """Route user prompts to tools using Gemini, with heuristic fallback."""

  def __init__(self, api_key: Optional[str], model: str = "gemini-1.5-flash-latest", debug: bool = True) -> None:
    self.api_key = api_key
    self.model = model
    self.debug = debug
    self._client: Optional[genai.Client] = genai.Client(api_key=api_key) if api_key else None
    # Heuristic-only fallback
    self._fallback = DeepseekRouter(api_key=None, debug=debug)

  def route(self, prompt: str) -> ToolCall:
    if self._client is None:
      return self._fallback.route(prompt)
    try:
      return self._gemini_route(prompt)
    except Exception as exc:  # pylint: disable=broad-except
      if self.debug:
        log_color(f"[Gemini Router] Falling back to heuristics due to: {exc}", "d", prefix="[debug]")
      return self._fallback.route(prompt)

  def _gemini_route(self, prompt: str) -> ToolCall:
    template = (
      "You are a routing assistant for a stock data toolset. "
      "Map the user's prompt to either 'get_stock_price' or "
      "'compare_stocks'. Always return JSON with keys "
      "tool (string) and arguments (object). For get_stock_price provide symbol. "
      "For compare_stocks provide symbol_one and symbol_two. Symbols must be uppercase tickers.\n"
      f"User prompt: {prompt}"
    )
    response = self._client.models.generate_content(  # type: ignore[union-attr]
      model=self.model,
      contents=template,
    )
    raw = response.text.strip() if hasattr(response, "text") else str(response)
    raw = raw.replace("```json", "").replace("```", "")
    parsed = json.loads(raw)

    tool_name = parsed.get("tool")
    arguments = parsed.get("arguments")
    if tool_name not in {"get_stock_price", "compare_stocks"} or not isinstance(arguments, dict):
      raise ValueError("Gemini response did not include a valid tool call.")

    tool_call = ToolCall(tool_name, {key: str(value) for key, value in arguments.items()}, source="gemini")
    if self.debug:
      log_color(f"[Gemini Router] Routed to: {tool_call.name} with args {tool_call.arguments}", "d", prefix="[debug]")
    return tool_call


class CourseMCPClient:
  """Thin MCP client using the official package for the course variant."""

  def __init__(self, server_path: Path, debug: bool = True) -> None:
    self.server_path = server_path
    self.debug = debug
    self._session: Optional[ClientSession] = None
    self._read = None
    self._write = None
    self._stdio_cm = None

  async def __aenter__(self) -> "CourseMCPClient":
    await self.start()
    return self

  async def __aexit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    await self.shutdown()

  async def start(self) -> None:
    if self._session is not None:
      return
    params = StdioServerParameters(
      command=os.environ.get("PYTHON", sys.executable),
      args=["-u", str(self.server_path)],
    )
    if self.debug:
      log_color(f"[Course MCP Client] Starting server: {params}", "d", prefix="[debug]")
    self._stdio_cm = stdio_client(params)
    self._read, self._write = await self._stdio_cm.__aenter__()
    self._session = ClientSession(self._read, self._write)
    await self._session.initialize()
    if self.debug:
      log_color("[Course MCP Client] MCP session initialised.", "d", prefix="[debug]")

  async def shutdown(self) -> None:
    if self._session is not None:
      await self._session.close()
      self._session = None
    if self._write is not None:
      await self._write.aclose()
      self._write = None
    if self._read is not None:
      await self._read.aclose()
      self._read = None
    if self._stdio_cm is not None:
      await self._stdio_cm.__aexit__(None, None, None)
      self._stdio_cm = None

  async def invoke(self, tool_call: ToolCall) -> Dict[str, Any]:
    if self._session is None:
      raise RuntimeError("MCP session is not initialised.")

    log_lifecycle_event(
      "mcp",
      f"Dispatching request to {tool_call.name} with arguments {tool_call.arguments}",
    )
    response = await self._session.call_tool(tool_call.name, tool_call.arguments)

    payload: Dict[str, Any] = {}
    if hasattr(response, "content"):
      text_chunks = [
        getattr(item, "text", "")
        for item in getattr(response, "content", [])
        if getattr(item, "type", "") == "text"
      ]
      if text_chunks:
        raw_text = text_chunks[0]
        try:
          payload = json.loads(raw_text)
        except json.JSONDecodeError:
          payload = {"data": raw_text}
    elif hasattr(response, "to_dict"):
      payload = response.to_dict()  # type: ignore[assignment]
    elif isinstance(response, dict):
      payload = response
    else:
      payload = {"data": response}

    log_lifecycle_event(
      "mcp",
      f"Received response payload keys: {list(payload.keys())}",
    )
    return payload


async def interactive_loop(debug: bool = True) -> None:
  load_dotenv()
  api_key = os.getenv("GEMINI_API_KEY")
  router = GeminiRouter(api_key=api_key, debug=debug)
  server_path = Path(__file__).with_name("server.py")

  if api_key:
    log_color("Gemini routing is enabled via google-genai SDK.", "w")
  else:
    log_color("Gemini API key not found. Falling back to keyword routing.", "w")

  if debug:
    log_color("Debug mode enabled; verbose MCP logs will be displayed.", "d", prefix="[debug]")

  log_color("Type 'exit' or 'quit' to leave the session.", "w")

  async with CourseMCPClient(server_path=server_path, debug=debug) as client:
    while True:
      try:
        prompt_text = log_color("What is your query? → ", "w", emit=False)
        loop = asyncio.get_running_loop()
        user_input = await loop.run_in_executor(None, input, prompt_text)
      except (EOFError, KeyboardInterrupt):
        log_color("\nGoodbye.", "w")
        break

      if debug:
        log_color(f"[Course MCP Client] User input: {user_input}", "d", prefix="[debug]")

      if user_input.strip().lower() in {"exit", "quit"}:
        log_color("Goodbye.", "w")
        break

      log_lifecycle_event("query", user_input)

      try:
        tool_call = router.route(user_input)
        analysis_detail = (
          f"Strategy={tool_call.source}; tool={tool_call.name}; args={tool_call.arguments}"
        )
        log_lifecycle_event("analysis", analysis_detail)
      except ValueError as exc:
        log_color(f"⚠️  {exc}", "r", prefix="[warning]")
        continue

      try:
        response = await client.invoke(tool_call)
        data = response.get("data") if isinstance(response, dict) else {}
        if tool_call.name == "get_stock_price":
          detail = f"Symbol={data.get('symbol', 'UNKNOWN')}; source={data.get('source', 'unknown')}"
        elif tool_call.name == "compare_stocks":
          symbol_one = (data or {}).get("symbol_one", {})
          symbol_two = (data or {}).get("symbol_two", {})
          detail = (
            f"Comparison payload ready: {symbol_one.get('symbol', '?')} vs "
            f"{symbol_two.get('symbol', '?')}"
          )
        else:
          detail = "Received response from tool execution."
        log_lifecycle_event("prepare", detail)
        message = render_result(tool_call, response)
        log_lifecycle_event("final", message)
      except Exception as exc:  # pylint: disable=broad-except
        log_color(f"⚠️  {exc}", "r", prefix="[warning]")


def main() -> None:
  parser = argparse.ArgumentParser(description="Course MCP client using google-genai routing.")
  parser.add_argument(
    "--no-debug",
    dest="debug",
    action="store_false",
    help="Disable verbose debug logging (default: enabled).",
  )
  parser.set_defaults(debug=True)
  args = parser.parse_args()
  asyncio.run(interactive_loop(debug=args.debug))


if __name__ == "__main__":
  main()
