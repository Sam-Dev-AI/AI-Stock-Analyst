import os
import sys
import warnings
import logging
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import google.generativeai as genai
import requests
import config
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS


# --- Suppress all warnings and logs ---
# This setup is important for clean logs in production.
os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GRPC_TRACE'] = ''
os.environ['GLOG_minloglevel'] = '3'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
logging.disable(logging.CRITICAL)
warnings.filterwarnings('ignore')

# --- Configure Gemini API at startup ---
# This will be checked when the server first loads.
try:
    genai.configure(api_key=config.GENIE_API_KEY)
except Exception as e:
    print(f"CRITICAL ERROR during Gemini configuration: {e}")
    # This will cause the server to fail at startup if the key is bad,
    # which is good for identifying configuration issues immediately.
    raise e

# --- Import Constants from Config ---
NEWSAPI_KEYS = config.NEWSAPI_KEYS
NIFTY_50_TICKERS = config.NIFTY_50_TICKERS
LARGE_CAP_MIN_MARKET_CAP = config.LARGE_CAP_MIN_MARKET_CAP
RSI_THRESHOLD = config.RSI_THRESHOLD
NEWS_API_MODE = config.NEWS_API_MODE
SYSTEM_INSTRUCTION = config.SYSTEM_INSTRUCTION

# --- Global variable for News API key rotation ---
current_api_index = 0

# --- Financial Tool Functions (No changes needed here) ---

def find_top_filtered_stocks(duration_days: int = 30, prefer_buy: bool = False):
    """Finds top NIFTY 50 stocks for a given holding duration."""
    ema_window = min(max(duration_days, 5), 200)
    filtered = []
    for ticker in NIFTY_50_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            if market_cap < LARGE_CAP_MIN_MARKET_CAP:
                continue
            history_period = max(ema_window * 2, 60)
            hist = stock.history(period=f"{history_period}d", interval="1d")
            if hist.empty or len(hist) < ema_window:
                continue
            rsi = RSIIndicator(hist['Close'], window=14).rsi().iloc[-1]
            ema = EMAIndicator(hist['Close'], window=ema_window).ema_indicator().iloc[-1]
            price = hist['Close'].iloc[-1]
            if prefer_buy:
                rsi_condition = 50 <= rsi <= 65
            else:
                rsi_condition = rsi > RSI_THRESHOLD
            if rsi_condition and price > ema:
                filtered.append({
                    'Ticker': ticker, 'Name': info.get('shortName', ticker), 'RSI': float(rsi),
                    'Price': float(price), 'EMA': float(ema)
                })
        except Exception:
            continue
    if not filtered:
        return f"No stocks found meeting the criteria for a {duration_days}-day hold."
    filtered.sort(key=lambda x: x['RSI'], reverse=True)
    return {"top_filtered_stocks": filtered[:3]}

def find_stocks_by_price_change(percentage: float = 0, timeframe: str = "1day"):
    """Finds stocks by price change over a relative timeframe."""
    timeframe_map = {
        "1day": {"period": "5d", "compare_days": 1},
        "1week": {"period": "1mo", "compare_days": 5},
        "1month": {"period": "3mo", "compare_days": 21}
    }
    config_data = timeframe_map.get(timeframe, timeframe_map["1day"])
    matching_stocks = []
    for ticker in NIFTY_50_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period=config_data["period"], interval="1d")
            if hist.empty or len(hist) < config_data["compare_days"] + 1:
                continue
            current_price = hist['Close'].iloc[-1]
            previous_price = hist['Close'].iloc[-(config_data["compare_days"] + 1)]
            price_change_pct = ((current_price - previous_price) / previous_price) * 100
            if percentage == 0 or abs(price_change_pct) >= percentage:
                matching_stocks.append({
                    'Ticker': ticker, 'Name': info.get('shortName', ticker),
                    'CurrentPrice': float(current_price), 'PreviousPrice': float(previous_price),
                    'PriceChange%': float(price_change_pct)
                })
        except Exception:
            continue
    if not matching_stocks:
        return f"No stocks found with a price movement of {percentage}% or more in {timeframe}."
    matching_stocks.sort(key=lambda x: abs(x['PriceChange%']), reverse=True)
    return {"stocks_by_price_change": matching_stocks[:10]}

def get_complete_stock_details(ticker: str):
    """Fetches comprehensive details for a single stock."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y", interval="1d")
        if hist.empty:
            return {"error": f"No data available for {ticker}"}
        return {
            "ticker": ticker,
            "company_name": info.get('shortName', ticker),
            "current_price": hist['Close'].iloc[-1],
            "52_week_high": info.get('fiftyTwoWeekHigh', 'N/A'),
            "market_cap": info.get('marketCap', 0),
            "pe_ratio": info.get('trailingPE', 'N/A'),
            "revenue_growth": f"{info.get('revenueGrowth', 0) * 100:.2f}%",
            "rsi_14": RSIIndicator(hist['Close'], window=14).rsi().iloc[-1],
            "business_summary": info.get('longBusinessSummary', 'N/A')
        }
    except Exception as e:
        return {"error": f"Failed to fetch details for {ticker}: {str(e)}"}

def get_recent_news(company_name):
    """Fetches recent news from NewsAPI.org."""
    global current_api_index
    api_key = NEWSAPI_KEYS[current_api_index]
    current_api_index = (current_api_index + 1) % len(NEWSAPI_KEYS)
    url = f"https://newsapi.org/v2/everything?q={company_name}&language=en&sortBy=publishedAt&apiKey={api_key}&pageSize=3"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get('status') == 'ok' and data.get('articles'):
            return {"news": [article['title'] for article in data['articles']]}
    except Exception:
        pass
    return {"news": [f"No recent news found for {company_name}."]}

def get_financial_highlights(ticker):
    """Fetches key financial highlights."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        pe = info.get('trailingPE', 'N/A')
        eps = info.get('trailingEps', 'N/A')
        revenue_growth = info.get('revenueGrowth', 'N/A')
        rev_growth_pct = f"{revenue_growth * 100:.2f}%" if isinstance(revenue_growth, float) else "N/A"
        return {"financials": f"P/E: {pe}, EPS: {eps}, Revenue Growth: {rev_growth_pct}"}
    except:
        return {"financials": "Financial data unavailable"}

def get_company_profile(ticker):
    """Fetches company business summary."""
    try:
        stock = yf.Ticker(ticker)
        return {"profile": stock.info.get('longBusinessSummary', "No profile available")}
    except:
        return {"profile": "Company profile unavailable"}

# --- Define the tools for the agent ---
agent_tools = [
    find_top_filtered_stocks,
    find_stocks_by_price_change,
    get_complete_stock_details,
    get_recent_news,
    get_financial_highlights,
    get_company_profile
]

# --- Create the Flask Web Server ---
app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- API endpoint for chat ---
@app.route('/api/chat', methods=['POST'])
def chat_handler():
    try:
        # ** LAZY INITIALIZATION **
        # Initialize the model inside the request to prevent startup crashes
        # if the API key is invalid or the model name is incorrect.
        model = genai.GenerativeModel(
            model_name='gemini-pro-latest',
            tools=agent_tools,
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Get the user's message from the request body
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"error": "Missing 'message' in request body"}), 400

        user_message = data['message']

        # Start a new chat session for each request for simplicity
        chat = model.start_chat(enable_automatic_function_calling=True)
        response = chat.send_message(user_message)

        # Return the agent's response
        return jsonify({"reply": response.text})

    except Exception as e:
        # This will catch errors during the request (e.g., Gemini API call failure)
        # and log them for debugging.
        print(f"An error occurred within the request handler: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

# This block is for local testing and is NOT run on Cloud Run.
# On Cloud Run, a production-grade server like Gunicorn is used.
if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
