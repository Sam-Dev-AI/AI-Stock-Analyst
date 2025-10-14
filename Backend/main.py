import os
import config
import random
import requests
import pandas as pd
import time
from datetime import date, timedelta
from nsepy import get_history
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import google.generativeai as genai
import yfinance as yf
import warnings

# Suppress all warnings
warnings.filterwarnings('ignore')

# --- Configuration ---
genai.configure(api_key=config.GENIE_API_KEY)
NIFTY_50_TICKERS_NSEPY = [ticker.replace('.NS', '') for ticker in config.NIFTY_50_TICKERS]


# --- High-Performance Financial Tool Functions with Fallback Logic ---

def find_top_filtered_stocks(duration_days: int = 30, prefer_buy: bool = False):
    """
    Finds top stocks using yfinance as the primary source and nsepy as a fallback.
    """
    try:
        # --- PRIMARY METHOD: HIGH-PERFORMANCE YFINANCE BULK DOWNLOAD ---
        ema_window = min(max(duration_days, 5), 200)
        end_date = date.today()
        start_date = end_date - timedelta(days=max(ema_window * 2, 90))
        
        hist_data = yf.download(config.NIFTY_50_TICKERS, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if hist_data.empty:
            raise ValueError("yfinance returned no data")

        tickers_info = yf.Tickers(config.NIFTY_50_TICKERS)
        filtered = []
        for ticker in config.NIFTY_50_TICKERS:
            try:
                info = tickers_info.tickers[ticker].info
                market_cap = info.get('marketCap', 0)
                if market_cap < config.LARGE_CAP_MIN_MARKET_CAP: continue

                close_prices = hist_data['Close'][ticker].dropna()
                if close_prices.empty or len(close_prices) < ema_window: continue

                price = close_prices.iloc[-1]
                rsi = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                ema = EMAIndicator(close_prices, window=ema_window).ema_indicator().iloc[-1]

                rsi_condition = (50 <= rsi <= 65) if prefer_buy else (rsi > config.RSI_THRESHOLD)
                if rsi_condition and price > ema:
                    filtered.append({'Ticker': ticker, 'Name': info.get('shortName', ticker), 'Price': float(price), 'RSI': float(rsi)})
            except Exception:
                continue
        
        if not filtered: return f"No stocks meet criteria via yfinance."
        filtered.sort(key=lambda x: x['RSI'], reverse=True)
        return {"top_filtered_stocks": filtered[:3]}

    except Exception as e:
        # --- FALLBACK METHOD: NSEPY ONE-BY-ONE ---
        try:
            ema_window = min(max(duration_days, 5), 200)
            end_date = date.today()
            start_date = end_date - timedelta(days=max(ema_window * 2, 90))
            filtered = []
            tickers_info = yf.Tickers(config.NIFTY_50_TICKERS)
            for ticker in NIFTY_50_TICKERS_NSEPY:
                try:
                    info = tickers_info.tickers[f"{ticker}.NS"].info
                    market_cap = info.get('marketCap', 0)
                    if market_cap < config.LARGE_CAP_MIN_MARKET_CAP: continue

                    hist = get_history(symbol=ticker, start=start_date, end=end_date)
                    if hist.empty or len(hist) < ema_window: continue

                    close_prices = hist['Close']
                    price = close_prices.iloc[-1]
                    rsi = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                    ema = EMAIndicator(close_prices, window=ema_window).ema_indicator().iloc[-1]
                    rsi_condition = (50 <= rsi <= 65) if prefer_buy else (rsi > config.RSI_THRESHOLD)
                    if rsi_condition and price > ema:
                        filtered.append({'Ticker': f"{ticker}.NS", 'Name': info.get('shortName', ticker), 'Price': float(price), 'RSI': float(rsi)})
                except Exception:
                    continue
                time.sleep(0.1)
            
            if not filtered: return f"No stocks meet criteria via nsepy fallback."
            filtered.sort(key=lambda x: x['RSI'], reverse=True)
            return {"top_filtered_stocks": filtered[:3]}
        except Exception as e2:
            return "Both primary (yfinance) and secondary (nsepy) data sources failed."


def find_stocks_by_price_change(percentage: float = 0, timeframe: str = "1day"):
    """
    Finds market movers using yfinance as the primary source and nsepy as a fallback.
    """
    try:
        # --- PRIMARY METHOD: HIGH-PERFORMANCE YFINANCE BULK DOWNLOAD ---
        timeframe_map = {"1day": 1, "1week": 5, "1month": 21}
        compare_days = timeframe_map.get(timeframe, 1)
        end_date = date.today()
        start_date = end_date - timedelta(days=60)

        hist_data = yf.download(config.NIFTY_50_TICKERS, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if hist_data.empty: raise ValueError("yfinance returned no data")
        
        close_prices = hist_data['Close'].dropna(axis=1)
        if len(close_prices) < compare_days + 1: return "Not enough historical data from yfinance."
        
        current_prices = close_prices.iloc[-1]
        previous_prices = close_prices.iloc[-(compare_days + 1)]
        price_change_pct = ((current_prices - previous_prices) / previous_prices) * 100
        price_change_pct = price_change_pct[abs(price_change_pct) >= percentage]
        if price_change_pct.empty: return f"No stocks found with a price change of ≥ {percentage}% from yfinance."

        sorted_tickers = price_change_pct.sort_values(ascending=False)
        matching_stocks = []
        for ticker, change in sorted_tickers.items():
            matching_stocks.append({'Ticker': ticker, 'Name': yf.Ticker(ticker).info.get('shortName', ticker), 'CurrentPrice': float(current_prices[ticker]), 'PreviousPrice': float(previous_prices[ticker]), 'PriceChange%': float(change)})
        
        return {"stocks_by_price_change": matching_stocks}

    except Exception as e:
        # --- FALLBACK METHOD: NSEPY ONE-BY-ONE ---
        try:
            timeframe_map = {"1day": 1, "1week": 5, "1month": 21}
            compare_days = timeframe_map.get(timeframe, 1)
            end_date = date.today()
            start_date = end_date - timedelta(days=60)
            matching_stocks = []

            for ticker in NIFTY_50_TICKERS_NSEPY:
                try:
                    hist = get_history(symbol=ticker, start=start_date, end=end_date)
                    if hist.empty or len(hist) < compare_days + 1: continue

                    current_price = hist['Close'].iloc[-1]
                    previous_price = hist['Close'].iloc[-(compare_days + 1)]
                    if previous_price == 0: continue
                    price_change_pct = ((current_price - previous_price) / previous_price) * 100

                    if percentage == 0 or abs(price_change_pct) >= percentage:
                        info = yf.Ticker(f"{ticker}.NS").info
                        matching_stocks.append({'Ticker': f"{ticker}.NS", 'Name': info.get('shortName', ticker), 'CurrentPrice': float(current_price), 'PreviousPrice': float(previous_price), 'PriceChange%': float(price_change_pct)})
                except Exception:
                    continue
                time.sleep(0.1)
            
            if not matching_stocks: return f"No stocks found with a price change of ≥ {percentage}% from nsepy fallback."
            matching_stocks.sort(key=lambda x: x['PriceChange%'], reverse=True)
            return {"stocks_by_price_change": matching_stocks}
        except Exception as e2:
            return "Both primary (yfinance) and secondary (nsepy) data sources failed."


# Other functions remain the same as they are for single-stock lookups
def get_complete_stock_details(ticker: str):
    # This function already has a good internal fallback, so we'll keep it as is.
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y", interval="1d", progress=False)
        if hist.empty: raise ValueError("Historical data not available")
        return { "status": "success", "ticker": ticker, "basic_info": {"company_name": info.get('shortName', ticker)}, "price_data": {"current_price": float(hist['Close'].iloc[-1])}, "financials": f"P/E: {info.get('trailingPE', 'N/A')}", "profile": info.get('longBusinessSummary', "N/A")}
    except Exception:
        try:
            profile_info = get_company_profile(ticker)
            financial_info = get_financial_highlights(ticker)
            company_name = yf.Ticker(ticker).info.get('shortName', ticker.replace('.NS', ''))
            news_info = get_recent_news(company_name)
            return { "status": "partial_success", "ticker": ticker, "profile": profile_info.get("profile"), "financials": financial_info.get("financials"), "news": news_info.get("news")}
        except Exception as e:
            return {"status": "failure", "error": f"Unable to retrieve any data for {ticker}: {str(e)}"}

def get_recent_news(company_name):
    try:
        api_key = random.choice(config.NEWSAPI_KEYS)
        url = f"https://newsapi.org/v2/everything?q={company_name}&language=en&sortBy=publishedAt&apiKey={api_key}&pageSize=3"
        data = requests.get(url, timeout=5).json()
        if data.get('status') == 'ok' and data.get('articles'):
            return {"news": [a['title'] for a in data['articles']]}
    except Exception:
        pass
    return {"news": [f"No news found for {company_name}."]}

def get_financial_highlights(ticker):
    try:
        info = yf.Ticker(ticker).info
        return {"financials": f"P/E: {info.get('trailingPE', 'N/A')}, EPS: {info.get('trailingEps', 'N/A')}"}
    except:
        return {"financials": "Unavailable"}

def get_company_profile(ticker):
    try:
        return {"profile": yf.Ticker(ticker).info.get('longBusinessSummary', "N/A")}
    except:
        return {"profile": "Unavailable"}


# --- Main Application Logic for Local Testing ---
if __name__ == "__main__":
    agent_tools = [
        find_top_filtered_stocks,
        find_stocks_by_price_change,
        get_complete_stock_details,
        get_recent_news,
        get_financial_highlights,
        get_company_profile,
    ]

    full_system_instruction = config.SYSTEM_INSTRUCTION + "\n" + config.FORMATTING_INSTRUCTION

    model = genai.GenerativeModel(
        model_name='gemini-pro-latest',
        tools=agent_tools,
        system_instruction=full_system_instruction
    )

    chat = model.start_chat(enable_automatic_function_calling=True)
    print("Welcome to the Stock Analysis Agent! (Fallback Mode) Type 'quit' to exit.\n")

    while True:
        user_input = input("> You: ").strip()
        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        try:
            print("Fetching data, please wait...")
            response = chat.send_message(user_input)
            print(f"\n> Agent: {response.text}\n")
        except Exception as e:
            print(f"\n> Agent: An error occurred: {e}\n")

