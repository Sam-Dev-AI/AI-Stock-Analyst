<div align="center">

# 🚀 AI Stock Analyst Platform (Agent v6.1)

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-Visit_Platform-blue?style=for-the-badge&logo=google-chrome&logoColor=white)](https://stock-agent-774764824527.us-central1.run.app)
  
*An Advanced, AI-Powered Trading Assistant for Indian Markets (NSE)*

[![Google Cloud](https://img.shields.io/badge/Google_Cloud-Run-4285F4?style=for-the-badge&logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Zerodha API](https://img.shields.io/badge/Zerodha-Kite_API-00BFA5?style=for-the-badge&logo=zerodha&logoColor=white)](https://kite.trade/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini AI](https://img.shields.io/badge/Gemini_2.5-Flash-8E75B2?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)

</div>

---

## 🧠 Overview

**AI Stock Analyst** is a cutting-edge financial analytics platform designed to democratize professional-grade trading insights. By fusing **Generative AI (Gemini 2.5)** with hard **Technical Analysis (TA-Lib)**, it offers real-time, actionable advice for the Indian Stock Market.

Whether you are a swing trader looking for opportunities or an investor balancing a portfolio, the AI Analyst acts as your 24/7 financial companion.

---

## 💡 What Problem Does It Solve?

In the fast-paced world of stock trading, **time** and **confidence** are your biggest assets. This platform solves critical challenges for modern traders:

1.  **Saves Massive Time**: Instead of spending hours manually analyzing charts, reading news, and calculating indicators, you can simply ask, *"Analyze Reliance"*. The agent instantly aggregates technical data, news sentiment, and fundamental metrics into a concise report.
2.  **Risk-Free Strategy Testing**: With the **Zerodha Sync** feature, you can import your *real* portfolio and specific holdings but trade in **Paper Mode**. This allows you to backtest strategies on your actual portfolio data without risking a single rupee.
3.  **Action-Oriented AI**: It's not just a chatbot; it's an agent. You don't just ask for advice—you command it. *"Buy 10 shares of Tata Motors"* executes the trade instantly (virtually or fast-tracked), bridging the gap between analysis and action.

---

## ✨ Key Features

### 🤖 Intelligent AI Core
- **Conversational Interface**: Chat naturally with the AI to get market insights, e.g., *"What is the support level for Tata Motors?"*.
- **Deep Technical Analysis**: Automatically calculates RSI, MACD, Bollinger Bands, and Moving Averages (EMA/SMA) to generate specific Buy/Sell/Hold ratings.
- **Smart Reasoning**: The AI explains *why* a stock is bullish or bearish, citing specific technical indicators.
- **Agent Actions**: Execute trades directly through conversation. Just say *"Buy 50 shares of Zomato"* or *"Sell my ITC holdings"*, and the agent handles the execution seamlessly.

### 🔌 Seamless Integration
- **Zerodha Kite Connect**: Sync your *real* live portfolio directly into the dashboard.
- **Live & Paper Trading**: Switch between practicing with virtual money (Paper Mode) or executing real orders via Zerodha.
- **News Sentiment**: Aggregates real-time news from across the web (NewsAPI + DuckDuckGo) to gauge market sentiment.

### 💻 Modern & Flexible Architecture
- **Dual Database Mode**: 
    - **Local Mode**: Runs entirely offline using a local JSON database—perfect for testing and development.
    - **Cloud Mode**: Scales effortlessly using Firebase Firestore/Auth for production.
- **Responsive UI**: A sleek, dark-themed interface built with **TailwindCSS** and **Alpine.js**, optimized for both Desktop and Mobile.
- **Interactive Charts**: Professional-grade Lightweight Charts for visual technical analysis.

---

## 🛠️ Installation & Setup Guide

Follow these steps to set up the project locally on your machine.

### 1. Prerequisites
- Python 3.9 or higher installed.
- Git installed.
- A code editor (VS Code recommended).

### 2. Clone the Repository
Open your terminal and run:
```bash
git clone https://github.com/Sam-Dev-AI/AI-Stock-Analyst.git
cd ai-stock-analyst
cd Backend
```

### 3. Install Dependencies
Install all required Python packages:
```bash
pip install -r requirements.txt
```

### 4. Configuration (`config.py`)
Open the `config.py` file in the `Backend` directory. You **must** configure the following settings for the app to work:

**A. Enable Local Development Mode:**
Make sure these two variables are set exactly as shown to avoid needing Firebase credentials immediately.
```python
DEBUG_MODE = True       # Enables detailed logs and local dev features
DB_MODE = "LOCAL"       # Uses local_database.json instead of Firebase
```

**B. Add Your API Keys:**
Replace the placeholder strings with your actual keys.
```python
# get a free key from https://ai.google.dev/
GENIE_API_KEY = "your_actual_gemini_api_key_here"

# (Optional) For Live Trading & Portfolio Sync
ZERODHA_API_KEY = "your_kite_connect_api_key"
ZERODHA_API_SECRET = "your_kite_connect_secret"

# (Optional) For News Sentiment
NEWSAPI_KEYS = ["your_newsapi_key_here"]
```


### 5. Zerodha Integration Setup (Optional)
To enable live portfolio sync and trading, you need a Zerodha Kite Connect account.

1.  **Sign Up for Kite Connect**:
    *   Go to [developers.kite.trade](https://developers.kite.trade/) and sign up.
    *   *Note: Zerodha charges ~₹2000 credits for API access.*

2.  **Create an App**:
    *   Click on "Create New App".
    *   **App Name**: `AI Stock Analyst` (or any name).
    *   **Zerodha Client ID**: Your actual Zerodha trading ID (e.g., `AB1234`).
    *   **Redirect URL**: `http://127.0.0.1:8080/api/zerodha/callback` (Important for Local Mode).
    *   **Postback URL**: You can leave this blank or use a placeholder.
    *   Click "Create".

3.  **Get Credentials**:
    *   Once created, you will see your **API Key** and **API Secret**.
    *   Copy these values.

4.  **Update Config**:
    *   Paste them into your `config.py`:
        ```python
        ZERODHA_API_KEY = "your_copied_api_key"
        ZERODHA_API_SECRET = "your_copied_api_secret"
        ```

### 6. Run the Application
Start the backend server:
```bash
python API_Server.py
```
*The server will start on `http://127.0.0.1:8080`.*

### 7. Access the App
Open your web browser and go to:
> **http://127.0.0.1:8080**

---

## 🧩 Technology Stack

| Component | Technology Used |
| :--- | :--- |
| **Frontend** | HTML5, Tailwind CSS, Alpine.js, Lightweight Charts |
| **Backend** | Python, Flask, Gunicorn |
| **AI Model** | Google Gemini 2.5 Flash |
| **Database** | TinyDB (Local) / Firebase Firestore (Cloud) |
| **Financial Data** | yfinance, NSEpy, Zerodha Kite Connect |
| **Search** | DuckDuckGo Search (DDGS), NewsAPI |

---

## ⚡ Quick Start Queries

Once the app is running, try asking the AI:

- *"Analyze Reliance Industries on a 1-day timeframe."*
- *"Show me my portfolio summary."*
- *"Find top bullish stocks in the IT sector."*
- *"What is the RSI of HDFC Bank?"*
- *"Buy 50 shares of Zomato at market price."* (Paper Mode)

---

## ⚠️ Disclaimer

This project is for **educational and research purposes only**. The analysis provided by the AI is based on technical indicators and should not be considered as financial advice. Always do your own research (DYOR) before trading with real money.

---

<div align="center">

**Built with ❤️ for Indian Traders**  
*Samir Lade*

</div>