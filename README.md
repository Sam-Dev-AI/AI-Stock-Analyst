<!-- --------------------------------------------------------------------- -->
<!-- 🚀 AI STOCK ANALYST PLATFORM — README.md -->
<!-- Designed for Professional Presentation (Zerodha / Tech Recruiters) -->
<!-- --------------------------------------------------------------------- -->

<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/2/28/Zerodha_logo.svg" alt="Zerodha Logo" width="200"/>

# 💹 **AI Stock Analyst Platform**
### _Powered by Synance AI — Intelligent Trading for Indian Markets (NSE)_

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Visit_Platform-blue?style=for-the-badge)](https://stock-agent-774764824527.us-central1.run.app)
[![Google Cloud](https://img.shields.io/badge/Google_Cloud-Run-4285F4?style=for-the-badge&logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Zerodha API](https://img.shields.io/badge/Zerodha-Kite_API-00BFA5?style=for-the-badge&logo=zerodha&logoColor=white)](https://kite.trade/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini AI](https://img.shields.io/badge/Gemini_2.5-Flash-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)

</div>

---

## 🧠 Overview

**AI Stock Analyst Platform** is a full-stack, AI-powered **trading and analytics system** for the **Indian Stock Market (NSE)**.  
Built with **Flask**, **Firebase**, and **Gemini 2.5 Flash**, it leverages **Synance AI**, an autonomous trading intelligence engine combining **technical analysis**, **portfolio optimization**, and **news sentiment**.

The platform supports **paper trading** and **live Zerodha Kite API integration**, bridging simulation with real-world execution.

---

## 🧩 What Makes It Unique

| Feature | Description |
|:---|:---|
| **🧠 Synance AI Engine** | Proprietary AI core that merges RSI, EMA, and sentiment for actionable insights. |
| **⚙️ Zerodha Integration (Kite API)** | Live-trading ready system with authentication, portfolio sync, and order execution. |
| **💬 Conversational Trading** | Execute trades or get analysis via natural language commands. |
| **📊 Intelligent Screening** | Multi-index (Nifty, Bank, IT, Auto, etc.) analysis using RSI & EMA. |
| **📰 Sentiment Analysis** | Combines NewsAPI and DuckDuckGo for market sentiment scoring. |
| **💼 Portfolio Optimization** | AI-driven risk and rebalancing recommendations. |
| **💻 Real-Time UI** | Tailwind CSS + Alpine.js frontend with dark mode and streaming updates. |
| **☁️ Cloud Native** | Fully containerized with Google Cloud Run and Firestore backend. |

---

## 🌐 Live Platform

> **[https://stock-agent-774764824527.us-central1.run.app](https://stock-agent-774764824527.us-central1.run.app)**  
> _(Optimized for desktop, tablet, and mobile)_

**Try:**
"Analyze Reliance for swing trading"
"Buy 10 shares of TCS"
"Show my portfolio performance"
"Find top 3 bullish IT stocks"

yaml
Copy code

---

## ✨ Key Features

### 🤖 AI-Powered Insights
- Gemini 2.5 Flash (or any Gemini model) for financial reasoning  
- Synance AI combines sentiment, technical indicators & market data  
- Conversational control over portfolio and trade execution  

### 📊 Market Analysis & Screening
- Supports 15+ NSE indices  
- Recent News, RSI, EMA, momentum & trend analysis  
- Fetches live prices and recent news  

### 💼 Portfolio & Trading
- ₹10L paper trading wallet  
- Trade history, day P&L, and portfolio metrics  
- Zerodha integration for live order execution  
- AI-based risk/reward analysis  

### 💻 Frontend & UX
- Tailwind CSS + Alpine.js + Firebase Auth  
- Floating portfolio dashboard  
- Multi-chat thread management  
- Real-time updates & sleek UI animations  

---

## 🧱 Technology Stack

| Layer | Tools Used |
|:---|:---|
| **Frontend** | Alpine.js • Tailwind CSS • Firebase Auth |
| **Backend** | Flask • Gemini 2.5 Flash • yfinance • pandas • TA-Lib |
| **AI Engine** | Synance AI Core (custom financial logic) |
| **Database** | Firebase Firestore |
| **Infrastructure** | Docker • Google Cloud Run |
| **Integration** | Zerodha Kite Connect API |

---

## ⚙️ Requirements

### 🧩 Backend
```bash
flask>=2.3.0
flask-cors>=4.0.0
google-generativeai>=0.3.0
yfinance>=0.2.28
firebase-admin>=6.2.0
pandas>=2.0.0
ta>=0.11.0
duckduckgo-search>=3.9.0
requests>=2.31.0
gunicorn>=21.2.0
cachetools>=5.3.3
🌐 Frontend
Alpine.js 3.x

Tailwind CSS 3.x

Firebase JS SDK v10+

Inter Font (Google Fonts)

🔧 Configuration
1️⃣ Environment Variables
bash
Copy code
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/serviceAccountKey.json"
export GENIE_API_KEY="your-gemini-api-key"
export NEWSAPI_KEY="your-newsapi-key"
export ZERODHA_API_KEY="your-zerodha-api-key"
export ZERODHA_API_SECRET="your-zerodha-secret"
2️⃣ config.py
python
Copy code
GENIE_API_KEY = "your-gemini-api-key"
NEWSAPI_KEYS = [
    "newsapi-key-1",
    "newsapi-key-2",
    "newsapi-key-3"
]
ZERODHA_API_KEY = "your-zerodha-api-key"
ZERODHA_API_SECRET = "your-zerodha-secret"
3️⃣ Firebase Setup
Create Firebase project

Enable Auth (Email/Password)

Create Firestore DB (Production)

Download serviceAccountKey.json

Add firebaseConfig to frontend index.html

🧩 Project Structure
bash
Copy code
ai-stock-analyst/
├── app.py                      # Flask backend entry
├── config.py                   # API keys & constants
├── indices.py                  # NSE index data
├── requirements.txt            # Dependencies
├── Dockerfile                  # Docker setup
├── templates/
│   ├── index.html              # Main frontend (Alpine.js)
│   └── components/             # UI elements
├── static/
│   ├── css/                    # Tailwind styles
│   └── js/                     # Chat logic & Firebase config
├── utils/
│   ├── portfolio_manager.py    # AI-based optimization
│   ├── trade_executor.py       # Order simulation/execution
│   ├── news_fetcher.py         # Sentiment analyzer
│   └── indicators.py           # RSI, EMA, momentum tools
└── credentials/
    └── serviceAccountKey.json  # Firebase credentials
🔑 Core Functionalities
🔹 normalize_ticker()
python
Copy code
def normalize_ticker(ticker_input: str) -> Optional[str]:
    """Converts 'Reliance' or 'reliance.ns' → 'RELIANCE.NS'"""
🔹 screen_static_index()
python
Copy code
def screen_static_index(index_name="NIFTY 50", num_stocks=5):
    """Screens top performing stocks using RSI & EMA indicators"""
🔹 analyze_portfolio()
python
Copy code
def analyze_portfolio(holdings: list):
    """Calculates P&L, diversification, and sector-wise allocation"""
🔹 execute_trade()
python
Copy code
def execute_trade(ticker: str, qty: int, action: str, user_id: str):
    """Performs BUY/SELL operation (paper or live via Zerodha)"""
🔹 get_news_sentiment()
python
Copy code
def get_news_sentiment(stock: str):
    """Fetches & classifies news as bullish/bearish/neutral"""
☁️ Deployment
🐳 Docker
bash
Copy code
docker build -t ai-stock-analyst .
docker run -p 8080:8080 \
  -v /path/to/serviceAccountKey.json:/app/credentials.json \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  ai-stock-analyst
🌍 Google Cloud Run
bash
Copy code
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy ai-stock-analyst \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300
🔮 Future Enhancements
 Real-time WebSocket market streaming

 Strategy backtesting & trade replay

 Options & derivatives analytics

 Multi-language support (Hindi & regional)

 Mobile App (Flutter)

 Social/copy trading features

 Full live broker integration with Zerodha (production release)

👨‍💻 Author
Samir Lade

🌐 Live Platform: stock-agent-774764824527.us-central1.run.app

💻 GitHub: @Sam-Dev-AI

✉️ Email: ladesamir10@gmail.com

<div align="center">
⭐ Star this repository if you like it!
Built with ❤️ by Samir — Empowering Indian Traders through AI

⬆ Back to Top

</div> ```