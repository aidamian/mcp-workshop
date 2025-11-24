# MCP Workshop
## Alglrithms & Flows
- **Use case:** A conversational stock assistant that turns natural-language prompts into tool calls (`get_stock_price`, `compare_stocks`), sourcing data from Yahoo Finance first and falling back to `stocks_data.csv` for deterministic replies.
- **Common flow:** User prompt → router picks tool/args (AI-assisted with heuristic fallback) → server executes against live/CSV data → client renders a concise, colour-coded response.
- **Raw stdio:** Minimal JSON-over-stdio between a subprocess client and server; fastest to run and the default for tests.
- **MCP SDK:** Uses the official `mcp` package with stdio or in-process memory transport; best when integrating external MCP-capable tools.
- **Course/Gemini:** Mirrors the MCP transport but asks Google Gemini to choose the tool/args; designed for tutorials showcasing alternate routing models.

This repository demonstrates a Deepseek-powered stock data assistant with three interchangeable implementations:

- **Raw stdio variant (`raw_version/`)** — mirrors the original workshop with a lightweight JSON-over-stdio contract between the client and server; the default for tests and quick demos.
- **MCP SDK variant (`mcp_version/`)** — reimplements the transport using the official `mcp` PyPI package so any MCP-capable tooling can connect over stdio.
- **Course/tutorial variant (`course_version/`)** — a teaching-focused MCP build that swaps Deepseek routing for Google Gemini to illustrate tool selection with a different model.

The root entry points (`mcp_client.py`, `mcp_server.py`) re-export the raw implementation for backwards compatibility. The MCP and course variants are self-contained under their folders and can be targeted explicitly by the test harness.

## Features

- 🤖 AI-Assisted Routing: Deepseek powers the raw and MCP builds (with deterministic heuristics as a fallback when no key is present); the course build swaps in Google Gemini for tool selection during the tutorial flow.
- 📊 Dual Data Sources: Yahoo Finance via `yfinance` when online, and `stocks_data.csv` for deterministic offline coverage.
- 🧰 Parallel Builds: Raw JSON stdio, MCP SDK stdio/memory, and a Gemini-powered course variant that share the same stock tools.
- 💬 Interactive CLIs: Every variant ships a conversational REPL that mirrors the same user experience.
- 🛡️ Graceful Degradation: Routers and data providers fall back automatically so live workshops continue to run even without network access.

## Architecture

### Raw Variant (`raw_version/`)

- `raw_version/client.py` contains the original Deepseek router, stdio subprocess client, and REPL.
- `raw_version/server.py` exposes `get_stock_price` and `compare_stocks` tools over newline-delimited JSON.
- Root modules (`mcp_client.py`, `mcp_server.py`) wrap this package to keep legacy imports and scripts working.

### MCP Variant (`mcp_version/`)

- `mcp_version/server.py` reuses the `StockDataProvider` but registers tools on `fastmcp` from the official `mcp` package, serving over stdio.
- `mcp_version/client.py` launches the MCP server in-process, establishes an MCP session using `StdioServerParameters`/`stdio_client`, and keeps the same routing logic and terminal UX.
- Any external MCP-aware client (for example, IDE integrations or agent frameworks) can connect to `mcp_version/server.py` directly.

### Course Variant (`course_version/`)

- `course_version/server.py` is another FastMCP server that uses the same CSV/yfinance data flow and colour-coded logging as the other builds.
- `course_version/client.py` demonstrates tool routing with Google Gemini (`gemini-2.0-flash-001`) instead of Deepseek. It fetches the tool list from the server, asks Gemini to pick a tool plus arguments, and then executes the call over MCP stdio.
- Run this variant from inside the `course_version/` directory (or adjust the `cwd` in the client) so the client can spawn `server.py` correctly. Set `GEMINI_API_KEY` in your `.env` before starting the REPL.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- A Deepseek API key (set `DEEPSEEK_KEY` in `.env`) for AI-assisted routing
- Optional internet connectivity for live Yahoo Finance data

### Common Setup

1. Create and activate a virtual environment with [uv](https://docs.astral.sh/uv/):
   ```bash
   uv venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```
3. Provide configuration:
   ```dotenv
   DEEPSEEK_KEY=your_deepseek_key_here
   ```
4. Ensure `stocks_data.csv` remains in the repository root. It supplies deterministic fixtures for offline testing.

### Running the Raw JSON Variant

1. Start the client (legacy behaviour retained). Verbose lifecycle logging is on by default:
   ```bash
   uv run python mcp_client.py
   ```
2. Example prompts:
   ```
   What's the current price of AAPL?
   Compare Apple and Microsoft stocks
   ```
3. To reduce output, disable debug logs explicitly:
   ```bash
   uv run python mcp_client.py --no-debug
   ```

### Logging Flow (Raw Variant and Shared Palette)

- `[agent]` (bright white): user-side events and prompts in the REPL.
- `[model]` (blue): Deepseek/heuristic analysis that selects a tool and arguments.
- `[mcp-client]` (purple): stdio dispatch/response lifecycle from the client transport (all variants reuse the same palette).
- `[mcp-server]` (purple): server execution logs for the invoked tool (stderr to avoid JSON noise).
- `[model]` (yellow): model drafting based on the tool payload.
- `[model]` (green): final model-facing reply shown to the user.
- `[warning]` (red): validation issues and execution errors; distinct from agent white logs.

### Running the MCP SDK Variant

1. Launch the MCP-aware client:
   ```bash
   uv run python -m mcp_version.client
   ```
2. The interactive loop mirrors the raw experience while using the MCP transport under the hood.
3. Alternatively, run only the server for external MCP clients:
   ```bash
   uv run python -m mcp_version.server
   ```
   Connect with your preferred MCP-enabled tooling by configuring it to spawn this module over stdio.

### Running the Course Tutorial Variant

1. Set `GEMINI_API_KEY` in `.env` so the client can route through Gemini.
2. From the repository root, change into the course folder to keep paths aligned:
   ```bash
   cd course_version
   ```
3. Start the Gemini-routed client (it spawns the FastMCP server automatically for each prompt):
   ```bash
   uv run python client.py
   ```
4. To host the course server for another MCP-aware client instead of the bundled REPL:
   ```bash
   uv run python server.py
   ```

## Testing

- Tests live in `tests/` and default to the raw variant so you can run them without API keys or optional packages.
- Target a specific build via the selector in `tests/run_tests.py`:
  ```bash
  uv run python tests/run_tests.py raw     # default
  uv run python tests/run_tests.py mcp     # requires `mcp` installed
  uv run python tests/run_tests.py course  # requires `google-genai` and `GEMINI_API_KEY` for Gemini routing
  ```
- You can also set `TEST_VARIANT` (for example, `TEST_VARIANT=mcp uv run python tests/run_tests.py`) to avoid passing CLI arguments.
- The course tutorial client is intentionally lightweight and may diverge from the shared pytest cases; focus on raw/mcp for automated runs, or align the tutorial helpers before running a full `uv run python -m pytest tests/` sweep.

## Repository Layout

```
├── mcp_client.py          # Wrapper around the raw client implementation
├── mcp_server.py          # Wrapper around the raw server implementation
├── raw_version/
│   ├── __init__.py
│   ├── client.py          # Original Deepseek router and stdio transport
│   └── server.py          # JSON-over-stdio tool server
├── mcp_version/
│   ├── __init__.py
│   ├── client.py          # Official MCP client using OpenAI SDK routing
│   └── server.py          # Official MCP server using fastmcp
├── course_version/        # Course-oriented MCP variant using google-genai routing
│   ├── client.py
│   └── server.py
├── stocks_data.csv        # Offline stock price cache
├── requirements.txt       # Python dependencies for both variants
├── tests/                 # Variant-aware integration tests and helpers
└── README.md              # Project overview
```

## Tools

`get_stock_price`

- **Purpose:** Retrieve the latest price for a single ticker.
- **Arguments:** `symbol` (string, uppercase stock ticker)
- **Typical prompts:** “Show me NVDA”, “What’s the price of AAPL?”

`compare_stocks`

- **Purpose:** Contrast prices for two symbols.
- **Arguments:** `symbol_one`, `symbol_two` (strings, uppercase tickers)
- **Typical prompts:** “Compare Apple and Microsoft”, “Is TSLA higher than AMZN?”

## Configuration Reference

- `.env` must define `DEEPSEEK_KEY`. Without it the router falls back to keyword heuristics.
- `.env` can include `DEEPSEEK_BASE_URL` to override the Deepseek endpoint used by the OpenAI client.
- `.env` may include `GEMINI_API_KEY` to enable Gemini routing in `course_version`.
- Set `MCP_FORCE_MEMORY=1` to force the MCP client to use the in-process memory transport instead of spawning a stdio subprocess (helpful for CI and offline runs).
- `stocks_data.csv` follows `symbol,price,last_updated`. Extend it with additional rows for more offline coverage.

## Data Sources

- **Primary:** `yfinance` for real-time data (requires outbound HTTPS).
- **Fallback:** `stocks_data.csv` for deterministic responses during workshops or offline sessions.

## Troubleshooting

- **Deepseek routing errors:** Confirm `DEEPSEEK_KEY` and network access. The client automatically falls back to heuristics when the API call fails.
- **Yahoo Finance connectivity issues:** Network/SSL problems trigger the CSV fallback. Populate `stocks_data.csv` with the tickers you need.
- **Integrating external MCP clients:** Run `python -m mcp_version.server` and point your MCP tooling at the spawned process. Ensure the tool accepts stdio transports.

## Dependencies

- `python-dotenv` — load environment variables from `.env`.
- `requests` — call the Deepseek REST API.
- `yfinance` — fetch live stock prices when available.
- `mcp` — official MCP client/server package powering the SDK variant.
- `openai` — official SDK used for Deepseek routing with the MCP client.
- `google-genai` — Google Gemini SDK used in the course variant routing.

Run `python -m compileall` before committing changes that touch server tooling to catch syntax issues early.
