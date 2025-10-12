import os
import sys
import warnings

# Suppress all warnings and logs BEFORE any imports
os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GRPC_TRACE'] = ''
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '3'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# Redirect stderr temporarily
class SuppressOutput:
    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self._original_stderr

warnings.filterwarnings('ignore')

import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

# Import genai with suppressed output
with SuppressOutput():
    import google.generativeai as genai

import requests
import Backend.config as config
import random
from datetime import datetime, timedelta

# Import configuration
genai.configure(api_key=config.GENIE_API_KEY)
NEWSAPI_KEYS = config.NEWSAPI_KEYS
NIFTY_50_TICKERS = config.NIFTY_50_TICKERS
LARGE_CAP_MIN_MARKET_CAP = config.LARGE_CAP_MIN_MARKET_CAP
RSI_THRESHOLD = config.RSI_THRESHOLD
EMA_PERIOD = config.EMA_PERIOD
NEWS_API_MODE = config.NEWS_API_MODE
SYSTEM_INSTRUCTION = config.SYSTEM_INSTRUCTION

# Track current API key index for sequential rotation
current_api_index = 0


def find_top_filtered_stocks():
    """Filters NIFTY 50 stocks by market cap, RSI > 50, price above EMA20 and returns top 3."""
    filtered = []
    for ticker in NIFTY_50_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            if market_cap < LARGE_CAP_MIN_MARKET_CAP:
                continue
            hist = stock.history(period="30d", interval="1d")
            if hist.empty or len(hist) < EMA_PERIOD:
                continue
            rsi = RSIIndicator(hist['Close'], window=14).rsi().iloc[-1]
            ema20 = EMAIndicator(hist['Close'], window=EMA_PERIOD).ema_indicator().iloc[-1]
            price = hist['Close'].iloc[-1]
            if rsi > RSI_THRESHOLD and price > ema20:
                filtered.append({
                    'Ticker': ticker,
                    'MarketCap': market_cap,
                    'RSI': rsi,
                    'Price': price,
                    'EMA20': ema20,
                    'Name': info.get('shortName', ticker)
                })
        except Exception:
            continue
    if not filtered:
        return "No stocks currently meet the filtering criteria."
    filtered.sort(key=lambda x: x['RSI'], reverse=True)
    top3 = filtered[:3]
    return {"top_filtered_stocks": top3}


def find_stocks_by_price_change(percentage: float = 0, timeframe: str = "1day", target_date: str = ""):
    """
    Universal function to find stocks by price change - works for both recent periods and specific dates.
    
    Args:
        percentage: Minimum percentage change threshold (use 0 to get all movers)
        timeframe: "1day", "1week", "1month" for recent periods (ignored if target_date is provided)
        target_date: Specific date like "2025-10-10", "friday", "10 oct 2025", "yesterday"
                     If provided, this overrides timeframe and searches for that specific date
    
    Returns:
        Stocks matching criteria with time context
    """
    # Determine if this is a historical date query or recent period query
    is_historical = bool(target_date and target_date.strip())
    
    if is_historical:
        # Parse target date
        target = None
        today = datetime.now()
        target_lower = target_date.lower().strip()
        
        if "friday" in target_lower or "last friday" in target_lower:
            days_back = (today.weekday() - 4) % 7
            if days_back == 0:
                days_back = 7
            target = today - timedelta(days=days_back)
        elif "yesterday" in target_lower:
            target = today - timedelta(days=1)
        elif "ago" in target_lower:
            try:
                days = int(''.join(filter(str.isdigit, target_date)))
                target = today - timedelta(days=days)
            except:
                target = today - timedelta(days=1)
        else:
            # Try various date formats
            for fmt in ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"]:
                try:
                    clean_date = target_date.replace("oct", "Oct").replace("OCT", "Oct")
                    target = datetime.strptime(clean_date, fmt)
                    break
                except:
                    continue
            
            if target is None:
                try:
                    parts = target_date.lower().replace(",", "").split()
                    if len(parts) >= 3:
                        day = int(parts[0])
                        month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                   "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                        month = month_map.get(parts[1][:3], 10)
                        year = int(parts[2])
                        target = datetime(year, month, day)
                except:
                    target = today - timedelta(days=1)
        
        # Get historical data for specific date
        matching_stocks = []
        
        for ticker in NIFTY_50_TICKERS:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                start_date = target - timedelta(days=10)
                end_date = target + timedelta(days=3)
                hist = stock.history(start=start_date, end=end_date)
                
                if hist.empty or len(hist) < 2:
                    continue
                
                hist.index = pd.to_datetime(hist.index).tz_localize(None)
                target_no_tz = pd.Timestamp(target).tz_localize(None)
                closest_idx = (hist.index - target_no_tz).abs().argmin()
                
                if closest_idx == 0:
                    continue
                
                actual_date = hist.index[closest_idx]
                current_price = hist['Close'].iloc[closest_idx]
                previous_price = hist['Close'].iloc[closest_idx - 1]
                price_change_pct = ((current_price - previous_price) / previous_price) * 100
                
                if len(hist) >= 14:
                    hist_rsi = RSIIndicator(hist['Close'], window=14).rsi()
                    rsi = hist_rsi.iloc[closest_idx]
                else:
                    rsi = None
                
                if abs(price_change_pct) >= percentage:
                    matching_stocks.append({
                        'Ticker': ticker,
                        'Name': info.get('shortName', ticker),
                        'TradingDate': actual_date.strftime("%Y-%m-%d"),
                        'CurrentPrice': float(current_price),
                        'PreviousPrice': float(previous_price),
                        'PriceChange%': float(price_change_pct),
                        'Direction': 'up' if price_change_pct > 0 else 'down',
                        'MarketCap': info.get('marketCap', 0),
                        'RSI': float(rsi) if rsi is not None else None,
                        'Timeframe': f"on {actual_date.strftime('%Y-%m-%d')}"
                    })
            except Exception:
                continue
        
        if not matching_stocks:
            return {"error": f"No stocks found with significant movement on {target.strftime('%Y-%m-%d')}"}
        
        matching_stocks.sort(key=lambda x: abs(x['PriceChange%']), reverse=True)
        
        return {
            "stocks_by_price_change": matching_stocks[:10],
            "target_date": target.strftime("%Y-%m-%d"),
            "percentage_threshold": percentage,
            "query_type": "historical"
        }
    
    else:
        # Recent period query (1day, 1week, 1month)
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
                
                if len(hist) >= 14:
                    rsi = RSIIndicator(hist['Close'], window=14).rsi().iloc[-1]
                else:
                    rsi = None
                
                if abs(price_change_pct) >= percentage:
                    matching_stocks.append({
                        'Ticker': ticker,
                        'Name': info.get('shortName', ticker),
                        'CurrentPrice': current_price,
                        'PreviousPrice': previous_price,
                        'PriceChange%': price_change_pct,
                        'Direction': 'up' if price_change_pct > 0 else 'down',
                        'MarketCap': info.get('marketCap', 0),
                        'RSI': rsi,
                        'Timeframe': timeframe
                    })
            except Exception:
                continue
        
        if not matching_stocks:
            return f"No stocks found with price movement of {percentage}% or more in {timeframe}."
        
        matching_stocks.sort(key=lambda x: abs(x['PriceChange%']), reverse=True)
        
        return {
            "stocks_by_price_change": matching_stocks[:10], 
            "percentage_threshold": percentage,
            "timeframe": timeframe,
            "timeframe_description": f"Price change over {timeframe.replace('1', '1 ')}",
            "query_type": "recent"
        }


def get_recent_news(company_name):
    """Fetches recent news from NewsAPI.org using multiple API keys with rotation."""
    global current_api_index
    
    if NEWS_API_MODE == 'random':
        api_keys_order = random.sample(NEWSAPI_KEYS, len(NEWSAPI_KEYS))
    else:
        api_keys_order = NEWSAPI_KEYS[current_api_index:] + NEWSAPI_KEYS[:current_api_index]
        current_api_index = (current_api_index + 1) % len(NEWSAPI_KEYS)
    
    for api_key in api_keys_order:
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={company_name}&"
            f"language=en&"
            f"sortBy=publishedAt&"
            f"apiKey={api_key}&"
            f"pageSize=3"
        )
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if data.get('status') == 'ok' and data.get('totalResults', 0) > 0:
                headlines = [article['title'] for article in data['articles']]
                return {"news": headlines}
            elif data.get('status') == 'error':
                continue
        except Exception:
            continue
    
    return {"news": [f"No recent news found for {company_name}."]}


def get_financial_highlights(ticker):
    """Fetches key financial highlights: P/E, EPS, Revenue Growth."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        pe = info.get('trailingPE', 'N/A')
        eps = info.get('trailingEps', 'N/A')
        revenue_growth = info.get('revenueGrowth', 'N/A')
        rev_growth_pct = f"{revenue_growth * 100:.2f}%" if isinstance(revenue_growth, (float, int)) else "N/A"
        return {"financials": f"P/E: {pe}, EPS: {eps}, Revenue Growth: {rev_growth_pct}"}
    except:
        return {"financials": "Financial data unavailable"}


def get_company_profile(ticker):
    """Fetches company business summary."""
    try:
        stock = yf.Ticker(ticker)
        summary = stock.info.get('longBusinessSummary', "No profile available")
        return {"profile": summary}
    except:
        return {"profile": "Company profile unavailable"}


agent_tools = [
    find_top_filtered_stocks,
    find_stocks_by_price_change,
    get_recent_news,
    get_financial_highlights,
    get_company_profile
]

model = genai.GenerativeModel(
    model_name='models/gemini-pro-latest',
    tools=agent_tools,
    system_instruction=SYSTEM_INSTRUCTION
)

if __name__ == "__main__":
    with SuppressOutput():
        chat = model.start_chat(enable_automatic_function_calling=True)
    
    print("AI Stock Analyst ready. Ask about stocks, price movements, or specific dates. Type 'quit' to exit.\n")

    while True:
        user_input = input("> You: ").strip()
        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        try:
            response = chat.send_message(user_input)
            print(f"\n> Agent: {response.text}\n")
        except Exception as e:
            print(f"\n> Agent: Error occurred: {e}\n")
