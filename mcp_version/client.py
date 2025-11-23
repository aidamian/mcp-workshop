from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from openai import OpenAI

from utils.deepseek import DEFAULT_MODEL, DeepseekRouter as BaseRouter
from utils.utils import ToolCall, log_color, log_lifecycle_event, render_result

try:  # pragma: no cover - optional dependency for this variant
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client
  from mcp.shared.memory import create_connected_server_and_client_session
except ImportError as exc:  # pragma: no cover - deferred dependency
  raise ImportError("Install the 'mcp' package to use the MCP client variant.") from exc


class OpenAIBackedRouter(BaseRouter):
  """
  Router that uses the official OpenAI Python SDK for structured routing with Deepseek.
  """

  def __init__(
    self,
    api_key: Optional[str],
    model: str = DEFAULT_MODEL,
    base_url: str = "https://api.deepseek.com",
    debug: bool = True,
  ) -> None:
    super().__init__(api_key=api_key, model=model, debug=debug)
    self.base_url = base_url
    if api_key:
      # Explicit http_client sidesteps httpx>=0.28 dropping the `proxies` kwarg the OpenAI SDK still uses.
      http_client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(600.0, connect=5.0))
      self._client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
    else:
      self._client = None

  def _deepseek_route(self, prompt: str) -> ToolCall:
    if not self._client:
      raise ValueError("Deepseek API key is not configured.")

    payload_messages = [
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
    ]
    self._log_debug(f"[Deepseek/OpenAI] Request messages: {payload_messages}")
    response = self._client.chat.completions.create(
      model=self.model,
      messages=payload_messages,
      response_format={"type": "json_object"},
      timeout=20,
    )
    choice_message = response.choices[0].message
    content = choice_message.content or ""
    if isinstance(content, list):
      content = "".join(str(chunk) for chunk in content)
    self._log_debug(f"[Deepseek/OpenAI] Raw content: {content}")

    try:
      parsed = json.loads(content)
    except json.JSONDecodeError as exc:
      raise ValueError("Deepseek response was not valid JSON.") from exc

    tool_name = parsed.get("tool")
    arguments = parsed.get("arguments")
    if tool_name not in {"get_stock_price", "compare_stocks"} or not isinstance(arguments, dict):
      raise ValueError("Deepseek response did not include a valid tool call.")

    tool_call = ToolCall(tool_name, {key: str(value) for key, value in arguments.items()}, source="openai")
    self._log_debug(f"[Deepseek/OpenAI] Routed to: {tool_call.name} with args {tool_call.arguments}")
    return tool_call


class MCPStockClient:
  """Manage an MCP stdio session against the stock tool server using the official MCP package."""

  def __init__(
    self,
    server_path: Path,
    debug: bool = True,
    *,
    force_memory: Optional[bool] = None,
    init_timeout: float = 10.0,
  ) -> None:
    self.server_path = server_path
    self.debug = debug
    force_memory_env = os.getenv("MCP_FORCE_MEMORY", "").lower() in {"1", "true", "yes"}
    self.force_memory = force_memory if force_memory is not None else force_memory_env
    self.init_timeout = init_timeout
    self._session: Optional[ClientSession] = None
    self._memory_session_cm = None
    self._read = None
    self._write = None
    self._stdio_cm = None

  async def __aenter__(self) -> "MCPStockClient":
    await self.start()
    return self

  async def __aexit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    await self.shutdown()

  async def start(self) -> None:
    """Launch the MCP server subprocess and handshake a session."""
    if self._session is not None:
      return

    if self.force_memory:
      if self.debug:
        log_color("Using in-process memory transport for MCP client.", "d", prefix="[debug]")
      await self._start_memory_session()
      return

    try:
      await self._start_stdio_session()
    except Exception as exc:  # pylint: disable=broad-except
      if self.debug:
        log_color(
          f"Stdio transport failed ({exc}); falling back to in-process transport.",
          "y",
          prefix="[debug]",
        )
      await self.shutdown()
      await self._start_memory_session()

  async def _start_stdio_session(self) -> None:
    """Spin up the FastMCP server as a subprocess and initialise the MCP session."""
    params = StdioServerParameters(command=sys.executable, args=["-u", str(self.server_path)])
    if self.debug:
      log_color(f"[MCP Client] Starting server: {params}", "d", prefix="[debug]")
      log_color("Running stdio_client...","d", prefix="[debug]")
    self._stdio_cm = stdio_client(params)
    if self.debug:
      log_color("stdio_client running.","d", prefix="[debug]")
      log_color("Entering stdio_client context manager...","d", prefix="[debug]")
    self._read, self._write = await self._stdio_cm.__aenter__()
    if self.debug:
      log_color("Stdio client context manager entered.","d", prefix="[debug]")
      log_color("Creating MCP client session...","d", prefix="[debug]")
    self._session = ClientSession(
      self._read,
      self._write,
      read_timeout_seconds=timedelta(seconds=self.init_timeout),
    )
    if self.debug:
      log_color("MCP client session created.","d", prefix="[debug]")
      log_color("Entering MCP client session context...","d", prefix="[debug]")
    await self._session.__aenter__()
    if self.debug:
      log_color("MCP client session context entered.","d", prefix="[debug]")
      log_color("Initializing MCP session...","d", prefix="[debug]")
    await self._session.initialize()
    if self.debug:
      log_color("[MCP Client] MCP session initialised.", "d", prefix="[debug]")

  async def _start_memory_session(self) -> None:
    """Connect to the FastMCP server in-process using memory streams."""
    from mcp_version import server as server_module

    self._memory_session_cm = create_connected_server_and_client_session(
      server_module.server._mcp_server,  # pylint: disable=protected-access
      raise_exceptions=True,
    )
    self._session = await self._memory_session_cm.__aenter__()
    if self.debug:
      log_color("In-process MCP session initialised.", "d", prefix="[debug]")

  async def shutdown(self) -> None:
    """Terminate the MCP session and the underlying subprocess."""
    if self._memory_session_cm is not None:
      await self._memory_session_cm.__aexit__(None, None, None)
      self._memory_session_cm = None
      self._session = None
      return

    if self._session is not None:
      await self._session.__aexit__(None, None, None)
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
    """Execute a tool call over the MCP session."""
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
  """Run the async REPL that communicates with the MCP server."""
  load_dotenv()
  api_key = os.getenv("DEEPSEEK_KEY")
  base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
  router = OpenAIBackedRouter(api_key=api_key, base_url=base_url, debug=debug)
  server_path = Path(__file__).with_name("server.py")

  if api_key:
    log_color("Deepseek routing is enabled via OpenAI SDK.", "y", prefix="[mcp-client]")
  else:
    log_color("Deepseek API key not found. Falling back to keyword routing.", "y", prefix="[mcp-client]")

  if debug:
    log_color("Debug mode enabled; verbose MCP logs will be displayed.", "d", prefix="[debug]")

  log_color("Type 'exit' or 'quit' to leave the session.", "w", prefix="[prompt]")

  async with MCPStockClient(server_path=server_path, debug=debug) as client:
    while True:
      try:
        prompt_text = log_color("What is your query? → ", "w", prefix="[prompt]", emit=False)
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

      log_lifecycle_event("query", user_input)

      try:
        tool_call = router.route(user_input)
        analysis_detail = (
          f"Strategy={tool_call.source}; tool={tool_call.name}; args={tool_call.arguments}"
        )
        log_lifecycle_event("analysis", analysis_detail)
      except ValueError as exc:
        log_color(f"⚠️  {exc}", "r", prefix="[error]")
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
        log_color(f"⚠️  {exc}", "r", prefix="[error]")


def main() -> None:
  """CLI entry point for the MCP-enabled client."""
  parser = argparse.ArgumentParser(description="Interact with the MCP-enabled stock client.")
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
