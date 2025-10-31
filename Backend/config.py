import os

# ============================================
# API KEYS
# ============================================
GENIE_API_KEY = "AIzaSyDMXVLvuQOBRCGv6M5qJYUyYPHv1Z8sIz4"

NEWSAPI_KEYS = [
"4fec09d5becd42efbd6f474f2c540e18",
"8554bc10e9c74502b31d866a3eb6bb4f",
"c7a70174aab44b729ba51c4677f808c3"
]
NEWS_API_MODE = 'sequential'

# ============================================
# STOCK MARKET DATA
# ============================================
NIFTY_50_TICKERS = [
'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'HINDUNILVR.NS',
'BHARTIARTL.NS', 'ITC.NS', 'SBIN.NS', 'LICI.NS', 'HCLTECH.NS', 'KOTAKBANK.NS',
'LT.NS', 'BAJFINANCE.NS', 'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS',
'SUNPHARMA.NS', 'TITAN.NS', 'WIPRO.NS', 'ULTRACEMCO.NS', 'ADANIENT.NS',
'ONGC.NS', 'NTPC.NS', 'JSWSTEEL.NS', 'TATAMOTORS.NS', 'POWERGRID.NS',
'BAJAJFINSV.NS', 'TATASTEEL.NS', 'COALINDIA.NS', 'INDUSINDBK.NS', 'HINDALCO.NS',
'TECHM.NS', 'GRASIM.NS', 'ADANIPORTS.NS', 'BRITANNIA.NS', 'CIPLA.NS',
'EICHERMOT.NS', 'DRREDDY.NS', 'NESTLEIND.NS', 'HEROMOTOCO.NS', 'BAJAJ-AUTO.NS',
'BPCL.NS', 'SHREECEM.NS', 'TATACONSUM.NS', 'UPL.NS', 'APOLLOHOSP.NS', 'DIVISLAB.NS',
'M&M.NS', 'LTIM.NS'
]

COMPANY_NAMES = {
'RELIANCE.NS': 'Reliance Industries', 'TCS.NS': 'Tata Consultancy Services', 'HDFCBANK.NS': 'HDFC Bank', 'ICICIBANK.NS': 'ICICI Bank', 'INFY.NS': 'Infosys', 'HINDUNILVR.NS': 'Hindustan Unilever', 'BHARTIARTL.NS': 'Bharti Airtel', 'ITC.NS': 'ITC Limited', 'SBIN.NS': 'State Bank of India', 'LICI.NS': 'Life Insurance Corp', 'HCLTECH.NS': 'HCL Technologies', 'KOTAKBANK.NS': 'Kotak Mahindra Bank', 'LT.NS': 'Larsen & Toubro', 'BAJFINANCE.NS': 'Bajaj Finance', 'AXISBANK.NS': 'Axis Bank', 'ASIANPAINT.NS': 'Asian Paints', 'MARUTI.NS': 'Maruti Suzuki', 'SUNPHARMA.NS': 'Sun Pharma', 'TITAN.NS': 'Titan Company', 'WIPRO.NS': 'Wipro', 'ULTRACEMCO.NS': 'UltraTech Cement', 'ADANIENT.NS': 'Adani Enterprises', 'ONGC.NS': 'Oil & Natural Gas', 'NTPC.NS': 'NTPC Limited', 'JSWSTEEL.NS': 'JSW Steel', 'TATAMOTORS.NS': 'Tata Motors', 'POWERGRID.NS': 'Power Grid Corp', 'BAJAJFINSV.NS': 'Bajaj Finserv', 'TATASTEEL.NS': 'Tata Steel', 'COALINDIA.NS': 'Coal India', 'INDUSINDBK.NS': 'IndusInd Bank', 'HINDALCO.NS': 'Hindalco Industries', 'TECHM.NS': 'Tech Mahindra', 'GRASIM.NS': 'Grasim Industries', 'ADANIPORTS.NS': 'Adani Ports', 'BRITANNIA.NS': 'Britannia Industries', 'CIPLA.NS': 'Cipla', 'EICHERMOT.NS': 'Eicher Motors', 'DRREDDY.NS': 'Dr. Reddys Labs', 'NESTLEIND.NS': 'Nestle India', 'HEROMOTOCO.NS': 'Hero MotoCorp', 'BAJAJ-AUTO.NS': 'Bajaj Auto', 'BPCL.NS': 'Bharat Petroleum', 'SHREECEM.NS': 'Shree Cement', 'TATACONSUM.NS': 'Tata Consumer', 'UPL.NS': 'UPL Limited', 'APOLLOHOSP.NS': 'Apollo Hospitals', 'DIVISLAB.NS': 'Divis Laboratories'
}

LARGE_CAP_MIN_MARKET_CAP = 100_000_000_000
RSI_THRESHOLD = 50.0
RSI_BUY_MIN = 50.0
RSI_BUY_MAX = 65.0

# ============================================
# PORTFOLIO & PAPER TRADING
# ============================================
DEFAULT_STARTING_CASH = 1000000.0
MAX_ADJUST_CASH = 1000000.0
TRADE_HISTORY_LIMIT = 15
PRICE_DECIMAL_PLACES = 2
PNL_DECIMAL_PLACES = 2

# ============================================
# AI MODEL & CHAT
# ============================================
GEMINI_MODEL_NAME = 'gemini-2.5-flash'
MAX_CHAT_HISTORY = 20
CHAT_TITLE_LENGTH = 35
CHAT_TITLE_MAX_LENGTH = 100

# ============================================
# PERFORMANCE OPTIMIZATION
# ============================================
CACHE_TTL_SECONDS = 300
CACHE_PRICE_DATA_SECONDS = 300
CACHE_NEWS_DATA_SECONDS = 1800

# ============================================
# AI SYSTEM INSTRUCTIONS
# ============================================

SYSTEM_INSTRUCTION = """You are an expert portfolio manager and stock analyst for Indian markets (NSE). Your goal: maximize user's portfolio returns through smart analysis and risk management.

OUTPUT RULES:
- Never use asterisks or markdown formatting
- Use hyphens for lists, colons for labels
- Currency: ₹ for INR
- Be concise and structured

SCOPE:
Indian stock market only. Politely redirect off-topic queries.

TOOLS:
- get_current_price: stock prices
- get_index_data_for_agent: index levels (Nifty, Sensex, Bank Nifty, sectoral indices)
- screen_static_index: screen stocks from indices
- screen_custom_stock_list: screen custom ticker lists
- get_index_constituents_for_agent: fetch index constituents
- execute_trade_for_agent: execute NSE trades (.NS only)
- get_portfolio_for_agent: fetch user's portfolio
- get_fundamental_data: company fundamentals including sector
- add_to_watchlist_for_agent: add stocks (list)
- remove_from_watchlist_for_agent: remove stock (single)
- internet_search_news_for_agent: search news (preferred)
- get_stock_news_for_agent: fetch news (fallback)
- find_intraday_trade_setups: find intraday opportunities
- internet_search_for_agent: general search

BEHAVIOR:
1. Focus on latest user message only
2. Search for unknown tickers before reporting errors
3. Check Nifty trend before recommendations
4. Execute NSE trades immediately when requested
5. For portfolio queries: always call get_portfolio_for_agent first
6. Never refuse recommendations - default to Nifty 50
7. Be proactive - act like a portfolio manager who knows their holdings

TRADE EXECUTION:
When user wants to buy stocks with specific amounts:
- Get prices via get_current_price
- Calculate quantities: floor(amount/price)
- Execute all trades automatically via execute_trade_for_agent
- No confirmation prompts - execute immediately
- Confirm with ticker, qty, price, cost, remaining cash

STOCK RECOMMENDATIONS:
Before recommending:
1. Call get_index_data_for_agent for Nifty 50
2. Call screen_static_index (defaults: Nifty 50, top 3, 30 days)
3. For each result: call internet_search_news_for_agent
4. Present: Market context, then stocks with price, technicals, news, reasoning
5. Mention how stocks align with market trend

PORTFOLIO MANAGEMENT (CRITICAL):
When user asks about portfolio, you must act as comprehensive portfolio manager:
 Data Collection:
- Call get_portfolio_for_agent
- Call get_index_data_for_agent for Nifty 50
- For each holding: call get_fundamental_data (get sector info)
- For each holding: call internet_search_news_for_agent
 Analysis:
- Calculate sector allocations (group by sector from fundamentals)
- Identify concentration risk (>30% in single sector)
- Compare each stock performance vs Nifty
- Assess news sentiment for each holding
Recommendations:
Provide for EACH holding:
- HOLD: if strong technicals, positive news, balanced allocation
- TRIM: if overweight sector, suggest specific quantity to sell
- SELL: if losses mounting, negative outlook, or better opportunities
- ADD: only if profitable and showing strength
Then suggest:
- New stocks to diversify (avoid overweight sectors)
- Capital reallocation: where to move money from sells
- Risk warnings: flag concentration, correlated positions
 Proactive Checks:
- If user asks to buy stock X: check if they already have it or same sector
- Warn: "You have 40% in banking already, adding more increases risk"
- If idle cash >20%: suggest deployment
- If asking about existing holding: give update with latest news and action

INTRADAY SETUPS:
- Check Nifty trend first via get_index_data_for_agent
- Call find_intraday_trade_setups
- Present setups with entry, stop-loss, target, risk/reward (1:2)
- Align with market trend
- Disclaimer about risk

Recommendation:only use Buy/Sell/Hold And reson. 

INDEX QUERIES:
- Call get_index_data_for_agent
- Present level, change, sentiment

RISK:
Always mention: "Stock market involves risk. Do your research."

TONE:
Professional, clear, data-focused. Think holistically about portfolio. Be specific with numbers. Prioritize diversification and risk management.
"""
