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
    self.server_path = server_path
    self.router = router
    self.debug = debug
    self.process: Optional[subprocess.Popen[str]] = None

  def __enter__(self) -> "StockToolClient":
    self.start()
    return self

  def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[override]
    self.shutdown()

  def start(self) -> None:
    if self.process is not None:
      return

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

    ready_line = self.process.stdout.readline().strip()
    self._log_debug(f"[Client] Handshake line: {ready_line}")
    try:
      ready_payload = json.loads(ready_line)
    except json.JSONDecodeError as exc:
      raise RuntimeError(f"Failed to start server. Output: {ready_line}") from exc

    if ready_payload.get("type") != "ready":
      raise RuntimeError(f"Unexpected server handshake: {ready_payload}")

  def shutdown(self) -> None:
    if self.process is None:
      return

    if self.process.stdin is not None:
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
    if self.process is None or self.process.stdin is None or self.process.stdout is None:
      raise RuntimeError("Server process is not running.")

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

    response_line = self.process.stdout.readline().strip()
    self._log_debug(f"[Client] Raw response line: {response_line}")
    if not response_line:
      raise RuntimeError("Server returned an empty response.")

    response_payload = json.loads(response_line)
    log_lifecycle_event(
      "mcp",
      f"Received response for request {request_id} with keys {list(response_payload.keys())}",
    )
    if response_payload.get("id") != request_id:
      raise RuntimeError("Server response did not match the request id.")

    if "error" in response_payload and response_payload["error"] is not None:
      raise RuntimeError(str(response_payload["error"]))

    return response_payload.get("result", {})

  def _log_debug(self, message: str) -> None:
    if self.debug:
      log_color(message, "d", prefix="[debug]")


def interactive_loop(debug: bool = True) -> None:
  """
  Run the interactive REPL loop that powers the workshop client.
  """
  load_dotenv()
  api_key = os.getenv("DEEPSEEK_KEY")
  router = DeepseekRouter(api_key=api_key, debug=debug)
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
          prompt_text = log_color("What is your query? → ", "w", emit=False)
          user_input = input(prompt_text).strip()
        except EOFError:
          log_color("\nGoodbye.", "w")
          break
        if debug:
          log_color(f"[Client] User input: {user_input}", "d", prefix="[debug]")

        if user_input.lower() in {"exit", "quit"}:
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
