"""
This file stores static constituent lists for common NSE indices.
These are used by the 'screen_static_index' tool in app.py for reliable screening.
The keys in STATIC_INDICES are normalized (uppercase) for easy matching.

Note: These lists represent the constituents at a specific point in time
and might require periodic updates based on official index rebalancing.
Lists are often less than 50 stocks for sectoral indices.
For large indices (Nifty 100/200/500), proxy lists are used for performance.
"""

# Nifty 50 (Top 50 Large Cap)
# Note: This is also defined in config.py, ensure consistency if changed.
NIFTY_50 = [
    'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'HINDUNILVR.NS',
    'BHARTIARTL.NS', 'ITC.NS', 'SBIN.NS', 'LICI.NS', 'HCLTECH.NS', 'KOTAKBANK.NS',
    'LT.NS', 'BAJFINANCE.NS', 'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS',
    'SUNPHARMA.NS', 'TITAN.NS', 'WIPRO.NS', 'ULTRACEMCO.NS', 'ADANIENT.NS',
    'ONGC.NS', 'NTPC.NS', 'JSWSTEEL.NS', 'TATAMOTORS.NS', 'POWERGRID.NS',
    'BAJAJFINSV.NS', 'TATASTEEL.NS', 'COALINDIA.NS', 'INDUSINDBK.NS', 'HINDALCO.NS',
    'TECHM.NS', 'GRASIM.NS', 'ADANIPORTS.NS', 'BRITANNIA.NS', 'CIPLA.NS',
    'EICHERMOT.NS', 'DRREDDY.NS', 'NESTLEIND.NS', 'HEROMOTOCO.NS', 'BAJAJ-AUTO.NS',
    'BPCL.NS', 'SHREECEM.NS', 'TATACONSUM.NS', 'UPL.NS', 'APOLLOHOSP.NS', 'DIVISLAB.NS',
    'M&M.NS', 'LTIM.NS' # LTIMindtree inclusion
]

# Nifty Bank (Currently 12 stocks)
NIFTY_BANK = [
    'HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS', 'KOTAKBANK.NS', 'AXISBANK.NS',
    'INDUSINDBK.NS', 'BANKBARODA.NS', 'PNB.NS', 'FEDERALBNK.NS', 'IDFCFIRSTB.NS',
    'AUBANK.NS', 'BANDHANBNK.NS'
]

# Nifty IT (Currently 10 stocks)
NIFTY_IT = [
    'TCS.NS', 'INFY.NS', 'HCLTECH.NS', 'WIPRO.NS', 'LTIM.NS', 'TECHM.NS',
    'OFSS.NS', 'PERSISTENT.NS', 'COFORGE.NS', 'MPHASIS.NS'
]

# Nifty Auto (Currently 15 stocks)
NIFTY_AUTO = [
    'M&M.NS', 'MARUTI.NS', 'TATAMOTORS.NS', 'BAJAJ-AUTO.NS', 'HEROMOTOCO.NS',
    'EICHERMOT.NS', 'TVSMOTOR.NS', 'BHARATFORG.NS', 'ASHOKLEY.NS', 'MRF.NS',
    'BOSCHLTD.NS', 'APOLLOTYRE.NS', 'BALKRISIND.NS', 'EXIDEIND.NS', 'AMARAJABAT.NS'
]

# Nifty FMCG (Currently 15+ stocks)
NIFTY_FMCG = [
    'HINDUNILVR.NS', 'ITC.NS', 'NESTLEIND.NS', 'BRITANNIA.NS', 'TATACONSUM.NS',
    'DABUR.NS', 'GODREJCP.NS', 'MARICO.NS', 'COLPAL.NS', 'PGHH.NS', 'VARUNBEV.NS',
    'UBL.NS', 'EMAMILTD.NS', 'RADICO.NS', 'JUBLFOOD.NS'
]

# Nifty Financial Services (Top ~20 stocks)
NIFTY_FINANCIAL_SERVICES = [
    'HDFCBANK.NS', 'ICICIBANK.NS', 'BAJFINANCE.NS', 'KOTAKBANK.NS', 'AXISBANK.NS',
    'SBIN.NS', 'BAJAJFINSV.NS', 'HDFCLIFE.NS', 'SBILIFE.NS', 'ICICIGI.NS',
    'INDUSINDBK.NS', 'SBICARD.NS', 'BAJAJHLDNG.NS', 'CHOLAFIN.NS', # HDFC removed post-merger
    'ICICIPRULI.NS', 'BANKBARODA.NS', 'PNB.NS', 'SRTRANSFIN.NS', 'MUTHOOTFIN.NS',
    'IDFCFIRSTB.NS'
]

# Nifty Pharma (Currently 20 stocks)
NIFTY_PHARMA = [
    'SUNPHARMA.NS', 'CIPLA.NS', 'DRREDDY.NS', 'DIVISLAB.NS', 'APOLLOHOSP.NS',
    'AUROPHARMA.NS', 'LUPIN.NS', 'ALKEM.NS', 'ZYDUSLIFE.NS', 'TORNTPHARM.NS',
    'IPCALAB.NS', 'GLENMARK.NS', 'BIOCON.NS', 'GLAND.NS', 'LAURUSLABS.NS',
    'NATCOPHARM.NS', 'GRANULES.NS', 'ERIS.NS', 'PEL.NS',
    'SYNGENE.NS'
]

# Nifty Metal (Currently 15 stocks)
NIFTY_METAL = [
    'TATASTEEL.NS', 'JSWSTEEL.NS', 'HINDALCO.NS', 'VEDL.NS', 'ADANIENT.NS',
    'JINDALSTEL.NS', 'NMDC.NS', 'SAIL.NS', 'HINDZINC.NS', 'APLAPOLLO.NS',
    'NATIONALUM.NS', 'RATNAMANI.NS', 'WELCORP.NS', 'MOIL.NS', 'JSL.NS'
]

# Nifty PSU Bank (Public Sector Banks - Currently 12 stocks)
NIFTY_PSU_BANK = [
    'SBIN.NS', 'BANKBARODA.NS', 'PNB.NS', 'CANBK.NS', 'UNIONBANK.NS',
    'INDIANB.NS', 'BANKINDIA.NS', 'UCOBANK.NS', 'CENTRALBK.NS', 'MAHABANK.NS',
    'IOB.NS', 'PSB.NS'
]

# Nifty Private Bank (Currently 10 stocks)
NIFTY_PRIVATE_BANK = [
    'HDFCBANK.NS', 'ICICIBANK.NS', 'KOTAKBANK.NS', 'AXISBANK.NS', 'INDUSINDBK.NS',
    'BANDHANBNK.NS', 'FEDERALBNK.NS', 'IDFCFIRSTB.NS', 'RBLBANK.NS', 'CSBBANK.NS'
]

# Nifty Realty (Currently 10 stocks)
NIFTY_REALTY = [
    'DLF.NS', 'GODREJPROP.NS', 'MACTEch.NS', # Macrotech Developers (Lodha)
    'PHOENIXLTD.NS', 'PRESTIGE.NS', 'OBEROIRLTY.NS', 'BRIGADE.NS',
    'IBREALEST.NS', 'SOBHA.NS', 'SUNTECK.NS'
]


# --- Nifty Broad Market Proxies (Using Top 50 from Nifty 50 as approximation) ---
# NOTE: Using dynamic fetching (get_index_constituents tool) is preferred for accuracy.
# These proxies allow the static tool to run but only screen top components.
NIFTY_BROAD_PROXY = NIFTY_50[:50] # Top 50 stocks as a general proxy


# --- Main dictionary for mapping user-friendly names to lists ---
# Keys are normalized (uppercase) for matching.
STATIC_INDICES = {
    "NIFTY 50": NIFTY_50,

    "NIFTY BANK": NIFTY_BANK,
    "BANK NIFTY": NIFTY_BANK,

    "NIFTY IT": NIFTY_IT,
    "IT NIFTY": NIFTY_IT,

    "NIFTY AUTO": NIFTY_AUTO,
    "AUTO NIFTY": NIFTY_AUTO,

    "NIFTY FMCG": NIFTY_FMCG,
    "FMCG NIFTY": NIFTY_FMCG,

    "NIFTY FINANCIAL SERVICES": NIFTY_FINANCIAL_SERVICES,
    "FINNIFTY": NIFTY_FINANCIAL_SERVICES,
    "FINANCIAL SERVICES NIFTY": NIFTY_FINANCIAL_SERVICES,

    "NIFTY PHARMA": NIFTY_PHARMA,
    "PHARMA NIFTY": NIFTY_PHARMA,

    "NIFTY METAL": NIFTY_METAL,
    "METAL NIFTY": NIFTY_METAL,

    "NIFTY PSU BANK": NIFTY_PSU_BANK,
    "PSU BANK NIFTY": NIFTY_PSU_BANK,

    "NIFTY PRIVATE BANK": NIFTY_PRIVATE_BANK,
    "PRIVATE BANK NIFTY": NIFTY_PRIVATE_BANK,

    "NIFTY REALTY": NIFTY_REALTY,
    "REALTY NIFTY": NIFTY_REALTY,

    # Broad Market Proxies (Using Nifty 50 base)
    "NIFTY 100": NIFTY_BROAD_PROXY,
    "NIFTY 200": NIFTY_BROAD_PROXY,
    "NIFTY 500": NIFTY_BROAD_PROXY, 
}           