import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import warnings
import google.generativeai as genai
import requests
import config

warnings.filterwarnings('ignore')

# Import configuration
genai.configure(api_key=config.GENIE_API_KEY)
NEWSAPI_API_KEY = config.NEWSAPI_API_KEY
NIFTY_50_TICKERS = config.NIFTY_50_TICKERS
LARGE_CAP_MIN_MARKET_CAP = config.LARGE_CAP_MIN_MARKET_CAP
RSI_THRESHOLD = config.RSI_THRESHOLD
EMA_PERIOD = config.EMA_PERIOD


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


def get_recent_news(company_name):
    """Fetches recent news from NewsAPI.org for a given company name."""
    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={company_name}&"
        f"language=en&"
        f"sortBy=publishedAt&"
        f"apiKey={NEWSAPI_API_KEY}&"
        f"pageSize=3"
    )
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('status') == 'ok' and data.get('totalResults', 0) > 0:
            headlines = [article['title'] for article in data['articles']]
            return {"news": headlines}
        else:
            return {"news": [f"No recent news found for {company_name}."]}
    except Exception as e:
        return {"news": [f"News fetch error: {str(e)}"]}


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
    get_recent_news,
    get_financial_highlights,
    get_company_profile
]

system_instruction = """
You are an expert AI stock analyst focused on large-cap Indian stocks.

When asked for 'top stocks' or 'top 3 stocks':
1. First use find_top_filtered_stocks to get candidate stocks filtered by market cap, RSI > 50, and price above EMA20.
2. For each filtered stock, use:
   - get_recent_news (with company name) to fetch latest news headlines
   - get_financial_highlights (with ticker) to get P/E, EPS, revenue growth
   - get_company_profile (with ticker) to understand the business
3. In your final output, you MUST include:
   - Stock ranking with reasoning
   - Key technical indicators (RSI, EMA20, price)
   - Financial highlights
   - Recent news headlines for each stock
   - Clear explanation of why each stock is recommended

Present the information in a structured, easy-to-read format with all the news headlines displayed for each stock.

For individual company queries, use the appropriate tools and always include recent news when available.
"""

model = genai.GenerativeModel(
    model_name='models/gemini-pro-latest',
    tools=agent_tools,
    system_instruction=system_instruction
)

if __name__ == "__main__":
    chat = model.start_chat(enable_automatic_function_calling=True)
    print("AI Stock Analyst ready. Ask for 'top 3 stocks' or company info. Type 'quit' to exit.")

    while True:
        user_input = input("\n> You: ").strip()
        if user_input.lower() == "quit":
            print("Goodbye!")
            break

        try:
            response = chat.send_message(user_input)
            print(f"\n> Agent: {response.text}")
        except Exception as e:
            print(f"\n> Agent: Error occurred: {e}")
