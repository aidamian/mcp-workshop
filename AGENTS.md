# Repository Guidelines

## Project Structure & Module Organization
The workshop centers on two entry points in the repo root: `mcp_client.py` (interactive CLI) and `mcp_server.py` (tool provider). Keep shared helpers alongside these modules or in a `utils/` package for clarity. Configuration lives in `.env`, dependency pins in `requirements.txt`, and fallback data in `stocks_data.csv`.

## Build, Test, and Development Commands
Use Python 3.10+. Create isolation with `uv venv` followed by `source .venv/bin/activate`. Install dependencies with `uv pip install -r requirements.txt`. Start the server via `uv run python mcp_server.py`; run the conversational client with `uv run python mcp_client.py` (verbose logging is on by default; pass `--no-debug` to quiet it). Once tests exist, execute them from the repo root with `uv run python -m pytest tests/` to keep discovery predictable. Populate `.env` with `DEEPSEEK_KEY` so the Deepseek router can classify user prompts; without it the client falls back to keyword heuristics.

## Coding Style & Naming Conventions
Follow PEP 8 with four-space indentation and descriptive snake_case names for functions, modules, and stock symbols (`fetch_stock_quote`, `compare_symbols`). Keep environment variables uppercase with underscores. Prefer single-responsibility functions, and split asynchronous routines into modules ending with `_async.py` if a file grows complex. Run `python -m compileall` before committing when you touch server tooling to catch syntax regressions early.

## Testing Guidelines
Aim to cover the client prompt parsing and server tool selection paths. Group tests by feature inside `tests/` (for example, `tests/test_price_lookup.py`). Use `stocks_data.csv` as deterministic fixtures for offline cases, and mock network calls to Yahoo Finance to keep runs fast. Track coverage informally until a threshold is defined, but flag gaps in pull requests.

## Commit & Pull Request Guidelines
History currently only contains the initial scaffolding, so adopt conventional commits going forward (`feat: add csv loader`, `fix: handle empty ticker`). Keep the subject line under 72 characters and include context in the body when behavior changes. Pull requests should link related issues, outline the testing performed, and include screenshots or terminal logs when modifying interactive flows. Surface configuration updates (`.env` changes, new data files) in the PR description so reviewers can validate local setup.

## Security & Configuration Tips
Never commit secrets; use `.env` and mention required variables in README updates. When adding new tools, validate user input before passing tickers to external APIs, and sanitize CSV additions to avoid malformed rows. Document any new permissions or environment requirements alongside the command examples above. Ensure Deepseek payloads request JSON output and gracefully degrade when API calls fail.
