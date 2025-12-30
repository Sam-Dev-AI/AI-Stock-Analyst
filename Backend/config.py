import os

# ============================================
# GENERAL SETTINGS
# ============================================
DEBUG_MODE = True# Set to False in production
DB_MODE = "LOCAL" # Options: 'local', 'firebase'
Local_API_URL = "http://127.0.0.1:8080"
Production_API_URL = "https://stock-agent-774764824527.us-central1.run.app" 

# ============================================
# Gemini API KEYS
# ============================================
GENIE_API_KEY ="Your API KEY"


# ============================================
# Database Configuration
# ============================================
# Determine the absolute path to the Backend/database directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB_FILE = os.path.join(BASE_DIR, 'database', 'local_database.json')

FIREBASE_CONFIG = {
    "apiKey": "Your API KEY",
    "authDomain": "your-project.firebaseapp.com",
    "projectId": "your-project-id",
    "storageBucket": "your-project.appspot.com",
    "messagingSenderId": "Your Sender ID",
    "appId": "Your App ID",
    "measurementId": "Your Measurement ID"
}

# ============================================
# FRONTEND API ENDPOINT
# ============================================

API_BASE_URL = Local_API_URL if DEBUG_MODE == True else "https://your-production-url.com"

# ============================================
# Zerodha API
# ============================================
ZERODHA_API_KEY = "Your Zerodha Key"
ZERODHA_API_SECRET = "Your Zerodha Secret"
ZERODHA_REDIRECT_URL = f"{Production_API_URL}/api/zerodha/callback"  if DEBUG_MODE == False else f"{Local_API_URL}/api/zerodha/callback"


# ============================================
# News API KEYS
# ============================================
#get from https://newsapi.org/
NEWSAPI_KEYS = [
"Your News API Key 1",
"Your News API Key 2"
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
GEMINI_MODEL_NAME = 'gemini-2.5-flash-lite'
MAX_CHAT_HISTORY = 20
CHAT_TITLE_LENGTH = 35
CHAT_TITLE_MAX_LENGTH = 100

# ============================================
# PRICING (Gemini 2.5 Flash-Lite)
# ============================================
GEMINI_INPUT_PRICE_PER_MILLION = 0.10
GEMINI_OUTPUT_PRICE_PER_MILLION = 0.40
INR_CONVERSION_RATE = 90 # Approx 1 USD = 89.5 INR

# ============================================
# PLANS CONFIGURATION
# ============================================
NEW_ACCOUNT_TOKEN_LIMIT = 100000 # Default limit for new accounts (1 Lakh)

PLANS = {
    "free": {
        "id": "free",
        "name": "Free Tier",
        "price": 0,
        "tokens": 100000,  # 1 Lakh
        "description": "Experience the power of AI analysis.",
        "features": ["1 Lakh Tokens", "Standard Access", "Community Support"]
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "price": 19,
        "tokens": 1000000,  # 10 Lakh
        "description": "Perfect for daily market updates.",
        "features": ["10 Lakh Tokens", "Fast Response", "Email Support"]
    },
    "plus": {
        "id": "plus",
        "name": "Plus",
        "price": 89,
        "tokens": 5000000,  # 50 Lakh
        "description": "For serious traders and analysts.",
        "features": ["50 Lakh Tokens", "Priority Access", "Priority Support"]
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price": 149,
        "tokens": 10000000,  # 1 Crore
        "description": "Unrestricted power for professionals.",
        "features": ["1 Crore Tokens", "Ultra Fast", "24/7 Priority Support"]
    }
}


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

SYSTEM_INSTRUCTION = """Role: Expert NSE Analyst Named Claroz.
Goal: Maximize returns, minimize risk.
Tone: Professional, data-driven, concise.
Context: Address user by name.
Zerodha: Call `sync_zerodha_portfolio_for_agent` on "sync"/"import".

1. **THINK FIRST (SUMMARY ONLY):** Before EVERY action, output a `<thought>` block.
   - **CONSTRAINT:** The thought must be a **Concise Narrative Summary** (Max 3-4 lines).
   - **FORBIDDEN:** Do NOT list stock details, prices, or indicators here. Do NOT repeat the tool output.
   - **GOAL:** Briefly explain the *deciding factor* for your top picks.
   - **Example:** `<thought>Market is Bullish (65% > 50EMA). Selected Adani Green due to major order win and strong RSI. Cholamandalam pushed to #2 due to volume breakout. Rejected others due to negative news.</thought>`

## 1. OUTPUT TEMPLATES

### Recommendations
"**Market:** [Insert 'market_trend' string provided by tool output]
**Top Picks ([Duration]):**

1. **[Ticker]** (₹[Price])
   • **Technicals:** [RSI] | [Trend] | [Volume] | [MACD]
   • **Why:**
     • **News:** [Explain IMPACT. e.g. "20% profit jump acts as a major catalyst for fresh buying."]
     • **Tech:** [Explain IMPLICATION. e.g. "RSI at 55 indicates healthy momentum with room to run."]
   • **Key Headlines:**
     • [Headline 1]
     • [Headline 2]

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

**CRITICAL:** Use '•' for lists Do not use '*' for listing. Use Indian Number System. NEVER output a block of text for "Why", use bullets."""

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