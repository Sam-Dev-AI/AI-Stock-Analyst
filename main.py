import os
import sys
import warnings
import logging

# Suppress all warnings and logs BEFORE any imports
os.environ['GRPC_VERBOSITY'] = 'NONE'
os.environ['GRPC_TRACE'] = ''
os.environ['GLOG_minloglevel'] = '3'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# Disable all logging
logging.disable(logging.CRITICAL)

# Suppress stderr completely during imports
class SuppressStderr:
    def __enter__(self):
        self._original_stderr = sys.stderr
        self._devnull = open(os.devnull, 'w')
        sys.stderr = self._devnull
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self._original_stderr
        self._devnull.close()

warnings.filterwarnings('ignore')

import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

# Import genai with suppressed output
with SuppressStderr():
    import google.generativeai as genai

import requests
import config
import random
from datetime import datetime, timedelta

# Import configuration
with SuppressStderr():
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


def find_top_filtered_stocks(duration_days: int = 30, prefer_buy: bool = False):
    """
    Finds top NIFTY 50 stocks for a given holding duration.
    
    Args:
        duration_days: Number of days for holding period
        prefer_buy: If True, filters for RSI 50-65 (not overbought, good for buying)
                    If False, shows all stocks with RSI > 50
    
    Returns:
        Top 3 stocks filtered by criteria
    """
    # Use duration_days as EMA window (adaptive to user's timeframe)
    ema_window = min(max(duration_days, 5), 200)
    
    filtered = []
    for ticker in NIFTY_50_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            if market_cap < LARGE_CAP_MIN_MARKET_CAP:
                continue
            
            # Get enough history for EMA calculation
            history_period = max(ema_window * 2, 30)
            hist = stock.history(period=f"{history_period}d", interval="1d")
            
            if hist.empty or len(hist) < ema_window:
                continue
            
            rsi = RSIIndicator(hist['Close'], window=14).rsi().iloc[-1]
            ema = EMAIndicator(hist['Close'], window=ema_window).ema_indicator().iloc[-1]
            price = hist['Close'].iloc[-1]
            
            # Apply RSI filter based on prefer_buy
            if prefer_buy:
                # For buying: RSI should be 50-65 (healthy momentum, not overbought)
                rsi_condition = 50 <= rsi <= 65
            else:
                # General screening: RSI > 50
                rsi_condition = rsi > RSI_THRESHOLD
            
            if rsi_condition and price > ema:
                filtered.append({
                    'Ticker': ticker,
                    'MarketCap': market_cap,
                    'RSI': float(rsi),
                    'Price': float(price),
                    'EMA': float(ema),
                    'EMAPeriod': ema_window,
                    'Name': info.get('shortName', ticker),
                    'Duration': f"{duration_days} days",
                    'BuyReady': prefer_buy
                })
        except Exception:
            continue
    
    if not filtered:
        if prefer_buy:
            return f"No stocks currently in the ideal buy zone (RSI 50-65) for {duration_days} days duration. Market may be overbought."
        else:
            return f"No stocks currently meet the filtering criteria for {duration_days} days duration."
    
    filtered.sort(key=lambda x: x['RSI'], reverse=True)
    top3 = filtered[:3]
    return {"top_filtered_stocks": top3, "duration_days": duration_days, "prefer_buy": prefer_buy}


def find_stocks_by_price_change(percentage: float = 0, timeframe: str = "1day"):
    """
    Finds stocks by price change over a relative timeframe.
    
    Args:
        percentage: Minimum percentage change threshold (use 0 to get all movers)
        timeframe: "1day", "1week", or "1month"
    
    Returns:
        Stocks matching criteria with time context
    """
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
            
            # Always include when percentage=0, otherwise filter by threshold
            if percentage == 0 or abs(price_change_pct) >= percentage:
                matching_stocks.append({
                    'Ticker': ticker,
                    'Name': info.get('shortName', ticker),
                    'CurrentPrice': float(current_price),
                    'PreviousPrice': float(previous_price),
                    'PriceChange%': float(price_change_pct),
                    'Direction': 'up' if price_change_pct > 0 else 'down',
                    'MarketCap': info.get('marketCap', 0),
                    'RSI': float(rsi) if rsi is not None else None,
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
        "total_found": len(matching_stocks)
    }


def get_complete_stock_details(ticker: str):

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y", interval="1d")
        
        if hist.empty:
            return {"error": f"No data available for {ticker}"}
        
        # Basic Information
        company_name = info.get('shortName', ticker)
        long_name = info.get('longName', company_name)
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')
        website = info.get('website', 'N/A')
        
        # Stock Prices
        current_price = hist['Close'].iloc[-1]
        day_high = hist['High'].iloc[-1]
        day_low = hist['Low'].iloc[-1]
        fifty_two_week_high = info.get('fiftyTwoWeekHigh', 'N/A')
        fifty_two_week_low = info.get('fiftyTwoWeekLow', 'N/A')
        
        # Performance Metrics
        ytd_return = ((current_price - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
        month_return = ((current_price - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21]) * 100 if len(hist) >= 21 else 'N/A'
        week_return = ((current_price - hist['Close'].iloc[-5]) / hist['Close'].iloc[-5]) * 100 if len(hist) >= 5 else 'N/A'
        
        # Volume Information
        current_volume = hist['Volume'].iloc[-1]
        avg_volume = info.get('averageVolume', 'N/A')
        
        # Financial Metrics
        market_cap = info.get('marketCap', 0)
        pe_ratio = info.get('trailingPE', 'N/A')
        forward_pe = info.get('forwardPE', 'N/A')
        peg_ratio = info.get('pegRatio', 'N/A')
        price_to_book = info.get('priceToBook', 'N/A')
        eps = info.get('trailingEps', 'N/A')
        
        # Profitability Metrics
        profit_margin = info.get('profitMargins', 'N/A')
        operating_margin = info.get('operatingMargins', 'N/A')
        roe = info.get('returnOnEquity', 'N/A')
        roa = info.get('returnOnAssets', 'N/A')
        
        # Growth Metrics
        revenue_growth = info.get('revenueGrowth', 'N/A')
        earnings_growth = info.get('earningsGrowth', 'N/A')
        revenue = info.get('totalRevenue', 'N/A')
        
        # Dividend Information
        dividend_yield = info.get('dividendYield', 'N/A')
        dividend_rate = info.get('dividendRate', 'N/A')
        payout_ratio = info.get('payoutRatio', 'N/A')
        
        # Debt Metrics
        debt_to_equity = info.get('debtToEquity', 'N/A')
        current_ratio = info.get('currentRatio', 'N/A')
        quick_ratio = info.get('quickRatio', 'N/A')
        
        # Technical Indicators
        if len(hist) >= 50:
            sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            sma_200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else 'N/A'
        else:
            sma_50 = 'N/A'
            sma_200 = 'N/A'
            
        if len(hist) >= 20:
            ema_20 = EMAIndicator(hist['Close'], window=20).ema_indicator().iloc[-1]
        else:
            ema_20 = 'N/A'
            
        if len(hist) >= 14:
            rsi = RSIIndicator(hist['Close'], window=14).rsi().iloc[-1]
        else:
            rsi = 'N/A'
        
        # Analyst Recommendations
        target_price = info.get('targetMeanPrice', 'N/A')
        recommendation = info.get('recommendationKey', 'N/A')
        num_analyst_opinions = info.get('numberOfAnalystOpinions', 'N/A')
        
        # Company Description
        business_summary = info.get('longBusinessSummary', 'No description available')
        
        # Key People
        ceo = 'N/A'
        if 'companyOfficers' in info and info['companyOfficers']:
            for officer in info['companyOfficers']:
                if 'CEO' in officer.get('title', ''):
                    ceo = officer.get('name', 'N/A')
                    break
        
        # Format the response
        return {
            "ticker": ticker,
            "basic_info": {
                "company_name": company_name,
                "long_name": long_name,
                "sector": sector,
                "industry": industry,
                "website": website,
                "ceo": ceo
            },
            "price_data": {
                "current_price": float(current_price),
                "day_high": float(day_high),
                "day_low": float(day_low),
                "52_week_high": fifty_two_week_high,
                "52_week_low": fifty_two_week_low
            },
            "performance": {
                "ytd_return": f"{ytd_return:.2f}%" if isinstance(ytd_return, (int, float)) else ytd_return,
                "1_month_return": f"{month_return:.2f}%" if isinstance(month_return, (int, float)) else month_return,
                "1_week_return": f"{week_return:.2f}%" if isinstance(week_return, (int, float)) else week_return
            },
            "volume": {
                "current_volume": int(current_volume),
                "average_volume": avg_volume
            },
            "valuation": {
                "market_cap": market_cap,
                "pe_ratio": pe_ratio,
                "forward_pe": forward_pe,
                "peg_ratio": peg_ratio,
                "price_to_book": price_to_book,
                "eps": eps
            },
            "profitability": {
                "profit_margin": f"{profit_margin * 100:.2f}%" if isinstance(profit_margin, (int, float)) else profit_margin,
                "operating_margin": f"{operating_margin * 100:.2f}%" if isinstance(operating_margin, (int, float)) else operating_margin,
                "return_on_equity": f"{roe * 100:.2f}%" if isinstance(roe, (int, float)) else roe,
                "return_on_assets": f"{roa * 100:.2f}%" if isinstance(roa, (int, float)) else roa
            },
            "growth": {
                "revenue_growth": f"{revenue_growth * 100:.2f}%" if isinstance(revenue_growth, (int, float)) else revenue_growth,
                "earnings_growth": f"{earnings_growth * 100:.2f}%" if isinstance(earnings_growth, (int, float)) else earnings_growth,
                "total_revenue": revenue
            },
            "dividends": {
                "dividend_yield": f"{dividend_yield * 100:.2f}%" if isinstance(dividend_yield, (int, float)) else dividend_yield,
                "dividend_rate": dividend_rate,
                "payout_ratio": f"{payout_ratio * 100:.2f}%" if isinstance(payout_ratio, (int, float)) else payout_ratio
            },
            "debt": {
                "debt_to_equity": debt_to_equity,
                "current_ratio": current_ratio,
                "quick_ratio": quick_ratio
            },
            "technicals": {
                "rsi_14": float(rsi) if isinstance(rsi, (int, float)) else rsi,
                "sma_50": float(sma_50) if isinstance(sma_50, (int, float)) else sma_50,
                "sma_200": float(sma_200) if isinstance(sma_200, (int, float)) else sma_200,
                "ema_20": float(ema_20) if isinstance(ema_20, (int, float)) else ema_20
            },
            "analyst_info": {
                "target_price": target_price,
                "recommendation": recommendation,
                "num_analysts": num_analyst_opinions
            },
            "business_summary": business_summary
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch details for {ticker}: {str(e)}"}


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
    get_complete_stock_details,
    get_recent_news,
    get_financial_highlights,
    get_company_profile
]

with SuppressStderr():
    model = genai.GenerativeModel(
        model_name='models/gemini-pro-latest',
        tools=agent_tools,
        system_instruction=SYSTEM_INSTRUCTION
    )

if __name__ == "__main__":
    with SuppressStderr():
        chat = model.start_chat(enable_automatic_function_calling=True)
    print("Welcome to the Stock Analysis Agent! Type 'quit' to exit.")

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
