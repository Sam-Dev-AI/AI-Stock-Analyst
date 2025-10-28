AI Stock Analyst Platform

<div align="center">
[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Visit_Platform-blue?https://your-app-name-xxxxxxxxxx.io/badge/Google_Cloud-Run-4285F4?style=for-the-badge&logo=google-cloud&logoColorg.shields.io/badge/Python-3.9+-3776AB?style=for-theps://img.shields.io/badge/Flask-2.3+-000000?style=for-thettps://img.shields.io/badge/Gemini-2.5_Flash-8E75B2?style=for-the-badge&logo=google& the Platform: https://stock-agent-774764824527.us-central1.run.app**

AI-Powered Stock Analysis & Paper Trading for the Indian Stock Market (NSE)

Features - Installation - Deployment - Documentation

</div>

🚀 Project Summary
A sophisticated AI-powered stock analysis and paper trading platform built for the Indian stock market (NSE). This full-stack application combines real-time market data, advanced technical analysis, AI-driven recommendations, and an interactive trading interface with Firebase-backed portfolio management.​

The platform leverages Google's Gemini AI to provide intelligent stock analysis, screening, and conversational trading assistance through a modern web interface with authentication, multi-chat management, and a comprehensive portfolio dashboard.

✨ Key Features
🤖 AI-Powered Analysis
Conversational AI Agent powered by Gemini 2.5 Flash with specialized financial knowledge​

Smart ticker normalization with fuzzy matching for company names and tickers​

Natural language trading - execute trades, screen stocks, and get recommendations via chat​

Automated news sentiment analysis using DuckDuckGo and NewsAPI integration​

📊 Technical Analysis & Screening
Multi-index screening with support for 15+ NSE indices (Nifty 50, Bank Nifty, IT, Auto, Pharma, etc.)​

Technical indicators: RSI, EMA, price momentum analysis​

Custom stock list screening with configurable parameters​

Intelligent fallback mechanisms for obscure index constituent fetching​

💼 Portfolio Management
Paper trading system with ₹10 lakh starting capital​

Real-time portfolio tracking with live P&L calculations​

Day P&L tracking with automatic daily resets​

Trade history with detailed performance metrics​

Watchlist management for monitoring favorite stocks​

💻 Modern Web Interface
Responsive design with mobile-first approach​

Firebase Authentication with email/password sign-in​

Multi-chat management with rename and delete capabilities​

Floating portfolio window with minimize/maximize controls​

Real-time message streaming with typing indicators​

Dark mode UI with gradient accents and smooth animations​

🛠️ Technology Stack
Backend
Framework: Flask (Python web framework)​

AI Model: Google Gemini 2.5 Flash via google-generativeai​

Market Data: yfinance for NSE stock prices and fundamentals​

Database: Firebase Firestore (NoSQL document database)​

Technical Analysis: ta library (RSI, EMA indicators)​

News Sources: DuckDuckGo Search (ddgs) + NewsAPI fallback​

Data Processing: pandas for time-series analysis​

Frontend
Framework: Alpine.js for reactive components​

Styling: Tailwind CSS with custom gradients​

Authentication: Firebase Auth SDK (v10.7.1)​

Icons: Inline SVG icons​

Fonts: Google Fonts (Inter)​

Infrastructure
Deployment: Google Cloud Run (containerized deployment)​

Containerization: Docker​

CORS Handling: Flask-CORS​

Caching: In-memory caching with TTL (5-30 min)​

📋 Requirements
Core Dependencies
python
# Backend
flask>=2.3.0
flask-cors>=4.0.0
google-generativeai>=0.3.0
yfinance>=0.2.28
firebase-admin>=6.2.0
pandas>=2.0.0
ta>=0.11.0
duckduckgo-search>=3.9.0
requests>=2.31.0
API Keys Required
Google Gemini API Key - For AI analysis (configured in config.py)​

NewsAPI Keys (3x) - For financial news fallback​

Firebase Project Credentials - For authentication and database​

System Requirements
Python: 3.9+

Node.js: Not required (frontend uses CDN resources)​

Memory: 2GB+ RAM recommended for concurrent analysis

Storage: 500MB for dependencies

🚀 Installation & Setup
1. Clone Repository
bash
git clone <your-repo-url>
cd ai-stock-analyst
2. Install Python Dependencies
bash
pip install -r requirements.txt
3. Configure Environment Variables
Create a config.py file with your API keys (or set environment variables):

python
# API Keys
GENIE_API_KEY = "your-gemini-api-key"
NEWSAPI_KEYS = [
    "your-newsapi-key-1",
    "your-newsapi-key-2",
    "your-newsapi-key-3"
]

# Firebase (or use GOOGLE_APPLICATION_CREDENTIALS env var)
# Set environment variable:
# export GOOGLE_APPLICATION_CREDENTIALS="path/to/serviceAccountKey.json"
4. Firebase Setup
Create a Firebase project at Firebase Console

Enable Authentication (Email/Password provider)

Create a Firestore Database in production mode

Download service account key from Project Settings → Service Accounts

Set the path as environment variable:

bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-firebase-key.json"
5. Update Frontend Configuration
In index.html, update the Firebase config (lines from your paste-2.txt):

javascript
const firebaseConfig = {
    apiKey: "your-firebase-api-key",
    authDomain: "your-project.firebaseapp.com",
    projectId: "your-project-id",
    // ... other config
};
6. Run Locally
bash
python app.py
The application will start on http://127.0.0.1:8080 (or port specified in your app.py).

🐳 Docker Deployment
Build Docker Image
bash
docker build -t ai-stock-analyst .
Run Container
bash
docker run -p 8080:8080 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  -v /path/to/local/credentials.json:/app/credentials.json \
  ai-stock-analyst
☁️ Google Cloud Run Deployment
Prerequisites
Google Cloud SDK installed (gcloud CLI)

Google Cloud project with billing enabled

Cloud Run API enabled

Deploy to Cloud Run
bash
# Authenticate
gcloud auth login

# Set project
gcloud config set project YOUR_PROJECT_ID

# Deploy (automatic Docker build)
gcloud run deploy ai-stock-analyst \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GENIE_API_KEY=your-key \
  --set-env-vars GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  --memory 2Gi \
  --timeout 300
Important: Store Firebase credentials as a secret in Google Secret Manager and mount it to the container for production deployments.

🔧 Detailed Architecture & Working
System Architecture
text
┌─────────────────┐
│   User Browser  │ (Alpine.js + Tailwind CSS)
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  Firebase Auth  │ (Authentication Layer)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         Flask Backend (app.py)          │
│  ┌───────────────────────────────────┐  │
│  │  REST API Endpoints               │  │
│  │  - /health, /api/chat             │  │
│  │  - /api/portfolio, /api/watchlist │  │
│  │  - /api/chats, /api/trade         │  │
│  └───────────────┬───────────────────┘  │
│                  │                       │
│  ┌───────────────▼───────────────────┐  │
│  │  AI Agent (Gemini 2.5 Flash)     │  │
│  │  - Tool calling & function exec   │  │
│  │  - Context-aware responses        │  │
│  └───────────────┬───────────────────┘  │
│                  │                       │
│  ┌───────────────▼───────────────────┐  │
│  │  Tool Functions                   │  │
│  │  - get_current_price()            │  │
│  │  - screen_static_index()          │  │
│  │  - execute_trade()                │  │
│  │  - internet_search_news()         │  │
│  │  - get_portfolio()                │  │
│  └───────────────┬───────────────────┘  │
└──────────────────┼───────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ yfinance │ │ Firestore│ │   DDGS   │
│   NSE    │ │Portfolio │ │  Search  │
└──────────┘ └──────────┘ └──────────┘
Core Workflow
1. User Authentication​
User signs up/logs in via Firebase Auth

Auth state persists in browser local storage

currentUser.uid becomes the user identifier for all backend operations

2. Chat Message Flow​
text
User Input → Frontend validates → POST /api/chat
                                     │
                                     ▼
                    Flask extracts user_id from token
                                     │
                                     ▼
                    Creates AI agent with function tools
                                     │
                                     ▼
                    Gemini processes with tool calling
                                     │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            Tool calls executed          Response generated
            (price fetch, trade,                  │
             news search, etc.)                   │
                    │                              │
                    └───────────────┬──────────────┘
                                    ▼
                    Response saved to Firestore
                                    │
                                    ▼
                    JSON response to frontend
                                    │
                                    ▼
                    Message rendered in chat UI
3. Stock Screening Logic​
When user asks "recommend stocks from Nifty 50":

Primary Path: screen_static_index("NIFTY 50")

Checks static list in indices.py​

Downloads historical data via yfinance

Calculates RSI & EMA indicators

Filters stocks meeting criteria (RSI 50-65, Price > EMA)

Returns top N stocks sorted by RSI

Fallback Path (for obscure indices):

get_index_constituents() → NSE API attempt

If NSE fails → DuckDuckGo search for constituents

AI extraction of tickers from search results

screen_custom_stock_list() with extracted tickers

News Enrichment:

For each screened stock → internet_search_news()

Sentiment analysis of headlines

Combined with technical reasoning in final recommendation

4. Portfolio Management​
Data Model: Firestore collections

text
users/{userId}/
  ├─ portfolio/{ticker} (holdings)
  ├─ watchlist/{ticker}
  ├─ chats/{chatId}/
  │   └─ messages/{messageId}
  └─ trade_history/{tradeId}
Day P&L Calculation:

python
day_start_portfolio_value = cash + holdings_value (at market open)
current_portfolio_value = cash + holdings_value (live)
day_pnl = current_portfolio_value - (day_start + net_cash_flow_today)
Trade Execution:

Validate ticker (must be .NS)

Get live price via yfinance

Check sufficient funds/shares

Update Firestore holdings & cash atomically

Record in trade history

5. Caching Strategy​
Price data: 5 min TTL (reduce yfinance API hits)

News results: 30 min TTL (DDGS + NewsAPI)

Index constituents: 1 hour TTL

In-memory dictionary cache with timestamp expiry

📁 Project Structure
text
ai-stock-analyst/
├── app.py                 # Main Flask application
├── config.py              # Configuration & API keys
├── indices.py             # Static index constituent lists
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container configuration
├── .gcloudignore          # Cloud deployment ignore rules
├── templates/
│   └── index.html         # Main web interface (Alpine.js app)
├── static/                # (Optional) Static assets
└── credentials/
    └── serviceAccountKey.json  # Firebase credentials (gitignored)
🔑 Key Functions Explained
Ticker Normalization​
python
def normalize_ticker(ticker_input: str) -> Optional[str]:
    """
    Converts user input like "Reliance", "RELIANCE", "reliance.ns"
    to standardized "RELIANCE.NS" format
    
    Handles:
    - Exact matches in NIFTY_50
    - Company name lookups
    - Fuzzy partial matching
    - .NS suffix addition
    """
Stock Screening​
python
def screen_static_index(index_name="NIFTY 50", num_stocks=3, 
                       duration_days=30, prefer_buy=False):
    """
    Multi-step screening:
    1. Load pre-defined ticker list from indices.py
    2. Download historical price data (yfinance bulk download)
    3. Calculate RSI (14-period) and EMA (duration_days window)
    4. Filter: RSI in range & Price > EMA & market_cap > 100B
    5. Sort by RSI descending, return top N
    """
AI Agent Setup​
python
# Inside /api/chat endpoint
model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=[
        get_current_price_for_agent,
        execute_trade_for_agent,
        get_portfolio_for_agent,
        screen_static_index_for_agent,
        internet_search_news_for_agent,
        # ... 10+ more tool functions
    ],
    system_instruction=SYSTEM_INSTRUCTION  # 500+ line prompt
)

chat = model.start_chat(history=chat_history_from_firestore)
response = chat.send_message(user_message)
Portfolio P&L Tracking​
python
def get_portfolio(user_id):
    """
    Calculates:
    - Total invested value (sum of avg_price * quantity)
    - Current holdings value (live_price * quantity)
    - Total P&L (current - invested)
    - Day P&L (current_value - day_start_value - net_cash_flows)
    
    Uses bulk price fetching for efficiency
    """
🎯 Usage Examples
1. Get Stock Price
User: "What's the current price of Reliance?"

AI Response:

text
Reliance Industries (RELIANCE.NS)
- Price: ₹2,456.30
- Change Today: ₹+12.50 (+0.51%)
- Day Range: ₹2,440.00 - ₹2,465.80
- Previous Close: ₹2,443.80
- Note: This is an NSE listed stock.
2. Screen Top Stocks
User: "Find top 3 stocks from Nifty Bank"

AI Response:

text
Top Stocks Screened: NIFTY BANK
- Criteria: RSI 50-65, Price > 30-day EMA, Stocks Requested: 3

1. HDFC Bank (HDFCBANK.NS)
 - Price: ₹1,650.25
 - Technicals: RSI 62.3 | Price > EMA (₹1,630.50)
 - News: HDFC Bank announces strong Q4 results with 18% YoY growth.
 - Reasoning: Meets criteria with strong technicals (RSI 62.3) and Positive recent news.

2. ICICI Bank (ICICIBANK.NS)
 - Price: ₹1,125.80
 - Technicals: RSI 58.7 | Price > EMA (₹1,110.00)
 - News: ICICI Bank expands digital lending portfolio.
 - Reasoning: Meets criteria with good technicals (RSI 58.7), recent news appears Positive.

...
3. Execute Trade
User: "Buy 10 shares of TCS"

AI Response:

text
Trade Confirmed: BUY
- Ticker: TCS.NS
- Quantity: 10
- Price: ₹3,842.50
- Total Cost: ₹38,425.00
- Remaining Cash: ₹961,575.00
4. Portfolio Analysis
User: "Show my portfolio and suggest what to sell"

AI Response (combines tools):

text
Portfolio Summary
- Total Value: ₹1,045,320.00
- Total Invested: ₹1,012,500.00
- Overall P&L: ₹32,820.00 (+3.24%)
- Day's P&L: ₹5,240.00 (+0.50%)
- Available Cash: ₹450,000.00

Holdings (3):
- TCS.NS: 10 shares @ ₹3,850.00 (Total P&L: ₹+75.00)
- RELIANCE.NS: 5 shares @ ₹2,460.00 (Total P&L: ₹+20.00)
- INFY.NS: 20 shares @ ₹1,520.00 (Total P&L: ₹-100.00)

--- Analysis ---

Analysis: Infosys (INFY.NS)
- Current Price: ₹1,515.00
- Recommendation: Consider Selling
- Rationale: Stock showing weakness with negative P&L. Recent news indicates margin pressure...
- News Summary: Infosys faces client ramp-down concerns...

(Analysis continues for each holding)
⚙️ Configuration Options
In config.py​
python
# Portfolio Settings
DEFAULT_STARTING_CASH = 1000000.0  # ₹10 lakh starting capital
MAX_ADJUST_CASH = 1000000.0        # Max cash adjustment allowed

# Cache Settings
CACHE_TTL_SECONDS = 300            # 5 min default cache
CACHE_PRICE_DATA_SECONDS = 300     # Price data cache
CACHE_NEWS_DATA_SECONDS = 1800     # 30 min news cache

# AI Model
GEMINI_MODEL_NAME = 'gemini-2.5-flash'  # Can switch to gemini-pro
MAX_CHAT_HISTORY = 20                    # Messages sent to AI as context

# Technical Analysis
RSI_BUY_MIN = 50.0                 # Minimum RSI for buy recommendation
RSI_BUY_MAX = 65.0                 # Maximum RSI (avoid overbought)
LARGE_CAP_MIN_MARKET_CAP = 100_000_000_000  # ₹100B minimum
🐛 Troubleshooting
Common Issues
"Firestore not available" Error

Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set

Verify service account key has Firestore permissions

"yfinance download empty" Warning

NSE market might be closed (use fallback to info pricing)

Check ticker format (must end in .NS)

"NewsAPI rate limited"

Configured to auto-rotate between 3 API keys

Falls back to DuckDuckGo search if all keys exhausted

"Index not in static list" Error

System attempts NSE API + DDGS fallback automatically

Add custom indices to indices.py for faster screening

Chat history not loading

Check Firestore security rules allow authenticated reads

Verify user is properly authenticated (check browser console)

📊 Performance Optimization
Bulk Price Fetching: Uses yfinance.download() with multiple tickers to reduce API calls​

Strategic Caching: Different TTLs for volatile (price) vs static (news) data​

Lazy Loading: Portfolio data fetched only when window opened​

Debounced Auto-resize: Textarea resizing optimized to prevent layout thrashing​

Index Proxies: Large indices (Nifty 500) use top 50 subset for faster screening​

🔒 Security Considerations
API Keys: Should be environment variables, never committed to git

Firebase Rules: Configure Firestore security rules:

javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
CORS: Currently allows all origins (configure for production)​

Input Validation: Ticker normalization prevents injection​

Token Verification: Backend should verify Firebase ID tokens (add middleware)

🚧 Future Enhancements
 Real-time WebSocket price streaming

 Options & derivatives analysis

 Advanced charting with TradingView integration

 Backtesting engine for strategies

 Multi-language support (Hindi, regional languages)

 Mobile app (React Native/Flutter)

 Social trading features (copy trading)

 Integration with real broker APIs (Zerodha, Upstox)

📄 License
[Specify your license - e.g., MIT, Apache 2.0]

👨‍💻 Author
Your Name

GitHub: @yourusername

LinkedIn: Your Profile

Email: your.email@example.com