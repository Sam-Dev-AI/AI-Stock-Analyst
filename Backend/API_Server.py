import os
import config
import time
from datetime import date, timedelta, datetime # Ensure timedelta and datetime are imported
import google.generativeai as genai
import yfinance as yf
import warnings
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import traceback
from typing import Optional, List
import requests # Still needed for NewsAPI fallback AND NSE API
import json
from urllib.parse import quote_plus # Used for NSE API URL encoding

from ddgs import DDGS # DuckDuckGo Search

# Import TA libraries
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

# --- Import the new indices file ---
import indices

# Suppress specific warnings if needed
warnings.filterwarnings('ignore')

# Configure Gemini API Key
genai.configure(api_key=config.GENIE_API_KEY)

# Initialize Firestore
db = None
try:
    if not firebase_admin._apps:
        cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if cred_path and os.path.exists(cred_path):
            print(f"Initializing Firestore with credentials from: {cred_path}")
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            print("GOOGLE_APPLICATION_CREDENTIALS not set or invalid. Trying Application Default Credentials.")
            firebase_admin.initialize_app()
            print("Initialized Firestore with Application Default Credentials.")

    db = firestore.client()
    db.collection('api-connection-test').document('heartbeat').get()
    print("✅ Firestore initialized and connection tested successfully")
except Exception as e:
    print(f"❌ FIREBASE ERROR: Failed to initialize Firestore or test connection.")
    print(f"    Error details: {e}")
    db = None

# Simple in-memory cache
_cache = {}
CACHE_TTL_SECONDS = config.CACHE_TTL_SECONDS

def set_cache(key, value, ttl_seconds=CACHE_TTL_SECONDS):
    """Sets a value in the cache with a specific TTL."""
    _cache[key] = (value, time.time() + ttl_seconds)
    pass

def get_cache(key):
    """Gets a value from the cache if it exists and hasn't expired."""
    if key in _cache:
        value, expiry_time = _cache[key]
        if time.time() < expiry_time:
            print(f"     CACHE HIT for {key}")
            return value
        else:
            del _cache[key]
    return None

def normalize_ticker(ticker_input: str) -> Optional[str]:
    """Normalizes a company name or partial ticker."""
    if not ticker_input or not isinstance(ticker_input, str): return None
    ticker_upper = ticker_input.strip().upper()
    if ticker_upper in config.NIFTY_50_TICKERS: return ticker_upper
    potential_ticker_ns = f"{ticker_upper}.NS"
    if potential_ticker_ns in config.NIFTY_50_TICKERS: return potential_ticker_ns
    if ticker_upper.endswith('.NS'): return ticker_upper
    for ticker, name in config.COMPANY_NAMES.items():
        if ticker_upper == name.upper(): return ticker
    possible_matches = [ticker for ticker, name in config.COMPANY_NAMES.items() if ticker_upper in name.upper()]
    if len(possible_matches) == 1: print(f"     Normalized '{ticker_input}' to '{possible_matches[0]}' via N50 name."); return possible_matches[0]
    elif len(possible_matches) > 1: print(f"     WARNING: Ambiguous N50 input '{ticker_input}'. Matches: {possible_matches}"); return None
    if ticker_upper in [t.replace('.NS', '') for t in config.NIFTY_50_TICKERS]: return f"{ticker_upper}.NS"
    if '.' in ticker_upper and len(ticker_upper) > 3:
         print(f"     Warning: Allowing potentially non-standard ticker '{ticker_upper}'")
         return ticker_upper
    print(f"     Could not normalize '{ticker_input}' confidently.")
    return None


def get_ticker_info(ticker_str: str):
    """Fetches stock info using yfinance, with caching."""
    if not isinstance(ticker_str, str): print(f"     Invalid ticker type: {ticker_str}"); return None
    cache_key = f"info_{ticker_str}"
    cached_info = get_cache(cache_key)
    if cached_info: return cached_info
    try:
        stock = yf.Ticker(ticker_str); info = stock.info
        if not info or not info.get('symbol'): print(f"     No valid info for {ticker_str}"); return None
        set_cache(cache_key, info, ttl_seconds=config.CACHE_PRICE_DATA_SECONDS); return info
    except Exception as e: print(f"     ❌ yfinance info exception for {ticker_str}: {e}"); return None

def get_current_price(ticker: str):
    """Gets a detailed price snapshot. Normalizes ticker automatically."""
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return {"error": f"Could not find a valid ticker for '{ticker}'. Please use a known name or full ticker (e.g., RELIANCE.NS)."}
    try:
        info = get_ticker_info(normalized_ticker)
        if not info: return {"error": f"Could not fetch basic info for {normalized_ticker}."}
        is_nse = normalized_ticker.endswith('.NS')
        currency_symbol = "₹" if is_nse else info.get('currency', '$')
        stock = yf.Ticker(normalized_ticker); hist = stock.history(period="5d", interval="1d")
        current_price = None
        if hist.empty or 'Close' not in hist.columns or hist['Close'].iloc[-1] is None or pd.isna(hist['Close'].iloc[-1]):
             current_price = info.get('currentPrice') or info.get('regularMarketPrice')
             if current_price is None: return {"error": f"Could not fetch price/history for {normalized_ticker}."}
             print(f"     ⚠️ History fetch failed/empty/NaN for {normalized_ticker}, using info price.")
        else: current_price = float(hist['Close'].iloc[-1])

        previous_close = info.get('previousClose')
        if previous_close is None and len(hist) > 1 and 'Close' in hist.columns:
             non_nan_closes = hist['Close'].dropna()
             if len(non_nan_closes) > 1:
                  previous_close = float(non_nan_closes.iloc[-2])

        if previous_close is None: previous_close = current_price # Ultimate fallback

        previous_close = float(previous_close); one_day_change_val = current_price - previous_close
        one_day_change_pct = (one_day_change_val / previous_close) * 100 if previous_close and previous_close != 0 else 0

        result = {
            "ticker": normalized_ticker, "company_name": info.get('shortName', info.get('longName', normalized_ticker)),
            "currency": currency_symbol, "current_price": round(current_price, config.PRICE_DECIMAL_PLACES),
            "change_value": round(one_day_change_val, config.PRICE_DECIMAL_PLACES), "change_percentage": round(one_day_change_pct, 2),
            "day_low": round(float(info.get('dayLow', current_price)), config.PRICE_DECIMAL_PLACES),
            "day_high": round(float(info.get('dayHigh', current_price)), config.PRICE_DECIMAL_PLACES),
            "previous_close": round(previous_close, config.PRICE_DECIMAL_PLACES), "is_nse": is_nse
        }
        return result
    except Exception as e: print(f"   ❌ Exception in get_current_price for {normalized_ticker}: {traceback.format_exc()}"); return {"error": f"Error fetching price details: {str(e)}"}


def screen_static_index(index_name: str = "NIFTY 50", num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False):
    """Finds top stocks from a PRE-DEFINED, STATIC index list."""
    print(f"   → screen_static_index (Index={index_name}, N={num_stocks}, Duration={duration_days}, Buy={prefer_buy})")
    ticker_list = None
    norm_name = index_name.strip().upper()
    if norm_name == "NIFTY 50": ticker_list = config.NIFTY_50_TICKERS
    else: ticker_list = indices.STATIC_INDICES.get(norm_name)
    if ticker_list is None:
        valid_indices = ["NIFTY 50"] + list(indices.STATIC_INDICES.keys())
        print(f"     ❌ Error: Index '{index_name}' not in static list.")
        return {"error": f"Index '{index_name}' not in pre-defined list. Try one of: {', '.join(valid_indices[:6])}..."}
    return screen_custom_stock_list(tickers=ticker_list, num_stocks=num_stocks, duration_days=duration_days, prefer_buy=prefer_buy, index_name_for_log=index_name)

def screen_custom_stock_list(tickers: List[str], num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False, index_name_for_log: str = "Custom List"):
    """Screens a CUSTOM list of tickers using technical indicators."""
    print(f"   → screen_custom_stock_list (Index={index_name_for_log}, N={num_stocks}, Tickers={len(tickers)}, Duration={duration_days}, Buy={prefer_buy})")
    if not tickers or not isinstance(tickers, list): return {"error": "No valid ticker list provided."}
    try:
        num_stocks = int(num_stocks)
        if num_stocks <= 0: num_stocks = 3
    except: num_stocks = 3
    cache_key = f"filtered_stocks_{index_name_for_log.replace(' ','_')}_{num_stocks}_{duration_days}_{prefer_buy}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        duration_days = max(10, min(duration_days, 365)); ema_window = min(max(duration_days, 10), 200)
        history_days_needed = max(ema_window + 15, 90); end_date = date.today(); start_date = end_date - timedelta(days=history_days_needed)
        valid_tickers = sorted(list(set([t for t in tickers if isinstance(t, str) and t.endswith('.NS')])))
        if not valid_tickers: return {"error": "The provided list contains no valid .NS tickers for screening."}

        print(f"     Downloading history for {len(valid_tickers)} tickers ({start_date} to {end_date})...")
        hist_data = yf.download(valid_tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if hist_data.empty or 'Close' not in hist_data.columns: raise ValueError("yfinance download empty.")

        filtered = []
        is_multi_ticker = len(valid_tickers) > 1
        for ticker in valid_tickers:
            try:
                if is_multi_ticker:
                    if ticker not in hist_data['Close'].columns or hist_data['Close'][ticker].isnull().all(): continue
                    close_prices = hist_data['Close'][ticker].dropna()
                else:
                    if 'Close' not in hist_data.columns or hist_data['Close'].isnull().all(): continue
                    close_prices = hist_data['Close'].dropna()
                if len(close_prices) < max(ema_window, 14): continue
                info = get_ticker_info(ticker)
                if not info or info.get('marketCap', 0) < config.LARGE_CAP_MIN_MARKET_CAP or info.get('exchange') != 'NSI': continue
                cp = close_prices.iloc[-1]; rsi_val = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                ema_val = EMAIndicator(close_prices, window=ema_window).ema_indicator().iloc[-1]
                if pd.isna(rsi_val) or pd.isna(ema_val): continue
                rsi_ok = (config.RSI_BUY_MIN <= rsi_val <= config.RSI_BUY_MAX) if prefer_buy else (rsi_val > config.RSI_THRESHOLD)
                if rsi_ok and cp > ema_val:
                    filtered.append({'Ticker': ticker, 'Name': info.get('shortName', ticker), 'Price': float(round(cp, config.PRICE_DECIMAL_PLACES)),
                                     'RSI': float(round(rsi_val, 2)), 'EMA': float(round(ema_val, config.PRICE_DECIMAL_PLACES))})
            except Exception as e: continue
        if not filtered: result = {"message": f"No stocks from the '{index_name_for_log}' list meet criteria (RSI & Price > EMA)."}
        else:
            filtered.sort(key=lambda x: x['RSI'], reverse=True);
            print(f"     ✅ Found {len(filtered)} stocks meeting criteria. Returning top {num_stocks}.")
            result = {"top_filtered_stocks": filtered[:num_stocks]}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS);
        return result
    except Exception as e:
        print(f"     ❌ Exception in screen_custom_stock_list: {traceback.format_exc()}");
        return {"message": f"Screening error: {str(e)}"}


def get_live_price(ticker: str) -> float:
    """Gets the most recent price. Normalizes ticker."""
    norm_t = normalize_ticker(ticker);
    if not norm_t: raise ValueError(f"Invalid ticker: '{ticker}'.")
    try:
        hist = yf.Ticker(norm_t).history(period='2d', interval='1d', auto_adjust=True)
        if hist.empty or 'Close' not in hist.columns or hist['Close'].isnull().all():
            info = get_ticker_info(norm_t); price = info.get('currentPrice') or info.get('regularMarketPrice')
            if price is not None: print(f"     ⚠️ Live price hist fail {norm_t}, using info."); return float(price)
            else: raise ValueError(f"No price data for {norm_t}.")
        lp = float(hist['Close'].dropna().iloc[-1]); return lp
    except Exception as e: print(f"     ❌ Live price fetch fail {norm_t}: {e}"); raise ValueError(f"Could not get live price for {norm_t}") from e

def get_fundamental_data(ticker: str) -> dict:
    """Retrieves key fundamental data points."""
    norm_t = normalize_ticker(ticker);
    if not norm_t: return {"error": f"Invalid ticker: '{ticker}'."}
    try:
        info = get_ticker_info(norm_t);
        if not info: return {"error": f"Could not retrieve data for {norm_t}."}
        is_nse = norm_t.endswith('.NS')
        currency_symbol = "₹" if is_nse else info.get('currency', '$')
        mc = info.get('marketCap'); div_y = info.get('dividendYield')
        funda = {
            "ticker": norm_t, "companyName": info.get('shortName', info.get('longName', norm_t)),
            "sector": info.get('sector', 'N/A'), "industry": info.get('industry', 'N/A'),
            "marketCap": f"{currency_symbol}{mc:,.0f}" if mc else "N/A",
            "peRatio": round(info['trailingPE'], 2) if info.get('trailingPE') else "N/A",
            "pbRatio": round(info['priceToBook'], 2) if info.get('priceToBook') else "N/A",
            "eps": f"{currency_symbol}{round(info['trailingEps'], 2)}" if info.get('trailingEps') else "N/A",
            "dividendYield": f"{div_y * 100:.2f}%" if div_y else "N/A",
            "52WeekHigh": f"{currency_symbol}{round(info['fiftyTwoWeekHigh'], config.PRICE_DECIMAL_PLACES)}" if info.get('fiftyTwoWeekHigh') else "N/A",
            "52WeekLow": f"{currency_symbol}{round(info['fiftyTwoWeekLow'], config.PRICE_DECIMAL_PLACES)}" if info.get('fiftyTwoWeekLow') else "N/A",
            "beta": round(info['beta'], 2) if info.get('beta') else "N/A", "is_nse": is_nse
        }
        return funda
    except Exception as e: print(f"     ❌ Exception in get_fundamental_data {norm_t}: {e}"); return {"error": f"Error retrieving fundamentals: {str(e)}"}

# --- News Tools ---
def get_stock_news(query: str, company_name: Optional[str] = None) -> dict:
    """(FALLBACK TOOL) Fetches recent news articles from NewsAPI."""
    print(f"   → get_stock_news (NewsAPI Fallback) for: '{query}' (Company: {company_name})")
    search_term = company_name if company_name else query
    if not search_term: return {"error": "No query/company name."}
    cache_key = f"newsapi_{search_term.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    encoded_search_term = quote_plus(search_term)
    params = {'language': 'en', 'country': 'in', 'category': 'business', 'sortBy': 'relevancy', 'pageSize': 5, 'q': encoded_search_term}
    base_url = "https://newsapi.org/v2/everything"
    for api_key in config.NEWSAPI_KEYS:
        params['apiKey'] = api_key
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'error':
                if data.get('code') == 'rateLimited': print(f"     ⚠️ NewsAPI Key {api_key[:8]}... rate limited."); continue
                else: print(f"     ❌ NewsAPI Error ({data.get('code')}): {data.get('message')}"); return {"error": f"NewsAPI Error: {data.get('message')}"}
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                if not articles: result = {"message": f"No NewsAPI news for '{search_term}'."}
                else:
                    fmt_news = [{"title": a.get('title'), "source": a.get('source', {}).get('name'), "description": a.get('description'), "url": a.get('url'), "publishedAt": a.get('publishedAt')} for a in articles]
                    print(f"     ✅ Found {len(fmt_news)} NewsAPI articles for '{search_term}'.")
                    result = {"articles": fmt_news}
                set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
        except requests.exceptions.HTTPError as http_err:
            response_obj = getattr(http_err, 'response', None)
            if response_obj is not None:
                 if response_obj.status_code == 400: print(f"     ❌ NewsAPI Bad Request (400) key {api_key[:8]}... URL: {response_obj.url}\nBody: {response_obj.text}"); return {"error": "NewsAPI Bad Request (400). Details logged."}
                 elif response_obj.status_code == 429: print(f"     ⚠️ NewsAPI Key {api_key[:8]} rate limited (429)."); continue
            print(f"     ❌ HTTP Error NewsAPI: {http_err}"); return {"error": f"NewsAPI HTTP Error: {http_err}"}
        except requests.exceptions.RequestException as req_err: print(f"     ❌ Request Ex NewsAPI: {req_err}"); return {"error": f"NewsAPI Connection Error: {req_err}"}
    result = {"error": "NewsAPI keys rate-limited or invalid."}; set_cache(cache_key, result, ttl_seconds=60); return result

def internet_search_news(query: str) -> dict:
    """(PREFERRED TOOL) Performs a news search using DuckDuckGo."""
    print(f"   → internet_search_news (DDGS) for: '{query}'")
    cache_key = f"ddgs_news_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.news(query, region='in-en', safesearch='off', max_results=5)
        if not results: result = {"message": f"No DDGS news found for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "source": i.get('source'), "description": i.get('body'), "url": i.get('url'), "publishedAt": i.get('date')} for i in results]
            print(f"     ✅ Found {len(fmt_res)} DDGS news results.")
            result = {"articles": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e: print(f"     ❌ DDGS News Search Error: {traceback.format_exc()}"); return {"error": f"DDGS news search error: {str(e)}"}

def internet_search(query: str) -> dict:
    """Performs a general web search using DuckDuckGo."""
    print(f"   → internet_search (DDGS) for: '{query}'")
    cache_key = f"ddgs_search_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.text(query, region='in-en', max_results=3)
        if not results: result = {"message": f"No DDGS search results for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "snippet": i.get('body'), "url": i.get('href')} for i in results]
            print(f"     ✅ Found {len(fmt_res)} DDGS search results.")
            result = {"results": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e: print(f"     ❌ DDGS Search Error: {traceback.format_exc()}"); return {"error": f"DDGS search error: {str(e)}"}

# ============================================
# [UPDATED TOOL w/ FALLBACK] Get Index Constituents
# ============================================
def get_index_constituents(index_name: str) -> dict:
    """
    Finds index constituents. Tries NSE API (with common symbol variations) first,
    falls back to DDGS search + AI extraction.
    """
    print(f"   → get_index_constituents for: '{index_name}'")
    cache_key = f"constituents_{index_name.replace(' ', '_').lower()}" # Combined cache key
    cached_result = get_cache(cache_key)
    if cached_result:
        return cached_result

    nse_error = None # Initialize nse_error

    # --- Known variations/official symbols for tricky indices ---
    index_symbol_map = {
        "NIFTY 200 MOMENTUM 30": "NIFTY200 MOMENTUM 30",
    }

    names_to_try = []
    normalized_input = index_name.strip().upper()
    if normalized_input in index_symbol_map:
        names_to_try.append(index_symbol_map[normalized_input])
    names_to_try.append(index_name) # Try original input
    if index_name != normalized_input and normalized_input not in names_to_try:
         names_to_try.append(normalized_input) # Try uppercase input

    # --- Stage 1: Try NSE API with variations ---
    print(f"     Attempting NSE API with potential names: {names_to_try}")
    base_url = "https://www.nseindia.com/api/equity-stockIndices"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/market-data/live-equity-market', 'X-Requested-With': 'XMLHttpRequest'
    }

    for name_attempt in names_to_try:
        try:
            encoded_index_name = quote_plus(name_attempt)
            url = f"{base_url}?index={encoded_index_name}"
            print(f"     Querying NSE API with name: '{name_attempt}' ({url})")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            constituents = data.get("data", [])

            if constituents:
                ticker_list = [item.get("symbol") + ".NS" for item in constituents if item.get("symbol")]
                valid_tickers = [ticker for ticker in ticker_list if ticker is not None]
                if valid_tickers:
                    print(f"     ✅ Successfully fetched {len(valid_tickers)} tickers from NSE API using name '{name_attempt}'.")
                    result = {"index_name": index_name, "tickers": valid_tickers, "source": f"NSE API ('{name_attempt}')"}
                    set_cache(cache_key, result, ttl_seconds=3600)
                    return result

            print(f"     ⚠️ NSE API returned no data for name '{name_attempt}'.")
            if nse_error is None: nse_error = f"NSE API returned empty data for '{name_attempt}'."

        except requests.exceptions.HTTPError as http_err:
            nse_error = f"NSE API HTTP Error for '{name_attempt}': {http_err}"
            print(f"     ❌ {nse_error}")
            if http_err.response.status_code == 404: continue
            else: break
        except requests.exceptions.RequestException as req_err:
            nse_error = f"NSE API Network Error for '{name_attempt}': {req_err}"
            print(f"     ❌ {nse_error}"); break
        except json.JSONDecodeError as json_err:
            nse_error = f"NSE API JSON Parse Error for '{name_attempt}': {json_err}"
            print(f"     ❌ {nse_error}"); break
        except Exception as e:
            nse_error = f"Unexpected NSE API Error for '{name_attempt}': {e}"
            print(f"     ❌ {nse_error}"); break

    # --- Stage 2: Fallback to DDGS + AI Extraction ---
    print(f"     ⚠️ NSE API failed for all attempts ({nse_error or 'Unknown reason'}). Falling back to DDGS + AI extraction...")
    try:
        query = f"{index_name} constituents tickers list NSE"
        print(f"     Searching DDGS for: '{query}'")
        search_snippets = []
        with DDGS() as ddgs:
            results = ddgs.text(query, region='in-en', max_results=5)
            if results: search_snippets = [r.get('body', '') for r in results]

        if not search_snippets:
            print("     ❌ DDGS fallback found no results.")
            final_error = f"NSE API failed and DDGS search found no results for '{index_name}'."
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
            return {"error": final_error}

        print(f"     Found {len(search_snippets)} snippets via DDGS. Asking AI to extract tickers...")
        extraction_prompt = f"""
        Extract all NSE stock tickers (ending in .NS) from the provided text snippets.
        Output ONLY a Python list of strings. Example: ['TICKER1.NS', 'TICKER2.NS']
        If none found, output: [].
        DO NOT include any explanation, code, or formatting other than the list itself.

        Snippets:
        ---
        {json.dumps(search_snippets)}
        ---

        Output:
        """
        extraction_model = genai.GenerativeModel(model_name=config.GEMINI_MODEL_NAME)
        safety_settings=[{"category": c, "threshold": "BLOCK_ONLY_HIGH"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        response = extraction_model.generate_content(extraction_prompt, safety_settings=safety_settings)
        extracted_text = response.text.strip()
        print(f"     AI extraction response: {extracted_text}")

        if extracted_text.startswith("```python"): extracted_text = extracted_text[len("```python"):].strip()
        if extracted_text.startswith("```"): extracted_text = extracted_text[len("```"):].strip()
        if extracted_text.endswith("```"): extracted_text = extracted_text[:-len("```")].strip()

        if not extracted_text.startswith('[') or not extracted_text.endswith(']'):
            final_error = "AI failed to extract tickers in list format from DDGS results."
            print(f"     ❌ {final_error}")
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
            return {"error": final_error}

        try:
            cleaned_text = extracted_text.replace("'", '"')
            ticker_list = json.loads(cleaned_text)
            if not isinstance(ticker_list, list): raise ValueError("AI did not return a list.")
            valid_tickers = [t for t in ticker_list if isinstance(t, str) and t.endswith('.NS')]

            if not valid_tickers:
                final_error = f"Could not extract valid .NS tickers for '{index_name}' from DDGS search results."
                print(f"     ❌ {final_error}")
                set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
                return {"error": final_error}

            print(f"     ✅ Successfully extracted {len(valid_tickers)} tickers via DDGS + AI.")
            result = {"index_name": index_name, "tickers": valid_tickers, "source": "DDGS+AI"}
            set_cache(cache_key, result, ttl_seconds=1800) # Cache fallback result (30 mins)
            return result

        except Exception as e:
            final_error = f"Error parsing AI response from DDGS fallback: {e}"
            print(f"     ❌ {final_error}")
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
            return {"error": final_error}

    except Exception as e:
        final_error = f"Unexpected Error during DDGS fallback: {e}"
        print(f"     ❌ Unexpected Error in DDGS fallback: {traceback.format_exc()}")
        set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
        return {"error": final_error}

# --- Bulk Price Fetch & Firestore Functions ---
def get_bulk_live_prices(tickers: list) -> dict:
    """Efficiently gets prices for multiple stocks."""
    if not tickers: return {}
    valid_tickers = [t for t in tickers if isinstance(t, str) and t.endswith('.NS')]
    if not valid_tickers: print("     No valid tickers for bulk fetch."); return {}
    try:
        data = yf.download(valid_tickers, period='2d', progress=False, auto_adjust=True, ignore_tz=True)
        if data.empty or 'Close' not in data.columns: print("     ⚠️ Bulk download empty/invalid."); raise ValueError("Empty bulk download")
        prices = {}
        close_data = data['Close'] if len(valid_tickers) > 1 else data[['Close']]
        last_valid_index = close_data.last_valid_index()
        if last_valid_index is None: raise ValueError("No valid close prices in bulk download.")
        last_prices = close_data.loc[last_valid_index]
        for ticker in valid_tickers:
            if ticker in last_prices.index and pd.notna(last_prices[ticker]): prices[ticker] = float(round(last_prices[ticker], config.PRICE_DECIMAL_PLACES))
            elif ticker in close_data.columns and pd.notna(close_data[ticker].loc[last_valid_index]): prices[ticker] = float(round(close_data[ticker].loc[last_valid_index], config.PRICE_DECIMAL_PLACES))
            else:
                print(f"     ⚠️ Price not in bulk for {ticker}. Falling back.")
                try: prices[ticker] = float(round(get_live_price(ticker), config.PRICE_DECIMAL_PLACES))
                except ValueError: print(f"     ❌ Fallback failed for {ticker}")
        return prices
    except Exception as e:
        print(f"     ❌ Bulk fetch failed: {e}. Falling back individually...")
        prices = {}
        for t in valid_tickers:
            try: price = get_live_price(t); prices[t] = float(round(price, config.PRICE_DECIMAL_PLACES))
            except ValueError: print(f"     ❌ Fallback failed for {t}")
        print(f"     ✅ Fallback fetch completed for {len(prices)} tickers.")
        return prices

def initialize_user_account(user_id: str) -> dict:
    # (Existing code...)
    if not db: raise Exception("Firestore database is not available.")
    try:
        account_ref = db.collection('users').document(user_id)
        account_doc = account_ref.get()
        today_str = datetime.now().strftime('%Y-%m-%d')
        if not account_doc.exists:
            print(f"🆕 NEW USER: Initializing account for {user_id}")
            initial_data = {'cash': config.DEFAULT_STARTING_CASH, 'initial_cash': config.DEFAULT_STARTING_CASH, 'account_initialized': True,
                            'created_at': firestore.SERVER_TIMESTAMP, 'day_start_portfolio_value': config.DEFAULT_STARTING_CASH,
                            'last_day_pnl_reset': today_str, 'net_cash_flow_today': 0.0 }
            account_ref.set(initial_data); print(f"     Account created for {user_id} with ₹{config.DEFAULT_STARTING_CASH:,.2f}"); return initial_data
        else:
            account_data = account_doc.to_dict(); update_fields = {}
            if not account_data.get('account_initialized'): update_fields['account_initialized'] = True; update_fields['initial_cash'] = account_data.get('cash', config.DEFAULT_STARTING_CASH)
            if 'day_start_portfolio_value' not in account_data: update_fields['day_start_portfolio_value'] = account_data.get('cash', config.DEFAULT_STARTING_CASH)
            if 'last_day_pnl_reset' not in account_data: update_fields['last_day_pnl_reset'] = today_str
            if 'net_cash_flow_today' not in account_data: update_fields['net_cash_flow_today'] = 0.0
            if update_fields: print(f"     Patching fields for {user_id}: {list(update_fields.keys())}"); account_ref.update(update_fields); account_data.update(update_fields)
            last_reset = account_data.get('last_day_pnl_reset', '')
            if last_reset != today_str:
                current_val = calculate_current_portfolio_value(user_id, account_data.get('cash', 0))
                print(f"📅 New day for {user_id}! Resetting P&L tracker.")
                reset_data = {'day_start_portfolio_value': current_val, 'last_day_pnl_reset': today_str, 'net_cash_flow_today': 0.0 }
                account_ref.update(reset_data); account_data.update(reset_data)
            return account_data
    except Exception as e: print(f"❌ Error initializing account {user_id}: {e}"); raise

def calculate_current_portfolio_value(user_id: str, current_cash: float) -> float:
    # (Existing code...)
    if not db: return current_cash
    try:
        holdings_docs = db.collection(f'users/{user_id}/portfolio').stream()
        holdings_data = {doc.id: doc.to_dict() for doc in holdings_docs}
        tickers = list(holdings_data.keys()); total_val = 0
        if tickers:
            prices = get_bulk_live_prices(tickers)
            for t, h in holdings_data.items(): total_val += h.get('quantity', 0) * prices.get(t, h.get('avg_price', 0))
        return current_cash + total_val
    except Exception as e: print(f"     ⚠️ Error calculating portfolio value {user_id}: {e}. Returning cash."); return current_cash

def get_portfolio(user_id: str) -> dict:
    # (Existing code...)
    if not db: raise Exception("Firestore unavailable.")
    try:
        acc_data = initialize_user_account(user_id)
        cash, day_start, net_flow = acc_data.get('cash', 0), acc_data.get('day_start_portfolio_value', 0), acc_data.get('net_cash_flow_today', 0)
        holdings_docs = db.collection(f'users/{user_id}/portfolio').stream()
        holdings_data = {doc.id: doc.to_dict() for doc in holdings_docs}
        tickers = list(holdings_data.keys()); holdings = []; total_inv = 0; total_curr_h_val = 0; total_pnl = 0
        if tickers:
            prices = get_bulk_live_prices(tickers)
            for t, h in holdings_data.items():
                q, avg_p = h.get('quantity', 0), h.get('avg_price', 0); cp = prices.get(t, avg_p)
                inv_v, curr_v = q * avg_p, q * cp; pnl = curr_v - inv_v; pnl_pct = (pnl / inv_v * 100) if inv_v else 0
                total_inv += inv_v; total_curr_h_val += curr_v; total_pnl += pnl
                price_info = get_ticker_info(t)
                prev_close = price_info.get('previousClose', cp) if price_info else cp
                approx_day_pnl = (cp - prev_close) * q
                holdings.append({"ticker": t, "quantity": q, "avg_price": round(avg_p, config.PRICE_DECIMAL_PLACES),
                                 "current_price": round(cp, config.PRICE_DECIMAL_PLACES), "invested_value": round(inv_v, config.PNL_DECIMAL_PLACES),
                                 "current_value": round(curr_v, config.PNL_DECIMAL_PLACES), "pnl": round(pnl, config.PNL_DECIMAL_PLACES),
                                 "pnl_percent": round(pnl_pct, 2), "approx_day_pnl": round(approx_day_pnl, config.PNL_DECIMAL_PLACES)})
        curr_port_val = cash + total_curr_h_val
        day_base = day_start + net_flow; day_pnl = curr_port_val - day_base; day_pnl_pct = (day_pnl / day_base * 100) if day_base else 0
        summary = {"portfolio_value": round(curr_port_val, config.PNL_DECIMAL_PLACES), "total_invested": round(total_inv, config.PNL_DECIMAL_PLACES),
                   "total_holdings_value": round(total_curr_h_val, config.PNL_DECIMAL_PLACES), "total_pnl": round(total_pnl, config.PNL_DECIMAL_PLACES),
                   "total_pnl_percent": round((total_pnl / total_inv * 100) if total_inv else 0, 2),
                   "day_pnl": round(day_pnl, config.PNL_DECIMAL_PLACES), "day_pnl_percent": round(day_pnl_pct, 2)}
        return {"cash": round(cash, config.PRICE_DECIMAL_PLACES), "holdings": holdings, "summary": summary}
    except Exception as e: print(f"❌ Error getting portfolio {user_id}: {e}"); raise

def execute_trade(user_id: str, ticker: str, quantity: int, action: str):
    """Executes buy/sell, logs, cleans history."""
    if not db: raise Exception("Firestore unavailable.")
    if not isinstance(quantity, int) or quantity <= 0: raise ValueError(f"Quantity must be a positive integer, got {quantity}.")
    norm_ticker = normalize_ticker(ticker);
    if not norm_ticker: raise ValueError(f"Invalid ticker: '{ticker}'.")
    print(f"💼 TRADE: User={user_id}, Action={action.upper()}, Qty={quantity}, Ticker={norm_ticker}")
    try: cp = get_live_price(norm_ticker)
    except ValueError as e: raise ValueError(f"Could not get price for {norm_ticker}. Error: {e}")
    trade_val = cp * quantity; user_ref = db.collection('users').document(user_id)
    hold_ref = user_ref.collection('portfolio').document(norm_ticker); hist_coll = user_ref.collection('history')
    @firestore.transactional
    def trade_trans(trans):
        user_snap = user_ref.get(transaction=trans);
        if not user_snap.exists: raise ValueError(f"User {user_id} not found.")
        acc_data = user_snap.to_dict(); cash = acc_data.get('cash', 0)
        hold_snap = hold_ref.get(transaction=trans); hist_ref = hist_coll.document()
        act = action.upper()
        if act == 'BUY':
            if cash < trade_val: raise ValueError(f"Insufficient funds. Need ₹{trade_val:,.2f}, have ₹{cash:,.2f}")
            new_cash = cash - trade_val; trans.update(user_ref, {'cash': new_cash})
            if hold_snap.exists:
                ch = hold_snap.to_dict(); cq, ca = ch.get('quantity', 0), ch.get('avg_price', 0)
                tq = cq + quantity; n_avg = ((cq * ca) + trade_val) / tq; trans.update(hold_ref, {'quantity': tq, 'avg_price': n_avg})
            else: trans.set(hold_ref, {'quantity': quantity, 'avg_price': cp})
            trans.set(hist_ref, {'action': 'BUY', 'ticker': norm_ticker, 'quantity': quantity, 'price': cp, 'total_value': trade_val, 'timestamp': firestore.SERVER_TIMESTAMP})
            print(f"     ✅ BUY success {user_id}"); return {"success": True, "action": "BUY", "ticker": norm_ticker, "quantity": quantity, "price": cp, "total_value": trade_val, "new_cash": new_cash}
        elif act == 'SELL':
            if not hold_snap.exists: raise ValueError(f"No shares of {norm_ticker} to sell.")
            ch = hold_snap.to_dict(); aq, avg_p = ch.get('quantity', 0), ch.get('avg_price', 0)
            if aq < quantity: raise ValueError(f"Insufficient shares. Have {aq}, selling {quantity} of {norm_ticker}.")
            new_cash = cash + trade_val; trans.update(user_ref, {'cash': new_cash})
            nq = aq - quantity
            if nq > 0: trans.update(hold_ref, {'quantity': nq})
            else: trans.delete(hold_ref)
            trans.set(hist_ref, {'action': 'SELL', 'ticker': norm_ticker, 'quantity': quantity, 'price': cp, 'total_value': trade_val, 'timestamp': firestore.SERVER_TIMESTAMP})
            profit = (cp - avg_p) * quantity; print(f"     ✅ SELL success {user_id}"); return {"success": True, "action": "SELL", "ticker": norm_ticker, "quantity": quantity, "price": cp, "total_value": trade_val, "profit": profit, "new_cash": new_cash}
        else: raise ValueError(f"Invalid action: '{action}'.")
    try:
        trans_inst = db.transaction(); result = trade_trans(trans_inst)
        if result.get("success"):
            try: # History cleanup
                hist_q = hist_coll.order_by('timestamp', direction=firestore.Query.ASCENDING).select([]).stream()
                hist_refs = [doc.reference for doc in hist_q]
                if len(hist_refs) > config.TRADE_HISTORY_LIMIT:
                    num_del = len(hist_refs) - config.TRADE_HISTORY_LIMIT; print(f"     🧹 History limit ({config.TRADE_HISTORY_LIMIT}) exceeded. Deleting {num_del}...")
                    batch = db.batch(); [batch.delete(hist_refs[i]) for i in range(num_del)]; batch.commit(); print(f"     ✅ History cleanup complete.")
            except Exception as clean_err: print(f"     ⚠️ History cleanup error {user_id}: {clean_err}")
        return result
    except ValueError as ve:
        print(f"     ❌ Trade failed {user_id}: {ve}")
        error_payload = {"error": True, "message": str(ve), "action": action.upper(), "ticker": norm_ticker, "quantity": quantity}
        if "Insufficient funds" in str(ve):
            try:
                user_doc = user_ref.get()
                if user_doc.exists: error_payload["available_cash"] = user_doc.to_dict().get('cash', 0)
                error_payload["current_price"] = cp
            except Exception as cash_err: print(f"     ⚠️ Could not fetch cash info for error message: {cash_err}")
        return error_payload
    except Exception as e: print(f"     ❌ Unexpected trade error {user_id}: {e}"); return {"error": True, "message": f"Unexpected error: {str(e)}", "action": action.upper(), "ticker": norm_ticker, "quantity": quantity }

# --- Flask App Setup & API Endpoints ---
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route('/')
def index(): return render_template('index.html')

# --- API Endpoints ---
@app.route('/api/portfolio/<user_id>', methods=['GET'])
def get_portfolio_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try: return jsonify(get_portfolio(user_id))
    except Exception as e: print(f"❌ API Error /portfolio/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/history/<user_id>', methods=['GET'])
def get_trade_history_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        hist_ref = db.collection(f'users/{user_id}/history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(config.TRADE_HISTORY_LIMIT).stream()
        history = []
        for doc in hist_ref: data = doc.to_dict(); data['timestamp'] = data['timestamp'].isoformat() if 'timestamp' in data and hasattr(data['timestamp'], 'isoformat') else None; history.append(data)
        return jsonify(history)
    except Exception as e: print(f"❌ API Error /history/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/adjust-cash/<user_id>', methods=['POST'])
def adjust_cash_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if data is None: return jsonify({"error": "Invalid JSON body."}), 400
        new_cash = data.get('cash')
        if not isinstance(new_cash, (int, float)) or not (0 <= new_cash <= config.MAX_ADJUST_CASH): return jsonify({"error": f"Invalid cash (0-{config.MAX_ADJUST_CASH:,.0f})."}), 400
        user_ref = db.collection('users').document(user_id)
        @firestore.transactional
        def update_cash_trans(trans):
            snap = user_ref.get(transaction=trans);
            if not snap.exists: raise ValueError(f"User {user_id} not found.")
            curr_cash = snap.to_dict().get('cash', 0); change = float(new_cash) - curr_cash
            trans.update(user_ref, {'cash': float(new_cash), 'net_cash_flow_today': firestore.Increment(change)})
            print(f"     💰 Cash adjusted {user_id} to ₹{float(new_cash):,.2f}. Change: ₹{change:,.2f}")
        trans = db.transaction(); update_cash_trans(trans)
        return jsonify({"success": True, "new_cash": round(float(new_cash), config.PRICE_DECIMAL_PLACES)})
    except ValueError as ve: print(f"❌ Adjust Cash Error {user_id}: {ve}"); return jsonify({"error": str(ve)}), 404
    except Exception as e: print(f"❌ Adjust Cash Error {user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/trade/<user_id>', methods=['POST'])
def trade_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if not data: return jsonify({"error": "Invalid JSON body."}), 400
        ticker, action = data.get('ticker'), data.get('action'); qty_in = data.get('quantity')
        if not all([ticker, qty_in, action]): return jsonify({"error": "Missing fields."}), 400
        try: qty = int(qty_in)
        except (ValueError, TypeError): return jsonify({"error": "Quantity not whole number."}), 400
        if not isinstance(action, str) or action.upper() not in ['BUY', 'SELL']: return jsonify({"error": "Action must be 'BUY' or 'SELL'."}), 400
        if not isinstance(ticker, str): return jsonify({"error": "Ticker must be string."}), 400
        result = execute_trade(user_id, ticker, qty, action)
        status = 500
        if result.get("error"):
            msg = result.get("message", "")
            if "Insufficient funds" in msg or "not found" in msg or "Invalid" in msg or "shares" in msg: status = 400
            else: status = 500
            return jsonify(result), status
        else:
             status = 200
             return jsonify(result), status
    except Exception as e:
        print(f"❌ API Error /trade/{user_id} PRE-EXECUTION: {traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/stock/price/<ticker>')
def get_stock_price_endpoint(ticker):
    try: price_data = get_current_price(ticker); return jsonify(price_data) # Return full data
    except ValueError as ve: return jsonify({"error": str(ve)}), 404
    except Exception as e: print(f"❌ API Error /stock/price/{ticker}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/watchlist/<user_id>', methods=['GET'])
def get_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        wl_ref = db.collection(f'users/{user_id}/watchlist').stream(); tickers = [doc.id for doc in wl_ref]
        if not tickers: return jsonify([])
        details = []; prices = get_bulk_live_prices(tickers); infos = {t: get_ticker_info(t) for t in tickers}
        for t in tickers:
            cp, info = prices.get(t), infos.get(t)
            if cp is None or info is None: print(f"     ⚠️ Missing watchlist data {t}."); details.append({"ticker": t, "price": "N/A", "change": "N/A", "dayRange": "N/A"}); continue
            try:
                pc = info.get('previousClose', cp); change = ((cp - pc) / pc) * 100 if pc else 0; dl, dh = info.get('dayLow', cp), info.get('dayHigh', cp)
                item = {"ticker": t, "price": round(cp, config.PRICE_DECIMAL_PLACES), "change": round(change, 2),
                        "dayRange": f"₹{dl:.{config.PRICE_DECIMAL_PLACES}f} - ₹{dh:.{config.PRICE_DECIMAL_PLACES}f}" if dl and dh else "N/A"}
                details.append(item)
            except Exception as e: print(f"     ❌ Error processing watchlist {t}: {e}"); details.append({"ticker": t, "price": "Error", "change": "Error", "dayRange": "Error"})
        return jsonify(details)
    except Exception as e: print(f"\n❌ CRITICAL WATCHLIST GET ERROR {user_id}: {traceback.format_exc()}\n"); return jsonify({"error": str(e)}), 500

@app.route('/api/watchlist/<user_id>', methods=['POST'])
def add_to_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if not data or 'tickers' not in data or not isinstance(data['tickers'], list): return jsonify({"error": "Invalid request: JSON with 'tickers' list needed."}), 400
        result = add_to_watchlist(user_id, data['tickers'])
        return jsonify(result), 400 if "error" in result else 200
    except Exception as e: print(f"❌ API Error POST /watchlist/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

def add_to_watchlist(user_id: str, tickers: List[str]) -> dict:
    """Adds one or more valid tickers to a user's Firestore watchlist."""
    if not db: return {"error": "DB unavailable"}
    if not isinstance(tickers, list): return {"error": "Input must be a list of tickers."}

    batch = db.batch()
    added_count = 0
    invalid_tickers = []
    added_tickers = []

    # Limit the number of tickers to add in one batch to avoid large writes
    MAX_WATCHLIST_ADD = 20
    tickers_to_process = tickers[:MAX_WATCHLIST_ADD]

    for ticker_input in tickers_to_process:
        if not isinstance(ticker_input, str):
            invalid_tickers.append(str(ticker_input))
            continue
        norm_ticker = normalize_ticker(ticker_input)
        if norm_ticker:
            doc_ref = db.collection(f'users/{user_id}/watchlist').document(norm_ticker)
            batch.set(doc_ref, {'added_at': firestore.SERVER_TIMESTAMP})
            added_tickers.append(norm_ticker)
            added_count += 1
        else:
            invalid_tickers.append(ticker_input)

    if added_count == 0 and not invalid_tickers:
         return {"error": "No tickers provided or all were empty strings."}
    elif added_count == 0 and invalid_tickers:
         return {"error": f"No valid tickers provided. Invalid inputs: {', '.join(invalid_tickers)}"}

    try:
        batch.commit()
        msg = f"Added {added_count} ticker(s): {', '.join(added_tickers)}."
        if invalid_tickers:
            msg += f" Invalid/skipped: {', '.join(invalid_tickers)}."
        if len(tickers) > MAX_WATCHLIST_ADD:
             msg += f" Processed first {MAX_WATCHLIST_ADD} tickers."
        print(f"     ✅ Watchlist add result for {user_id}: {msg}")
        return {"status": "success", "message": msg, "added": added_tickers, "invalid": invalid_tickers}
    except Exception as e:
        print(f"     ❌ Error committing watchlist add for {user_id}: {e}")
        return {"error": f"Database error while adding to watchlist: {str(e)}"}

def remove_from_watchlist(user_id: str, ticker: str) -> dict:
    """Removes a single ticker from a user's Firestore watchlist."""
    if not db: return {"error": "DB unavailable"}
    if not isinstance(ticker, str) or not ticker.strip():
        return {"error": "Invalid ticker provided. Must be a non-empty string."}
    try:
        norm_ticker = normalize_ticker(ticker)
        if not norm_ticker: return {"error": f"Could not normalize ticker: '{ticker}'."}

        ref = db.collection(f'users/{user_id}/watchlist').document(norm_ticker)
        doc_snapshot = ref.get()

        if not doc_snapshot.exists:
             print(f"     ⚠️ Ticker {norm_ticker} not found in watchlist {user_id}")
             return {"error": f"Ticker '{norm_ticker}' not found in watchlist."}

        ref.delete()
        print(f"     ✅ Removed {norm_ticker} from watchlist {user_id}")
        return {"status": "success", "message": f"Removed {norm_ticker}.", "removed_ticker": norm_ticker}

    except Exception as e:
        print(f"     ❌ Error removing {ticker} from watchlist {user_id}: {e}")
        return {"error": f"Database error while removing from watchlist: {str(e)}"}

@app.route('/api/watchlist/<user_id>/<ticker>', methods=['DELETE'])
def remove_from_watchlist_endpoint(user_id, ticker):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        if not ticker or not isinstance(ticker, str):
            return jsonify({"error": "Invalid ticker in URL."}), 400

        result = remove_from_watchlist(user_id, ticker)
        status_code = 404 if result.get("error") and "not found" in result["error"] else \
                      400 if result.get("error") else \
                      200
        return jsonify(result), status_code
    except Exception as e:
        print(f"❌ API Error DELETE /watchlist/{user_id}/{ticker}: {traceback.format_exc()}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/chats/<user_id>')
def get_chat_list_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        chats_ref = db.collection(f'users/{user_id}/chats')
        q = chats_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50).stream()
        cl = [{"chatId": d.id, "title": d.to_dict().get("title", f"Chat {d.id[:6]}...")} for d in q]
        return jsonify(cl)
    except Exception as e: print(f"❌ API Error /chats/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/chat/<user_id>/<chat_id>')
def get_chat_messages_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        msgs_ref = db.collection(f'users/{user_id}/chats/{chat_id}/messages')
        q = msgs_ref.order_by('timestamp', direction=firestore.Query.ASCENDING).limit(100).stream()
        msgs = [{"role": m.to_dict().get('role', 'model'), "text": m.to_dict().get('text', '')} for m in q]
        return jsonify(msgs)
    except Exception as e: print(f"❌ API Error /chat/{user_id}/{chat_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/chat/<user_id>/<chat_id>', methods=['DELETE'])
def delete_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        ref = db.collection(f'users/{user_id}/chats').document(chat_id)
        # TODO: Implement recursive delete
        ref.delete(); print(f"🗑️ Deleted chat {chat_id} for {user_id}")
        return jsonify({"success": True, "message": f"Chat {chat_id} deleted."})
    except Exception as e: print(f"❌ API Error DELETE /chat/{user_id}/{chat_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

@app.route('/api/chat/<user_id>/<chat_id>', methods=['PUT'])
def rename_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if not data or 'title' not in data: return jsonify({"error": "Missing 'title'."}), 400
        nt = data['title'].strip()
        if not nt: return jsonify({"error": "Title empty."}), 400
        if len(nt) > config.CHAT_TITLE_MAX_LENGTH: return jsonify({"error": f"Title > {config.CHAT_TITLE_MAX_LENGTH} chars."}), 400
        ref = db.collection(f'users/{user_id}/chats').document(chat_id)
        ref.update({'title': nt, 'timestamp': firestore.SERVER_TIMESTAMP})
        print(f"✏️ Renamed chat {chat_id} for {user_id} to '{nt}'")
        return jsonify({"success": True, "message": "Chat renamed."})
    except Exception as e: print(f"❌ API Error PUT /chat/{user_id}/{chat_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

# --- Main Chat Handler (using Gemini) ---
@app.route('/api/chat', methods=['POST'])
def chat_handler():
    if not db: return jsonify({"error": "Database not configured"}), 503
    try:
        data = request.get_json();
        if not data: return jsonify({"error": "Invalid JSON body"}), 400
        user_id, user_message, chat_id = data.get('userId'), data.get('message'), data.get('chatId')
        if not user_id or not user_message: return jsonify({"error": "Missing 'userId' or 'message'."}), 400
        if not isinstance(user_message, str) or not user_message.strip(): return jsonify({"error": "'message' empty."}), 400
        print(f"\n📩 Chat request: User={user_id}, ChatID={chat_id or 'New'}, Msg='{user_message[:50]}...'")

        # --- Agent-facing tool function definitions ---
        def execute_trade_for_agent(ticker: str, quantity: int, action: str) -> dict:
            print(f"     🤖 Agent calls execute_trade: {action} {quantity} x {ticker}")
            available_cash = None; current_price = None
            try:
                qty = int(quantity)
                if qty <= 0: return {"error": True, "message": "Quantity must be positive."}
                user_doc = db.collection('users').document(user_id).get()
                available_cash = user_doc.to_dict().get('cash', 0) if user_doc.exists else 0
                norm_ticker = normalize_ticker(ticker)
                if not norm_ticker: return {"error": True, "message": f"Invalid ticker: '{ticker}'."}
                current_price = get_live_price(norm_ticker)
                return execute_trade(user_id, norm_ticker, qty, action)
            except (ValueError, TypeError) as val_err:
                 is_insufficient = "Insufficient funds" in str(val_err)
                 error_payload = {"error": True, "message": str(val_err)}
                 if is_insufficient and current_price is not None and available_cash is not None:
                      error_payload["current_price"] = current_price
                      error_payload["available_cash"] = available_cash
                      error_payload["requested_quantity"] = quantity
                      error_payload["ticker"] = norm_ticker
                 return error_payload
            except Exception as e: print(f"     ❌ Error in execute_trade_for_agent: {traceback.format_exc()}"); return {"error": True, "message": f"Unexpected error: {str(e)}"}

        def get_portfolio_for_agent() -> dict:
            print("     🤖 Agent calls get_portfolio");
            try: return get_portfolio(user_id)
            except Exception as e: print(f"     ❌ Error in get_portfolio_for_agent: {traceback.format_exc()}"); return {"error": str(e)}

        def add_to_watchlist_for_agent(tickers: List[str]) -> dict:
            print(f"     🤖 Agent calls add_to_watchlist: {tickers}");
            if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers): return {"error": "Invalid input: Requires a list of ticker strings."}
            try: return add_to_watchlist(user_id, tickers)
            except Exception as e: print(f"     ❌ Error in add_to_watchlist_for_agent: {traceback.format_exc()}"); return {"error": str(e)}

        def remove_from_watchlist_for_agent(ticker: str) -> dict:
            """Removes a SINGLE stock ticker from the user's watchlist."""
            print(f"     🤖 Agent calls remove_from_watchlist: {ticker}");
            if not isinstance(ticker, str) or not ticker.strip():
                return {"error": "Invalid input: Requires a single non-empty ticker string."}
            try:
                return remove_from_watchlist(user_id, ticker)
            except Exception as e:
                print(f"     ❌ Error in remove_from_watchlist_for_agent: {traceback.format_exc()}");
                return {"error": str(e)}

        def get_index_constituents_for_agent(index_name: str) -> dict:
            print(f"     🤖 Agent calls get_index_constituents: '{index_name}'");
            try: return get_index_constituents(index_name)
            except Exception as e: print(f"     ❌ Error in get_index_constituents_for_agent: {traceback.format_exc()}"); return {"error": str(e)}

        def internet_search_news_for_agent(query: str, company_name: Optional[str] = None) -> dict:
             print(f"     🤖 Agent calls internet_search_news: '{query}' (Company: {company_name})");
             search_query = company_name if company_name else query
             try: return internet_search_news(search_query)
             except Exception as e: print(f"     ❌ Error in internet_search_news_for_agent: {traceback.format_exc()}"); return {"error": str(e)}
        def get_stock_news_for_agent(query: str, company_name: Optional[str] = None) -> dict:
             print(f"     🤖 Agent calls get_stock_news (Fallback): '{query}' (Company: {company_name})");
             search_query = company_name if company_name else query
             try: return get_stock_news(search_query, company_name)
             except Exception as e: print(f"     ❌ Error in get_stock_news_for_agent: {traceback.format_exc()}"); return {"error": str(e)}
        def internet_search_for_agent(query: str) -> dict:
             print(f"     🤖 Agent calls internet_search: '{query}'");
             try: return internet_search(query)
             except Exception as e: print(f"     ❌ Error in internet_search_for_agent: {traceback.format_exc()}"); return {"error": str(e)}
        # --- End tool definitions ---

        chat_history = []
        if chat_id:
            try:
                msgs_ref = db.collection(f'users/{user_id}/chats/{chat_id}/messages')
                msgs_query = msgs_ref.order_by('timestamp', direction=firestore.Query.ASCENDING).limit(config.MAX_CHAT_HISTORY).stream()
                for msg in msgs_query: msg_data = msg.to_dict(); chat_history.append({'role': 'user' if msg_data.get('role') == 'user' else 'model', 'parts': [{'text': msg_data.get('text', '')}]})
            except Exception as hist_err: print(f"     ⚠️ Failed history load {chat_id}: {hist_err}."); chat_history = []

        try:
            model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL_NAME,
                tools=[ screen_static_index, screen_custom_stock_list, get_index_constituents_for_agent, get_current_price, execute_trade_for_agent, get_portfolio_for_agent, get_fundamental_data, add_to_watchlist_for_agent, remove_from_watchlist_for_agent, internet_search_news_for_agent, get_stock_news_for_agent, internet_search_for_agent ],
                system_instruction=config.SYSTEM_INSTRUCTION + "\n\n" + config.FORMATTING_INSTRUCTION)
            chat_session = model.start_chat(history=chat_history, enable_automatic_function_calling=True)

            print(f"     Sending message to {config.GEMINI_MODEL_NAME}...")
            response = chat_session.send_message(user_message)
            print(f"     Received response from Gemini.")

            agent_reply = ""
            finish_details = "UNKNOWN"; finish_reason_raw = None
            finish_reason_map = {0: "UNKNOWN", 1: "STOP", 2: "MAX_TOKENS", 3: "SAFETY", 4: "RECITATION", 5: "OTHER"}
            try:
                candidate = response.candidates[0] if response.candidates else None
                if candidate:
                    finish_reason_raw = candidate.finish_reason
                    finish_details = finish_reason_map.get(finish_reason_raw, f"UNKNOWN ({finish_reason_raw})")
                    if candidate.content and candidate.content.parts:
                        agent_reply = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text') and part.text)
                if not agent_reply:
                    if finish_reason_raw == 1: agent_reply = "OK. Action completed."
                    elif finish_reason_raw == 3: agent_reply = f"Blocked: safety ({finish_details})."
                    elif finish_reason_raw == 4: agent_reply = f"Blocked: recitation ({finish_details})."
                    elif finish_reason_raw == 2: agent_reply = "Response cut short (max length)."
                    else: agent_reply = f"Response generation failed ({finish_details})."
                    print(f"     ⚠️ Gemini response fallback needed. Finish Reason: {finish_details}")
            except Exception as resp_err:
                 finish_details_str = finish_details or f"RAW({finish_reason_raw})"
                 print(f"     ❌ Error processing Gemini response: {resp_err}. Finish Reason: {finish_details_str}")
                 agent_reply = f"Error processing response ({finish_details_str})."
                 traceback.print_exc()
        except Exception as model_err:
            print(f"❌ Error during Gemini API call: {traceback.format_exc()}")
            return jsonify({"error": "AI communication error."}), 500

        try: # Save to DB
            batch = db.batch(); chat_doc_ref = None
            if not chat_id:
                chat_doc_ref = db.collection(f'users/{user_id}/chats').document(); chat_id = chat_doc_ref.id
                title = user_message[:config.CHAT_TITLE_LENGTH] + ('...' if len(user_message) > config.CHAT_TITLE_LENGTH else '')
                batch.set(chat_doc_ref, {'title': title, 'timestamp': firestore.SERVER_TIMESTAMP}); print(f"     Created chat: {chat_id}")
            msgs_coll = db.collection(f'users/{user_id}/chats/{chat_id}/messages')
            user_ref = msgs_coll.document(); batch.set(user_ref, {'role': 'user', 'text': user_message, 'timestamp': firestore.SERVER_TIMESTAMP})
            model_ref = msgs_coll.document(); batch.set(model_ref, {'role': 'model', 'text': agent_reply, 'timestamp': firestore.SERVER_TIMESTAMP})
            batch.commit(); print(f"     ✅ Saved messages to chat {chat_id}")
            return jsonify({"reply": agent_reply, "chatId": chat_id})
        except Exception as db_err:
            print(f"❌ Error saving chat messages: {traceback.format_exc()}")
            return jsonify({"reply": agent_reply, "chatId": chat_id, "warning": "Could not save history."})
    except Exception as e:
        print(f"❌ Unexpected error in chat_handler: {traceback.format_exc()}")
        return jsonify({"error": "Internal server error."}), 500
# ============================================
# Main Execution Block
# ============================================
if __name__ == "__main__":
    print("\n" + "="*60 + "\n🚀 AI Stock Analyst API Server Initializing...\n" + "="*60)
    print(f"💰 Start Cash: ₹{config.DEFAULT_STARTING_CASH:,.2f} | Max Adjust: ₹{config.MAX_ADJUST_CASH:,.2f}")
    print(f"🤖 Model: {config.GEMINI_MODEL_NAME} | History Limit: {config.MAX_CHAT_HISTORY}")
    print(f"🔥 Firestore: {'✅ Connected' if db else '❌ NOT CONNECTED!'}")
    print(f"📜 Trade History: {config.TRADE_HISTORY_LIMIT} | ⏱️ Cache TTL: {config.CACHE_TTL_SECONDS}s")
    if not config.NEWSAPI_KEYS or not config.NEWSAPI_KEYS[0]: print("     ⚠️ NewsAPI keys MISSING.")
    else: print(f"     ✅ NewsAPI Keys: {len(config.NEWSAPI_KEYS)} found.")
    print("     ✅ Free Search (DDGS): Enabled | Free News (DDGS): Enabled (Preferred)")
    print(f"     ✅ New Tool: Get Index Constituents (NSE API w/ Fallback)") # <<< Updated Startup Log
    print(f"     ✅ Static Indices Loaded: {len(indices.STATIC_INDICES.keys())} mappings (e.g., NIFTY BANK, NIFTY IT)")
    print("="*60 + "\n")
    port = int(os.environ.get('PORT', 8080))
    print(f"🌍 Server starting on http://0.0.0.0:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)