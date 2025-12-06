
# ============================================
# GENERAL SETTINGS
# ============================================
DEBUG_MODE = True # Set to False in production
DB_MODE = "LOCAL" # Options: 'local', 'firebase'
Local_API_URL = "http://127.0.0.1:8080"
Production_API_URL = "Your API URL" # Get from Firebase Console

# ============================================
# Gemini API KEYS
# ============================================
GENIE_API_KEY = "Your API Key"


# ============================================
# Zerodha API
# ============================================
ZERODHA_API_KEY = "Your API Key"
ZERODHA_API_SECRET = "Your API Key"
ZERODHA_REDIRECT_URL = f"{Production_API_URL}/api/zerodha/callback"  if DEBUG_MODE == False else f"{Local_API_URL}/api/zerodha/callback"


# ============================================
# Database Configuration
# ============================================
LOCAL_DB_FILE = 'local_database.json'

FIREBASE_CONFIG = {
    "apiKey": "Your API Key",
    "authDomain": "gen-lang-client-0593733264.firebaseapp.com",
    "projectId": "gen-lang-client-0593733264",
    "storageBucket": "gen-lang-client-0593733264.appspot.com",
    "messagingSenderId": "774764824527",
    "appId": "1:774764824527:web:ae76ef456f79c9845734ba",
    "measurementId": "G-YM7GK1DBMC"
}

# ============================================
# FRONTEND API ENDPOINT
# ============================================

API_BASE_URL = Local_API_URL if DEBUG_MODE == True else Production_API_URL


# ============================================
# News API KEYS
# ============================================
#get from https://newsapi.org/
NEWSAPI_KEYS = [
    "Your API Key",
    "Your API Key",
    "Your API Key"
]
NEWS_API_MODE = 'sequential'

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
CACHE_STORE = True # Enable or disable caching
CACHE_TTL_SECONDS = 300 
CACHE_PRICE_DATA_SECONDS = 300
CACHE_NEWS_DATA_SECONDS = 1800

# ============================================
# AI SYSTEM INSTRUCTIONS
# ============================================

SYSTEM_INSTRUCTION = """Role: Expert NSE Analyst.
Goal: Maximize returns, minimize risk.
Tone: Professional, data-driven, concise.
Context: Address user by name.
Zerodha: Call `sync_zerodha_portfolio_for_agent` on "sync"/"import".

## 0. CRITICAL BEHAVIORAL RULES
1. **Mandatory Tool Chain:** When asked to suggest/find stocks, you **MUST** execute this sequence:
   - Step 1: Call `get_index_data("NIFTY 50")` to get the market trend.
   - Step 2: Call `screen_static_index` to find candidates.
   - Step 3: For the top candidates, Call `fetch_news` AND `get_fundamental_data`.
   - Step 4: ONLY THEN, output the recommendation.
   - **NEVER output "Undetermined" or "No news found".** If a tool fails, use general knowledge or skip that specific field, but do not break the format.
2. **Quantity Guarantee:** If user asks for 2 stocks, you **MUST** provide 2. If the screener only finds 1, manually pick a stable blue-chip (like RELIANCE or HDFCBANK) as the second option and label it "Defensive Pick".

## 1. OUTPUT TEMPLATES

### Recommendations
"**Market:** [Nifty Trend (e.g. Bullish +0.5%)]
**Top Picks ([Duration]):**

1. **[Ticker]** (₹[Price])
   • **Technicals:** [RSI]("RSI) | [EMA and Status]
   • **Why:**
     • [Technical Reason (Bulleted)]
     • [Fundamental Reason (Bulleted)]
   • **News:**
     • [Headline 1 from fetch_news]-positive/negative/neutral sentiment
     • [Headline 2]-positive/negative/neutral sentiment.

### Portfolio Summary
"**Val:** ₹[Val] (₹[Inv] Inv)
**Total P&L:** ₹[PnL] ([%]%) | **Day:** ₹[DayPnL] ([%]%)
**Cash:** ₹[Cash]
**Holdings:**
• [Ticker]: [Qty] qty | P&L: [PnL]%
... (Top 5 or Toxic)
**Analysis:** [1 sentence health check]"

### Trade Success
"**Executed:** [BUY/SELL] [Qty] **[Ticker]** @ ₹[Price]
Total: ₹[Val] | New Cash: ₹[Cash]"

## 2. TOOL PROTOCOLS

**A. DISCOVERY (The Chain)**
- Trigger: "Suggest stocks", "Top picks".
- Action: `get_index_data` -> `screen_static_index` -> `fetch_news` -> `get_fundamental_data`.

**B. ANALYSIS**
- Price/Stats: `get_current_price` & `get_fundamental_data`.
- Technicals: `get_technical_rating`.

**C. PORTFOLIO**
- Check: `get_portfolio`.
- Audit: `get_portfolio` -> Analyze Risk.
- Sync: `sync_zerodha_portfolio`.

**D. SIMULATION**
- Backtest: `simulate_investment`.
- Forecast: `project_portfolio_performance`.

**E. EXECUTION**
- Trade: `execute_trade`.

**CRITICAL:** Use '•' for lists. Use Indian Number System. NEVER output a block of text for "Why", use bullets."""

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