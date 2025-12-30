# Enhanced Stock Screening & Analysis Agent

I have upgraded the Agent's capabilities to perform deeper, multi-factor analysis and stock screening while providing visibility into its "thought process" on the console.

## Key Changes

### 1. Advanced Screening Indicators
The stock screener now analyzes **5 key indicators** instead of just 2:
- **RSI (Relative Strength Index)**: Identifies overbought/oversold conditions.
- **MACD (Moving Average Convergence Divergence)**: Detects trend changes and momentum.
- **Bollinger Bands**: Evaluating volatility and potential breakouts (squeezes).
- **Volume Spikes**: Confirms price moves with volume analysis.
- **EMA Trend**: existing trend confirmation.

### 2. New "Deep Analysis" Tool
I created a new powerful tool `deep_screen_and_analyze` that streamlines the workflow:
- **One-Step Execution**: Instead of calling 3 separate tools (Screen -> News -> Fundamentals) for every stock, this tool does it all in one highly efficient backend process.
- **"Mini 10" Ready**: It effectively screens a large pool of stocks (e.g., NIFTY 50/500) and returns the top `X` (e.g., 10) fully analyzed candidates as requested.
- **Holistic Scoring**: It combines technical scores with fundamental data and news sentiment.

### 3. Console "Thoughts"
To meet the requirement of seeing the Agent's "thoughts" without wasting tokens on generating text:
- The tools now emit real-time **[Agent Thought]** and **[Deep Analysis]** logs to the backend console.
- You will see lines like:
  ```text
  [Deep Analysis] Starting deep analysis for NIFTY 50 (Target: 10)...
  [Deep Analysis] Screening 50 stocks...
  [Tool] Screening complete. Found 20 top candidates.
  [Deep Analysis] Deep diving into top 20 candidates...
     [1/20] Analyzing RELIANCE (RELIANCE.NS)...
     [2/20] Analyzing TATASTEEL (TATASTEEL.NS)...
  ```

### 4. Smart Holding Period
- The analysis now respects the user's "holding period" (e.g., "x days of holding") by adjusting the historical data fetch and analysis window accordingly.

## How to Verify
1. Start the backend server (`python Backend/main.py`).
2. In the chat, ask:
   > "Screen top 10 stocks from NIFTY 50 for a 2 month holding period. Look for strong indicators."
3. **Watch the Terminal**: You should see the `[Deep Analysis]` logs appearing as the agent works.
4. **Result**: The Agent should return a detailed list of 10 stocks with Technicals, Fundamentals, and News summaries.
