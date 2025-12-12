import os
import config
import re
import time
from datetime import datetime
import google.generativeai as genai
import yfinance as yf
import traceback
from typing import Optional, List
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_session import Session
import firebase_admin
from firebase_admin import credentials, firestore, auth

# Import all tools
from tools import * 
import tools # Access tools module directly if needed

# --- Flask App Setup & API Endpoints ---
app = Flask(__name__, template_folder='templates', static_folder='templates/static')
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_development_secret_key')
app.config['SESSION_TYPE'] = 'filesystem' 
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache') # Ensure absolute path to cache based on file location
Session(app)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Authentication Decorator
def auth_required(f):
    def decorated_function(*args, **kwargs):
        if config.DEBUG_MODE: return f(*args, **kwargs)
        
        auth_header = request.headers.get('Authorization')
        if not auth_header: return jsonify({"error": "No Authorization header"}), 401
        
        try:
            id_token = auth_header.split('Bearer ')[-1]
            if config.DB_MODE == 'LOCAL':
                # In local mode, we trust the client-side ID (or implement simple check)
                pass
            else:
                decoded_token = auth.verify_id_token(id_token)
                request.user_id = decoded_token['uid']
        except Exception as e:
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 401
            
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

#--- Web Routes ---
@app.route('/')
def index(): 
    return render_template('landing.html')

@app.route('/app')
def app_route():
    return render_template('index.html')

@app.route('/auth/action')
def auth_action_route():
    return render_template('auth-action.html')

# Legacy route aliases (optional, but good for safety if user typed them manually)
@app.route('/reset-password')
def reset_password_route():
    return redirect(url_for('auth_action_route', mode='resetPassword', **request.args))

@app.route('/verify-email')
def verify_email_route():
    return redirect(url_for('auth_action_route', mode='verifyEmail', **request.args))


# --- API Endpoints ---
@app.route('/api/portfolio/<user_id>', methods=['GET'])
@auth_required
def get_portfolio_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try: return jsonify(get_portfolio(user_id))
    except Exception as e: print(f"[Error] API Error /portfolio/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

# Trade History Endpoint
@app.route('/api/history/<user_id>', methods=['GET'])
@auth_required
def get_trade_history_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        history_data = db.get_history(user_id, limit=config.TRADE_HISTORY_LIMIT)
        
        # Format timestamps
        formatted_history = []
        for item in history_data:
            if 'timestamp' in item and hasattr(item['timestamp'], 'isoformat'):
                item['timestamp'] = item['timestamp'].isoformat()
            formatted_history.append(item)
            
        return jsonify(formatted_history)
    except Exception as e: 
        print(f"[Error] API Error /history/{user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500
    
# Adjust Cash Endpoint
@app.route('/api/adjust-cash/<user_id>', methods=['POST'])
@auth_required
def adjust_cash_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        if data is None: return jsonify({"error": "Invalid JSON body."}), 400
        
        new_cash_input = data.get('cash')
        
        try:
            new_cash = float(new_cash_input)
        except (ValueError, TypeError):
             print(f"[Error] Invalid cash input type: {type(new_cash_input)} value: {new_cash_input}")
             return jsonify({"error": "Invalid cash format."}), 400
             
        if not (0 <= new_cash <= config.MAX_ADJUST_CASH):
            return jsonify({"error": f"Invalid cash amount (0-{config.MAX_ADJUST_CASH:,.0f})."}), 400
            
        user_data = db.get_user(user_id)
        if not user_data:
            return jsonify({"error": "User not found"}), 404
            
        db.update_user_cash(user_id, new_cash)
        
        print(f"[Cash] Cash adjusted for {user_id} to ₹{new_cash:,.2f}")
        
        return jsonify({"success": True, "new_cash": round(new_cash, config.PRICE_DECIMAL_PLACES)})

    except Exception as e:
        print(f"[Error] Adjust Cash Error {user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Trade Execution Endpoint
@app.route('/api/trade/<user_id>', methods=['POST'])
@auth_required
def trade_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Invalid JSON body."}), 400
        ticker, action = data.get('ticker'), data.get('action'); qty_in = data.get('quantity')
        if not all([ticker, qty_in, action]): return jsonify({"error": "Missing fields."}), 400
        try: qty = int(qty_in)
        except (ValueError, TypeError): return jsonify({"error": "Quantity not whole number."}), 400
        if not isinstance(action, str) or action.upper() not in ['BUY', 'SELL']: return jsonify({"error": "Action must be 'BUY' or 'SELL'."}), 400
        if not isinstance(ticker, str): return jsonify({"error": "Ticker must be string."}), 400
        
        result = execute_trade(user_id, ticker, qty, action)
        
        status = 500
        if result.get("error"):
            msg = result.get("message", "")
            if "Insufficient funds" in msg or "not found" in msg or "Invalid" in msg or "shares" in msg: status = 400
            else: status = 500
            return jsonify(result), status
        else:
            status = 200
            return jsonify(result), status
    except Exception as e:
        print(f"[Error] API Error /trade/{user_id} PRE-EXECUTION: {traceback.format_exc()}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# Stock Price Endpoint
@app.route('/api/stock/price/<ticker>')
def get_stock_price_endpoint(ticker):
    try: 
        price_data = get_current_price(ticker)
        if price_data.get("error"):
            return jsonify(price_data), 404
        return jsonify(price_data)
    except ValueError as ve: return jsonify({"error": str(ve)}), 404
    except Exception as e: print(f"[Error] API Error /stock/price/{ticker}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500

# Watchlist Endpoints
@app.route('/api/watchlist/<user_id>', methods=['GET'])
@auth_required
def get_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        tickers = db.get_watchlist(user_id)
        
        if not tickers: return jsonify([])
        
        details = []
        prices = get_bulk_live_prices(tickers)
        
        infos = {}
        max_w = min(10, len(tickers) if len(tickers) > 0 else 1)  
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_ticker = {executor.submit(get_ticker_info, t): t for t in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    infos[ticker] = future.result()
                except Exception as e:
                    print(f"      [Warning] Parallel watchlist fetch error for {ticker}: {e}")
                    infos[ticker] = None

        for t in tickers:
            cp = prices.get(t)
            info = infos.get(t)
            
            if cp is None or info is None:  
                print(f"      [Warning] Missing watchlist data {t}.")
                details.append({"ticker": t, "price": "N/A", "change": "N/A", "dayRange": "N/A"})
                continue
            try:
                pc = info.get('previousClose', cp)
                change = ((cp - pc) / pc) * 100 if pc and pc != 0 else 0
                dl, dh = info.get('dayLow', cp), info.get('dayHigh', cp)
                
                item = {
                    "ticker": t, 
                    "price": round(cp, config.PRICE_DECIMAL_PLACES), 
                    "change": round(change, 2),
                    "dayRange": f"₹{dl:.{config.PRICE_DECIMAL_PLACES}f} - ₹{dh:.{config.PRICE_DECIMAL_PLACES}f}" if dl and dh else "N/A"
                }
                details.append(item)
            except Exception as e:  
                print(f"      [Error] Error processing watchlist {t}: {e}")
                details.append({"ticker": t, "price": "Error", "change": "Error", "dayRange": "Error"})
                
        return jsonify(details)
    except Exception as e:  
        print(f"\n[Error] CRITICAL WATCHLIST GET ERROR {user_id}: {traceback.format_exc()}\n")
        return jsonify({"error": str(e)}), 500
    
#watchlist Add Endpoint
@app.route('/api/watchlist/<user_id>', methods=['POST'])
@auth_required
def add_to_watchlist_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json();
        if not data or 'tickers' not in data or not isinstance(data['tickers'], list): return jsonify({"error": "Invalid request: JSON with 'tickers' list needed."}), 400
        result = add_to_watchlist(user_id, data['tickers'])
        return jsonify(result), 400 if "error" in result else 200
    except Exception as e: print(f"[Error] API Error POST /watchlist/{user_id}: {traceback.format_exc()}"); return jsonify({"error": str(e)}), 500


#Watchlist Remove Endpoint
@app.route('/api/watchlist/<user_id>/<ticker>', methods=['DELETE'])
@auth_required
def remove_from_watchlist_endpoint(user_id, ticker):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        if not ticker or not isinstance(ticker, str):
            return jsonify({"error": "Invalid ticker in URL."}), 400

        result = remove_from_watchlist(user_id, ticker)
        status_code = 404 if result.get("error") and "not found" in result["error"] else \
                      400 if result.get("error") else \
                      200
        return jsonify(result), status_code
    except Exception as e:
        print(f"[Error] API Error DELETE /watchlist/{user_id}/{ticker}: {traceback.format_exc()}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

# Zerodha Integration Endpoints
@app.route('/api/zerodha/connect/<user_id>', methods=['GET'])
def zerodha_connect(user_id):
    try:
        session['zerodha_auth_user_id'] = user_id
        
        kite = get_kite_instance() # Use tool
        login_url = kite.login_url()
        
        print(f"Redirecting user {user_id} to Zerodha login: {login_url}")
        return redirect(login_url)
    except Exception as e:
        print(f"[Error] Error generating Zerodha login URL: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Could not initiate Zerodha connection: {str(e)}"}), 500

@app.route('/api/config', methods=['GET'])
def get_frontend_config():
    return jsonify({
        "firebaseConfig": config.FIREBASE_CONFIG,
        "apiBaseUrl": config.API_BASE_URL,
        "dbMode": config.DB_MODE, 
        "geminiPrices": {
            "inputPerMillion": config.GEMINI_INPUT_PRICE_PER_MILLION,
            "outputPerMillion": config.GEMINI_OUTPUT_PRICE_PER_MILLION,
            "inrRate": config.INR_CONVERSION_RATE
        }
    })
    
@app.route('/api/zerodha/callback', methods=['GET'])
def zerodha_callback():
    if not db: return "Error: Database not available.", 503
    
    request_token = request.args.get('request_token')
    user_id = session.get('zerodha_auth_user_id')

    if not request_token:
        return "Error: No request_token provided.", 400
    if not user_id:
        return "Error: User session expired. Please close this window and try again.", 400

    print(f"Received Zerodha callback for user {user_id}")
    
    try:
        kite = get_kite_instance()
        data = kite.generate_session(request_token, api_secret=config.ZERODHA_API_SECRET)
        access_token = data['access_token']
        db.create_or_update_user(user_id, {
            'zerodha_access_token': access_token,
            'zerodha_synced_at': db.get_timestamp()
        })
        print(f"[Success] Access Token saved for {user_id}")
        sync_result = sync_zerodha_portfolio(user_id, access_token)
        
        status_msg = "Sync Successful!"
        if "error" in sync_result:
            status_msg = f"Token saved, but sync failed: {sync_result['error']}"

        return f"""
        <html>
        <head><title>Connected</title></head>
        <body style="background-color: #0f172a; color: #10b981; font-family: sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div style="text-align: center;">
                <svg style="width: 64px; height: 64px; margin: 0 auto 20px;" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                <h1 style="margin: 0; font-size: 24px;">{status_msg}</h1>
                <p style="color: #94a3b8;">Closing window...</p>
            </div>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'ZERODHA_SUCCESS', userId: '{user_id}' }}, '*');
                }}
                setTimeout(() => window.close(), 1500);
            </script>
        </body>
        </html>
        """

    except Exception as e:
        print(f"[Error] Zerodha Callback Error: {traceback.format_exc()}")
        return f"Error: {str(e)}", 500
    finally:
        if 'zerodha_auth_user_id' in session:
            session.pop('zerodha_auth_user_id')

@app.route('/api/stock/analysis/<user_id>/<ticker>', methods=['GET'])
@auth_required
def get_stock_analysis(user_id, ticker):
    timeframe = request.args.get('timeframe', '1D').lower()
    indicators_str = request.args.get('indicators', 'rsi,ema,volume')
    indicators = [ind.strip().lower() for ind in indicators_str.split(',') if ind.strip()]

    try:
        # Call the new tool function
        result = get_stock_analysis_data(ticker, timeframe, indicators)
        
        if result.get("error"):
            return jsonify(result), 404
            
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in get_stock_analysis: {e}")
        return jsonify({'error': str(e)}), 500
    
# Chat Endpoints
@app.route('/api/chats/<user_id>')
@auth_required
def get_chat_list_endpoint(user_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        chat_list = db.get_chats(user_id)
        return jsonify(chat_list)
    except Exception as e: 
        print(f"[Error] API Error /chats/{user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Chat Messages Endpoint
@app.route('/api/chat/<user_id>/<chat_id>')
@auth_required
def get_chat_messages_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        msgs = db.get_chat_messages(user_id, chat_id)
        return jsonify(msgs)
    except Exception as e: 
        print(f"[Error] API Error /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# Delete Chat Endpoint
@app.route('/api/chat/<user_id>/<chat_id>', methods=['DELETE'])
@auth_required
def delete_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        db.delete_chat(user_id, chat_id)
        print(f"[Deleted] Deleted chat {chat_id} for {user_id}")
        return jsonify({"success": True, "message": f"Chat {chat_id} deleted."})
    except Exception as e: 
        print(f"[Error] API Error DELETE /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stock/fundamentals/<ticker>')
def get_stock_fundamentals_endpoint(ticker):
    """Public endpoint to get fundamental data for a stock."""
    try: 
        funda_data = get_fundamental_data(ticker)
        if funda_data.get("error"):
            return jsonify(funda_data), 404
        return jsonify(funda_data)
    except ValueError as ve: 
        return jsonify({"error": str(ve)}), 404
    except Exception as e: 
        print(f"❌ API Error /stock/fundamentals/{ticker}: {traceback.format_exc()}"); 
        return jsonify({"error": str(e)}), 500
    
# Rename Chat Endpoint
@app.route('/api/chat/<user_id>/<chat_id>', methods=['PUT'])
@auth_required
def rename_chat_endpoint(user_id, chat_id):
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        if not data or 'title' not in data: return jsonify({"error": "Missing 'title'."}), 400
        nt = data['title'].strip()
        
        db.rename_chat(user_id, chat_id, nt)
        
        print(f"✏️ Renamed chat {chat_id} for {user_id} to '{nt}'")
        return jsonify({"success": True, "message": "Chat renamed."})
    except Exception as e: 
        print(f"❌ API Error PUT /chat/{user_id}/{chat_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# --- Main Chat Handler (using Gemini) ---
@app.route('/api/chat', methods=['POST'])
def chat_handler():
    if not db: return jsonify({"error": "Database not configured"}), 503
    
    try:
        data = request.get_json()
        user_id, user_message, chat_id = data.get('userId'), data.get('message'), data.get('chatId')

        # --- AUTHENTICATION ---
        if not config.DEBUG_MODE:
            auth_header = request.headers.get('Authorization')
            if not auth_header: return jsonify({"error": "No Auth Header"}), 401
            id_token = auth_header.split('Bearer ')[-1]
            if config.DB_MODE == 'LOCAL':
                if id_token != user_id: pass 
            else:
                try:
                    auth.verify_id_token(id_token) 
                except: return jsonify({"error": "Auth Failed"}), 401
        
        if not user_message.strip(): return jsonify({"error": "Empty message"}), 400

        # --- TOKEN LIMIT CHECK ---
        token_status = db.check_token_access(user_id)
        if not token_status['allowed']:
            return jsonify({
                "error": "TOKEN_LIMIT_EXCEEDED", 
                "message": "Free token limit exceeded.",
                "days_remaining": token_status['days_remaining']
            }), 403

        # --- DB SAVE (User Message) ---
        try:
            if not chat_id:
                title = user_message[:config.CHAT_TITLE_LENGTH] + "..."
                chat_id = db.create_chat(user_id, title, user_message, first_msg_role='user')
            else:
                db.add_message(user_id, chat_id, 'user', user_message)
        except: return jsonify({"error": "Database error"}), 500

        # ============================================
        # AGENT TOOLS
        # ============================================
        
        # Tool wrappers for the Agent (mapping agent calls to tool functions)
        def execute_trade_for_agent(ticker: str, quantity: int, action: str) -> dict:
            return execute_trade(user_id, ticker, quantity, action)
        
        def get_portfolio_for_agent() -> dict:
            try: return get_portfolio(user_id)
            except Exception as e: return {"error": str(e)}
            
        def manage_watchlist_for_agent(ticker: str, action: str) -> dict:
            if action.upper() == 'ADD': return add_to_watchlist(user_id, [ticker])
            elif action.upper() == 'REMOVE': return remove_from_watchlist(user_id, ticker)
            return {"error": "Invalid action"}
            
        def get_watchlist_for_agent_wrapper() -> dict:
            return get_watchlist_for_agent(user_id)

        def sync_zerodha_portfolio_for_agent() -> dict:
            if not db: return {"error": "DB unavailable"}
            try:
                user_doc = db.get_user(user_id)
                if not user_doc or not user_doc.get('zerodha_access_token'):
                    return {"error": "Zerodha not connected", "connect_url": f"/api/zerodha/connect/{user_id}"}
                return sync_zerodha_portfolio(user_id, user_doc.get('zerodha_access_token'))
            except Exception as e: return {"error": str(e)}

        
        def get_index_constituents_for_agent(index_name: str) -> dict:
            return get_index_constituents(index_name)
            
        def fetch_news_for_agent(query: str) -> dict:
            result = internet_search_news(query)
            if "error" not in result and result.get('articles'): return result
            return get_stock_news(query)
            
        def get_stock_chart_details_for_agent(ticker: str, period: str = "1y") -> dict:
            return get_stock_chart_details(ticker, period)
            
        def internet_search_for_agent(query: str) -> dict:
            try: return internet_search(query)
            except Exception as e: return {"error": str(e)}

        def simulate_investment_for_agent(ticker: str, amount: float, years: int, mode: str = 'lumpsum') -> dict:
            return simulate_investment(ticker, amount, years, mode)

        def project_portfolio_performance_for_agent(direction: str, duration_months: int = 12) -> dict:
            return project_portfolio_performance(user_id, direction, duration_months)

        chat_history = [{'role': 'user', 'parts': [{'text': config.SYSTEM_INSTRUCTION}]}]
        try:
            raw_msgs = db.get_chat_messages(user_id, chat_id)
            recent = raw_msgs[-16:-1] if raw_msgs else []
            for m in recent:
                chat_history.append({'role': 'user' if m['role'] == 'user' else 'model', 'parts': [{'text': m['text']}]})
        except: pass

        # --- CALL AI ---
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL_NAME,
            tools=[
                screen_static_index, screen_custom_stock_list, get_index_constituents_for_agent,
                get_current_price, execute_trade_for_agent, get_portfolio_for_agent,
                get_fundamental_data, manage_watchlist_for_agent, fetch_news_for_agent,
                internet_search_for_agent, find_intraday_trade_setups, get_index_data_for_agent,
                sync_zerodha_portfolio_for_agent, get_watchlist_for_agent_wrapper,simulate_investment_for_agent,project_portfolio_performance_for_agent,get_stock_chart_details_for_agent
            ]
        )
        
        chat_session = model.start_chat(history=chat_history, enable_automatic_function_calling=True)
        response = chat_session.send_message(user_message)
        
        # --- EXTRACT METADATA ---
        input_tokens = output_tokens = total_tokens = 0
        if hasattr(response, 'usage_metadata'):
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            total_tokens = response.usage_metadata.total_token_count

        tools_used = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tools_used.append(part.function_call.name)
            for msg in chat_session.history:
                if hasattr(msg, 'parts'):
                    for p in msg.parts:
                        if hasattr(p, 'function_call') and p.function_call:
                            tools_used.append(p.function_call.name)
            tools_used = list(set(tools_used))
        except: pass

        agent_reply = ""
        if response.candidates and response.candidates[0].content.parts:
            agent_reply = "".join(p.text for p in response.candidates[0].content.parts if p.text)
        
        if not agent_reply: agent_reply = "I processed your request."

        # Construct Metadata
        metadata = {
            "tokenUsage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": total_tokens
            },
            "toolsUsed": tools_used
        }

        db.add_message(user_id, chat_id, 'model', agent_reply, metadata)
        db.update_user_tokens(user_id, input_tokens, output_tokens)

        # ======================================================
        # CLEAN TERMINAL OUTPUT
        # ======================================================
        print("\n" + "━"*60)
        print(f"AGENT INTERACTION REPORT ({config.DB_MODE})")
        print("━"*60)
        print(f" USER INPUT:\n   \"{user_message[:100]}{'...' if len(user_message)>100 else ''}\"\n")
        
        if tools_used:
            print(f"TOOLS USED:")
            for t in tools_used:
                print(f"   • {t}")
        else:
            print("TOOLS USED: None (Direct Response)")

        print(f"\nTOKEN USAGE:")
        print(f"   Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens}")
        
        print(f"\nAGENT REPLY (Snippet):")
        clean_reply = agent_reply.replace('\n', ' ').replace('*', '')
        print(f"   \"{clean_reply[:150]}...\"")
        print("━"*60 + "\n")
        # ======================================================

        return jsonify({
            "reply": agent_reply,
            "chatId": chat_id,
            "toolsUsed": tools_used,
            "tokenUsage": {
                "inputTokens": input_tokens, 
                "outputTokens": output_tokens, 
                "totalTokens": total_tokens
            }
        })

    except Exception as e:
        print("\n" + "!"*60)
        print(f"CRITICAL ERROR:")
        print(f"   {str(e)}")            
        print("-" * 60)          
        print("!"*60 + "\n")
        return jsonify({"error": "Server Error"}), 500
    
# ============================================
# Main Execution Block
# ============================================
@app.route('/api/plans', methods=['GET'])
def get_plans_endpoint():
    """Returns available pricing plans."""
    return jsonify(config.PLANS)

@app.route('/api/user/plan/<user_id>', methods=['POST'])
@auth_required
def update_user_plan_endpoint(user_id):
    """Updates the user's selected plan."""
    if not db: return jsonify({"error": "DB unavailable"}), 503
    try:
        data = request.get_json()
        new_plan_id = data.get('planId')
        
        if not new_plan_id or new_plan_id not in config.PLANS:
            return jsonify({"error": "Invalid plan ID"}), 400
            
        # Update user plan
        today_str = datetime.now().strftime('%Y-%m-%d')
        update_fields = {
            'plan': new_plan_id,
            'plan_start_date': today_str
        }
        
        db.create_or_update_user(user_id, update_fields)
        
        # Return updated plan details
        plan_details = config.PLANS[new_plan_id]
        return jsonify({"success": True, "plan": plan_details})
        
    except Exception as e:
        print(f"[Error] Update Plan Error {user_id}: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    print(f"Server starting on http://127.0.0.1:{port}")    
    app.run(debug=False, host='0.0.0.0', port=port)