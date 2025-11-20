# MCP Workshop
This repository demonstrates a Deepseek-powered stock data assistant with two interchangeable implementations:

- **Raw stdio variant (`raw_version/`)** — mirrors the original workshop with a lightweight JSON-over-stdio contract between the client and server.
- **MCP SDK variant (`mcp_version/`)** — reimplements the transport using the official `mcp` PyPI package so any MCP-capable tooling can connect.

The root entry points (`mcp_client.py`, `mcp_server.py`) now re-export the raw implementation for backwards compatibility, while the new MCP-aware modules live under `mcp_version/`.

## Features

- 🤖 Deepseek-Assisted Query Understanding: Natural-language prompts are routed to tools via Deepseek when an API key is present, with deterministic heuristics as a fallback.
- 📊 Dual Data Sources: Yahoo Finance via `yfinance` when online, and `stocks_data.csv` for deterministic offline coverage.
- 🔌 Two Transport Options: Choose between the original JSON-over-stdio flow or the MCP SDK-powered tooling, depending on your integration target.
- 💬 Interactive CLIs: Both variants ship conversational REPLs that mirror the same user experience.
- 🛡️ Graceful Degradation: Router and data providers fall back automatically so live workshops continue to run even without network access.

## Architecture

### Raw Variant (`raw_version/`)

- `raw_version/client.py` contains the original Deepseek router, stdio subprocess client, and REPL.
- `raw_version/server.py` exposes `get_stock_price` and `compare_stocks` tools over newline-delimited JSON.
- Root modules (`mcp_client.py`, `mcp_server.py`) wrap this package to keep legacy imports and scripts working.

### MCP Variant (`mcp_version/`)

- `mcp_version/server.py` reuses the `StockDataProvider` but registers tools on `fastmcp` from the official `mcp` package, serving over stdio.
- `mcp_version/client.py` launches the MCP server in-process, establishes an MCP session using `StdioServerParameters`/`stdio_client`, and keeps the same routing logic and terminal UX.
- Any external MCP-aware client (for example, IDE integrations or agent frameworks) can connect to `mcp_version/server.py` directly.

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

### Logging Flow (Raw Variant)

- `[agent]` (bright white): user-side events and prompts in the REPL.
- `[model]` (blue): Deepseek/heuristic analysis that selects a tool and arguments.
- `[mcp-client]` (purple): stdio dispatch/response lifecycle from the client transport.
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
├── tests/                 # Integration tests against the raw variant
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
