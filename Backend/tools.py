import os
import config
import re
import time
from datetime import date, timedelta, datetime
import google.generativeai as genai
import yfinance as yf
import requests
import json
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from ddgs import DDGS
from kiteconnect import KiteConnect
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD, SMAIndicator, ADXIndicator
from ta.volatility import BollingerBands
import pandas as pd
import traceback
from typing import Optional, List
import indices
import db_helper
import logging

# Initialize DB Manager
db = db_helper.DBManager()

# Initialize Gemini
genai.configure(api_key=config.GENIE_API_KEY)

# Simple in-memory cache
_cache = {}
CACHE_TTL_SECONDS = config.CACHE_TTL_SECONDS

# Cache setter and getter
def set_cache(key, value, ttl_seconds=CACHE_TTL_SECONDS):
    if not config.CACHE_STORE:
        return
    _cache[key] = (value, time.time() + ttl_seconds)
    pass

def get_cache(key):
    if not config.CACHE_STORE:
        return None
    if key in _cache:
        value, expiry_time = _cache[key]
        if time.time() < expiry_time:
            # print(f"      CACHE HIT for {key}")
            return value
        else:
            del _cache[key]
    return None

# Initialize Zerodha Kite Connect
def get_kite_instance():
   return KiteConnect(api_key=config.ZERODHA_API_KEY)

# Ticker Normalization
def normalize_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    
    ticker = ticker.strip().upper()
    
    # If already has exchange suffix, return as-is
    if ticker.endswith('.NS') or ticker.endswith('.BO'):
        # print(f"      Ticker {ticker} already has exchange suffix")
        return ticker
    
    # Check Nifty 50 mapping
    if ticker in indices.NAME_TO_SYMBOL:
        normalized = indices.NAME_TO_SYMBOL[ticker]
        # print(f"      Mapped {ticker} -> {normalized} via N50")
        return normalized
    if not any(ticker.endswith(suffix) for suffix in ['.US', '.L', '.TO', '.AX']):
        normalized = f"{ticker}.NS"
        # print(f"      Assumed Indian stock: {ticker} -> {normalized}")
        return normalized
    
    # print(f"      Could not normalize '{ticker}' via N50 maps. Assuming direct ticker.")
    return ticker

# Investment Simulation
def simulate_investment(ticker: str, amount: float, duration_years: int, mode: str = 'lumpsum'):
    """
    Simulates an investment in a stock over a past duration.
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

# Project Portfolio Performance
def project_portfolio_performance(user_id: str, direction: str = 'future', duration_months: int = 12):
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
        if direction == 'future':
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
                    
                    target = info.get('targetMeanPrice')
                    if not target: target = cp 
                    
                    if duration_months != 12:
                        yearly_diff = target - cp
                        scaled_diff = yearly_diff * (duration_months / 12)
                        final_price = cp + scaled_diff
                    else:
                        final_price = target
                        
                    projected_val = qty * final_price
                    projected_value += projected_val
                    
                    pct_change = ((final_price - cp) / cp) * 100
                    if abs(pct_change) > abs(top_mover['change']):
                        top_mover = {"ticker": t, "change": pct_change}

        else:
            # Backtest
            end_date = date.today()
            start_date = end_date - timedelta(days=int(duration_months * 30))
            data = yf.download(tickers, start=start_date, end=end_date, progress=False)['Close']
            
            if data.empty: return {"error": "Historical data unavailable"}

            for t in tickers:
                qty = holdings[t]['quantity']
                if len(tickers) > 1:
                    if t not in data.columns: continue
                    hist_series = data[t].dropna()
                else:
                    hist_series = data.dropna()
                
                if hist_series.empty: continue
                
                price_then = float(hist_series.iloc[0])
                price_now = float(hist_series.iloc[-1])
                
                val_then = qty * price_then
                val_now = qty * price_now
                
                total_current_value += val_now 
                projected_value += val_then 
                
                pct_change = ((price_now - price_then) / price_then) * 100
                if abs(pct_change) > abs(top_mover['change']):
                    top_mover = {"ticker": t, "change": pct_change}

        # 3. Final Calculations
        if direction == 'past':
            diff = total_current_value - projected_value
            pct = (diff / projected_value * 100) if projected_value > 0 else 0
            base_label = f"Value {duration_months} months ago"
            final_label = "Current Value"
            val_start = projected_value
            val_end = total_current_value
        else:
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

def format_market_cap(market_cap):
    if not market_cap or market_cap == 0:
        return 'N/A'
    
    try:
        market_cap = float(market_cap)
        if market_cap >= 1_000_000_000_000:
            return f"₹{market_cap / 1_000_000_000_000:.2f}T"
        elif market_cap >= 1_000_000_000:
            return f"₹{market_cap / 10_000_000_000:.2f}L Cr"
        elif market_cap >= 10_000_000:
            return f"₹{market_cap / 10_000_000:.2f} Cr"
        elif market_cap >= 100_000:
            return f"₹{market_cap / 100_000:.2f}L"
        else:
            return f"₹{market_cap:,.0f}"
    except (ValueError, TypeError):
        return 'N/A'

def _get_compact_ticker_info(ticker_str: str) -> Optional[dict]:
    try:
        stock = yf.Ticker(ticker_str)
        info = stock.info
        
        if not info or not info.get('symbol'):
            # print(f"    _get_compact_ticker_info: No valid info for {ticker_str}")
            return None

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
        
        if compact_info['currentPrice'] is None:
            hist = stock.history(period="2d", interval="1d")
            if not hist.empty and 'Close' in hist.columns:
                compact_info['currentPrice'] = hist['Close'].iloc[-1]
                if compact_info['previousClose'] is None and len(hist) > 1:
                    compact_info['previousClose'] = hist['Close'].iloc[-2]
            
            if compact_info['currentPrice'] is None:
                 return None

        if compact_info['previousClose'] is None:
            compact_info['previousClose'] = compact_info['currentPrice'] 

        return compact_info

    except Exception as e:
        print(f"    [Error] _get_compact_ticker_info exception for {ticker_str}: {e}")
        return None

def get_ticker_info(ticker_str: str):
    if not isinstance(ticker_str, str): 
        return None
    
    cache_key = f"info_{ticker_str}"
    cached_info = get_cache(cache_key)
    
    if cached_info: 
        return cached_info
    
    try:
        compact_info = _get_compact_ticker_info(ticker_str)
        
        if not compact_info:
            return None
            
        set_cache(cache_key, compact_info, ttl_seconds=config.CACHE_PRICE_DATA_SECONDS)
        return compact_info
        
    except Exception as e: 
        print(f"     [Error] yfinance info exception for {ticker_str}: {e}")
        return None

def get_technical_rating(ticker: str, timeframe: str = '1D') -> str:
    cache_key = f"tech_rating_{ticker}_{timeframe}"
    cached_rating = get_cache(cache_key)
    if cached_rating:
        return cached_rating
    
    try:
        norm_ticker = normalize_ticker(ticker)
        if not norm_ticker:
            return "N/A"
        
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
        
        if len(close_prices) < 50:
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
        # traceback.print_exc()
        set_cache(cache_key, "N/A", ttl_seconds=600)
        return "N/A"

# Get Current Price with detailed snapshot
def get_current_price(ticker: str):
    normalized_ticker = normalize_ticker(ticker)
    if not normalized_ticker:
        return {"error": f"Could not find a valid ticker for '{ticker}'. Please use a known name or ticker (e.g., RELIANCE or ZOMATO.NS)."}

    info = get_ticker_info(normalized_ticker) 
    
    if not info:
        return {"error": f"Ticker '{normalized_ticker}' seems invalid. No data found."}

    try:
        is_nse = normalized_ticker.endswith('.NS')
        currency_symbol = "₹" if is_nse else info.get('currency', '$')
        
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
    index_map = {
        'NIFTY': '^NSEI', 'NIFTY 50': '^NSEI', 'NIFTY50': '^NSEI',
        'SENSEX': '^BSESN', 'BSE SENSEX': '^BSESN',
        'BANK NIFTY': '^NSEBANK', 'BANKNIFTY': '^NSEBANK', 'NIFTY BANK': '^NSEBANK',
        'NIFTY IT': '^CNXIT', 'NIFTY PHARMA': '^CNXPHARMA', 'NIFTY FMCG': '^CNXFMCG',
        'NIFTY AUTO': '^CNXAUTO', 'NIFTY METAL': '^CNXMETAL', 'NIFTY REALTY': '^CNXREALTY',
        'NIFTY ENERGY': '^CNXENERGY', 'NIFTY INFRA': '^CNXINFRA',
        'NIFTY MIDCAP': '^NSEMDCP50', 'NIFTY SMALLCAP': '^CNXSC'
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

def get_index_data_for_agent(index_name: str) -> dict:
    try:
        return get_index_data(index_name)
    except Exception as e:
        print(f"[Error] in get_index_data_for_agent: {traceback.format_exc()}")
        return {"error": str(e)}

# screen_static_index
def screen_static_index(index_name: str = "NIFTY 50", num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False):
    norm_name = index_name.strip().upper()
    ticker_list = indices.STATIC_INDICES.get(norm_name)  

    if ticker_list is None:
        valid_indices = list(indices.STATIC_INDICES.keys())
        print(f"      [Error] Error: Index '{index_name}' (Normalized: '{norm_name}') not in static list.")
        return {"error": f"Index '{index_name}' not in pre-defined list. Try one of: {', '.join(valid_indices[:6])}..."}

    return screen_custom_stock_list(tickers=ticker_list, num_stocks=num_stocks, duration_days=duration_days, prefer_buy=prefer_buy, index_name_for_log=index_name)

# screen_custom_stock_list
def screen_custom_stock_list(tickers: List[str], num_stocks: int = 3, duration_days: int = 30, prefer_buy: bool = False, index_name_for_log: str = "Custom List"):
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
                if current_price > ema_val: score += 50  
                else: score -= 20
                
                # RSI Score
                if 40 <= rsi_val <= 65: score += 30
                elif rsi_val > 70: score -= 10 * prefer_buy
                elif rsi_val < 30: score += 20
                
                info = get_ticker_info(ticker)
                
                candidates.append({
                    'Ticker': ticker,
                    'Name': info.get('shortName', ticker) if info else ticker,
                    'Price': float(round(current_price, 2)),
                    'RSI': float(round(rsi_val, 2)),
                    'EMA': float(round(ema_val, 2)),
                    'Score': score
                })

            except Exception: continue
        if not candidates:
            return {"message": f"Could not calculate technicals for any stocks in {index_name_for_log}."}

        # Sort by Score -> Then by RSI
        candidates.sort(key=lambda x: (x['Score'], x['RSI']), reverse=True)
        
        top_picks = candidates[:num_stocks]
        
        result = {"top_filtered_stocks": top_picks}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS)
        return result

    except Exception as e:
        print(f"      [Error] Screening error: {traceback.format_exc()}")
        return {"message": f"Screening failed: {str(e)}"}

def get_conversation_summary(history_list):
    if not history_list:
        return ""
        
    conversation_text = ""
    for msg in history_list:
        role = "User" if msg['role'] == 'user' else "AI"
        text = msg['parts'][0]['text']
        conversation_text += f"{role}: {text}\n"

    summary_prompt = f"""Summarize this stock analysis chat into one dense paragraph. Must include: user risk/prefs, specific tickers discussed, trades executed, and pending requests. Omit filler.
    Chat:
    {conversation_text}"""
    
    try:
        summary_model = genai.GenerativeModel('gemini-2.5-flash') 
        response = summary_model.generate_content(summary_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Summarization failed: {e}")
        return ""

def get_live_price(ticker: str) -> float:
    norm_t = normalize_ticker(ticker)
    if not norm_t: 
        raise ValueError(f"Invalid ticker: '{ticker}'.")
    
    info = get_ticker_info(norm_t)
    
    if not info:
        raise ValueError(f"Ticker {norm_t} is invalid, no info.")
        
    price = info.get('currentPrice')
    
    if price is not None:
        return float(price)
    else:
        raise ValueError(f"No price data found for {norm_t} even after info fetch.")

def get_fundamental_data(ticker: str) -> dict:
    """Retrieves key fundamental data points with enhanced ratings."""
    norm_t = normalize_ticker(ticker)
    if not norm_t:
        return {"error": f"Invalid ticker: '{ticker}'."}
    
    try:
        info = get_ticker_info(norm_t) 
        
        if not info:
            if norm_t.endswith('.NS'):
                # print(f"     Retrying with .BO suffix...")
                alt_ticker = norm_t.replace('.NS', '.BO')
                info = get_ticker_info(alt_ticker)
                if info:
                    norm_t = alt_ticker
                else:
                    return {"error": f"Could not retrieve data for {ticker}."}
            else:
                return {"error": f"Could not retrieve data for {ticker}."}
        
        is_nse = norm_t.endswith('.NS')
        currency_symbol = "₹" if is_nse or norm_t.endswith('.BO') else info.get('currency', '$')
        
        current_price = info.get('currentPrice')
        mc = info.get('marketCap')
        div_y = info.get('dividendYield')
        target_price = info.get('targetMeanPrice')
        
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
        # traceback.print_exc()
        return {"error": f"Error retrieving fundamentals: {str(e)}"}

def find_intraday_trade_setups(tickers: Optional[List[str]] = None, num_setups: int = 3) -> dict:
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
    
    try:
        hist_data = yf.download(tickers_to_scan, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if hist_data.empty or 'Close' not in hist_data.columns:
            raise ValueError("yfinance download returned empty data.")
    except Exception as e:
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
            # print(f"      [Warning] Error processing setup for {ticker}: {e}")
            continue 
    
    if not setups:
        return {"message": f"No stocks from the '{scan_source}' list currently meet the high-probability intraday trade setup criteria (RSI + Trend + Volume)."}

    setups.sort(key=lambda x: x['risk_percent'])
    
    return {"setups": setups[:num_setups]}

def get_stock_news(query: str, company_name: Optional[str] = None) -> dict: 
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
                 continue
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                if not articles: result = {"message": f"No NewsAPI news for '{search_term}'."}
                else:
                    fmt_news = [{"title": a.get('title'), "source": a.get('source', {}).get('name'), "description": a.get('description'), "url": a.get('url'), "publishedAt": a.get('publishedAt')} for a in articles]
                    result = {"articles": fmt_news}
                set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
        except:
             continue
    result = {"error": "NewsAPI keys rate-limited or invalid."}; set_cache(cache_key, result, ttl_seconds=60); return result

def internet_search_news(query: str) -> dict:
    cache_key = f"ddgs_news_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.news(query, region='in-en', safesearch='off', max_results=5)
        if not results: result = {"message": f"No DDGS news found for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "source": i.get('source'), "description": i.get('body'), "url": i.get('url'), "publishedAt": i.get('date')} for i in results]
            result = {"articles": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e:
        return {"error": f"DDGS news search error: {str(e)}"}

def internet_search(query: str) -> dict:
    cache_key = f"ddgs_search_{query.replace(' ', '_').lower()}"
    cached_result = get_cache(cache_key)
    if cached_result: return cached_result
    try:
        with DDGS() as ddgs: results = ddgs.text(query, region='in-en', max_results=3)
        if not results: result = {"message": f"No DDGS search results for '{query}'."}
        else:
            fmt_res = [{"title": i.get('title'), "snippet": i.get('body'), "url": i.get('href')} for i in results]
            result = {"results": fmt_res}
        set_cache(cache_key, result, ttl_seconds=config.CACHE_NEWS_DATA_SECONDS); return result
    except Exception as e: return {"error": f"DDGS search error: {str(e)}"}

def get_index_constituents(index_name: str) -> dict:
    cache_key = f"constituents_{index_name.strip().upper().replace(' ', '_')}"
    cached_result = get_cache(cache_key)
    if cached_result:
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
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status() 
            data = response.json()
            constituents = data.get("data", [])

            if constituents:
                ticker_list = [item.get("symbol") + ".NS" for item in constituents if item.get("symbol")]
                valid_tickers = [ticker for ticker in ticker_list if ticker is not None]
                if valid_tickers:
                    result = {"index_name": index_name, "tickers": valid_tickers, "source": f"NSE API ('{name_attempt}')"}
                    set_cache(cache_key, result, ttl_seconds=3600) 
                    return result

            if nse_error is None: nse_error = f"NSE API returned empty data for '{name_attempt}'."

        except:
             break

    try:
        query = f"{index_name} constituents tickers list NSE"
        search_snippets = []
        with DDGS() as ddgs:
            results = ddgs.text(query, region='in-en', max_results=7)
            if results: search_snippets = [str(r.get('body', '')) for r in results if r.get('body')]

        if not search_snippets:
            final_error = f"NSE API failed and DDGS search found no results for '{index_name}'."
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600) 
            return {"error": final_error}

        extraction_prompt = f"""Extract unique NSE tickers (ending .NS) from text below for '{index_name}'.
        Return ONLY a JSON list of strings. No markdown, no explanation.
        Example: ["HDFCBANK.NS", "SBIN.NS"]

        Text:
        {json.dumps(search_snippets)}"""
        extraction_model = genai.GenerativeModel(model_name=config.GEMINI_MODEL_NAME)
        
        extracted_text = ""
        try:
            response = extraction_model.generate_content(extraction_prompt)
            if response.candidates:
                extracted_text = response.text.strip()
        except: pass

        if extracted_text.startswith("```python"): extracted_text = extracted_text[len("```python"):].strip()
        if extracted_text.startswith("```"): extracted_text = extracted_text[len("```"):].strip()
        if extracted_text.endswith("```"): extracted_text = extracted_text[:-len("```")].strip()

        valid_tickers = []
        parsing_error = None

        try:
            try:
                cleaned_text = extracted_text.replace("'", '"') if extracted_text else "[]"
                if not cleaned_text.strip(): cleaned_text = "[]"
                parsed_json = json.loads(cleaned_text)

                if isinstance(parsed_json, list):
                    valid_tickers = [t for t in parsed_json if isinstance(t, str) and t.endswith('.NS')]
            except: pass 
            
            if not valid_tickers:
                potential_tickers = re.findall(r"['\"]?([A-Z0-9\-&]+?\.NS)['\"]?", extracted_text, re.IGNORECASE)
                current_valid_regex = sorted(list(set(
                    t.upper() for t in potential_tickers if isinstance(t, str) and t.upper().endswith('.NS')
                )))

                if current_valid_regex:
                    valid_tickers = current_valid_regex 

            if not valid_tickers:
               return {"error": "Could not extract tickers."}

            result = {"index_name": index_name, "tickers": valid_tickers, "source": "DDGS+AI"}
            set_cache(cache_key, result, ttl_seconds=1800) 
            return result

        except Exception as e:
            final_error = f"Error processing AI response/DDGS fallback for '{index_name}': {e}"
            set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
            return {"error": final_error}

    except Exception as e:
        final_error = f"Unexpected Error: {e}"
        set_cache(cache_key, {"error": final_error}, ttl_seconds=600)
        return {"error": final_error}

# Zerodha Portfolio Sync
def sync_zerodha_portfolio(user_id: str, access_token: str) -> dict:
    if not db: return {"error": "DB unavailable"}
    
    try:
        # print(f"Starting Zerodha sync for user {user_id}...")
        kite = KiteConnect(api_key=config.ZERODHA_API_KEY)
        kite.set_access_token(access_token)

        # 1. Fetch Data
        margins = kite.margins()
        equity_margin = margins.get('equity', {})
        available_balance = equity_margin.get('available', {}).get('cash', 0.0)
        cash_balance = available_balance 
        
        holdings = kite.holdings()
        positions = kite.positions().get('net', []) 
        
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
                'exchange': item.get('exchange'), 
                'product': item.get('product', 'CNC').upper(),
                'prev_close_price': float(item.get('close_price', 0)) 
            }

        for item in positions:
            ticker = item.get('tradingsymbol')
            quantity = float(item.get('quantity', 0))
            product = item.get('product', '').upper()
            
            if quantity <= 0 or product == 'MIS': continue
            
            exchange = item.get('exchange')

            if product in ['MTF', 'NRML', 'CNC']: 
                if ticker in all_instruments:
                    all_instruments[ticker]['quantity'] += quantity 
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
            
            MAJOR_STOCKS = [
                'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ITC', 'SBIN', 'BHARTIARTL', 
                'HINDUNILVR', 'ICICIBANK', 'KOTAKBANK', 'LT', 'AXISBANK', 'BAJFINANCE',
                'MARUTI', 'ASIANPAINT', 'TITAN', 'ULTRACEMCO', 'SUNPHARMA', 'WIPRO',
                'TATAMOTORS', 'ADANIENT', 'ADANIPORTS', 'POWERGRID', 'NTPC', 'ONGC'
            ]

            for ticker, item in all_instruments.items():
                exchange = item.get('exchange', 'NSE') 
                quantity = item.get('quantity')
                avg_price = item.get('avg_price')
                product = item.get('product')
                prev_close_price = item.get('prev_close_price') 

                ticker_yf = None
                clean_ticker = ticker.strip().upper()
                
                if exchange == 'NSE':
                    ticker_yf = f"{clean_ticker}.NS"
                elif exchange == 'BSE':
                    if clean_ticker in MAJOR_STOCKS:
                        ticker_yf = f"{clean_ticker}.NS"
                    else:
                        ticker_yf = f"{clean_ticker}.BO"
                
                if not ticker_yf and (clean_ticker.endswith('ETF') or clean_ticker.endswith('BEES') or 'INDX' in clean_ticker):
                    ticker_yf = f"{clean_ticker}.NS"
                
                if not ticker_yf:
                    ticker_yf = f"{clean_ticker}.NS"

                db.update_holding(user_id, ticker_yf, {
                    'quantity': quantity,
                    'avg_price': avg_price,
                    'product_type': product,
                    'prev_close_price': prev_close_price 
                })
                holdings_synced_count += 1

            current_port_value = calculate_current_portfolio_value(user_id, float(cash_balance))
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            db.create_or_update_user(user_id, {
                'day_start_portfolio_value': current_port_value,
                'last_day_pnl_reset': today_str,
                'net_cash_flow_today': 0.0,
                'zerodha_synced_once': True
            })

            # print(f"    [Success] Synced {holdings_synced_count} holdings.")
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

# Watchlist Management for Agents
def get_watchlist_for_agent(user_id: str) -> dict:
    """Retrieves all stocks from the user's watchlist with their current prices."""
    if not db: return {"error": "DB unavailable"}
    try:
        # Use DB helper
        tickers = db.get_watchlist(user_id)
        if not tickers: 
            return {"message": "User's watchlist is empty."}
        
        watchlist_items = []
        prices = get_bulk_live_prices(tickers)
        
        for t in tickers:
            cp = prices.get(t)
            if cp is None: continue
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
    
    if not valid_tickers: return {}
    try:
        data = yf.download(valid_tickers, period='2d', progress=False, auto_adjust=True, ignore_tz=True)
        if data.empty or 'Close' not in data.columns: raise ValueError("Empty bulk download")
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
                     try: prices[ticker] = float(round(get_live_price(ticker), config.PRICE_DECIMAL_PLACES))
                     except ValueError: pass
            else: 
                if pd.notna(last_prices.iloc[0]):
                    prices[ticker] = float(round(last_prices.iloc[0], config.PRICE_DECIMAL_PLACES))
                else:
                     try: prices[ticker] = float(round(get_live_price(ticker), config.PRICE_DECIMAL_PLACES))
                     except ValueError: pass
        return prices
    except Exception as e:
        # Fallback
        prices = {}
        time.sleep(1) 
        for t in valid_tickers:
            try: 
                price = get_live_price(t)
                prices[t] = float(round(price, config.PRICE_DECIMAL_PLACES))
                time.sleep(0.1) 
            except ValueError: pass
        return prices

def initialize_user_account(user_id: str) -> dict:
    try:
        account_data = db.get_user(user_id)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        if not account_data:
            initial_data = {
                'cash': config.DEFAULT_STARTING_CASH, 
                'initial_cash': config.DEFAULT_STARTING_CASH, 
                'account_initialized': True,
                'zerodha_synced_once': False, 
                'created_at': db.get_timestamp(), 
                'day_start_portfolio_value': config.DEFAULT_STARTING_CASH,
                'last_day_pnl_reset': today_str, 
                'token_usage': {'input': 0, 'output': 0, 'total': 0},
                'net_cash_flow_today': 0.0,
                'plan': 'free',
                'plan_start_date': today_str
            }
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
            if 'plan' not in account_data: 
                update_fields['plan'] = 'free'
                update_fields['plan_start_date'] = today_str

            last_reset = account_data.get('last_day_pnl_reset', '')
            if last_reset != today_str:
                current_val = calculate_current_portfolio_value(user_id, account_data.get('cash', 0))
                update_fields['day_start_portfolio_value'] = current_val
                update_fields['last_day_pnl_reset'] = today_str
                update_fields['net_cash_flow_today'] = 0.0
            
            if update_fields:
                account_data = db.create_or_update_user(user_id, update_fields)
            
            if 'token_usage' not in account_data:
                update_fields['token_usage'] = {'input': 0, 'output': 0, 'total': 0}
            
            if update_fields:
                account_data = db.create_or_update_user(user_id, update_fields)
            
            return account_data
    except Exception as e: 
        print(f"[Error] Error initializing account {user_id}: {e}")
        raise

def calculate_current_portfolio_value(user_id: str, current_cash: float) -> float:
    try:
        holdings_data = db.get_portfolio_holdings(user_id)
        tickers = list(holdings_data.keys())
        total_val = 0
        
        if tickers:
            prices = get_bulk_live_prices(tickers)
            for t, h in holdings_data.items(): 
                total_val += h.get('quantity', 0) * prices.get(t, h.get('avg_price', 0))
        
        return current_cash + total_val
    except Exception as e: 
        return current_cash

def get_portfolio(user_id: str) -> dict:
    if not db: raise Exception("Firestore unavailable.")
    try:
        acc_data = initialize_user_account(user_id)
        
        cash = acc_data.get('cash', 0)
        synced_flag = acc_data.get('zerodha_synced_once', False)
        saved_tokens = acc_data.get('token_usage', {'input': 0, 'output': 0, 'total': 0})

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
        
        # Calculate Token Limit & Plan
        plan_id = acc_data.get('plan', 'free')
        plan_details = config.PLANS.get(plan_id, config.PLANS['free'])
        plan_name = plan_details.get('name', 'Free Tier')
        
        token_limit = acc_data.get('custom_token_limit', plan_details['tokens'])
        current_usage = saved_tokens.get('total', 0)
        tokens_left = max(0, token_limit - current_usage)
        
        summary = {
            "portfolio_value": round(cash + total_curr_h_val, config.PNL_DECIMAL_PLACES),
            "total_invested": round(total_inv, config.PNL_DECIMAL_PLACES),
            "total_holdings_value": round(total_curr_h_val, config.PNL_DECIMAL_PLACES), 
            "total_pnl": round(total_pnl, config.PNL_DECIMAL_PLACES),
            "total_pnl_percent": round((total_pnl / total_inv * 100) if total_inv != 0 else 0, 2),
            "day_pnl": round(total_day_pnl, config.PNL_DECIMAL_PLACES), 
            "day_pnl_percent": round(day_pnl_pct, 2),
            "zerodha_synced_once": synced_flag,
            "token_usage": saved_tokens,
            "plan_name": plan_name,
            "token_limit": token_limit,
            "tokens_left": tokens_left
        }
        return {"cash": round(cash, 2), "holdings": holdings, "summary": summary} 
    except Exception as e: 
        print(f"[Error] Error getting portfolio {user_id}: {traceback.format_exc()}")
        raise

def execute_trade(user_id: str, ticker: str, quantity: int, action: str):
    """
    Executes a virtual buy or sell trade for a user.
    """
    try: quantity = int(float(quantity))
    except: return {"error": True, "message": f"Invalid quantity: {quantity}"}
    if quantity <= 0: return {"error": True, "message": "Quantity must be positive."}

    norm_ticker = normalize_ticker(ticker)
    if not norm_ticker: return {"error": True, "message": f"Invalid ticker: {ticker}"}
    
    try: 
        stock = yf.Ticker(norm_ticker)
        hist = stock.history(period="1d")
        if hist.empty: raise ValueError("Price data unavailable")
        cp = float(hist['Close'].iloc[-1])
    except Exception as e: 
        return {"error": True, "message": f"Price fetch failed: {str(e)}"}

    trade_val = cp * quantity

    try:
        user_data = db.get_user(user_id)
        if not user_data: return {"error": True, "message": "User not found"}
        
        cash = user_data.get('cash', 0)
        
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
            
            db.update_user_cash(user_id, new_cash)
            db.update_holding(user_id, norm_ticker, {'quantity': new_qty, 'avg_price': new_avg, 'company_name': norm_ticker})

        elif act == 'SELL':
            if current_qty < quantity: 
                raise ValueError(f"Insufficient shares. Have {current_qty}")
            
            new_cash = cash + trade_val
            new_qty = current_qty - quantity
            
            db.update_user_cash(user_id, new_cash)
            if new_qty > 0:
                db.update_holding(user_id, norm_ticker, {'quantity': new_qty}) 
            else:
                db.delete_holding(user_id, norm_ticker)

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

def remove_from_watchlist(user_id: str, ticker: str) -> dict:
    norm = normalize_ticker(ticker) or ticker.upper()
    success = db.remove_from_watchlist(user_id, norm)
    if success:
        return {"status": "success", "removed_ticker": norm}
    return {"error": "Ticker not found in watchlist"}

def get_stock_analysis_data(ticker, timeframe, indicators):
    try:
        # 1. Get the ROBUST, CACHED fundamental data first.
        analysis_data = get_fundamental_data(ticker)
        
        if analysis_data.get("error"):
            return analysis_data
            
        norm_ticker = analysis_data['ticker'] 
        
        # 2. RE-CALCULATE the technical rating based on the SELECTED timeframe
        analysis_data['technicalRating'] = get_technical_rating(norm_ticker, timeframe)
        
        # 3. Map timeframe to yfinance history parameters
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
        
        # 4. Get Ticker and History
        stock = yf.Ticker(norm_ticker)
        hist = stock.history(period=params['period'], interval=params['interval'])
        
        indicator_values = {}
        
        # 5. Check history and calculate all requested indicators
        if hist.empty or 'Close' not in hist.columns:
            # print(f"No historical data for {norm_ticker} with params {params}")
            for ind in indicators: indicator_values[ind] = 'N/A'
        
        else:
            close_prices = hist['Close'].dropna()
            
            if len(close_prices) < 55: 
                 # print(f"Not enough data for indicators {norm_ticker} (need 55, got {len(close_prices)})")
                 for ind in indicators: indicator_values[ind] = 'N/A'
            else:
                # --- Start Safe Calculation ---
                try:
                    if 'rsi' in indicators:
                        # from ta.momentum import RSIIndicator # Already imported
                        val = RSIIndicator(close_prices, window=14).rsi().iloc[-1]
                        indicator_values['rsi'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'ema' in indicators:
                        # from ta.trend import EMAIndicator
                        val = EMAIndicator(close_prices, window=20).ema_indicator().iloc[-1]
                        indicator_values['ema'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'sma' in indicators:
                        # from ta.trend import SMAIndicator
                        val = SMAIndicator(close_prices, window=50).sma_indicator().iloc[-1]
                        indicator_values['sma'] = round(val, 2) if pd.notna(val) else 'N/A'
                    
                    if 'macd' in indicators:
                        # from ta.trend import MACD
                        val = MACD(close_prices).macd().iloc[-1]
                        indicator_values['macd'] = round(val, 2) if pd.notna(val) else 'N/A'
                        
                    if 'volume' in indicators and 'Volume' in hist.columns:
                        val = hist['Volume'].iloc[-1]
                        indicator_values['volume'] = int(val) if pd.notna(val) else 'N/A'
                    elif 'volume' in indicators:
                        indicator_values['volume'] = 'N/A'
                        
                    if 'bollinger' in indicators:
                        # from ta.volatility import BollingerBands
                        bb = BollingerBands(close_prices)
                        lower = bb.bollinger_lband().iloc[-1]
                        upper = bb.bollinger_hband().iloc[-1]
                        indicator_values['bollinger'] = f"₹{lower:.2f}-₹{upper:.2f}" if pd.notna(lower) and pd.notna(upper) else 'N/A'

                    if 'adx' in indicators:
                        # from ta.trend import ADXIndicator
                        adx_val = ADXIndicator(hist['High'], hist['Low'], close_prices, window=14).adx().iloc[-1]
                        indicator_values['adx'] = round(adx_val, 2) if pd.notna(adx_val) else 'N/A'
                        
                    if 'stochastic' in indicators:
                        # from ta.momentum import StochasticOscillator
                        stoch_val = StochasticOscillator(hist['High'], hist['Low'], close_prices).stoch().iloc[-1]
                        indicator_values['stochastic'] = round(stoch_val, 2) if pd.notna(stoch_val) else 'N/A'

                except Exception as ind_error:
                    # print(f"Indicator calculation error for {norm_ticker}: {ind_error}")
                    for ind in indicators:
                        if ind not in indicator_values:
                            indicator_values[ind] = 'N/A'
        
        # 6. Add the calculated indicators to the main analysis object
        analysis_data['indicators'] = indicator_values
        
        # 7. Return the combined, robust data
        return analysis_data
        
    except Exception as e:
        print(f"Error in get_stock_analysis: {e}")
        # traceback.print_exc()
        return {'error': str(e)}
