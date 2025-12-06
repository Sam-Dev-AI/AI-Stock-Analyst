import os
import config
import re
import time
from datetime import date, timedelta, datetime
import google.generativeai as genai
import yfinance as yf
import warnings
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
from flask_session import Session 
import firebase_admin
from firebase_admin import credentials, firestore, auth
from functools import wraps
import pandas as pd
import traceback
from typing import Optional, List
import requests
import json
from urllib.parse import quote_plus 
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from ddgs import DDGS 
from kiteconnect import KiteConnect
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import indices
import db_helper
import logging

# Suppress Flask startup messages
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Suppress yfinance and other library noise
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

# Suppress specific warnings if needed
warnings.filterwarnings('ignore')

# Configure Gemini API Key
genai.configure(api_key=config.GENIE_API_KEY)

# Initialize Zerodha Kite Connect
def get_kite_instance():
   return KiteConnect(api_key=config.ZERODHA_API_KEY)

db = db_helper.DBManager()

# Simple in-memory cache
_cache = {}
CACHE_TTL_SECONDS = config.CACHE_TTL_SECONDS

# Cache setter and getter
def set_cache(key, value, ttl_seconds=CACHE_TTL_SECONDS):
    if not config.CACHE_STORE:  
        return  
    _cache[key] = (value, time.time() + ttl_seconds)
    pass

# Investment Simulation
def simulate_investment(ticker: str, amount: float, duration_years: int, mode: str = 'lumpsum'):
    """
    Simulates an investment in a stock over a past duration.

    Args:
        ticker (str): Stock ticker symbol (e.g., RELIANCE.NS).
        amount (float): Total amount to invest.
        duration_years (int): Number of years to look back.
        mode (str): Investment mode - 'lumpsum' or 'sip' (Systematic Investment Plan).

    Returns:
        dict: Simulation results including total invested, current value, and returns.
    """
    try:
        norm_ticker = normalize_ticker(ticker)
        if not norm_ticker: return {"error": "Invalid ticker"}
        
        # Calculate Start Date
        end_date = datetime.now()
        start_date = end_date - timedelta(days=duration_years * 365)
        
        # Fetch History
        data = yf.download(norm_ticker, start=start_date, end=end_date, interval="1mo", progress=False)
        
        if data.empty: return {"error": "No historical data found"}
        
        data = data['Close']
        
        # Logic
        invested_capital = 0
        total_units = 0
        
        if mode.lower() == 'sip':
            # Simulate Monthly Buy
            for date, price in data.items():
                # Handle Multi-level column if present (yfinance update)
                p = float(price.iloc[0]) if hasattr(price, 'iloc') else float(price)
                if p > 0:
                    units = amount / p
                    total_units += units
                    invested_capital += amount
        else:
            # Lumpsum (One time buy at start)
            start_price = float(data.iloc[0])
            if start_price > 0:
                total_units = amount / start_price
                invested_capital = amount
            
        current_price = get_live_price(norm_ticker)
        current_value = total_units * current_price
        gains = current_value - invested_capital
        percent = (gains / invested_capital) * 100 if invested_capital > 0 else 0
        
        return {
            "ticker": norm_ticker,
            "mode": mode,
            "duration_years": duration_years,
            "total_invested": round(invested_capital, 2),
            "current_value": round(current_value, 2),
            "absolute_return": round(gains, 2),
            "percent_return": round(percent, 2)
        }
        
    except Exception as e:
        print(f"Simulation error: {e}")
        return {"error": str(e)}

# Cache getter
def get_cache(key):
    if not config.CACHE_STORE: 
        return None  
    if key in _cache:
        value, expiry_time = _cache[key]
        if time.time() < expiry_time:
            print(f"      CACHE HIT for {key}")
            return value
        else:
            del _cache[key]  
    return None

# verify Firebase Auth Token Decorator
def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if config.DEBUG_MODE:
            return f(*args, **kwargs)
            
        url_user_id = kwargs.get('user_id')
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"error": "Authorization header is missing"}), 401
        
        id_token = auth_header.split('Bearer ').pop()

        if config.DB_MODE == 'LOCAL':
            if url_user_id and id_token != url_user_id:
                 pass 
            return f(*args, **kwargs)

        try:
            decoded_token = auth.verify_id_token(id_token)
            token_user_id = decoded_token['uid']
            if url_user_id and token_user_id != url_user_id:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({"error": "Invalid token"}), 401
    
    return decorated_function

# Ticker Normalization
def normalize_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    
    ticker = ticker.strip().upper()
    
    # If already has exchange suffix, return as-is
    if ticker.endswith('.NS') or ticker.endswith('.BO'):
        print(f"      Ticker {ticker} already has exchange suffix")
        return ticker
    
    # Check Nifty 50 mapping
    if ticker in indices.NAME_TO_SYMBOL:
        normalized = indices.NAME_TO_SYMBOL[ticker]
        print(f"      Mapped {ticker} -> {normalized} via N50")
        return normalized
    if not any(ticker.endswith(suffix) for suffix in ['.US', '.L', '.TO', '.AX']):
        normalized = f"{ticker}.NS"
        print(f"      Assumed Indian stock: {ticker} -> {normalized}")
        return normalized
    
    print(f"      Could not normalize '{ticker}' via N50 maps. Assuming direct ticker.")
    return ticker

# Enhanced Analyst Rating Calculation
def get_enhanced_analyst_rating(ticker: str, info: dict) -> str:
    try:
        # Start with base consensus but give it LESS weight (only 30%)
        base_recommendation = info.get('recommendationKey', 'hold')
        
        recommendation_map = {
            'strong_buy': 60, 'buy': 55, 'hold': 50,
            'underperform': 45, 'sell': 40, 'strong_sell': 35
        }
        score = recommendation_map.get(base_recommendation.lower().replace(' ', '_'), 50)
        
        # CONSERVATIVE LONG-TERM FUNDAMENTALS (70% weight)
        
        # Valuation - P/E Ratio (25%)
        pe_ratio = info.get('trailingPE')
        if pe_ratio and pe_ratio > 0:
            if pe_ratio < 12:
                score += 12  # Deep value
            elif pe_ratio < 20:
                score += 6
            elif pe_ratio > 50:
                score -= 12  # Overvalued
            elif pe_ratio > 35:
                score -= 6
        
        # Growth - Revenue & Earnings (20%)
        revenue_growth = info.get('revenueGrowth')
        earnings_growth = info.get('earningsQuarterlyGrowth')
        
        if revenue_growth:
            if revenue_growth > 0.25:
                score += 8
            elif revenue_growth > 0.15:
                score += 5
            elif revenue_growth < 0:
                score -= 8
        
        if earnings_growth:
            if earnings_growth > 0.20:
                score += 4
            elif earnings_growth < -0.10:
                score -= 4
        
        # Quality - Margins & ROE (15%)
        profit_margins = info.get('profitMargins')
        roe = info.get('returnOnEquity')
        
        if profit_margins:
            if profit_margins > 0.25:
                score += 6
            elif profit_margins < 0.08:
                score -= 6
        
        if roe:
            if roe > 0.25:
                score += 4
            elif roe < 0.12:
                score -= 4
        
        # Safety - Debt & Current Ratio (10%)
        debt_to_equity = info.get('debtToEquity')
        current_ratio = info.get('currentRatio')
        
        if debt_to_equity is not None:
            if debt_to_equity < 30:
                score += 3
            elif debt_to_equity > 250:
                score -= 5
        
        if current_ratio:
            if current_ratio > 2.0:
                score += 2
            elif current_ratio < 1.0:
                score -= 3
        
        score = max(0, min(100, score))
        
        # CONSERVATIVE THRESHOLDS for long-term investing
        if score >= 75:
            rating = "Strong Buy"
        elif score >= 62:
            rating = "Buy"
        elif score >= 38:
            rating = "Hold"
        elif score >= 25:
            rating = "Sell"
        else:
            rating = "Strong Sell"
        
        #print(f"      [Analyst] (Long-term) for {ticker}:")
        #print(f"         Base={base_recommendation}, P/E={pe_ratio}, Score={score}/100 -> {rating}")
        
        return rating
        
    except Exception as e:
        print(f"      [Error] in analyst rating: {e}")
        base_rec = info.get('recommendationKey', 'N/A')
        return base_rec.replace("_", " ").title() if base_rec else "N/A"

# Stock Chart Details
def get_stock_chart_details(ticker: str, period: str = "1y"):
    """
    Generates chart context (Support/Resistance) and a valid TradingView URL.
    """
    try:
        norm_ticker = normalize_ticker(ticker)
        if not norm_ticker: return {"error": "Invalid ticker"}
        
        # 1. Fetch History for Context
        stock = yf.Ticker(norm_ticker)
        # Map period to yfinance format if needed, else default to 1y
        valid_periods = ['1mo', '3mo', '6mo', '1y', '2y', '5y', 'max']
        if period not in valid_periods: period = '1y'
        
        hist = stock.history(period=period)
        
        if hist.empty:
            return {"error": "No data found"}
            
        # 2. Calculate Simple Levels
        high = round(hist['High'].max(), 2)
        low = round(hist['Low'].min(), 2)
        current = round(hist['Close'].iloc[-1], 2)
        
        # 3. Generate TradingView URL
        # Format: RELIANCE.NS -> RELIANCE
        clean_symbol = norm_ticker.replace('.NS', '').replace('.BO', '')
        chart_url = f"https://www.tradingview.com/chart/?symbol=NSE:{clean_symbol}"
        
        return {
            "ticker": norm_ticker,
            "period": period,
            "high": high,
            "low": low,
            "current": current,
            "chart_url": chart_url,
            "summary": f"In the last {period}, {norm_ticker} ranged from ₹{low} to ₹{high}. Current: ₹{current}."
        }
        
    except Exception as e:
        print(f"Chart tool error: {e}")
        return {"error": str(e)}
    
# Technical Rating Calculation for Timeframe
def get_technical_rating_for_timeframe(ticker, timeframe):
    """Calculate technical rating based on timeframe"""
    try:
        period_map = {
            '1m': '5d', '5m': '60d', '15m': '60d', '30m': '60d',
            '1H': '730d', '4H': '730d', '1D': '1y', '1W': '2y',
            '1MO': '5y', '3M': '10y', '6M': '10y', '1Y': 'max'
        }
        
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period_map.get(timeframe, '1y'))
        
        if hist.empty:
            return 'N/A'
        
        close = hist['Close']
        
        # Calculate multiple indicators
        rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
        ema20 = EMAIndicator(close, window=20).ema_indicator().iloc[-1]
        current_price = close.iloc[-1]
        
        score = 0
        
        # RSI scoring
        if rsi < 30:
            score += 2  # Oversold - Strong Buy
        elif rsi < 40:
            score += 1  # Buy
        elif rsi > 70:
            score -= 2  # Overbought - Strong Sell
        elif rsi > 60:
            score -= 1  # Sell
        
        # EMA trend
        if current_price > ema20:
            score += 1
        else:
            score -= 1
        
        # Map score to rating
        if score >= 2:
            return 'Strong Buy'
        elif score == 1:
            return 'Buy'
        elif score == 0:
            return 'Neutral'
        elif score == -1:
            return 'Sell'
        else:
            return 'Strong Sell'
            
    except:
        return 'N/A'

# Portfolio Performance Projection    
def project_portfolio_performance(user_id: str, direction: str = 'future', duration_months: int = 12):
    """
    Projects future portfolio value based on analyst targets or backtests past performance.

    Args:
        user_id (str): User identifier.
        direction (str): 'future' (Forecast) or 'past' (Backtest).
        duration_months (int): Duration for projection/backtest.

    Returns:
        dict: Analysis including base value, final value, and percent change.
    """
    if not db: return {"error": "DB unavailable"}
    
    try:
        # 1. Get Holdings
        holdings = db.get_portfolio_holdings(user_id)
        if not holdings: return {"error": "Portfolio is empty. Add stocks first."}
        
        tickers = list(holdings.keys())
        total_current_value = 0
        projected_value = 0
        top_mover = {"ticker": "None", "change": 0}

        # 2. Batch Fetch Data
        # We fetch info for Future (Targets) or History for Past
        
        if direction == 'future':
            # FORECAST LOGIC: Use Analyst Targets (targetMeanPrice)
            # If target missing, assume flat (0% growth) to be conservative
            prices = get_bulk_live_prices(tickers)
            
            with ThreadPoolExecutor() as executor:
                future_infos = {executor.submit(get_ticker_info, t): t for t in tickers}
                
                for future in concurrent.futures.as_completed(future_infos):
                    t = future_infos[future]
                    info = future.result() or {}
                    qty = holdings[t]['quantity']
                    cp = prices.get(t, holdings[t]['avg_price'])
                    
                    current_val = qty * cp
                    total_current_value += current_val
                    
                    # Get Target Price. If None, use Current Price (0% gain)
                    target = info.get('targetMeanPrice')
                    if not target: target = cp 
                    
                    # Scale target based on duration (Analyst targets are usually 12 months)
                    # Formula: Projected = Current + ((Target - Current) * (months/12))
                    if duration_months != 12:
                        yearly_diff = target - cp
                        scaled_diff = yearly_diff * (duration_months / 12)
                        final_price = cp + scaled_diff
                    else:
                        final_price = target
                        
                    projected_val = qty * final_price
                    projected_value += projected_val
                    
                    # Track top mover
                    pct_change = ((final_price - cp) / cp) * 100
                    if abs(pct_change) > abs(top_mover['change']):
                        top_mover = {"ticker": t, "change": pct_change}

        else:
            # BACKTEST LOGIC: 'past'
            # "If I held these stocks X months ago..."
            end_date = date.today()
            start_date = end_date - timedelta(days=int(duration_months * 30))
            
            # Fetch historical data
            data = yf.download(tickers, start=start_date, end=end_date, progress=False)['Close']
            
            if data.empty: return {"error": "Historical data unavailable"}

            for t in tickers:
                qty = holdings[t]['quantity']
                
                # Handle single ticker vs multi-ticker DataFrame structure
                if len(tickers) > 1:
                    if t not in data.columns: continue
                    hist_series = data[t].dropna()
                else:
                    hist_series = data.dropna() # For single ticker, it's a Series
                
                if hist_series.empty: continue
                
                price_then = float(hist_series.iloc[0])
                price_now = float(hist_series.iloc[-1])
                
                val_then = qty * price_then
                val_now = qty * price_now
                
                # In 'past' mode: 
                # Current Value = What it is worth now
                # Projected Value (actually Past Value) = What it cost then
                total_current_value += val_now 
                projected_value += val_then 
                
                pct_change = ((price_now - price_then) / price_then) * 100
                if abs(pct_change) > abs(top_mover['change']):
                    top_mover = {"ticker": t, "change": pct_change}

        # 3. Final Calculations
        if direction == 'past':
            # Logic: You HAVE X now. It COST Y then.
            diff = total_current_value - projected_value
            pct = (diff / projected_value * 100) if projected_value > 0 else 0
            base_label = f"Value {duration_months} months ago"
            final_label = "Current Value"
            val_start = projected_value
            val_end = total_current_value
        else:
            # Logic: You HAVE X now. It WILL BE Y later.
            diff = projected_value - total_current_value
            pct = (diff / total_current_value * 100) if total_current_value > 0 else 0
            base_label = "Current Value"
            final_label = f"Expected Value in {duration_months} months"
            val_start = total_current_value
            val_end = projected_value

        return {
            "analysis_type": direction.upper(),
            "duration_months": duration_months,
            "base_value_label": base_label,
            "base_value": round(val_start, 2),
            "final_value_label": final_label,
            "final_value": round(val_end, 2),
            "absolute_change": round(diff, 2),
            "percent_change": round(pct, 2),
            "top_driver": top_mover
        }

    except Exception as e:
        print(f"Portfolio Project Error: {e}")
        return {"error": str(e)}
    
# Market Cap Formatting      
def format_market_cap(market_cap):
    """
    Format market cap into readable format (e.g., ₹16.5T, ₹2.3L Cr)
    """
    if not market_cap or market_cap == 0:
        return 'N/A'
    
    try:
        market_cap = float(market_cap)
        
        # Convert to Trillion (T)
        if market_cap >= 1_000_000_000_000:
            return f"₹{market_cap / 1_000_000_000_000:.2f}T"
        
        # Convert to Lakh Crore (L Cr)
        elif market_cap >= 1_000_000_000:
            return f"₹{market_cap / 10_000_000_000:.2f}L Cr"
        
        # Convert to Crore (Cr)
        elif market_cap >= 10_000_000:
            return f"₹{market_cap / 10_000_000:.2f} Cr"
        
        # Convert to Lakh (L)
        elif market_cap >= 100_000:
            return f"₹{market_cap / 100_000:.2f}L"
        
        else:
            return f"₹{market_cap:,.0f}"
    
    except (ValueError, TypeError):
        return 'N/A'

# Internal function to get compact ticker info        
def _get_compact_ticker_info(ticker_str: str) -> Optional[dict]:
    try:
        stock = yf.Ticker(ticker_str)
        info = stock.info
        
        if not info or not info.get('symbol'):
            print(f"    _get_compact_ticker_info: No valid info for {ticker_str}")
            return None

        # Extract only the keys we actually use across all functions
        compact_info = {
            'symbol': info.get('symbol'),
            'shortName': info.get('shortName'),
            'longName': info.get('longName'),
            'currency': info.get('currency', '$'),
            'currentPrice': info.get('currentPrice') or info.get('regularMarketPrice'),
            'previousClose': info.get('previousClose'),
            'dayLow': info.get('dayLow'),
            'dayHigh': info.get('dayHigh'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'marketCap': info.get('marketCap'),
            'trailingPE': info.get('trailingPE'),
            'priceToBook': info.get('priceToBook'),
            'trailingEps': info.get('trailingEps'),
            'dividendYield': info.get('dividendYield'),
            'fiftyTwoWeekHigh': info.get('fiftyTwoWeekHigh'),
            'fiftyTwoWeekLow': info.get('fiftyTwoWeekLow'),
            'beta': info.get('beta'),
            'recommendationKey': info.get('recommendationKey'),
            'targetMeanPrice': info.get('targetMeanPrice'),
            'revenueGrowth': info.get('revenueGrowth'),
            'earningsQuarterlyGrowth': info.get('earningsQuarterlyGrowth'),
            'profitMargins': info.get('profitMargins'),
            'returnOnEquity': info.get('returnOnEquity'),
            'debtToEquity': info.get('debtToEquity'),
            'currentRatio': info.get('currentRatio')
        }
        
        # Ensure critical price fields are present
        if compact_info['currentPrice'] is None:
            print(f"    _get_compact_ticker_info: Missing currentPrice for {ticker_str}")
            # Try to get from history as a last resort
            hist = stock.history(period="2d", interval="1d")
            if not hist.empty and 'Close' in hist.columns:
                compact_info['currentPrice'] = hist['Close'].iloc[-1]
                if compact_info['previousClose'] is None and len(hist) > 1:
                    compact_info['previousClose'] = hist['Close'].iloc[-2]
            
            if compact_info['currentPrice'] is None:
                 return None # Failed to get any price

        if compact_info['previousClose'] is None:
            compact_info['previousClose'] = compact_info['currentPrice'] # Fallback

        return compact_info

    except Exception as e:
        print(f"    [Error] _get_compact_ticker_info exception for {ticker_str}: {e}")
        return None

# Fetch Ticker Info with Caching
def get_ticker_info(ticker_str: str):
    if not isinstance(ticker_str, str): 
        print(f"     Invalid ticker type: {ticker_str}")
        return None
    
    cache_key = f"info_{ticker_str}"
    cached_info = get_cache(cache_key)
    
    if cached_info: 
        return cached_info
    
    try:
        # Call our new internal function to get the compact data
        compact_info = _get_compact_ticker_info(ticker_str)
        
        if not compact_info:
            print(f"     No valid COMPACT info for {ticker_str}"); 
            return None
            
        # Cache the SMALL compact object, not the giant 'info' object
        set_cache(cache_key, compact_info, ttl_seconds=config.CACHE_PRICE_DATA_SECONDS)
        return compact_info
        
    except Exception as e: 
        print(f"     [Error] yfinance info exception for {ticker_str}: {e}")
        return None

# Technical Rating Calculation
def get_technical_rating(ticker: str, timeframe: str = '1D') -> str:
    cache_key = f"tech_rating_{ticker}_{timeframe}"
    cached_rating = get_cache(cache_key)
    if cached_rating:
        print(f"[CACHE HIT] for Technical Rating {ticker} {timeframe} -> {cached_rating}")
        return cached_rating
    
    try:
        from ta.volatility import BollingerBands
        from ta.trend import MACD
        
        norm_ticker = normalize_ticker(ticker)
        if not norm_ticker:
            return "N/A"
        
        # Map timeframes to yfinance parameters
        timeframe_map = {
            '1m': {'period': '7d', 'interval': '1m'},
            '5m': {'period': '60d', 'interval': '5m'},
            '15m': {'period': '60d', 'interval': '15m'},
            '30m': {'period': '60d', 'interval': '30m'},
            '1h': {'period': '730d', 'interval': '1h'},
            '4h': {'period': '730d', 'interval': '1h'}, 
            '1d': {'period': '1y', 'interval': '1d'},
            '1w': {'period': '2y', 'interval': '1wk'},
            '1mo': {'period': '5y', 'interval': '1mo'},
            '3m': {'period': '6mo', 'interval': '1d'},
            '6m': {'period': '1y', 'interval': '1d'},
            '1y': {'period': '2y', 'interval': '1d'}
        }
        
        params = timeframe_map.get(timeframe, timeframe_map['1d'])
        
        stock = yf.Ticker(norm_ticker)
        hist = stock.history(period=params['period'], interval=params['interval'])
        
        if hist.empty or 'Close' not in hist.columns or 'Volume' not in hist.columns:
            return "N/A"
        
        close_prices = hist['Close'].dropna()
        volumes = hist['Volume'].dropna()
        
        if len(close_prices) < 50: # Need at least 50 data points for 50-day avg vol
            print(f"Not enough data for TA on {ticker} ({len(close_prices)} points)")
            return "N/A"
        rsi_indicator = RSIIndicator(close_prices, window=14)
        current_rsi = rsi_indicator.rsi().iloc[-1]
        
        macd_indicator = MACD(close_prices, window_slow=26, window_fast=12, window_sign=9)
        macd_diff = macd_indicator.macd_diff().iloc[-1] 
        
        bb_indicator = BollingerBands(close_prices, window=20, window_dev=2)
        current_price = close_prices.iloc[-1]
        bb_upper = bb_indicator.bollinger_hband().iloc[-1]
        bb_lower = bb_indicator.bollinger_lband().iloc[-1]
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        avg_volume_50 = volumes.iloc[-50:].mean()
        current_volume = volumes.iloc[-1]
        volume_spike = current_volume / avg_volume_50 if avg_volume_50 > 0 else 1.0
        
        # Use 3-day price momentum
        price_momentum = ((close_prices.iloc[-1] - close_prices.iloc[-4]) / close_prices.iloc[-4]) * 100 if len(close_prices) > 3 else 0
        
        if pd.isna(current_rsi) or pd.isna(macd_diff) or pd.isna(bb_position):
            return "N/A"
        
        score = 50 

        if current_rsi < 30: score += 15    
        elif current_rsi < 45: score += 8     
        elif current_rsi > 75: score -= 15    
        elif current_rsi > 65: score -= 8     
        elif 55 <= current_rsi <= 65: score += 5 
        if macd_diff > 0.5: score += 15 
        elif macd_diff > 0: score += 8  
        elif macd_diff < -0.5: score -= 15 
        elif macd_diff < 0: score -= 8  
        if bb_position < 0.1: score += 10    #
        elif bb_position > 0.9: score -= 10   
        if volume_spike > 1.8: # > 80% increase
            if price_momentum > 1: score += 10   
            elif price_momentum < -1: score -= 10 

        # Clamp score between 0 and 100
        score = max(0, min(100, score))
        if score >= 75: rating = "Strong Buy"
        elif score >= 58: rating = "Buy"
        elif score >= 42: rating = "Neutral"
        elif score >= 25: rating = "Sell"
        else: rating = "Strong Sell"
        set_cache(cache_key, rating, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS) 

        return rating
            
    except Exception as e:
        print(f"    [Error] in technical rating: {e}")
        traceback.print_exc()
        set_cache(cache_key, "N/A", ttl_seconds=600)
        return "N/A"
    
# Get Current Price with detailed snapshot
def get_current_price(ticker: str):
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return {"error": f"Could not find a valid ticker for '{ticker}'. Please use a known name or ticker (e.g., RELIANCE or ZOMATO.NS)."}

    # This call is now fast, cached, and returns the small compact object
    info = get_ticker_info(normalized_ticker) 
    
    if not info:
        return {"error": f"Ticker '{normalized_ticker}' seems invalid. No data found."}

    try:
        is_nse = normalized_ticker.endswith('.NS')
        currency_symbol = "₹" if is_nse else info.get('currency', '$')
        
        # Get all data directly from the compact 'info' object
        current_price = float(info['currentPrice'])
        previous_close = float(info['previousClose'])
        
        one_day_change_val = current_price - previous_close
        one_day_change_pct = (one_day_change_val / previous_close) * 100 if previous_close and previous_close != 0 else 0

        result = {
            "ticker": normalized_ticker, 
            "company_name": info.get('shortName', info.get('longName', normalized_ticker)),
            "currency": currency_symbol, 
            "current_price": round(current_price, config.PRICE_DECIMAL_PLACES),
            "change_value": round(one_day_change_val, config.PRICE_DECIMAL_PLACES), 
            "change_percentage": round(one_day_change_pct, 2),
            "day_low": round(float(info.get('dayLow', current_price)), config.PRICE_DECIMAL_PLACES),
            "day_high": round(float(info.get('dayHigh', current_price)), config.PRICE_DECIMAL_PLACES),
            "previous_close": round(previous_close, config.PRICE_DECIMAL_PLACES), 
            "is_nse": is_nse
        }
        return result
    except Exception as e: 
        print(f"     [Error] Exception in get_current_price for {normalized_ticker}: {traceback.format_exc()}")
        return {"error": f"Error fetching price details: {str(e)}"}

# Get Index Data
def get_index_data(index_name: str) -> dict:
    #print(f"[get_index_data] Fetching data for: {index_name}")
    index_map = {
        'NIFTY': '^NSEI',
        'NIFTY 50': '^NSEI',
        'NIFTY50': '^NSEI',
        'SENSEX': '^BSESN',
        'BSE SENSEX': '^BSESN',
        'BANK NIFTY': '^NSEBANK',
        'BANKNIFTY': '^NSEBANK',
        'NIFTY BANK': '^NSEBANK',
        'NIFTY IT': '^CNXIT',
        'NIFTY PHARMA': '^CNXPHARMA',
        'NIFTY FMCG': '^CNXFMCG',
        'NIFTY AUTO': '^CNXAUTO',
        'NIFTY METAL': '^CNXMETAL',
        'NIFTY REALTY': '^CNXREALTY',
        'NIFTY ENERGY': '^CNXENERGY',
        'NIFTY INFRA': '^CNXINFRA',
        'NIFTY MIDCAP': '^NSEMDCP50',
        'NIFTY SMALLCAP': '^CNXSC'
    }
    
    normalized = index_name.strip().upper()
    ticker = index_map.get(normalized)
    
    if not ticker:
        for key, val in index_map.items():
            if normalized in key or key in normalized:
                ticker = val
                break
    
    if not ticker:
        return {"error": f"Index '{index_name}' not recognized. Supported: NIFTY, SENSEX, BANK NIFTY, NIFTY IT, etc."}
    
    try:
        index = yf.Ticker(ticker)
        hist = index.history(period="5d", interval="1d")
        
        if hist.empty or 'Close' not in hist.columns:
            return {"error": f"Could not fetch data for {index_name} (ticker: {ticker})"}
        
        current_level = float(hist['Close'].iloc[-1])
        previous_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_level
        
        change_value = current_level - previous_close
        change_percent = (change_value / previous_close * 100) if previous_close else 0
        
        day_high = float(hist['High'].iloc[-1]) if 'High' in hist.columns else current_level
        day_low = float(hist['Low'].iloc[-1]) if 'Low' in hist.columns else current_level
        
        return {
            "index_name": index_name,
            "ticker": ticker,
            "current_level": round(current_level, 2),
            "previous_close": round(previous_close, 2),
            "change_value": round(change_value, 2),
            "change_percent": round(change_percent, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2)
        }
        
    except Exception as e:
        print(f"[get_index_data] Error for {index_name}: {e}")
        return {"error": f"Failed to fetch index data: {str(e)}"}

# Agent-facing wrapper for get_index_data
def get_index_data_for_agent(index_name: str) -> dict:
    print(f"[Agent] calls get_index_data: {index_name}")
    try:
        return get_index_data(index_name)
    except Exception as e:
        print(f"[Error] in get_index_data_for_agent: {traceback.format_exc()}")
        return {"error": str(e)}

# screen_static_index
def screen_static_index(index_name: str = "NIFTY 50", num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False):
    #print(f"      → screen_static_index (Index={index_name}, N={num_stocks}, Duration={duration_days}, Buy={prefer_buy})")

    norm_name = index_name.strip().upper()
    ticker_list = indices.STATIC_INDICES.get(norm_name)  

    if ticker_list is None:
        valid_indices = list(indices.STATIC_INDICES.keys())
        print(f"      [Error] Error: Index '{index_name}' (Normalized: '{norm_name}') not in static list.")
        return {"error": f"Index '{index_name}' not in pre-defined list. Try one of: {', '.join(valid_indices[:6])}..."}

    return screen_custom_stock_list(tickers=ticker_list, num_stocks=num_stocks, duration_days=duration_days, prefer_buy=prefer_buy, index_name_for_log=index_name)

# screen_custom_stock_list
def screen_custom_stock_list(tickers: List[str], num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False, index_name_for_log: str = "Custom List"):
    """
    Screens stocks using a 'Best Available' scoring system. 
    Guarantees results even in bearish markets.
    """
    print(f"      → screen_custom_stock_list (Index={index_name_for_log}, N={num_stocks})")
    
    if not tickers or not isinstance(tickers, list): 
        return {"error": "No valid ticker list provided."}
    
    try:
        num_stocks = int(num_stocks)
        if num_stocks <= 0: num_stocks = 3
    except: num_stocks = 3

    cache_key = f"filtered_stocks_{index_name_for_log.replace(' ','_')}_{num_stocks}_{duration_days}_{prefer_buy}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result

    try:
        duration_days = max(10, min(duration_days, 365))
        ema_window = min(max(duration_days, 10), 200)
        history_days_needed = max(ema_window + 15, 90)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=history_days_needed)
        valid_tickers = sorted(list(set([t for t in tickers if isinstance(t, str) and t.endswith('.NS')])))
        if not valid_tickers: return {"error": "No valid .NS tickers found."}
        hist_data = yf.download(valid_tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
        
        if hist_data.empty or 'Close' not in hist_data.columns: 
            raise ValueError("yfinance download returned empty data.")

        candidates = []
        is_multi_ticker = len(valid_tickers) > 1
        for ticker in valid_tickers:
            try:
                if is_multi_ticker:
                    if ticker not in hist_data['Close'].columns: continue
                    close_prices = hist_data['Close'][ticker].dropna()
                else:
                    close_prices = hist_data['Close'].dropna()
                
                if len(close_prices) < max(ema_window, 14): continue
                current_price = close_prices.iloc[-1]
                rsi_val = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                ema_val = EMAIndicator(close_prices, window=ema_window).ema_indicator().iloc[-1]
                
                if pd.isna(rsi_val) or pd.isna(ema_val): continue
                score = 0
                
                # Trend Score
                if current_price > ema_val: score += 50  # Above EMA is good
                else: score -= 20 # Below EMA is bad
                
                # RSI Score (0-100 scale preference)
                # Ideal Buy zone: 40-60. Overbought > 70.
                if 40 <= rsi_val <= 65: score += 30
                elif rsi_val > 70: score -= 10 * prefer_buy # Penalty for overbought if buying
                elif rsi_val < 30: score += 20 # Oversold bounce candidate
                
                info = get_ticker_info(ticker)
                
                candidates.append({
                    'Ticker': ticker,
                    'Name': info.get('shortName', ticker) if info else ticker,
                    'Price': float(round(current_price, 2)),
                    'RSI': float(round(rsi_val, 2)),
                    'EMA': float(round(ema_val, 2)),
                    'Score': score
                })

            except Exception as e: continue
        if not candidates:
            return {"message": f"Could not calculate technicals for any stocks in {index_name_for_log}."}

        # Sort by Score (Highest first) -> Then by RSI
        candidates.sort(key=lambda x: (x['Score'], x['RSI']), reverse=True)
        
        top_picks = candidates[:num_stocks]
        
        result = {"top_filtered_stocks": top_picks}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS)
        return result

    except Exception as e:
        print(f"      [Error] Screening error: {traceback.format_exc()}")
        return {"message": f"Screening failed: {str(e)}"}

#summary for memory
def get_conversation_summary(history_list):
    if not history_list:
        return ""
        
    # Convert list of dicts to a single string string
    conversation_text = ""
    for msg in history_list:
        role = "User" if msg['role'] == 'user' else "AI"
        text = msg['parts'][0]['text']
        conversation_text += f"{role}: {text}\n"

    summary_prompt = f"""
    Summarize the following stock analysis conversation into a single concise paragraph. 
    Retain key details like:
    1. User's risk profile or preferences.
    2. Stocks discussed (Tickers).
    3. Specific trade actions taken (Bought/Sold).
    4. Any pending requests.
    
    Conversation:
    {conversation_text}
    
    Summary:
    """
    
    try:
        summary_model = genai.GenerativeModel('gemini-2.5-flash') 
        response = summary_model.generate_content(summary_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Summarization failed: {e}")
        return ""

#get_live_price
def get_live_price(ticker: str) -> float:
    norm_t = normalize_ticker(ticker)
    if not norm_t: 
        raise ValueError(f"Invalid ticker: '{ticker}'.")
    
    # This is now the single, fast, cached source of truth
    info = get_ticker_info(norm_t)
    
    if not info:
        raise ValueError(f"Ticker {norm_t} is invalid, no info.")
        
    price = info.get('currentPrice')
    
    if price is not None:
        return float(price)
    else:
        # This should theoretically not be reachable if _get_compact_ticker_info works
        raise ValueError(f"No price data found for {norm_t} even after info fetch.")

# Get Fundamental Data
def get_fundamental_data(ticker: str) -> dict:
    """Retrieves key fundamental data points with enhanced ratings."""
    norm_t = normalize_ticker(ticker)
    if not norm_t:
        return {"error": f"Invalid ticker: '{ticker}'."}
    
    try:
        # This call is now fast, cached, and returns the small compact object
        info = get_ticker_info(norm_t) 
        
        if not info:
            if norm_t.endswith('.NS'):
                print(f"     Retrying with .BO suffix...")
                alt_ticker = norm_t.replace('.NS', '.BO')
                info = get_ticker_info(alt_ticker) # This is also fast/cached
                if info:
                    norm_t = alt_ticker
                else:
                    return {"error": f"Could not retrieve data for {ticker}."}
            else:
                return {"error": f"Could not retrieve data for {ticker}."}
        
        is_nse = norm_t.endswith('.NS')
        currency_symbol = "₹" if is_nse or norm_t.endswith('.BO') else info.get('currency', '$')
        
        # All these fields are guaranteed to be in our compact 'info' object
        current_price = info.get('currentPrice')
        mc = info.get('marketCap')
        div_y = info.get('dividendYield')
        target_price = info.get('targetMeanPrice')
        
        # These functions will now use the fast, cached get_ticker_info()
        technical_rating = get_technical_rating(norm_t) 
        enhanced_recommendation = get_enhanced_analyst_rating(norm_t, info)
        
        funda = {
            "ticker": norm_t,
            "companyName": info.get('shortName', info.get('longName', norm_t)),
            "currentPrice": f"{currency_symbol}{round(current_price, 2)}" if current_price else "N/A",
            "recommendation": enhanced_recommendation,
            "technicalRating": technical_rating,
            "targetPrice": f"{currency_symbol}{round(target_price, 2)}" if target_price else "N/A",
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "marketCap": f"{currency_symbol}{mc:,.0f}" if mc else "N/A",
            "peRatio": round(info['trailingPE'], 2) if info.get('trailingPE') else "N/A",
            "pbRatio": round(info['priceToBook'], 2) if info.get('priceToBook') else "N/A",
            "eps": f"{currency_symbol}{round(info['trailingEps'], 2)}" if info.get('trailingEps') else "N/A",
            "dividendYield": f"{div_y * 100:.2f}%" if div_y else "N/A",
            "52WeekHigh": f"{currency_symbol}{round(info['fiftyTwoWeekHigh'], config.PRICE_DECIMAL_PLACES)}" if info.get('fiftyTwoWeekHigh') else "N/A",
            "52WeekLow": f"{currency_symbol}{round(info['fiftyTwoWeekLow'], config.PRICE_DECIMAL_PLACES)}" if info.get('fiftyTwoWeekLow') else "N/A",
            "beta": round(info['beta'], 2) if info.get('beta') else "N/A",
            "is_nse": is_nse
        }
        return funda
        
    except Exception as e:
        print(f"     [Error] Exception in get_fundamental_data {ticker}: {e}")
        traceback.print_exc()
        return {"error": f"Error retrieving fundamentals: {str(e)}"}
    
# Find Intraday Trade Setups with Trend and Volume Confluence
def find_intraday_trade_setups(tickers: Optional[List[str]] = None, num_setups: int = 3) -> dict:
    """
            Scans the market for high-probability Intraday trade setups.
            TRIGGER: Use ONLY when the user explicitly asks for 'intraday', 'day trading', 'setups', or 'scanning'.
            DO NOT use for general greetings.
            """
    print(f"      → find_intraday_trade_setups (N={num_setups}, Tickers={'Scan All' if not tickers else len(tickers)})")
    
    if not tickers:
        tickers_to_scan = indices.NIFTY_50
        scan_source = "NIFTY 50"
    else:
        tickers_to_scan = [normalize_ticker(t) for t in tickers if normalize_ticker(t)]
        if not tickers_to_scan:
            return {"error": "No valid .NS tickers were provided or normalized from the input list."}
        scan_source = "User-Provided List"

    setups = []
    
    history_days_needed = 70 
    end_date = date.today()
    start_date = end_date - timedelta(days=history_days_needed)

    print(f"      Downloading history for {len(tickers_to_scan)} tickers ({start_date} to {end_date})...")
    
    try:
        hist_data = yf.download(tickers_to_scan, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if hist_data.empty or 'Close' not in hist_data.columns:
            raise ValueError("yfinance download returned empty data.")
    except Exception as e:
        print(f"      [Error] Exception in yf.download for setups: {e}")
        return {"error": f"Failed to download historical data for screening: {str(e)}"}
        
    is_multi_ticker = len(tickers_to_scan) > 1

    for ticker in tickers_to_scan:
        try:
            stock_hist_data = None
            if is_multi_ticker:
                if ticker not in hist_data['Close'].columns or hist_data['Close'][ticker].isnull().all():
                    continue
                stock_hist_data = hist_data.loc[:, (slice(None), ticker)]
                stock_hist_data.columns = stock_hist_data.columns.droplevel(1)
            else:
                if hist_data.empty or 'Close' not in hist_data.columns:
                    continue
                stock_hist_data = hist_data
            
            if stock_hist_data.empty or len(stock_hist_data['Close'].dropna()) < 55:  
                continue

            close_prices = stock_hist_data['Close'].dropna()
            volumes = stock_hist_data['Volume'].dropna() 
            
            if len(close_prices) < 55 or len(volumes) < 55: continue  
            
            rsi_val = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
            ema_20 = EMAIndicator(close_prices, window=20).ema_indicator().iloc[-1] 
            
            avg_volume_50 = volumes.iloc[-51:-1].mean() 
            last_volume = volumes.iloc[-1]            
            
            if pd.isna(rsi_val) or pd.isna(ema_20) or pd.isna(avg_volume_50) or avg_volume_50 == 0:
                continue

            entry = close_prices.iloc[-1]
            prev_low = stock_hist_data['Low'].iloc[-2]
            prev_high = stock_hist_data['High'].iloc[-2]
            
            info = get_ticker_info(ticker)
            company_name = info.get('shortName', ticker) if info else ticker
            if 50 < rsi_val < 70:
                sl_price_buy = prev_low
                risk_amount_buy = entry - sl_price_buy
                
                if risk_amount_buy > 0:
                    risk_percent_buy = risk_amount_buy / entry
                    
                    is_uptrend = entry > ema_20
                    is_volume_confirmed = last_volume > avg_volume_50
                    if 0.005 < risk_percent_buy < 0.03 and is_uptrend and is_volume_confirmed:
                        tp_price_buy = entry + 2 * risk_amount_buy
                        rationale = f"RSI {rsi_val:.1f} (bullish), in short-term uptrend (Price > 20-EMA), and on above-average volume."
                        
                        setups.append({
                            "ticker": ticker,
                            "name": company_name,
                            "trade_type": "Long (Buy)",
                            "entry_price": float(round(entry, config.PRICE_DECIMAL_PLACES)),
                            "sl_price": float(round(sl_price_buy, config.PRICE_DECIMAL_PLACES)),
                            "tp_price": float(round(tp_price_buy, config.PRICE_DECIMAL_PLACES)),
                            "risk_amount": float(round(risk_amount_buy, config.PRICE_DECIMAL_PLACES)),
                            "risk_percent": float(round(risk_percent_buy * 100, 2)),
                            "rationale": rationale 
                        })

            if 30 < rsi_val < 50:
                sl_price_sell = prev_high
                risk_amount_sell = sl_price_sell - entry

                if risk_amount_sell > 0:
                    risk_percent_sell = risk_amount_sell / entry
                    
                    is_downtrend = entry < ema_20
                    is_volume_confirmed = last_volume > avg_volume_50
                    
                    if 0.005 < risk_percent_sell < 0.03 and is_downtrend and is_volume_confirmed:
                        tp_price_sell = entry - 2 * risk_amount_sell
                        
                        rationale = f"RSI {rsi_val:.1f} (bearish), in short-term downtrend (Price < 20-EMA), and on above-average volume."

                        setups.append({
                            "ticker": ticker,
                            "name": company_name,
                            "trade_type": "Short (Sell)",
                            "entry_price": float(round(entry, config.PRICE_DECIMAL_PLACES)),
                            "sl_price": float(round(sl_price_sell, config.PRICE_DECIMAL_PLACES)),
                            "tp_price": float(round(tp_price_sell, config.PRICE_DECIMAL_PLACES)),
                            "risk_amount": float(round(risk_amount_sell, config.PRICE_DECIMAL_PLACES)),
                            "risk_percent": float(round(risk_percent_sell * 100, 2)),
                            "rationale": rationale 
                        })

        except Exception as e:
            print(f"      [Warning] Error processing setup for {ticker}: {e}")
            continue 
    
    if not setups:
        return {"message": f"No stocks from the '{scan_source}' list currently meet the high-probability intraday trade setup criteria (RSI + Trend + Volume)."}

    setups.sort(key=lambda x: x['risk_percent'])
    
    print(f"      [Success] Found {len(setups)} total high-probability setups. Returning top {num_setups}.")
    return {"setups": setups[:num_setups]}

# News Fetching Functions
def get_stock_news(query: str, company_name: Optional[str] = None) -> dict: 
    """
    Fetches stock news using NewsAPI.

    Args:
        query (str): Search query or ticker.
        company_name (str, optional): Full company name for better search results.

    Returns:
        dict: List of news articles with title, source, and description.
    """ 
    print(f"      → get_stock_news (NewsAPI Fallback) for: '{query}' (Company: {company_name})")
    search_term = company_name if company_name else query
    if not search_term: return {"error": "No query/company name."}
    cache_key = f"newsapi_{search_term.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    encoded_search_term = quote_plus(search_term)
    params = {'language': 'en', 'category': 'business', 'sortBy': 'relevancy', 'pageSize': 5, 'q': encoded_search_term}
    base_url = "https://newsapi.org/v2/everything"
    for api_key in config.NEWSAPI_KEYS:
        params['apiKey'] = api_key
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'error':
                if data.get('code') == 'rateLimited': print(f"      [Warning] NewsAPI Key {api_key[:8]}... rate limited."); continue
                else: print(f"      [Error] NewsAPI Error ({data.get('code')}): {data.get('message')}"); return {"error": f"NewsAPI Error: {data.get('message')}"}
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                if not articles: result = {"message": f"No NewsAPI news for '{search_term}'."}
                else:
                    fmt_news = [{"title": a.get('title'), "source": a.get('source', {}).get('name'), "description": a.get('description'), "url": a.get('url'), "publishedAt": a.get('publishedAt')} for a in articles]
                    print(f"      [Success] Found {len(fmt_news)} NewsAPI articles for '{search_term}'.")
                    result = {"articles": fmt_news}
                set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
        except requests.exceptions.HTTPError as http_err:
            response_obj = getattr(http_err, 'response', None)
            if response_obj is not None:
                if response_obj.status_code == 400: print(f"      [Error] NewsAPI Bad Request (400) key {api_key[:8]}... URL: {response_obj.url}\nBody: {response_obj.text}"); return {"error": "NewsAPI Bad Request (400). Details logged."}
                elif response_obj.status_code == 429: print(f"      [Warning] NewsAPI Key {api_key[:8]} rate limited (429)."); continue
            print(f"      [Error] HTTP Error NewsAPI: {http_err}"); return {"error": f"NewsAPI HTTP Error: {http_err}"}
        except requests.exceptions.RequestException as req_err: print(f"      [Error] Request Ex NewsAPI: {req_err}"); return {"error": f"NewsAPI Connection Error: {req_err}"}
    result = {"error": "NewsAPI keys rate-limited or invalid."}; set_cache(cache_key, result, ttl_seconds=60); return result

# DuckDuckGo News and Search
def internet_search_news(query: str) -> dict:
    #print(f"      → internet_search_news (DDGS) for: '{query}'")
    cache_key = f"ddgs_news_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.news(query, region='in-en', safesearch='off', max_results=5)
        if not results: result = {"message": f"No DDGS news found for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "source": i.get('source'), "description": i.get('body'), "url": i.get('url'), "publishedAt": i.get('date')} for i in results]
            #print(f"      [Success] Found {len(fmt_res)} DDGS news results.")
            result = {"articles": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e:
        print(f"      [Error] DDGS News Search Error: {traceback.format_exc()}")
        return {"error": f"DDGS news search error: {str(e)}"}

# Zerodha Portfolio Sync
def sync_zerodha_portfolio(user_id: str, access_token: str) -> dict:
    """
    Synchronizes the user's Zerodha portfolio holdings and positions with the local database.

    Args:
        user_id (str): User identifier.
        access_token (str): Valid Zerodha access token.

    Returns:
        dict: Sync status, number of holdings synced, and updated portfolio value.
    """
    if not db: return {"error": "DB unavailable"}
    
    try:
        print(f"Starting Zerodha sync for user {user_id}...")
        kite = KiteConnect(api_key=config.ZERODHA_API_KEY)
        kite.set_access_token(access_token)

        # 1. Fetch Data
        margins = kite.margins()
        equity_margin = margins.get('equity', {})
        available_balance = equity_margin.get('available', {}).get('cash', 0.0)
        cash_balance = available_balance 
        
        holdings = kite.holdings()
        positions = kite.positions().get('net', []) 
        
        print(f"    Found {len(holdings)} holdings and {len(positions)} net positions.")

        # 2. Process Instruments
        all_instruments = {}

        for item in holdings:
            ticker = item.get('tradingsymbol')
            quantity_settled = float(item.get('quantity', 0))
            quantity_t1 = float(item.get('t1_quantity', 0))
            mtf_data = item.get('mtf', {}) 
            quantity_mtf = float(mtf_data.get('quantity', 0))
            
            total_quantity = quantity_settled + quantity_t1 + quantity_mtf
            
            if not ticker or total_quantity <= 0: continue 

            all_instruments[ticker] = {
                'quantity': total_quantity,
                'avg_price': float(item.get('average_price', 0)),
                'exchange': item.get('exchange'), # Could be NSE or BSE
                'product': item.get('product', 'CNC').upper(),
                'prev_close_price': float(item.get('close_price', 0)) 
            }

        for item in positions:
            ticker = item.get('tradingsymbol')
            quantity = float(item.get('quantity', 0))
            product = item.get('product', '').upper()
            
            if quantity <= 0 or product == 'MIS': continue
            
            # Prioritize Position exchange if available
            exchange = item.get('exchange')

            if product in ['MTF', 'NRML', 'CNC']: 
                if ticker in all_instruments:
                    all_instruments[ticker]['quantity'] += quantity 
                    # If holding says BSE but Position says NSE, upgrade to NSE
                    if exchange == 'NSE':
                        all_instruments[ticker]['exchange'] = 'NSE'
                else:
                    all_instruments[ticker] = {
                        'quantity': quantity,
                        'avg_price': float(item.get('average_price', 0)),
                        'exchange': exchange,
                        'product': product,
                        'prev_close_price': float(item.get('close_price', 0))
                    }
        
        # 3. Database Updates
        try:
            db.reset_portfolio(user_id, float(cash_balance))
            holdings_synced_count = 0
            
            # Define Major Stocks to FORCE to NSE (Add more if needed)
            # This prevents RELIANCE.BO or ITC.BO if you prefer NSE
            MAJOR_STOCKS = [
                'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ITC', 'SBIN', 'BHARTIARTL', 
                'HINDUNILVR', 'ICICIBANK', 'KOTAKBANK', 'LT', 'AXISBANK', 'BAJFINANCE',
                'MARUTI', 'ASIANPAINT', 'TITAN', 'ULTRACEMCO', 'SUNPHARMA', 'WIPRO',
                'TATAMOTORS', 'ADANIENT', 'ADANIPORTS', 'POWERGRID', 'NTPC', 'ONGC'
            ]

            for ticker, item in all_instruments.items():
                exchange = item.get('exchange', 'NSE') # Default to NSE if missing
                quantity = item.get('quantity')
                avg_price = item.get('avg_price')
                product = item.get('product')
                prev_close_price = item.get('prev_close_price') 

                ticker_yf = None
                clean_ticker = ticker.strip().upper()
                
                # --- SMART EXCHANGE LOGIC ---
                # 1. If explicitly NSE, use it.
                if exchange == 'NSE':
                    ticker_yf = f"{clean_ticker}.NS"
                
                # 2. If BSE, check if it's a major stock we should force to NSE
                elif exchange == 'BSE':
                    # FIX: Removed 'indices.nifty50_name_to_symbol' to prevent crash
                    if clean_ticker in MAJOR_STOCKS:
                        print(f"      [Warning] Converting {clean_ticker} (BSE) -> .NS (Preference)")
                        ticker_yf = f"{clean_ticker}.NS"
                    else:
                        ticker_yf = f"{clean_ticker}.BO"
                
                # 3. ETFs/Indices fallback
                if not ticker_yf and (clean_ticker.endswith('ETF') or clean_ticker.endswith('BEES') or 'INDX' in clean_ticker):
                    ticker_yf = f"{clean_ticker}.NS"
                
                # 4. Final Fallback: Default to NSE if still unknown
                if not ticker_yf:
                    ticker_yf = f"{clean_ticker}.NS"

                # Save to DB
                db.update_holding(user_id, ticker_yf, {
                    'quantity': quantity,
                    'avg_price': avg_price,
                    'product_type': product,
                    'prev_close_price': prev_close_price 
                })
                holdings_synced_count += 1

            # Update Meta
            current_port_value = calculate_current_portfolio_value(user_id, float(cash_balance))
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            db.create_or_update_user(user_id, {
                'day_start_portfolio_value': current_port_value,
                'last_day_pnl_reset': today_str,
                'net_cash_flow_today': 0.0,
                'zerodha_synced_once': True
            })

            print(f"    [Success] Synced {holdings_synced_count} holdings. Value: {currency_symbol}{current_port_value:,.2f}")
            return {"status": "success", "holdings_synced": holdings_synced_count, "cash": cash_balance, "new_portfolio_value": current_port_value}

        except Exception as db_err:
            print(f"[Error] DB Error during sync: {db_err}")
            raise db_err

    except Exception as e:
        print(f"[Error] Error during Zerodha sync logic: {traceback.format_exc()}")
        if "TokenException" in str(e):
            try: db.create_or_update_user(user_id, {'zerodha_synced_once': False})
            except: pass
            return {"error": "Zerodha token expired. Please sync again."}
        return {"error": f"Failed to sync portfolio: {str(e)}"}
    
# General Internet Search
def internet_search(query: str) -> dict:
    print(f"      → internet_search (DDGS) for: '{query}'")
    cache_key = f"ddgs_search_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.text(query, region='in-en', max_results=3)
        if not results: result = {"message": f"No DDGS search results for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "snippet": i.get('body'), "url": i.get('href')} for i in results]
            print(f"      [Success] Found {len(fmt_res)} DDGS search results.")
            result = {"results": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e: print(f"      [Error] DDGS Search Error: {traceback.format_exc()}"); return {"error": f"DDGS search error: {str(e)}"}

# Get Index Constituents
def get_index_constituents(index_name: str) -> dict:
    print(f"      → get_index_constituents for: '{index_name}'")
    cache_key = f"constituents_{index_name.strip().upper().replace(' ', '_')}"
    cached_result = get_cache(cache_key)
    if cached_result:
        print(f"      CACHE HIT for {cache_key}")
        return cached_result

    nse_error = None 

    index_symbol_map = {
        "NIFTY 200 MOMENTUM 30": "NIFTY200 MOMENTUM 30",

    }

    names_to_try = []
    normalized_input = index_name.strip().upper()
    if normalized_input in index_symbol_map:
        names_to_try.append(index_symbol_map[normalized_input])
    names_to_try.append(index_name)
    if index_name != normalized_input and normalized_input not in names_to_try:
        names_to_try.append(normalized_input) 

    print(f"      Attempting NSE API with potential names: {names_to_try}")
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
            print(f"      Querying NSE API with name: '{name_attempt}' ({url})")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status() 
            data = response.json()
            constituents = data.get("data", [])

            if constituents:
                ticker_list = [item.get("symbol") + ".NS" for item in constituents if item.get("symbol")]
                valid_tickers = [ticker for ticker in ticker_list if ticker is not None]
                if valid_tickers:
                    print(f"      [Success] Successfully extracted {len(valid_tickers)} tickers from NSE API using name '{name_attempt}'.")
                    result = {"index_name": index_name, "tickers": valid_tickers, "source": f"NSE API ('{name_attempt}')"}
                    set_cache(cache_key, result, ttl_seconds=3600) 
                    return result

            print(f"      [Warning] NSE API returned no data/constituents for name '{name_attempt}'.")
            if nse_error is None: nse_error = f"NSE API returned empty data for '{name_attempt}'."

        except requests.exceptions.HTTPError as http_err:
            nse_error = f"NSE API HTTP Error for '{name_attempt}': {http_err}"
            print(f"      [Error] {nse_error}")
            if http_err.response is not None and http_err.response.status_code == 404:
                continue
            else:
                break 
        except requests.exceptions.RequestException as req_err:
            nse_error = f"NSE API Network Error for '{name_attempt}': {req_err}"
            print(f"      [Error] {nse_error}"); break 
        except json.JSONDecodeError as json_err:
            nse_error = f"NSE API JSON Parse Error for '{name_attempt}': {json_err}. Response: {response.text[:200]}" 
            print(f"      [Error] {nse_error}"); break 
        except Exception as e:
            nse_error = f"Unexpected NSE API Error for '{name_attempt}': {e}"
            print(f"      [Error] {nse_error}\n{traceback.format_exc()}"); break 

    print(f"      [Warning] NSE API failed for all attempts ({nse_error or 'No constituents found'}). Falling back to DDGS + AI extraction...")
    try:
        query = f"{index_name} constituents tickers list NSE"
        print(f"      Searching DDGS for: '{query}'")
        search_snippets = []
        with DDGS() as ddgs:
            results = ddgs.text(query, region='in-en', max_results=7)
            if results: search_snippets = [str(r.get('body', '')) for r in results if r.get('body')]

        if not search_snippets:
            print("      [Error] DDGS fallback found no results.")
            final_error = f"NSE API failed and DDGS search found no results for '{index_name}'."
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600) 
            return {"error": final_error}

        print(f"      Found {len(search_snippets)} snippets via DDGS. Asking AI to extract tickers...")
        extraction_prompt = f"""
        Extract all valid NSE stock tickers (ending in .NS, typically uppercase letters, numbers, hyphens, ampersands before .NS) found within the following text snippets related to the '{index_name}' index.
        Output ONLY a Python-style list of these ticker strings.
        Example output for Nifty Bank: ['HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS']
        If no valid .NS tickers are found in the snippets, output an empty list: [].
        Do NOT include explanations, comments, code formatting (like ```python), or any text besides the list itself.

        Snippets:
        ---
        {json.dumps(search_snippets)}
        ---

        Output:
        """
        extraction_model = genai.GenerativeModel(model_name=config.GEMINI_MODEL_NAME)
        safety_settings=[{"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = extraction_model.generate_content(extraction_prompt, safety_settings=safety_settings)
                if not response.candidates:
                    finish_reason = getattr(response, 'prompt_feedback', 'Unknown')
                    raise Exception(f"AI response blocked or empty. Reason: {finish_reason}")
                extracted_text = response.text.strip()
                break 
            except Exception as ai_err:
                print(f"      [Warning] AI generation attempt {attempt + 1} failed: {ai_err}")
                if attempt == max_retries - 1:
                    raise 
                time.sleep(1) 

        print(f"      AI extraction raw response: {extracted_text}")

        if extracted_text.startswith("```python"): extracted_text = extracted_text[len("```python"):].strip()
        if extracted_text.startswith("```"): extracted_text = extracted_text[len("```"):].strip()
        if extracted_text.endswith("```"): extracted_text = extracted_text[:-len("```")].strip()

        
        looks_like_list = extracted_text.startswith('[') and extracted_text.endswith(']')

        valid_tickers = []
        parsing_error = None

        try:
            
            try:
                cleaned_text = extracted_text.replace("'", '"') if extracted_text else "[]"
                if not cleaned_text.strip(): cleaned_text = "[]"
                parsed_json = json.loads(cleaned_text)

                if isinstance(parsed_json, list):
                    valid_tickers = [t for t in parsed_json if isinstance(t, str) and t.endswith('.NS')]
                    if valid_tickers:
                        print(f"  Successfully extracted {len(valid_tickers)} tickers via DDGS + AI (JSON parse).")
                    else:
                        print(f" AI response parsed as JSON list, but contained no valid .NS tickers. Will try regex.")
                        
                else:  
                    print(f" AI response parsed as JSON, but was not a list ({type(parsed_json)}). Will try regex.")
                    

            except (json.JSONDecodeError, ValueError) as json_e:
                print(f" AI response wasn't valid JSON list ({json_e}). Trying regex extraction...")
                
                pass  
            
            if not valid_tickers:
                print(f"      Attempting regex extraction on AI response.")
                
                potential_tickers = re.findall(r"['\"]?([A-Z0-9\-&]+?\.NS)['\"]?", extracted_text, re.IGNORECASE)
            
                current_valid_regex = sorted(list(set(
                    t.upper() for t in potential_tickers if isinstance(t, str) and t.upper().endswith('.NS')
                )))

                if current_valid_regex:
                    valid_tickers = current_valid_regex 
                    print(f"      [Success] Successfully extracted {len(valid_tickers)} tickers via DDGS + AI (Regex parse).")
                else:
                    print(f"      [Warning] Regex could not find valid .NS tickers in AI response.")
                    if not looks_like_list:
                        parsing_error = ValueError("Could not meaningfully parse AI response using JSON or Regex.")

            if parsing_error:
                raise parsing_error 
            source_msg = "DDGS+AI"
            if not valid_tickers:
                source_msg = "DDGS+AI (No tickers found in snippets)"
                print(f"      [Success] AI processed snippets for '{index_name}' but found no valid .NS tickers. Returning empty list.")

            result = {"index_name": index_name, "tickers": valid_tickers, "source": source_msg}
            set_cache(cache_key, result, ttl_seconds=1800) 
            return result

        except Exception as e:
            final_error = f"Error processing AI response/DDGS fallback for '{index_name}': {e}"
            print(f"      [Error] {final_error}\n{traceback.format_exc()}")
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
            return {"error": final_error}

    except Exception as e:
        final_error = f"Unexpected Error during DDGS search or AI call setup for '{index_name}': {e}"
        print(f"      [Error] Unexpected Error in DDGS/AI setup: {traceback.format_exc()}")
        set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
        return {"error": final_error}

# Watchlist Management for Agents
def get_watchlist_for_agent(user_id: str) -> dict:
    """Retrieves all stocks from the user's watchlist with their current prices."""
    print(f"Agent calls get_watchlist for user {user_id}")
    if not db: return {"error": "DB unavailable"}
    try:
        wl_ref = db.collection(f'users/{user_id}/watchlist').stream()
        tickers = [doc.id for doc in wl_ref]
        if not tickers: 
            return {"message": "User's watchlist is empty."}
        
        watchlist_items = []
        prices = get_bulk_live_prices(tickers)
        
        for t in tickers:
            cp = prices.get(t)
            if cp is None: continue
            # We can re-use get_current_price to get the change %
            price_data = get_current_price(t)
            if price_data.get("error"): continue
            
            watchlist_items.append({
                "ticker": t,
                "company_name": price_data.get("company_name"),
                "current_price": price_data.get("current_price"),
                "change_percentage": price_data.get("change_percentage")
            })
        return {"watchlist": watchlist_items}
    except Exception as e:
        print(f"     [Error] Error in get_watchlist_for_agent: {traceback.format_exc()}")
        return {"error": str(e)}
    
# Bulk Live Prices
def get_bulk_live_prices(tickers: list) -> dict:
    if not tickers: return {}
    valid_tickers = [t for t in tickers if isinstance(t, str) and (t.endswith('.NS') or t.endswith('.BO'))]
    
    if not valid_tickers: print("      No valid tickers for bulk fetch."); return {}
    try:
        data = yf.download(valid_tickers, period='2d', progress=False, auto_adjust=True, ignore_tz=True)
        if data.empty or 'Close' not in data.columns: print("      [Warning] Bulk download empty/invalid."); raise ValueError("Empty bulk download")
        prices = {}
        close_data = data['Close'] if len(valid_tickers) > 1 else data[['Close']]
        last_valid_index = close_data.last_valid_index()
        if last_valid_index is None: raise ValueError("No valid close prices in bulk download.")
        last_prices = close_data.loc[last_valid_index]
        for ticker in valid_tickers:
            if len(valid_tickers) > 1:
                if ticker in last_prices.index and pd.notna(last_prices[ticker]): 
                    prices[ticker] = float(round(last_prices[ticker], config.PRICE_DECIMAL_PLACES))
                else:                   
                     print(f"      [Warning] Price not in bulk for {ticker}. Falling back.")
                     try: prices[ticker] = float(round(get_live_price(ticker), config.PRICE_DECIMAL_PLACES))
                     except ValueError: print(f"      [Error] Fallback failed for {ticker}")
            else: 
                if pd.notna(last_prices.iloc[0]):
                    prices[ticker] = float(round(last_prices.iloc[0], config.PRICE_DECIMAL_PLACES))
                else:
                     print(f"      [Warning] Single price not in bulk for {ticker}. Falling back.")
                     try: prices[ticker] = float(round(get_live_price(ticker), config.PRICE_DECIMAL_PLACES))
                     except ValueError: print(f"      [Error] Fallback failed for {ticker}")
        return prices
    except Exception as e:
        print(f"      [Error] Bulk fetch failed: {e}. Falling back individually with delay...")
        prices = {}
        time.sleep(1) 
        for t in valid_tickers:
            try: 
                price = get_live_price(t)
                prices[t] = float(round(price, config.PRICE_DECIMAL_PLACES))
                time.sleep(0.1) 
                
            except ValueError: 
                print(f"      [Error] Fallback failed for {t}")
                
        print(f"      [Success] Fallback fetch completed for {len(prices)} tickers.")
        return prices

# User Account Initialization and Portfolio Management
def initialize_user_account(user_id: str) -> dict:
    try:
        # Use the helper, not direct collection access
        account_data = db.get_user(user_id)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        if not account_data:
            print(f"[New] NEW USER: Initializing account for {user_id}")
            initial_data = {
                'cash': config.DEFAULT_STARTING_CASH, 
                'initial_cash': config.DEFAULT_STARTING_CASH, 
                'account_initialized': True,
                'zerodha_synced_once': False, 
                'created_at': db.get_timestamp(), 
                'day_start_portfolio_value': config.DEFAULT_STARTING_CASH,
                'last_day_pnl_reset': today_str, 
                'token_usage': {'input': 0, 'output': 0, 'total': 0},
                'net_cash_flow_today': 0.0 
            }
            # Use helper to save
            return db.create_or_update_user(user_id, initial_data)
        else:
            update_fields = {}
            if not account_data.get('account_initialized'): 
                update_fields['account_initialized'] = True
                update_fields['initial_cash'] = account_data.get('cash', config.DEFAULT_STARTING_CASH)
            
            if 'day_start_portfolio_value' not in account_data: update_fields['day_start_portfolio_value'] = account_data.get('cash', config.DEFAULT_STARTING_CASH)
            if 'last_day_pnl_reset' not in account_data: update_fields['last_day_pnl_reset'] = today_str
            if 'net_cash_flow_today' not in account_data: update_fields['net_cash_flow_today'] = 0.0
            if 'zerodha_synced_once' not in account_data: update_fields['zerodha_synced_once'] = False

            # PnL Reset Logic
            last_reset = account_data.get('last_day_pnl_reset', '')
            if last_reset != today_str:
                current_val = calculate_current_portfolio_value(user_id, account_data.get('cash', 0))
                update_fields['day_start_portfolio_value'] = current_val
                update_fields['last_day_pnl_reset'] = today_str
                update_fields['net_cash_flow_today'] = 0.0
            
            if update_fields:
                # Use helper to update
                account_data = db.create_or_update_user(user_id, update_fields)
            
            if 'token_usage' not in account_data:
                update_fields['token_usage'] = {'input': 0, 'output': 0, 'total': 0}
            
            if update_fields:
                # This saves the 0 count to the DB so update_user_tokens finds it later
                account_data = db.create_or_update_user(user_id, update_fields)
            
            return account_data
    except Exception as e: 
        print(f"[Error] Error initializing account {user_id}: {e}")
        raise

# Calculate Current Portfolio Value
def calculate_current_portfolio_value(user_id: str, current_cash: float) -> float:
    try:
        # Use helper
        holdings_data = db.get_portfolio_holdings(user_id)
        tickers = list(holdings_data.keys())
        total_val = 0
        
        if tickers:
            prices = get_bulk_live_prices(tickers)
            for t, h in holdings_data.items(): 
                total_val += h.get('quantity', 0) * prices.get(t, h.get('avg_price', 0))
        
        return current_cash + total_val
    except Exception as e: 
        print(f"[Warning] Error calc portfolio value {user_id}: {e}"); return current_cash

# Get User Portfolio
def get_portfolio(user_id: str) -> dict:
    if not db: raise Exception("Firestore unavailable.")
    try:
        # 1. Fetch User Data First
        acc_data = initialize_user_account(user_id)
        
        # 2. Extract Cash & Tokens safely
        cash = acc_data.get('cash', 0)
        synced_flag = acc_data.get('zerodha_synced_once', False)
        saved_tokens = acc_data.get('token_usage', {'input': 0, 'output': 0, 'total': 0})

        # 3. Fetch Holdings
        holdings_data = db.get_portfolio_holdings(user_id)
        tickers = list(holdings_data.keys())
        
        holdings = []; total_inv = 0; total_curr_h_val = 0; total_pnl = 0
        total_day_pnl = 0.0; total_prev_day_value = 0.0

        if tickers:
            prices = get_bulk_live_prices(tickers)
            infos = {}
            max_w = min(10, len(tickers) if len(tickers) > 0 else 1) 
            with ThreadPoolExecutor(max_workers=max_w) as executor:
                future_to_ticker = {executor.submit(get_ticker_info, t): t for t in tickers}
                for future in concurrent.futures.as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try: infos[ticker] = future.result()
                    except: infos[ticker] = None

            for t, h in holdings_data.items():
                q, avg_p = h.get('quantity', 0), h.get('avg_price', 0)
                cp = prices.get(t, avg_p) 
                
                inv_v, curr_v = q * avg_p, q * cp; pnl = curr_v - inv_v
                pnl_pct = (pnl / inv_v * 100) if inv_v != 0 else 0
                total_inv += inv_v; total_curr_h_val += curr_v; total_pnl += pnl
                
                price_info = infos.get(t) 
                company_name = price_info.get('shortName', t) if price_info else indices.COMPANY_NAMES.get(t, t)
                
                prev_close = h.get('prev_close_price') 
                if not prev_close or prev_close == 0:
                    prev_close = price_info.get('previousClose', cp) if price_info else cp
                
                approx_day_pnl = (cp - prev_close) * q
                prev_day_value = prev_close * q
                approx_day_pnl_pct = (approx_day_pnl / prev_day_value * 100) if prev_day_value and prev_day_value != 0 else 0
              
                total_day_pnl += approx_day_pnl
                total_prev_day_value += prev_day_value
                
                holdings.append({
                    "ticker": t, "company_name": company_name, "quantity": q, 
                    "avg_price": round(avg_p, config.PRICE_DECIMAL_PLACES),
                    "current_price": round(cp, config.PRICE_DECIMAL_PLACES),  
                    "invested_value": round(inv_v, config.PNL_DECIMAL_PLACES),
                    "current_value": round(curr_v, config.PNL_DECIMAL_PLACES),
                    "pnl": round(pnl, config.PNL_DECIMAL_PLACES),
                    "pnl_percent": round(pnl_pct, 2),  
                    "approx_day_pnl": round(approx_day_pnl, config.PNL_DECIMAL_PLACES),
                    "approx_day_pnl_pct": round(approx_day_pnl_pct, 2)
                })
        
        day_pnl_pct = (total_day_pnl / total_prev_day_value * 100) if total_prev_day_value != 0 else 0
        
        summary = {
            "portfolio_value": round(cash + total_curr_h_val, config.PNL_DECIMAL_PLACES),
            "total_invested": round(total_inv, config.PNL_DECIMAL_PLACES),
            "total_holdings_value": round(total_curr_h_val, config.PNL_DECIMAL_PLACES), 
            "total_pnl": round(total_pnl, config.PNL_DECIMAL_PLACES),
            "total_pnl_percent": round((total_pnl / total_inv * 100) if total_inv != 0 else 0, 2),
            "day_pnl": round(total_day_pnl, config.PNL_DECIMAL_PLACES), 
            "day_pnl_percent": round(day_pnl_pct, 2),
            "zerodha_synced_once": synced_flag,
            "token_usage": saved_tokens  # <--- No error now, variable is defined at top
        }
        return {"cash": round(cash, 2), "holdings": holdings, "summary": summary} 
    except Exception as e: 
        print(f"[Error] Error getting portfolio {user_id}: {traceback.format_exc()}")
        raise

# Trade Execution
def execute_trade(user_id: str, ticker: str, quantity: int, action: str):
    """
    Executes a virtual buy or sell trade for a user.

    Args:
        user_id (str): User identifier.
        ticker (str): Stock ticker symbol.
        quantity (int): Number of shares.
        action (str): 'BUY' or 'SELL'.

    Returns:
        dict: Trade result details or error message.
    """
    # FIX: Cast quantity
    try: quantity = int(float(quantity))
    except: return {"error": True, "message": f"Invalid quantity: {quantity}"}
    if quantity <= 0: return {"error": True, "message": "Quantity must be positive."}

    norm_ticker = normalize_ticker(ticker)
    if not norm_ticker: return {"error": True, "message": f"Invalid ticker: {ticker}"}
    
    print(f"[Trade] TRADE: User={user_id}, Action={action.upper()}, Qty={quantity}, Ticker={norm_ticker}")
    
    try: 
        # Force live fetch for trade execution
        stock = yf.Ticker(norm_ticker)
        hist = stock.history(period="1d")
        if hist.empty: raise ValueError("Price data unavailable")
        cp = float(hist['Close'].iloc[-1])
    except Exception as e: 
        return {"error": True, "message": f"Price fetch failed: {str(e)}"}

    trade_val = cp * quantity

    try:
        # 1. Get User Data
        user_data = db.get_user(user_id)
        if not user_data: return {"error": True, "message": "User not found"}
        
        cash = user_data.get('cash', 0)
        
        # 2. Get Current Holding
        holdings = db.get_portfolio_holdings(user_id)
        current_holding = holdings.get(norm_ticker, {})
        current_qty = current_holding.get('quantity', 0)
        current_avg = current_holding.get('avg_price', 0)

        act = action.upper()
        new_cash = cash

        if act == 'BUY':
            if cash < trade_val: 
                raise ValueError(f"Insufficient funds. Have ₹{cash:,.2f}, Need ₹{trade_val:,.2f}")
            
            new_cash = cash - trade_val
            new_qty = current_qty + quantity
            new_avg = ((current_qty * current_avg) + trade_val) / new_qty
            
            # Update DB
            db.update_user_cash(user_id, new_cash)
            db.update_holding(user_id, norm_ticker, {'quantity': new_qty, 'avg_price': new_avg, 'company_name': norm_ticker})

        elif act == 'SELL':
            if current_qty < quantity: 
                raise ValueError(f"Insufficient shares. Have {current_qty}")
            
            new_cash = cash + trade_val
            new_qty = current_qty - quantity
            
            # Update DB
            db.update_user_cash(user_id, new_cash)
            if new_qty > 0:
                db.update_holding(user_id, norm_ticker, {'quantity': new_qty}) # Keep existing avg
            else:
                db.delete_holding(user_id, norm_ticker)

        # 3. Log History
        db.add_history_entry(user_id, {
            'action': act, 'ticker': norm_ticker, 'quantity': quantity, 
            'price': cp, 'total_value': trade_val
        })
        
        return {"success": True, "action": act, "ticker": norm_ticker, "quantity": quantity, "price": cp, "total_value": trade_val, "new_cash": new_cash}

    except ValueError as ve:
        return {"error": True, "message": str(ve)}
    except Exception as e:
        print(f"Trade Error: {traceback.format_exc()}")
        return {"error": True, "message": f"Transaction failed: {str(e)}"}

# Watchlist Add Logic
def add_to_watchlist(user_id: str, tickers: List[str]) -> dict:
    if not isinstance(tickers, list): return {"error": "Input must be a list."}
    
    added = []
    invalid = []
    
    for t in tickers[:20]:
        norm = normalize_ticker(t)
        if norm and get_ticker_info(norm):
            db.add_to_watchlist(user_id, norm)
            added.append(norm)
        else:
            invalid.append(t)
            
    return {"status": "success", "added": added, "invalid": invalid}

# Watchlist Remove Logic
def remove_from_watchlist(user_id: str, ticker: str) -> dict:
    norm = normalize_ticker(ticker) or ticker.upper()
    success = db.remove_from_watchlist(user_id, norm)
    if success:
        return {"status": "success", "removed_ticker": norm}
    return {"error": "Ticker not found in watchlist"}
    
# --- Flask App Setup & API Endpoints ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_development_secret_key')
app.config['SESSION_TYPE'] = 'filesystem' 
Session(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})

#--- Web Routes ---
@app.route('/')
def index(): return render_template('index.html')

# --- API Endpoints ---
@app.route('/api/portfolio/<user_id>', methods=['GET'])
@auth_required
def get_portfolio_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try: return jsonify(get_portfolio(user_id))
    except Exception as e: print(f"[Error] API Error /portfolio/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

# Trade History Endpoint
@app.route('/api/history/<user_id>', methods=['GET'])
@auth_required
def get_trade_history_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        # FIX: Use helper method instead of db.collection(...)
        history_data = db.get_history(user_id, limit=config.TRADE_HISTORY_LIMIT)
        
        # Format timestamps if they aren't already strings
        formatted_history = []
        for item in history_data:
            if 'timestamp' in item and hasattr(item['timestamp'], 'isoformat'):
                item['timestamp'] = item['timestamp'].isoformat()
            formatted_history.append(item)
            
        return jsonify(formatted_history)
    except Exception as e: 
        print(f"[Error] API Error /history/{user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500
    
# Adjust Cash Endpoint
@app.route('/api/adjust-cash/<user_id>', methods=['POST'])
@auth_required
def adjust_cash_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        if data is None: return jsonify({"error": "Invalid JSON body."}), 400
        
        new_cash = data.get('cash')
        # Validation
        if not isinstance(new_cash, (int, float)) or not (0 <= new_cash <= config.MAX_ADJUST_CASH):
            return jsonify({"error": f"Invalid cash (0-{config.MAX_ADJUST_CASH:,.0f})."}), 400
            
        # 1. Calculate the difference (Optional, for P&L tracking)
        # We get current user state first
        user_data = db.get_user(user_id)
        if not user_data:
            return jsonify({"error": "User not found"}), 404
            
        # 2. Perform the Update via Helper
        # This works for BOTH Firebase and Local mode
        db.update_user_cash(user_id, float(new_cash))
        
        print(f"[Cash] Cash adjusted for {user_id} to {currency_symbol}{float(new_cash):,.2f}")
        
        return jsonify({"success": True, "new_cash": round(float(new_cash), config.PRICE_DECIMAL_PLACES)})

    except Exception as e:
        print(f"[Error] Adjust Cash Error {user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Trade Execution Endpoint
@app.route('/api/trade/<user_id>', methods=['POST'])
@auth_required
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
        print(f"[Error] API Error /trade/{user_id} PRE-EXECUTION: {traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# Stock Price Endpoint
@app.route('/api/stock/price/<ticker>')
def get_stock_price_endpoint(ticker):
    try: 
        price_data = get_current_price(ticker)
        if price_data.get("error"):
            return jsonify(price_data), 404
        return jsonify(price_data)
    except ValueError as ve: return jsonify({"error": str(ve)}), 404
    except Exception as e: print(f"[Error] API Error /stock/price/{ticker}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

# Watchlist Endpoints
@app.route('/api/watchlist/<user_id>', methods=['GET'])
@auth_required
def get_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        # FIX: Use helper method instead of db.collection(...)
        tickers = db.get_watchlist(user_id)
        
        if not tickers: return jsonify([])
        
        details = []
        # Bulk fetch prices (Optimized)
        prices = get_bulk_live_prices(tickers)
        
        infos = {}
        max_w = min(10, len(tickers) if len(tickers) > 0 else 1)  
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_ticker = {executor.submit(get_ticker_info, t): t for t in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    infos[ticker] = future.result()
                except Exception as e:
                    print(f"      [Warning] Parallel watchlist fetch error for {ticker}: {e}")
                    infos[ticker] = None

        for t in tickers:
            cp = prices.get(t)
            info = infos.get(t)
            
            if cp is None or info is None:  
                print(f"      [Warning] Missing watchlist data {t}.")
                details.append({"ticker": t, "price": "N/A", "change": "N/A", "dayRange": "N/A"})
                continue
            try:
                pc = info.get('previousClose', cp)
                # Handle division by zero if previous close is 0
                change = ((cp - pc) / pc) * 100 if pc and pc != 0 else 0
                dl, dh = info.get('dayLow', cp), info.get('dayHigh', cp)
                
                item = {
                    "ticker": t, 
                    "price": round(cp, config.PRICE_DECIMAL_PLACES), 
                    "change": round(change, 2),
                    "dayRange": f"₹{dl:.{config.PRICE_DECIMAL_PLACES}f} - ₹{dh:.{config.PRICE_DECIMAL_PLACES}f}" if dl and dh else "N/A"
                }
                details.append(item)
            except Exception as e:  
                print(f"      [Error] Error processing watchlist {t}: {e}")
                details.append({"ticker": t, "price": "Error", "change": "Error", "dayRange": "Error"})
                
        return jsonify(details)
    except Exception as e:  
        print(f"\n[Error] CRITICAL WATCHLIST GET ERROR {user_id}: {traceback.format_exc()}\n")
        return jsonify({"error": str(e)}), 500
    
#watchlist Add Endpoint
@app.route('/api/watchlist/<user_id>', methods=['POST'])
@auth_required
def add_to_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if not data or 'tickers' not in data or not isinstance(data['tickers'], list): return jsonify({"error": "Invalid request: JSON with 'tickers' list needed."}), 400
        result = add_to_watchlist(user_id, data['tickers'])
        return jsonify(result), 400 if "error" in result else 200
    except Exception as e: print(f"[Error] API Error POST /watchlist/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500


#Watchlist Remove Endpoint
@app.route('/api/watchlist/<user_id>/<ticker>', methods=['DELETE'])
@auth_required
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
        print(f"[Error] API Error DELETE /watchlist/{user_id}/{ticker}: {traceback.format_exc()}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

# Zerodha Integration Endpoints
@app.route('/api/zerodha/connect/<user_id>', methods=['GET'])
def zerodha_connect(user_id):
    try:
        session['zerodha_auth_user_id'] = user_id
        
        kite = KiteConnect(api_key=config.ZERODHA_API_KEY)
        login_url = kite.login_url()
        
        print(f"Redirecting user {user_id} to Zerodha login: {login_url}")
        return redirect(login_url)
    except Exception as e:
        print(f"[Error] Error generating Zerodha login URL: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Could not initiate Zerodha connection: {str(e)}"}), 500

@app.route('/api/config', methods=['GET'])
def get_frontend_config():
    return jsonify({
        "firebaseConfig": config.FIREBASE_CONFIG,
        "apiBaseUrl": config.API_BASE_URL,
        "dbMode": config.DB_MODE # Send mode to frontend
    })
    
@app.route('/api/zerodha/callback', methods=['GET'])
def zerodha_callback():
    if not db: return "Error: Database not available.", 503
    
    request_token = request.args.get('request_token')
    user_id = session.get('zerodha_auth_user_id')

    if not request_token:
        return "Error: No request_token provided.", 400
    if not user_id:
        return "Error: User session expired. Please close this window and try again.", 400

    print(f"Received Zerodha callback for user {user_id}")
    
    try:
        kite = get_kite_instance()
        data = kite.generate_session(request_token, api_secret=config.ZERODHA_API_SECRET)
        access_token = data['access_token']
        db.create_or_update_user(user_id, {
            'zerodha_access_token': access_token,
            'zerodha_synced_at': db.get_timestamp()
        })
        print(f"[Success] Access Token saved for {user_id}")
        sync_result = sync_zerodha_portfolio(user_id, access_token)
        
        status_msg = "Sync Successful!"
        if "error" in sync_result:
            status_msg = f"Token saved, but sync failed: {sync_result['error']}"

        return f"""
        <html>
        <head><title>Connected</title></head>
        <body style="background-color: #0f172a; color: #10b981; font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div style="text-align: center;">
                <svg style="width: 64px; height: 64px; margin: 0 auto 20px;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                <h1 style="margin: 0; font-size: 24px;">{status_msg}</h1>
                <p style="color: #94a3b8;">Closing window...</p>
            </div>
            <script>
                // 1. Send success message to the main window (the "Opener")
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'ZERODHA_SUCCESS', userId: '{user_id}' }}, '*');
                }}
                // 2. Close this popup after 1.5 seconds
                setTimeout(() => window.close(), 1500);
            </script>
        </body>
        </html>
        """

    except Exception as e:
        print(f"[Error] Zerodha Callback Error: {traceback.format_exc()}")
        return f"Error: {str(e)}", 500
    finally:
        if 'zerodha_auth_user_id' in session:
            session.pop('zerodha_auth_user_id')

@app.route('/api/stock/analysis/<user_id>/<ticker>', methods=['GET'])
@auth_required
def get_stock_analysis(user_id, ticker):
    timeframe = request.args.get('timeframe', '1D').lower()
    indicators_str = request.args.get('indicators', 'rsi,ema,volume')
    indicators = [ind.strip().lower() for ind in indicators_str.split(',') if ind.strip()]

    try:
        # 1. Get the ROBUST, CACHED fundamental data first.
        analysis_data = get_fundamental_data(ticker)
        
        if analysis_data.get("error"):
            return jsonify(analysis_data), 404
            
        norm_ticker = analysis_data['ticker'] 
        
        # 2. RE-CALCULATE the technical rating based on the SELECTED timeframe
        analysis_data['technicalRating'] = get_technical_rating(norm_ticker, timeframe)
        
        # 3. Map timeframe to yfinance history parameters (FIXED)
        timeframe_map = {
            '1m': {'period': '7d', 'interval': '1m'},
            '5m': {'period': '60d', 'interval': '5m'},
            '15m': {'period': '60d', 'interval': '15m'},
            '30m': {'period': '60d', 'interval': '30m'},
            '1h': {'period': '730d', 'interval': '1h'},
            '4h': {'period': '730d', 'interval': '1h'}, 
            '1d': {'period': '1y', 'interval': '1d'},
            '1w': {'period': '2y', 'interval': '1wk'},
            '1mo': {'period': '5y', 'interval': '1mo'},
            # --- FIXED ENTRIES ---
            '3m': {'period': '6mo', 'interval': '1d'},  # Fetch 6 months of daily data
            '6m': {'period': '1y', 'interval': '1d'},   # Fetch 1 year of daily data
            '1y': {'period': '2y', 'interval': '1d'}    # Fetch 2 years of daily data
        }
        params = timeframe_map.get(timeframe, timeframe_map['1d'])
        
        # 4. Get Ticker and History
        stock = yf.Ticker(norm_ticker)
        hist = stock.history(period=params['period'], interval=params['interval'])
        
        indicator_values = {}
        
        # 5. Check history and calculate all requested indicators
        if hist.empty or 'Close' not in hist.columns:
            print(f"No historical data for {norm_ticker} with params {params}")
            for ind in indicators: indicator_values[ind] = 'N/A'
        
        else:
            close_prices = hist['Close'].dropna()
            
            if len(close_prices) < 55: 
                 print(f"Not enough data for indicators {norm_ticker} (need 55, got {len(close_prices)})")
                 for ind in indicators: indicator_values[ind] = 'N/A'
            else:
                # --- Start Safe Calculation ---
                try:
                    if 'rsi' in indicators:
                        from ta.momentum import RSIIndicator
                        val = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                        indicator_values['rsi'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'ema' in indicators:
                        from ta.trend import EMAIndicator
                        val = EMAIndicator(close_prices, window=20).ema_indicator().iloc[-1]
                        indicator_values['ema'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'sma' in indicators:
                        from ta.trend import SMAIndicator
                        val = SMAIndicator(close_prices, window=50).sma_indicator().iloc[-1]
                        indicator_values['sma'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'macd' in indicators:
                        from ta.trend import MACD
                        val = MACD(close_prices).macd().iloc[-1]
                        indicator_values['macd'] = round(val, 2) if pd.notna(val) else 'N/A'
                        
                    if 'volume' in indicators and 'Volume' in hist.columns:
                        val = hist['Volume'].iloc[-1]
                        indicator_values['volume'] = int(val) if pd.notna(val) else 'N/A'
                    elif 'volume' in indicators:
                        indicator_values['volume'] = 'N/A'
                        
                    if 'bollinger' in indicators:
                        from ta.volatility import BollingerBands
                        bb = BollingerBands(close_prices)
                        lower = bb.bollinger_lband().iloc[-1]
                        upper = bb.bollinger_hband().iloc[-1]
                        indicator_values['bollinger'] = f"₹{lower:.2f}-₹{upper:.2f}" if pd.notna(lower) and pd.notna(upper) else 'N/A'

                    if 'adx' in indicators:
                        from ta.trend import ADXIndicator
                        adx_val = ADXIndicator(hist['High'], hist['Low'], close_prices, window=14).adx().iloc[-1]
                        indicator_values['adx'] = round(adx_val, 2) if pd.notna(adx_val) else 'N/A'
                        
                    if 'stochastic' in indicators:
                        from ta.momentum import StochasticOscillator
                        stoch_val = StochasticOscillator(hist['High'], hist['Low'], close_prices).stoch().iloc[-1]
                        indicator_values['stochastic'] = round(stoch_val, 2) if pd.notna(stoch_val) else 'N/A'

                except Exception as ind_error:
                    print(f"Indicator calculation error for {norm_ticker}: {ind_error}")
                    for ind in indicators:
                        if ind not in indicator_values:
                            indicator_values[ind] = 'N/A'
        
        # 6. Add the calculated indicators to the main analysis object
        analysis_data['indicators'] = indicator_values
        
        # 7. Return the combined, robust data
        return jsonify(analysis_data)
        
    except Exception as e:
        print(f"Error in get_stock_analysis: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# Chat Endpoints
@app.route('/api/chats/<user_id>')
@auth_required
def get_chat_list_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        # FIX: Use the helper method instead of db.collection()
        chat_list = db.get_chats(user_id)
        return jsonify(chat_list)
    except Exception as e: 
        print(f"[Error] API Error /chats/{user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Chat Messages Endpoint
@app.route('/api/chat/<user_id>/<chat_id>')
@auth_required
def get_chat_messages_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        msgs = db.get_chat_messages(user_id, chat_id)
        return jsonify(msgs)
    except Exception as e: 
        print(f"[Error] API Error /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Delete Chat Endpoint
@app.route('/api/chat/<user_id>/<chat_id>', methods=['DELETE'])
@auth_required
def delete_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        # FIX: Use helper
        db.delete_chat(user_id, chat_id)
        print(f"[Deleted] Deleted chat {chat_id} for {user_id}")
        return jsonify({"success": True, "message": f"Chat {chat_id} deleted."})
    except Exception as e: 
        print(f"[Error] API Error DELETE /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stock/fundamentals/<ticker>')
def get_stock_fundamentals_endpoint(ticker):
    """Public endpoint to get fundamental data for a stock."""
    try: 
        funda_data = get_fundamental_data(ticker)
        if funda_data.get("error"):
            return jsonify(funda_data), 404
        return jsonify(funda_data)
    except ValueError as ve: 
        return jsonify({"error": str(ve)}), 404
    except Exception as e: 
        print(f"❌ API Error /stock/fundamentals/{ticker}: {traceback.format_exc()}"); 
        return jsonify({"error": str(e)}), 500
    
# Rename Chat Endpoint
@app.route('/api/chat/<user_id>/<chat_id>', methods=['PUT'])
@auth_required
def rename_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        if not data or 'title' not in data: return jsonify({"error": "Missing 'title'."}), 400
        nt = data['title'].strip()
        
        # FIX: Use helper
        db.rename_chat(user_id, chat_id, nt)
        
        print(f"✏️ Renamed chat {chat_id} for {user_id} to '{nt}'")
        return jsonify({"success": True, "message": "Chat renamed."})
    except Exception as e: 
        print(f"❌ API Error PUT /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# --- Main Chat Handler (using Gemini) ---
@app.route('/api/chat', methods=['POST'])
def chat_handler():
    if not db: return jsonify({"error": "Database not configured"}), 503
    
    try:
        data = request.get_json()
        user_id, user_message, chat_id = data.get('userId'), data.get('message'), data.get('chatId')

        # --- AUTHENTICATION (Keep your existing auth logic) ---
        if not config.DEBUG_MODE:
            auth_header = request.headers.get('Authorization')
            if not auth_header: return jsonify({"error": "No Auth Header"}), 401
            id_token = auth_header.split('Bearer ')[-1]
            if config.DB_MODE == 'LOCAL':
                if id_token != user_id: pass 
            else:
                try:
                    auth.verify_id_token(id_token) # Simplified check
                except: return jsonify({"error": "Auth Failed"}), 401
        
        if not user_message.strip(): return jsonify({"error": "Empty message"}), 400

        # --- DB SAVE (User Message) ---
        try:
            if not chat_id:
                title = user_message[:config.CHAT_TITLE_LENGTH] + "..."
                chat_id = db.create_chat(user_id, title, user_message, first_msg_role='user')
            else:
                db.add_message(user_id, chat_id, 'user', user_message)
        except: return jsonify({"error": "Database error"}), 500

        # ============================================
        # AGENT TOOLS (With Optimized Descriptions)
        # ============================================
        
        def execute_trade_for_agent(ticker: str, quantity: int, action: str) -> dict:
            """Execute a paper trade. Action must be 'BUY' or 'SELL'."""
            return execute_trade(user_id, ticker, quantity, action)
        
        def get_portfolio_for_agent() -> dict:
            """Get current holdings, cash balance, and total P&L."""
            try: return get_portfolio(user_id)
            except Exception as e: return {"error": str(e)}
            
        def manage_watchlist_for_agent(ticker: str, action: str) -> dict:
            """Add or remove stocks from watchlist. Action: 'ADD' or 'REMOVE'."""
            if action.upper() == 'ADD': return add_to_watchlist(user_id, [ticker])
            elif action.upper() == 'REMOVE': return remove_from_watchlist(user_id, ticker)
            return {"error": "Invalid action"}
            
        def get_watchlist_for_agent_wrapper() -> dict:
            """Retrieve the user's current watchlist with live prices."""
            return get_watchlist_for_agent(user_id)

        def sync_zerodha_portfolio_for_agent() -> dict:
            """Import/Sync real holdings from Zerodha to update paper portfolio."""
            if not db: return {"error": "DB unavailable"}
            try:
                user_doc = db.get_user(user_id)
                if not user_doc or not user_doc.get('zerodha_access_token'):
                    return {"error": "Zerodha not connected", "connect_url": f"/api/zerodha/connect/{user_id}"}
                return sync_zerodha_portfolio(user_id, user_doc.get('zerodha_access_token'))
            except Exception as e: return {"error": str(e)}

        # --- MARKET DATA ---
        def get_index_constituents_for_agent(index_name: str) -> dict:
            """Get list of all stock tickers inside a specific market index (e.g. NIFTY 50)."""
            return get_index_constituents(index_name)
            
        def fetch_news_for_agent(query: str) -> dict:
            """Search for recent news articles about a specific stock or topic."""
            result = internet_search_news(query)
            if "error" not in result and result.get('articles'): return result
            return get_stock_news(query)
            
        def get_stock_chart_details_for_agent(ticker: str, period: str = "1y") -> dict:
            """Get chart link, support/resistance levels, and 52-week range for a stock."""
            return get_stock_chart_details(ticker, period)
            
        def internet_search_for_agent(query: str) -> dict:
            """General web search for real-time market info or specific queries."""
            try: return internet_search(query)
            except Exception as e: return {"error": str(e)}

        # --- ADVANCED SIMULATION ---
        def simulate_investment_for_agent(ticker: str, amount: float, years: int, mode: str = 'lumpsum') -> dict:
            """Backtest a SINGLE stock investment (SIP or Lumpsum) over a past duration."""
            return simulate_investment(ticker, amount, years, mode)

        def project_portfolio_performance_for_agent(direction: str, duration_months: int = 12) -> dict:
            """Forecast future portfolio value (Analyst Targets) OR backtest current allocation history."""
            return project_portfolio_performance(user_id, direction, duration_months)

        chat_history = [{'role': 'user', 'parts': [{'text': config.SYSTEM_INSTRUCTION}]}]
        try:
            raw_msgs = db.get_chat_messages(user_id, chat_id)
            recent = raw_msgs[-16:-1] if raw_msgs else []
            for m in recent:
                chat_history.append({'role': 'user' if m['role'] == 'user' else 'model', 'parts': [{'text': m['text']}]})
        except: pass

        # --- CALL AI ---
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL_NAME,
            tools=[
                screen_static_index, screen_custom_stock_list, get_index_constituents_for_agent,
                get_current_price, execute_trade_for_agent, get_portfolio_for_agent,
                get_fundamental_data, manage_watchlist_for_agent, fetch_news_for_agent,
                internet_search_for_agent, find_intraday_trade_setups, get_index_data_for_agent,
                sync_zerodha_portfolio_for_agent, get_watchlist_for_agent_wrapper,simulate_investment_for_agent,project_portfolio_performance_for_agent,get_stock_chart_details_for_agent
            ]
        )
        
        chat_session = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
        response = chat_session.send_message(user_message)
        
        # --- EXTRACT METADATA ---
        input_tokens = output_tokens = total_tokens = 0
        if hasattr(response, 'usage_metadata'):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            total_tokens = response.usage_metadata.total_token_count

        tools_used = []
        try:
            # Check final response for tool calls
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tools_used.append(part.function_call.name)
            # Check intermediate history for tool calls (reasoning steps)
            for msg in chat_session.history:
                if hasattr(msg, 'parts'):
                    for p in msg.parts:
                        if hasattr(p, 'function_call') and p.function_call:
                            tools_used.append(p.function_call.name)
            tools_used = list(set(tools_used))
        except: pass

        agent_reply = ""
        if response.candidates and response.candidates[0].content.parts:
            agent_reply = "".join(p.text for p in response.candidates[0].content.parts if p.text)
        
        if not agent_reply: agent_reply = "I processed your request."

        db.add_message(user_id, chat_id, 'model', agent_reply)
        db.update_user_tokens(user_id, input_tokens, output_tokens)

        # ======================================================
        # CLEAN TERMINAL OUTPUT
        # ======================================================
        print("\n" + "━"*60)
        print(f"AGENT INTERACTION REPORT ({config.DB_MODE})")
        print("━"*60)
        print(f" USER INPUT:\n   \"{user_message[:100]}{'...' if len(user_message)>100 else ''}\"\n")
        
        if tools_used:
            print(f"TOOLS USED:")
            for t in tools_used:
                print(f"   • {t}")
        else:
            print("TOOLS USED: None (Direct Response)")

        print(f"\nTOKEN USAGE:")
        print(f"   Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens}")
        
        print(f"\nAGENT REPLY (Snippet):")
        clean_reply = agent_reply.replace('\n', ' ').replace('*', '')
        print(f"   \"{clean_reply[:150]}...\"")
        print("━"*60 + "\n")
        # ======================================================

        return jsonify({
            "reply": agent_reply,
            "chatId": chat_id,
            "toolsUsed": tools_used,
            "tokenUsage": {
                "inputTokens": input_tokens, 
                "outputTokens": output_tokens, 
                "totalTokens": total_tokens
            }
        })

    except Exception as e:
        print("\n" + "!"*60)
        print(f"CRITICAL ERROR:")
        print(f"   {str(e)}")            
        print("-" * 60)          
        print("!"*60 + "\n")
        return jsonify({"error": "Server Error"}), 500
    
# ============================================
# Main Execution Block
# ============================================
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    print(f"Server starting on http://127.0.0.1:{port}")    
    app.run(debug=False, host='0.0.0.0', port=port)