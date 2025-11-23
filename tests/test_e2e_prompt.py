from __future__ import annotations

import asyncio
import os
from pathlib import Path
import unittest

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT = "What is the price of Tesla?"


class RawEndToEndTest(unittest.TestCase):
  def setUp(self) -> None:
    load_dotenv()
    os.environ["DEEPSEEK_KEY"] = ""

  def test_raw_version_prompt(self) -> None:
    from raw_version.client import DeepseekRouter, StockToolClient

    router = DeepseekRouter(api_key=None, debug=False)
    tool_call = router.route(PROMPT)
    server_path = REPO_ROOT / "raw_version" / "server.py"
    with StockToolClient(server_path=server_path, router=router, debug=False) as client:
      result = client.invoke(tool_call)

    data = result.get("data") or {}
    self.assertEqual(data.get("symbol"), "TSLA")
    self.assertIn("price", data)


class McpEndToEndTest(unittest.TestCase):
  def setUp(self) -> None:
    load_dotenv()
    os.environ["DEEPSEEK_KEY"] = ""
    os.environ["MCP_FORCE_MEMORY"] = "1"

  def _invoke(self) -> dict:
    from mcp_version.client import MCPStockClient, OpenAIBackedRouter

    router = OpenAIBackedRouter(api_key=None, debug=False)
    tool_call = router.route(PROMPT)
    server_path = REPO_ROOT / "mcp_version" / "server.py"

    async def _runner() -> dict:
      async with MCPStockClient(
        server_path=server_path,
        debug=False,
        force_memory=True,
      ) as client:
        return await client.invoke(tool_call)

    return asyncio.run(_runner())

  def test_mcp_version_prompt(self) -> None:
    result = self._invoke()
    data = result.get("data") or {}
    self.assertEqual(data.get("symbol"), "TSLA")
    self.assertIn("source", data)


class CourseEndToEndTest(unittest.TestCase):
  def setUp(self) -> None:
    load_dotenv()
    os.environ["GEMINI_API_KEY"] = ""
    os.environ["DEEPSEEK_KEY"] = ""
    os.environ["MCP_FORCE_MEMORY"] = "1"

  def _invoke(self) -> str:
    from course_version.client import CourseMCPClient, GeminiRouter

    router = GeminiRouter(api_key=None, debug=False)
    tool_call = router.route(PROMPT)
    server_path = REPO_ROOT / "course_version" / "server.py"

    async def _runner() -> str:
      async with CourseMCPClient(
        server_path=server_path,
        debug=False,
        force_memory=True,
      ) as client:
        return await client.invoke(tool_call)

    return asyncio.run(_runner())

  def test_course_version_prompt(self) -> None:
    response_text = self._invoke()
    self.assertTrue(response_text)
    self.assertIn("TSLA", response_text.upper())


if __name__ == "__main__":
  unittest.main()
