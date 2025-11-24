from __future__ import annotations

"""
Interactive CLI that delegates stock queries to the MCP-style tool server.

The router relies on Deepseek for natural language interpretation when an API
key is present. If the key is missing or the API call fails, a deterministic
keyword-based classifier is used instead so that the workshop remains usable in
offline settings.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from utils.deepseek import DeepseekRouter
from utils.utils import ToolCall, log_color, log_lifecycle_event, render_result


class StockToolClient:
  """
  Manage the lifecycle of the stock tool server and act as a thin RPC client.
  """

  def __init__(self, server_path: Path, router: DeepseekRouter, debug: bool = True) -> None:
    """
    Create the client wrapper.

    Parameters
    ----------
    server_path : Path
        Filesystem path to the stdio server entry point.
    router : DeepseekRouter
        Router used to turn natural language into tool calls.
    debug : bool, optional
        Whether to emit verbose lifecycle logs. Defaults to ``True``.
    """
    # Path to the server script we will spawn in a subprocess.
    self.server_path = server_path
    # Router used for tool selection (stored for parity with other variants).
    self.router = router
    # Toggle extra debug logging from the client helper.
    self.debug = debug
    # The running subprocess (None until started).
    self.process: Optional[subprocess.Popen[str]] = None

  def __enter__(self) -> "StockToolClient":
    """
    Enter the context manager by ensuring the server is running.

    Returns
    -------
    StockToolClient
        The started client instance.
    """
    self.start()
    return self

  def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    """
    Exit the context manager by shutting down the server process.

    Parameters
    ----------
    exc_type : type
        Exception type if one was raised inside the context.
    exc : BaseException
        Exception instance if present.
    traceback : TracebackType
        Traceback associated with the exception, if any.
    """
    self.shutdown()

  def start(self) -> None:
    """
    Launch the stdio server subprocess and wait for its ready signal.

    Raises
    ------
    RuntimeError
        If the server fails to start or does not emit a ready payload.
    """
    if self.process is not None:
      return

    # Build the Python command to start the server with unbuffered output.
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

    # Wait for the server to print its readiness JSON line.
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
    Tear down the server subprocess cleanly.
    """
    if self.process is None:
      return

    if self.process.stdin is not None:
      # Send a shutdown request so the server can exit gracefully.
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
    Send a tool invocation request and return the parsed response.

    Parameters
    ----------
    tool_call : ToolCall
        Routed tool name and arguments to forward to the server.

    Returns
    -------
    Dict[str, object]
        Response payload containing tool output.

    Raises
    ------
    RuntimeError
        If the server is not running, returns mismatched ids, or reports an error.
    """
    if self.process is None or self.process.stdin is None or self.process.stdout is None:
      raise RuntimeError("Server process is not running.")

    # Generate a unique id so request/response lines can be correlated.
    request_id = str(uuid.uuid4())
    payload = {
      "type": "invoke",
      "id": request_id,
      "tool": tool_call.name,
      "arguments": tool_call.arguments,
    }
    log_lifecycle_event(
      "mcp",
      f"Dispatching request {request_id} to {tool_call.name} with arguments {tool_call.arguments}",
    )
    self._log_debug(f"[Client] Sending request: {payload}")

    self.process.stdin.write(json.dumps(payload) + "\n")
    self.process.stdin.flush()

    # Read a single response line back from the server.
    response_line = self.process.stdout.readline().strip()
    self._log_debug(f"[Client] Raw response line: {response_line}")
    if not response_line:
      raise RuntimeError("Server returned an empty response.")

    response_payload = json.loads(response_line)
    # Track the response lifecycle for observability.
    log_lifecycle_event(
      "mcp",
      f"Received response for request {request_id} with keys {list(response_payload.keys())}",
    )
    # Validate that the correlation id matches the request we sent.
    if response_payload.get("id") != request_id:
      raise RuntimeError("Server response did not match the request id.")

    if "error" in response_payload and response_payload["error"] is not None:
      raise RuntimeError(str(response_payload["error"]))

    return response_payload.get("result", {})

  def _log_debug(self, message: str) -> None:
    """
    Emit debug logs when debug mode is enabled.

    Parameters
    ----------
    message : str
        Text to log with the debug colour palette.
    """
    if self.debug:
      log_color(message, "d", prefix="[debug]")


def interactive_loop(debug: bool = True) -> None:
  """
  Run the interactive REPL loop that powers the workshop client.

  Parameters
  ----------
  debug : bool, optional
      Whether to show verbose logs. Defaults to ``True``.
  """
  load_dotenv()
  # Pull the Deepseek key for routing; fall back to heuristics if absent.
  api_key = os.getenv("DEEPSEEK_KEY")
  # Router remains a dependency even when heuristics are used.
  router = DeepseekRouter(api_key=api_key, debug=debug)
  # The server lives next to this client in the raw variant.
  server_path = Path(__file__).with_name("server.py")

  if api_key:
    log_color("Deepseek routing is enabled.", "y", prefix="[mcp-client]")
  else:
    log_color("Deepseek API key not found. Falling back to keyword routing.", "y", prefix="[mcp-client]")

  if debug:
    log_color("Debug mode enabled; verbose logs will be displayed.", "d", prefix="[debug]")

  log_color("Type 'exit' or 'quit' to leave the session.", "w", prefix="[prompt]")

  try:
    with StockToolClient(server_path=server_path, router=router, debug=debug) as client:
      while True:
        try:
          # Render the coloured prompt without emitting a newline early.
          prompt_text = log_color("What is your query? → ", "w", prefix="[prompt]", emit=False)
          user_input = input(prompt_text).strip()
        except EOFError:
          log_color("\nGoodbye.", "w")
          break
        if debug:
          log_color(f"[Client] User input: {user_input}", "d", prefix="[debug]")

        if user_input.lower() in {"exit", "quit"}:
          log_color("Goodbye.", "w")
          break

        # Track the raw query event for downstream logging/analytics.
        log_lifecycle_event("query", user_input)

        try:
          # Route the prompt to a tool call (AI when available; heuristics otherwise).
          tool_call = router.route(user_input)
          analysis_detail = (
            f"Strategy={tool_call.source}; tool={tool_call.name}; args={tool_call.arguments}"
          )
          log_lifecycle_event("analysis", analysis_detail)
        except ValueError as exc:
          log_color(f"⚠️  {exc}", "r", prefix="[error]")
          continue

        try:
          # Dispatch the tool invocation and render the structured result.
          response = client.invoke(tool_call)
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
  finally:
    pass


def main() -> None:
  """
  Parse CLI flags and start the interactive client.
  """
  parser = argparse.ArgumentParser(description="Interact with the Deepseek MCP workshop client.")
  parser.add_argument(
    "--no-debug",
    dest="debug",
    action="store_false",
    help="Disable verbose debug logging (default: enabled).",
  )
  parser.set_defaults(debug=True)
  args = parser.parse_args()
  interactive_loop(debug=args.debug)


if __name__ == "__main__":
  main()
