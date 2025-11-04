<div align="center">

# AI Stock Analyst Platform

*Powered by Synance AI — Intelligent Trading for Indian Markets (NSE)*

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Visit_Platform-blue?style=for-the-badge)](https://stock-agent-774764824527.us-central1.run.app)
[![Google Cloud](https://img.shields.io/badge/Google_Cloud-Run-4285F4?style=for-the-badge&logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Zerodha API](https://img.shields.io/badge/Zerodha-Kite_API-00BFA5?style=for-the-badge&logo=zerodha&logoColor=white)](https://kite.trade/)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini AI](https://img.shields.io/badge/Gemini_2.5-Flash-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)

</div>

---

## 🧠 Overview

AI Stock Analyst Platform is a full-stack, AI-powered trading and analytics platform for Indian Stock Markets (NSE). It leverages Synance AI for technical analysis, portfolio optimization, and market news sentiment within a streamlined modern interface.

---

## 🚀 Features

| Feature | Description |
|:---|:---|
| 🧠 Synance AI Engine | Proprietary AI that fuses RSI, EMA, and news sentiment for actionable trading insights |
| ⚙️ Zerodha Integration | Live-trading using Kite API, authentication, portfolio sync, and order execution |
| 💬 Conversational Trading | Use natural language for trades and analytics |
| 📊 Intelligent Screening | Multi-index analysis (Nifty, Bank, IT, Auto, etc.), RSI & EMA screening |
| 📰 News Sentiment | Aggregates and scores news sentiment using NewsAPI and DuckDuckGo |
| 💼 Portfolio Optimization | AI-driven rebalancing and risk assessment |
| 💻 Real-Time UI | Tailwind CSS + Alpine.js, dark mode, streaming updates |
| ☁️ Cloud Native | Dockerized, Google Cloud Run and Firestore backend |

---

## 🌐 Live Platform

**Web:** [https://stock-agent-774764824527.us-central1.run.app](https://stock-agent-774764824527.us-central1.run.app)

**Try queries like:**
- "Analyze Reliance for swing trading"
- "Buy 10 shares of TCS"
- "Show my portfolio performance"
- "Find top 3 bullish IT stocks"

---

## 🧩 Technology Stack

| Layer       | Tools                                    |
|-------------|------------------------------------------|
| Frontend    | Alpine.js, Tailwind CSS, Firebase Auth   |
| Backend     | Flask, Gemini 2.5 Flash, yfinance, pandas, TA-Lib |
| AI Engine   | Synance AI Core (custom financial logic) |
| Database    | Firebase Firestore                       |
| Infra       | Docker, Google Cloud Run                 |
| Integration | Zerodha Kite Connect API                 |

---

## ⚙️ Installation & Setup

### Backend

git clone https://github.com/yourusername/ai-stock-analyst.git
cd ai-stock-analyst
pip install -r requirements.txt

text

**Main dependencies:**
- flask>=2.3.0
- flask-cors>=4.0.0
- google-generativeai>=0.3.0
- yfinance>=0.2.28
- firebase-admin>=6.2.0
- pandas>=2.0.0
- ta>=0.11.0
- duckduckgo-search>=3.9.0
- requests>=2.31.0
- gunicorn>=21.2.0
- cachetools>=5.3.3

### Frontend
- Alpine.js 3.x
- Tailwind CSS 3.x
- Firebase JS SDK v10+
- Inter Font (Google Fonts)

---

## 🔧 Configuration

### Environment Variables

export GOOGLE_APPLICATION_CREDENTIALS="/path/to/serviceAccountKey.json"
export GENIE_API_KEY="your-gemini-api-key"
export NEWSAPI_KEY="your-newsapi-key"
export ZERODHA_API_KEY="your-zerodha-api-key"
export ZERODHA_API_SECRET="your-zerodha-secret"

text

### Firebase Setup

1. Create Firebase project
2. Enable Auth (Email/Password)
3. Create Firestore DB
4. Download `serviceAccountKey.json`
5. Add firebaseConfig to `index.html`

---

## 🧱 Project Structure

ai-stock-analyst/
├── app.py # Flask backend entry
├── config.py # API keys & constants
├── indices.py # NSE index data
├── requirements.txt # Dependencies
├── Dockerfile # Docker setup
├── templates/
│ └── index.html # Frontend (Alpine.js)
├── static/
│ ├── css/ # Tailwind styles
│ └── js/ # Chat logic & Firebase config
├── utils/
│ ├── portfolio_manager.py# AI-based optimization
│ ├── trade_executor.py # Order simulation/execution
│ ├── news_fetcher.py # Sentiment analyzer
│ └── indicators.py # RSI, EMA, momentum tools
└── credentials/
└── serviceAccountKey.json # Firebase credentials

text

---

## 🧩 Key Functionality (Sample)

- Normalize ticker symbols
    ```
    def normalize_ticker(ticker_input: str) -> Optional[str]:
        """Converts 'Reliance' or 'reliance.ns' → 'RELIANCE.NS'"""
    ```
- Screen top stocks via RSI & EMA
    ```
    def screen_static_index(index_name="NIFTY 50", num_stocks=5):
        """Screens top performing stocks using RSI & EMA indicators"""
    ```
- Portfolio analytics
    ```
    def analyze_portfolio(holdings: list):
        """Calculates P&L, diversification, and sector-wise allocation"""
    ```
- Trade execution (paper/live)
    ```
    def execute_trade(ticker: str, qty: int, action: str, user_id: str):
        """Performs BUY/SELL operation (paper or live via Zerodha)"""
    ```
- News sentiment
    ```
    def get_news_sentiment(stock: str):
        """Fetches & classifies news as bullish/bearish/neutral"""
    ```

---

## ☁️ Deployment

### Docker Local

docker build -t ai-stock-analyst .
docker run -p 8080:8080
-v /path/to/serviceAccountKey.json:/app/credentials.json
-e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
ai-stock-analyst

text

### Google Cloud Run

gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy ai-stock-analyst
--source .
--platform managed
--region asia-south1
--allow-unauthenticated
--memory 2Gi
--timeout 300

text

---

## 🔮 Future Roadmap

- Real-time WebSocket streaming
- Strategy backtesting & trade replay
- Options & derivatives analytics
- Hindi & regional language support
- Mobile App (Flutter)
- Social/copy trading
- Full Zerodha live trading in production

---

## 👨‍💻 Author & Contact

**Samir Lade**  
Email: [ladesamir10@gmail.com](mailto:ladesamir10@gmail.com)  
Live Platform: [stock-agent-774764824527.us-central1.run.app](https://stock-agent-774764824527.us-central1.run.app)

---

<div align="center">
⭐ Star this repository if you like it!  
Built with ❤️ by Samir — Empowering Indian Traders through AI  
</div>