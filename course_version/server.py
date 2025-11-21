"""
MCP Stock Server - Financial Data Provider with CSV Fallback

This module implements a Model Context Protocol (MCP) server that provides stock market
data functionality using the Yahoo Finance API with CSV fallback support. It offers tools 
for retrieving current stock prices and comparing multiple stock symbols.

The server exposes two main tools:
1. get_stock_price: Retrieves current price for a single stock symbol
2. compare_stocks: Compares prices between two stock symbols

Fallback Strategy:
- Primary: Yahoo Finance API (yfinance)
- Fallback: Local CSV file (stocks_data.csv)

Dependencies:
- mcp.server.fastmcp: FastMCP framework for creating MCP servers
- yfinance: Yahoo Finance API wrapper for stock data retrieval
- pandas: For CSV data handling
"""

from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas as pd
import os
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.utils import log_color

mcp = FastMCP("Stock Server")

# CSV file path - modify as needed
CSV_FILE_PATH = "stocks_data.csv"

def get_price_from_csv(symbol: str) -> Optional[float]:
    """
    Retrieve stock price from local CSV file.
    
    Expected CSV format:
    symbol,price,last_updated
    AAPL,150.25,2024-01-15
    MSFT,380.50,2024-01-15
    
    Parameters:
        symbol: Stock ticker symbol
        
    Returns:
        Stock price if found, None otherwise
    """
    log_color(f"CSV lookup requested for {symbol}", "d", prefix="[course-server]")
    try:
        if not os.path.exists(CSV_FILE_PATH):
            log_color(f"CSV file missing at {CSV_FILE_PATH}", "y", prefix="[course-server]")
            return None
            
        df = pd.read_csv(CSV_FILE_PATH)
        
        # Convert symbol column to uppercase for case-insensitive matching
        df['symbol'] = df['symbol'].str.upper()
        symbol = symbol.upper()
        
        # Find the stock in the CSV
        stock_row = df[df['symbol'] == symbol]
        
        if not stock_row.empty:
            log_color(f"Found {symbol} price in CSV", "g", prefix="[course-server]")
            return float(stock_row['price'].iloc[0])
        else:
            return None
            
    except Exception as e:
        log_color(f"Error reading CSV file: {e}", "r", prefix="[course-server]")
        return None

def get_stock_price_with_fallback(symbol: str) -> tuple[Optional[float], str]:
    """
    Get stock price with fallback mechanism.
    
    Parameters:
        symbol: Stock ticker symbol
        
    Returns:
        Tuple of (price, source) where source is 'yfinance' or 'csv'
    """
    log_color(f"Fetching price for {symbol} with yfinance fallback", "p", prefix="[course-server]")
    # Try yfinance first
    try:
        ticker = yf.Ticker(symbol)
        
        # Get today's data (may be empty if market is closed)
        data = ticker.history(period="1d")
        
        if not data.empty:
            price = data['Close'].iloc[-1]
            log_color(f"yfinance returned closing price for {symbol}", "g", prefix="[course-server]")
            return price, 'yfinance'
        else:
            # Try using regular market price from ticker info
            info = ticker.info
            price = info.get("regularMarketPrice")
            
            if price is not None:
                log_color(f"yfinance regularMarketPrice used for {symbol}", "g", prefix="[course-server]")
                return price, 'yfinance'
    
    except Exception as e:
        log_color(f"yfinance lookup failed for {symbol}: {e}", "y", prefix="[course-server]")
        pass
    
    # Fallback to CSV
    csv_price = get_price_from_csv(symbol)
    if csv_price is not None:
        log_color(f"Using CSV fallback for {symbol}", "b", prefix="[course-server]")
        return csv_price, 'csv'
    
    log_color(f"No data found for {symbol}", "r", prefix="[course-server]")
    return None, 'none'

@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """
    Retrieve the current stock price for the given ticker symbol.
    First tries Yahoo Finance API, then falls back to local CSV file.
    
    Parameters:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        
    Returns:
        Current stock price information
    """
    log_color(f"Tool invoked: get_stock_price({symbol})", "p", prefix="[course-server]")
    price, source = get_stock_price_with_fallback(symbol)
    
    if price is not None:
        source_text = " (from Yahoo Finance)" if source == 'yfinance' else " (from local data)"
        log_color(f"Responding with price {price:.2f} from {source}", "g", prefix="[course-server]")
        return f"The current price of {symbol} is ${price:.2f}{source_text}"
    else:
        log_color(f"Unable to resolve price for {symbol}", "r", prefix="[course-server]")
        return f"Could not retrieve price for {symbol} from either Yahoo Finance or local data. "\
               f"Please ensure the symbol is correct and that local data file '{CSV_FILE_PATH}' "\
               f"exists with the required format."

@mcp.tool()
def compare_stocks(symbol1: str, symbol2: str) -> str:
    """
    Compare the current stock prices of two ticker symbols.
    First tries Yahoo Finance API, then falls back to local CSV file for each symbol.
    
    Parameters:
        symbol1: First stock ticker symbol
        symbol2: Second stock ticker symbol
        
    Returns:
        Comparison of the two stock prices
    """
    log_color(f"Tool invoked: compare_stocks({symbol1}, {symbol2})", "p", prefix="[course-server]")
    # Get prices for both symbols
    price1, source1 = get_stock_price_with_fallback(symbol1)
    price2, source2 = get_stock_price_with_fallback(symbol2)
    
    if price1 is None:
        log_color(f"Missing data for {symbol1}", "r", prefix="[course-server]")
        return f"Could not retrieve price for {symbol1} from either Yahoo Finance or local data."
    
    if price2 is None:
        log_color(f"Missing data for {symbol2}", "r", prefix="[course-server]")
        return f"Could not retrieve price for {symbol2} from either Yahoo Finance or local data."
    
    # Create source information
    source1_text = " (YF)" if source1 == 'yfinance' else " (local)"
    source2_text = " (YF)" if source2 == 'yfinance' else " (local)"
    
    if price1 > price2:
        return f"{symbol1} (${price1:.2f}{source1_text}) is higher than {symbol2} (${price2:.2f}{source2_text})."
    elif price1 < price2:
        return f"{symbol1} (${price1:.2f}{source1_text}) is lower than {symbol2} (${price2:.2f}{source2_text})."
    else:
        return f"Both {symbol1} and {symbol2} have the same price (${price1:.2f})."

if __name__ == "__main__":
    """
    Entry point for the MCP Stock Server with CSV Fallback.
    
    When this script is run directly, it starts the FastMCP server which will:
    1. Register the available tools (get_stock_price, compare_stocks, check_data_sources)
    2. Listen for MCP client connections
    3. Handle tool execution requests from clients
    4. Provide stock data through Yahoo Finance with CSV fallback
    
    The server runs indefinitely until manually stopped (Ctrl+C) or terminated.
    
    CSV File Format:
        The CSV file should be named 'stocks_data.csv' and have the following format:
        symbol,price,last_updated
        AAPL,150.25,2024-01-15
        MSFT,380.50,2024-01-15
        GOOGL,140.75,2024-01-15
    
    Server Details:
        - Server Name: "Stock Server"
        - Available Tools: get_stock_price, compare_stocks, check_data_sources
        - Protocol: Model Context Protocol (MCP)
        - Primary Data Source: Yahoo Finance via yfinance library
        - Fallback Data Source: Local CSV file (stocks_data.csv)
    """
    log_color("Starting FastMCP Stock Server (course version)", "w", prefix="[course-server]")
    mcp.run()
