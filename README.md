# MCP Workshop
This repository demonstrates a Deepseek-powered stock data assistant that follows a lightweight Model Context Protocol (MCP) workflow. A conversational client leverages Deepseek for natural-language routing, while a tool server resolves stock lookups with live Yahoo Finance data and a deterministic CSV fallback.

## Features

- 🤖 Deepseek-Assisted Query Understanding: Uses Deepseek to classify natural language into tool calls when connectivity allows, with keyword heuristics as a backup.
- 📊 Dual Data Sources: Prioritises Yahoo Finance through `yfinance`, with `stocks_data.csv` supplying reliable offline results.
- 🔄 MCP-Style Tool Routing: JSON-over-stdio contract between client and server keeps the workshop true to MCP concepts without extra infrastructure.
- 💬 Interactive CLI: `mcp_client.py` offers a conversational REPL that accepts everyday language.
- 🛡️ Graceful Degradation: Automatic fallbacks for both AI routing and market data avoid hard failures during workshops.

## Architecture

### MCP Client (`mcp_client.py`)

- Loads the Deepseek API key from `.env`.
- Sends the user query to Deepseek for routing (or a deterministic heuristic if the key/network is unavailable).
- Launches `mcp_server.py` as a subprocess and communicates via line-delimited JSON messages.
- Formats tool responses for display in the terminal.

### MCP Server (`mcp_server.py`)

- Loads fallback pricing data from `stocks_data.csv`.
- Exposes two tools: `get_stock_price` and `compare_stocks`.
- Attempts to fetch real-time prices with `yfinance`, then falls back to the CSV cache on error.
- Speaks the same JSON protocol as the client over stdio, making it easy to swap or extend tools.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- A Deepseek API key (set as `DEEPSEEK_KEY` in `.env`)
- Internet connectivity for real-time Yahoo Finance data (optional but recommended)

### Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Populate `.env`:
   ```dotenv
   DEEPSEEK_KEY=your_deepseek_key_here
   ```
4. Confirm that `stocks_data.csv` is present. It ships with representative tickers so no additional work is required.

### Running the Assistant

1. Start the conversational client:
   ```bash
   python mcp_client.py
   ```
2. Enter natural language queries:
   ```
   What is your query? → What's the current price of AAPL?
   What is your query? → Compare Apple and Microsoft stocks
   ```
3. Exit with `exit` or `quit`.

Enable verbose logging (including Deepseek payloads and tool responses) with the debug flag:

```bash
python mcp_client.py --debug
```

### Example Interactions

- **Single Stock**
  ```
  Input:  What's the price of AAPL?
  Output: The current price of AAPL is $188.12 (yfinance).
  ```
- **Comparison**
  ```
  Input:  Compare Apple and Microsoft stocks
  Output: AAPL is trading lower than MSFT (188.12 vs 405.15).
  ```
- **Offline Fallback**
  ```
  Input:  Get Tesla stock price
  Output: The current price of TSLA is $198.45 (fallback_csv).
  ```

## Repository Layout

```
├── mcp_client.py          # Deepseek-enabled conversational client
├── mcp_server.py          # MCP-style tool server for stock lookups
├── stocks_data.csv        # Offline stock price cache
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (ignored by git)
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

- `.env` must define `DEEPSEEK_KEY`. If absent, the client prints a warning and uses the heuristic router.
- `stocks_data.csv` follows the format `symbol,price,last_updated`. Extend it with additional rows to enrich offline coverage.

## Data Sources

- **Primary:** `yfinance` for real-time data (requires network access).
- **Fallback:** `stocks_data.csv` for deterministic responses during workshops or offline sessions.

## Troubleshooting

- **Deepseek routing errors:** Ensure `DEEPSEEK_KEY` is set and that outbound HTTPS is allowed. The CLI will continue with keyword routing if the API call fails.
- **Yahoo Finance connectivity issues:** Network/SSL problems automatically trigger the CSV fallback. Populate `stocks_data.csv` with the needed tickers if you expand beyond the defaults.
- **Unhandled prompts:** Use explicit tickers (e.g., `AAPL`, `MSFT`) to improve routing accuracy, especially when running without the Deepseek key.

## Dependencies

- `python-dotenv` — load `.env` files for configuration.
- `requests` — call the Deepseek REST API.
- `yfinance` — fetch live stock prices when available.

Run `python -m compileall` before committing changes that touch server tooling to catch syntax issues early.
